import os
import time
import requests
from collections import defaultdict, deque
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# ---------------------------------------------------------------- rate limit / ban / paid key
RATE_LIMIT_FREE = 100     # request per menit buat IP biasa (gratis)
RATE_WINDOW = 60          # detik (60 = per menit)
VIOLATION_WINDOW = 3600   # strike ke-limit dihitung dalam 1 jam
BAN_THRESHOLD = 5         # kena limit 5x dalam 1 jam -> auto-ban (permanen sampe di-unban manual)

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET")  # buat endpoint /api/admin/*

# Fallback in-memory buat local dev kalau env Upstash belum di-set
_hits = defaultdict(deque)
_banned_memory = set()


def get_client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def redis_cmd(*parts):
    """Jalanin 1 command Redis via Upstash REST. Return hasilnya (results['result'])."""
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    r = requests.post(f"{UPSTASH_URL}/{'/'.join(str(p) for p in parts)}", headers=headers, timeout=5)
    return r.json().get("result")


def redis_pipeline(commands):
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    r = requests.post(f"{UPSTASH_URL}/pipeline", json=commands, headers=headers, timeout=5)
    return r.json()


def is_banned_redis(ip):
    return redis_cmd("GET", f"banned:{ip}") is not None


def get_api_key_limit_redis(key):
    val = redis_cmd("GET", f"apikey:{key}")
    return int(val) if val else None


def record_violation_and_maybe_ban_redis(ip):
    key = f"violations:{ip}"
    results = redis_pipeline([["INCR", key], ["EXPIRE", key, VIOLATION_WINDOW]])
    count = results[0]["result"]
    if count >= BAN_THRESHOLD:
        redis_cmd("SET", f"banned:{ip}", "1")  # gak dikasih TTL = permanen sampe di-unban manual


def check_rate_limit_redis(identifier, limit):
    key = f"ratelimit:{identifier}:{int(time.time() // RATE_WINDOW)}"
    results = redis_pipeline([["INCR", key], ["EXPIRE", key, RATE_WINDOW]])
    count = results[0]["result"]
    if count > limit:
        return False, RATE_WINDOW
    return True, 0


def check_rate_limit_memory(ip, limit):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= limit:
        return False, int(RATE_WINDOW - (now - q[0])) + 1
    q.append(now)
    return True, 0


@app.before_request
def rate_limit():
    if request.path.startswith("/static") or request.path.startswith("/api/admin"):
        return

    ip = get_client_ip()
    api_key = request.headers.get("X-API-Key")
    use_redis = bool(UPSTASH_URL and UPSTASH_TOKEN)

    try:
        if use_redis and is_banned_redis(ip):
            resp = jsonify({"error": "IP kamu diblokir karena berulang kali melebihi rate limit. Hubungi admin buat unban."})
            resp.status_code = 403
            return resp
    except Exception:
        pass  # kalau Upstash lagi error, jangan sampe nge-block semua orang

    if ip in _banned_memory:
        resp = jsonify({"error": "IP kamu diblokir karena berulang kali melebihi rate limit. Hubungi admin buat unban."})
        resp.status_code = 403
        return resp

    limit = RATE_LIMIT_FREE
    identifier = ip
    is_paid = False

    if api_key and use_redis:
        try:
            key_limit = get_api_key_limit_redis(api_key)
            if key_limit:
                limit = key_limit
                identifier = f"key:{api_key}"
                is_paid = True
        except Exception:
            pass

    try:
        if use_redis:
            allowed, retry_after = check_rate_limit_redis(identifier, limit)
        else:
            allowed, retry_after = check_rate_limit_memory(identifier, limit)
    except Exception:
        allowed, retry_after = check_rate_limit_memory(identifier, limit)

    if not allowed:
        if not is_paid:
            try:
                if use_redis:
                    record_violation_and_maybe_ban_redis(ip)
                else:
                    _hits[ip]  # no-op, memory mode gak nge-track strike/ban
            except Exception:
                pass
        resp = jsonify({"error": "Terlalu banyak request, coba lagi nanti.", "limit": limit, "window_seconds": RATE_WINDOW})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp


def require_admin():
    secret = request.headers.get("X-Admin-Key")
    return bool(ADMIN_SECRET) and secret == ADMIN_SECRET


@app.route("/api/admin/unban", methods=["POST"])
def admin_unban():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ip = data.get("ip")
    if not ip:
        return jsonify({"error": "missing 'ip'"}), 400
    if UPSTASH_URL and UPSTASH_TOKEN:
        redis_cmd("DEL", f"banned:{ip}")
        redis_cmd("DEL", f"violations:{ip}")
    _banned_memory.discard(ip)
    return jsonify({"ok": True, "unbanned": ip})


