import os
import time
import requests
from collections import defaultdict, deque
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)

# ---------------------------------------------------------------- rate limit
RATE_LIMIT = 100          # max request
RATE_WINDOW = 60          # per detik (60 = per menit)

UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN")

# Fallback in-memory buat local dev kalau env Upstash belum di-set
_hits = defaultdict(deque)


def get_client_ip():
    # Kalau di belakang proxy/CDN (Vercel), ambil IP asli dari header ini
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or "unknown"


def check_rate_limit_redis(ip):
    """Pakai pipeline INCR + EXPIRE biar atomic. Return (allowed, retry_after)."""
    key = f"ratelimit:{ip}:{int(time.time() // RATE_WINDOW)}"
    headers = {"Authorization": f"Bearer {UPSTASH_TOKEN}"}
    pipeline = [["INCR", key], ["EXPIRE", key, RATE_WINDOW]]
    r = requests.post(f"{UPSTASH_URL}/pipeline", json=pipeline, headers=headers, timeout=5)
    results = r.json()
    count = results[0]["result"]
    if count > RATE_LIMIT:
        return False, RATE_WINDOW
    return True, 0


def check_rate_limit_memory(ip):
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        return False, int(RATE_WINDOW - (now - q[0])) + 1
    q.append(now)
    return True, 0


@app.before_request
def rate_limit():
    if request.path.startswith("/static"):
        return
    ip = get_client_ip()
    try:
        if UPSTASH_URL and UPSTASH_TOKEN:
            allowed, retry_after = check_rate_limit_redis(ip)
        else:
            allowed, retry_after = check_rate_limit_memory(ip)
    except Exception:
        # Kalau Upstash lagi down/timeout, jangan sampe API ikut down—fallback ke memory
        allowed, retry_after = check_rate_limit_memory(ip)

    if not allowed:
        resp = jsonify({"error": "Terlalu banyak request, coba lagi nanti.", "limit": RATE_LIMIT, "window_seconds": RATE_WINDOW})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp


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