@app.route("/api/admin/ban", methods=["POST"])
def admin_ban():
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    ip = data.get("ip")
    if not ip:
        return jsonify({"error": "missing 'ip'"}), 400
    if UPSTASH_URL and UPSTASH_TOKEN:
        redis_cmd("SET", f"banned:{ip}", "1")
    else:
        _banned_memory.add(ip)
    return jsonify({"ok": True, "banned": ip})


@app.route("/api/admin/add-key", methods=["POST"])
def admin_add_key():
    """Bikin/update API key berbayar. Body: {"key": "abc123", "limit": 1000}"""
    if not require_admin():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    key = data.get("key")
    limit = data.get("limit")
    if not key or not limit:
        return jsonify({"error": "missing 'key' or 'limit'"}), 400
    if not (UPSTASH_URL and UPSTASH_TOKEN):
        return jsonify({"error": "Upstash belum dikonfigurasi"}), 500
    redis_cmd("SET", f"apikey:{key}", str(int(limit)))
    return jsonify({"ok": True, "key": key, "limit": int(limit)})


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp

TMDB_KEY = os.environ.get("TMDB_API_KEY", "fbeec4ffd07eae8cfe5c2cf8d1be632e")
TMDB_BASE = "https://api.themoviedb.org/3"

# ---- Embed servers (decoded from the reference site's obfuscated payload) ----
SERVERS = [
    {"name": "VIDSRC", "base": "https://vidsrcme.su/embed", "pattern": "vidsrc"},
    {"name": "VIDSRC", "base": "https://vsrc.su/embed", "pattern": "vidsrc"},
    {"name": "VIDEASY", "base": "https://player.videasy.net", "pattern": "videasy"},
    {"name": "VIDFAST", "base": "https://vidfast.pro", "pattern": "vidfast"},
    {"name": "VIDLINK", "base": "https://vidlink.pro", "pattern": "vidlink"},
]

GENRES = {
    28: "Aksi", 12: "Petualangan", 16: "Animasi", 35: "Komedi", 80: "Kejahatan",
    99: "Dokumenter", 18: "Drama", 10751: "Keluarga", 14: "Fantasi", 36: "Sejarah",
    27: "Horor", 10402: "Musik", 9648: "Misteri", 10749: "Romansa", 878: "Fiksi Ilmiah",
    10770: "Film TV", 53: "Thriller", 10752: "Perang", 37: "Barat",
}

_cache = {}
CACHE_TTL = 300


def tmdb_get(path, params=None):
    params = params or {}
    params["api_key"] = TMDB_KEY
    params.setdefault("language", "id-ID")
    key = path + str(sorted(params.items()))
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL:
        return _cache[key][1]
    r = requests.get(f"{TMDB_BASE}{path}", params=params, timeout=10)
    data = r.json()
    _cache[key] = (now, data)
    return data


def build_embed(server, media_type, tmdb_id, season=None, episode=None):
    base = server["base"].rstrip("/")
    if media_type == "tv":
        return f"{base}/tv/{tmdb_id}/{season or 1}/{episode or 1}"
    return f"{base}/movie/{tmdb_id}"


# ---------------------------------------------------------------- pages
@app.route("/")
def docs():
    return render_template("index.html")


# ---------------------------------------------------------------- api
@app.route("/api/status")
def status():
    try:
        r = requests.get(f"{TMDB_BASE}/movie/550", params={"api_key": TMDB_KEY}, timeout=5)
        ok = r.status_code == 200
    except Exception:
        ok = False
    return jsonify({"online": ok, "upstream": "themoviedb"})


@app.route("/api/trending")
def trending():
    media = request.args.get("media", "movie")
    window = request.args.get("window", "day")
    data = tmdb_get(f"/trending/{media}/{window}")
    return jsonify(data)


@app.route("/api/popular")
def popular():
    page = request.args.get("page", 1)
    media = request.args.get("media", "movie")
    data = tmdb_get(f"/{media}/popular", {"page": page})
    return jsonify(data)


@app.route("/api/now-playing")
def now_playing():
    page = request.args.get("page", 1)
    return jsonify(tmdb_get("/movie/now_playing", {"page": page}))


@app.route("/api/upcoming")
def upcoming():
    page = request.args.get("page", 1)
    return jsonify(tmdb_get("/movie/upcoming", {"page": page}))


@app.route("/api/discover")
def discover():
    page = request.args.get("page", 1)
    params = {"page": page, "sort_by": "popularity.desc"}
    if request.args.get("country"):
        params["with_origin_country"] = request.args["country"]
    if request.args.get("genre"):
        params["with_genres"] = request.args["genre"]
    if request.args.get("year"):
        params["primary_release_year"] = request.args["year"]
    return jsonify(tmdb_get("/discover/movie", params))


@app.route("/api/search")
def search():
    q = request.args.get("q", "")
    media = request.args.get("type", "all")
    if not q:
        return jsonify({"error": "missing query param 'q'"}), 400
    results = []
    if media in ("all", "movie"):
        d = tmdb_get("/search/movie", {"query": q})
        for m in d.get("results", []):
            m["media_type"] = "movie"
            results.append(m)
    if media in ("all", "tv"):
        d = tmdb_get("/search/tv", {"query": q})
        for t in d.get("results", []):
            t["media_type"] = "tv"
            results.append(t)
    results.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    return jsonify({"query": q, "results": results})


@app.route("/api/genres")
def genres():
    return jsonify({"genres": [{"id": k, "name": v} for k, v in GENRES.items()]})


# Section definitions mirror loadAllHomeRows() order found in the reference site
HOME_SECTIONS = [
    ("trending", "Trending", lambda: tmdb_get("/trending/movie/day")),
    ("popular", "Populer", lambda: tmdb_get("/movie/popular", {"page": 1})),
    ("now_playing", "Sedang Tayang", lambda: tmdb_get("/movie/now_playing", {"page": 1})),
    ("upcoming", "Akan Datang", lambda: tmdb_get("/movie/upcoming", {"page": 1})),
    ("indonesia", "Film Indonesia", lambda: tmdb_get("/discover/movie", {"with_origin_country": "ID", "sort_by": "popularity.desc"})),
    ("korea", "Trending Korea", lambda: tmdb_get("/discover/movie", {"with_origin_country": "KR", "sort_by": "popularity.desc"})),
    ("china", "Trending China", lambda: tmdb_get("/discover/movie", {"with_origin_country": "CN", "sort_by": "popularity.desc"})),
    ("animation", "Animasi & Anime", lambda: tmdb_get("/discover/movie", {"with_genres": 16})),
    ("tv_trending", "Trending Serial TV", lambda: tmdb_get("/trending/tv/day")),
    ("asia", "Asia Tenggara & Selatan", lambda: tmdb_get("/discover/movie", {"with_origin_country": "TH|MY|PH|SG|IN", "sort_by": "popularity.desc"})),
    ("action", "Aksi", lambda: tmdb_get("/discover/movie", {"with_genres": 28})),
    ("drama", "Drama", lambda: tmdb_get("/discover/movie", {"with_genres": 18})),
    ("horror", "Horor", lambda: tmdb_get("/discover/movie", {"with_genres": 27})),
    ("romance", "Romansa", lambda: tmdb_get("/discover/movie", {"with_genres": 10749})),
    ("comedy", "Komedi", lambda: tmdb_get("/discover/movie", {"with_genres": 35})),
]


@app.route("/api/home")
def home():
    """
    Satu panggilan buat semua section homepage sekaligus (trending, populer,
    now playing, upcoming, per-negara, per-genre). Sengaja digabung jadi 1
    endpoint biar frontend gak perlu 15x request kayak di reference site.
    Tambahin ?only=trending,popular kalau cuma butuh sebagian section.
    """
    only = request.args.get("only")
    wanted = set(only.split(",")) if only else None

    sections = {}
    for key, label, fetcher in HOME_SECTIONS:
        if wanted and key not in wanted:
            continue
        data = fetcher()
        sections[key] = {
            "label": label,
            "results": data.get("results", [])[:20],
        }
    return jsonify({"sections": sections})


@app.route("/api/detail/<media_type>/<int:tmdb_id>")
def detail(media_type, tmdb_id):
    if media_type not in ("movie", "tv"):
        return jsonify({"error": "media_type must be movie or tv"}), 400
    data = tmdb_get(f"/{media_type}/{tmdb_id}", {"append_to_response": "credits,similar"})
    return jsonify(data)


@app.route("/api/servers/<media_type>/<int:tmdb_id>")
def servers(media_type, tmdb_id):
    season = request.args.get("season", 1)
    episode = request.args.get("episode", 1)
    out = []
    for s in SERVERS:
        out.append({
            "name": s["name"],
            "url": build_embed(s, media_type, tmdb_id, season, episode),
        })
    return jsonify({"type": media_type, "id": tmdb_id, "servers": out})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
