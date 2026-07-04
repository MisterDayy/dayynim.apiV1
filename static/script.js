// ---------------- endpoint reference data ----------------
const ENDPOINTS = [
  {
    method: "GET", path: "/api/home", desc: "Semua section homepage jadi satu response (trending, populer, per-negara, per-genre)",
    params: [["only", "cth trending,popular (opsional, comma-separated)", "semua section"]],
    example: "curl /api/home?only=trending,popular",
    response: `{
  "sections": {
    "trending": { "label": "Trending", "results": [ { "id": 550, "title": "..." } ] },
    "popular": { "label": "Populer", "results": [ { "id": 129, "title": "..." } ] },
    "indonesia": { "label": "Film Indonesia", "results": [ ... ] },
    "korea": { "label": "Trending Korea", "results": [ ... ] },
    "action": { "label": "Aksi", "results": [ ... ] }
  }
}`
  },
  {
    method: "GET", path: "/api/trending", desc: "Film/serial trending harian",
    params: [["media", "movie | tv", "movie"], ["window", "day | week", "day"]],
    example: "curl /api/trending?media=movie",
    response: `{
  "page": 1,
  "results": [
    {
      "id": 550,
      "title": "Fight Club",
      "poster_path": "/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg",
      "release_date": "1999-10-15",
      "vote_average": 8.4,
      "genre_ids": [18, 53]
    }
  ],
  "total_pages": 41,
  "total_results": 820
}`
  },
  {
    method: "GET", path: "/api/popular", desc: "Film populer",
    params: [["page", "angka", "1"], ["media", "movie | tv", "movie"]],
    example: "curl /api/popular?page=2",
    response: `{
  "page": 2,
  "results": [ { "id": 1197306, "title": "...", "vote_average": 7.5 } ],
  "total_pages": 47000,
  "total_results": 940000
}`
  },
  {
    method: "GET", path: "/api/now-playing", desc: "Film sedang tayang di bioskop",
    params: [["page", "angka", "1"]],
    example: "curl /api/now-playing",
    response: `{
  "page": 1,
  "results": [ { "id": 1234, "title": "...", "release_date": "2026-06-20" } ],
  "dates": { "minimum": "2026-05-01", "maximum": "2026-07-10" }
}`
  },
  {
    method: "GET", path: "/api/upcoming", desc: "Film akan datang",
    params: [["page", "angka", "1"]],
    example: "curl /api/upcoming",
    response: `{
  "page": 1,
  "results": [ { "id": 5678, "title": "...", "release_date": "2026-08-14" } ]
}`
  },
  {
    method: "GET", path: "/api/discover", desc: "Filter film by negara / genre / tahun",
    params: [["country", "kode ISO, cth ID|KR|CN", "-"], ["genre", "id genre TMDB", "-"], ["year", "angka", "-"], ["page", "angka", "1"]],
    example: "curl /api/discover?country=ID&genre=28",
    response: `{
  "page": 1,
  "results": [ { "id": 999, "title": "...", "genre_ids": [28], "origin_country": ["ID"] } ]
}`
  },
  {
    method: "GET", path: "/api/search", desc: "Cari film & serial sekaligus, digabung & di-sort by popularity",
    params: [["q", "kata kunci", "wajib"], ["type", "all | movie | tv", "all"]],
    example: "curl /api/search?q=moana",
    response: `{
  "query": "moana",
  "results": [
    { "id": 129, "title": "Moana", "media_type": "movie", "popularity": 812.3 },
    { "id": 4321, "name": "Moana Series", "media_type": "tv", "popularity": 40.1 }
  ]
}`
  },
  {
    method: "GET", path: "/api/genres", desc: "Daftar genre & ID-nya",
    params: [],
    example: "curl /api/genres",
    response: `{
  "genres": [
    { "id": 28, "name": "Aksi" },
    { "id": 35, "name": "Komedi" }
  ]
}`
  },
  {
    method: "GET", path: "/api/detail/:type/:id", desc: "Detail lengkap + cast + rekomendasi serupa",
    params: [["type", "movie | tv", "wajib"], ["id", "TMDB id", "wajib"]],
    example: "curl /api/detail/movie/550",
    response: `{
  "id": 550,
  "title": "Fight Club",
  "genres": [ { "id": 18, "name": "Drama" } ],
  "credits": { "cast": [ { "name": "Brad Pitt", "character": "Tyler Durden" } ] },
  "similar": { "results": [ { "id": 807, "title": "Se7en" } ] }
}`
  },
  {
    method: "GET", path: "/api/servers/:type/:id", desc: "Resolve daftar URL embed dari semua provider",
    params: [["season", "angka (tv)", "1"], ["episode", "angka (tv)", "1"]],
    example: "curl /api/servers/movie/550",
    response: `{
  "type": "movie",
  "id": 550,
  "servers": [
    { "name": "VIDSRC", "url": "https://vidsrcme.su/embed/movie/550" },
    { "name": "VIDFAST", "url": "https://vidfast.pro/movie/550" },
    { "name": "VIDLINK", "url": "https://vidlink.pro/movie/550" }
  ]
}`
  },
  {
    method: "GET", path: "/api/status", desc: "Cek konektivitas ke upstream (TMDB)",
    params: [],
    example: "curl /api/status",
    response: `{
  "online": true,
  "upstream": "themoviedb"
}`
  },
];

function renderEndpoints() {
  const list = document.getElementById("endpointList");
  list.innerHTML = ENDPOINTS.map((e, i) => `
    <div class="endpoint-row" data-i="${i}">
      <div class="endpoint-head">
        <span class="method">${e.method}</span>
        <span class="endpoint-path">${e.path}</span>
        <span class="endpoint-desc">${e.desc}</span>
        <span class="chevron">&#9656;</span>
      </div>
      <div class="endpoint-body">
        <p style="color:var(--muted); margin:0 0 8px;">${e.desc}</p>
        ${e.params.length ? `
        <table class="param-table">
          <tr><th>Param</th><th>Tipe</th><th>Default</th></tr>
          ${e.params.map(p => `<tr><td>${p[0]}</td><td>${p[1]}</td><td>${p[2]}</td></tr>`).join("")}
        </table>` : ""}
        <p class="block-label">Request</p>
        <div class="code-block">${e.example}</div>
        <p class="block-label">Response <span class="block-label-sub">200 OK</span></p>
        <pre class="code-block">${e.response}</pre>
      </div>
    </div>
  `).join("");

  list.querySelectorAll(".endpoint-head").forEach(head => {
    head.addEventListener("click", () => {
      head.parentElement.classList.toggle("open");
    });
  });
}

// ---------------- server grid ----------------
const SERVER_NAMES = [
  ["VIDSRC", "vidsrcme.su/embed"],
  ["VIDEASY", "player.videasy.net"],
  ["VIDFAST", "vidfast.pro"],
  ["VIDLINK", "vidlink.pro"],
];
function renderServers() {
  document.getElementById("serverGrid").innerHTML = SERVER_NAMES.map(s => `
    <div class="server-card">
      <div class="name">${s[0]}</div>
      <div class="pattern">${s[1]}</div>
    </div>
  `).join("");
}

// ---------------- status pill ----------------
async function checkStatus() {
  const pill = document.getElementById("statusPill");
  const dot = pill.querySelector(".dot");
  try {
    const r = await fetch("/api/status");
    const d = await r.json();
    dot.className = "dot " + (d.online ? "online" : "offline");
    pill.lastChild.textContent = " " + (d.online ? "online" : "offline");
  } catch {
    dot.className = "dot offline";
    pill.lastChild.textContent = " offline";
  }
}

// ---------------- hero terminal typing sequence ----------------
async function runHeroTerminal() {
  const body = document.getElementById("terminalBody");
  const lines = [
    { type: "cmd", text: "curl https://dayyapi.vercel.app/api/trending?media=movie" },
  ];
  body.innerHTML = "";

  for (const line of lines) {
    const span = document.createElement("div");
    span.innerHTML = '<span class="prompt">$</span> ';
    body.appendChild(span);
    for (const ch of line.text) {
      span.innerHTML += ch;
      await sleep(18);
    }
    await sleep(300);
  }

  try {
    const r = await fetch("/api/trending?media=movie");
    const d = await r.json();
    const first = (d.results || []).slice(0, 3).map(m => ({
      title: m.title, rating: m.vote_average, year: (m.release_date || "").slice(0, 4)
    }));
    const pretty = JSON.stringify(first, null, 2);
    const out = document.createElement("pre");
    out.style.margin = "10px 0 0";
    out.style.color = "#c9d6c8";
    body.appendChild(out);
    for (const ch of pretty) {
      out.textContent += ch;
      await sleep(4);
    }
  } catch (e) {
    body.innerHTML += "\n<span style='color:var(--red)'>request failed — cek koneksi</span>";
  }

  const cursor = document.createElement("span");
  cursor.className = "cursor";
  body.appendChild(document.createElement("br"));
  body.appendChild(cursor);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ---------------- try it sandbox ----------------
function initBaseUrl() {
  const base = window.location.origin;
  const textEl = document.getElementById("baseUrlText");
  const btn = document.getElementById("copyBaseUrl");
  if (!textEl || !btn) return;
  textEl.textContent = base;

  btn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(base);
    } catch (e) {
      // fallback buat browser lama / non-https context
      const tmp = document.createElement("textarea");
      tmp.value = base;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      document.body.removeChild(tmp);
    }
    btn.textContent = "Copied!";
    btn.classList.add("copied");
    setTimeout(() => {
      btn.textContent = "Copy";
      btn.classList.remove("copied");
    }, 1500);
  });
}

document.addEventListener("DOMContentLoaded", () => {
  renderEndpoints();
  renderServers();
  checkStatus();
  runHeroTerminal();
  initBaseUrl();

  document.getElementById("tryRun").addEventListener("click", async () => {
    const path = document.getElementById("tryEndpoint").value;
    const out = document.getElementById("tryOutput");
    out.textContent = "// loading...";
    try {
      const r = await fetch(path);
      const d = await r.json();
      out.textContent = JSON.stringify(d, null, 2).slice(0, 4000);
    } catch (e) {
      out.textContent = "// error: " + e.message;
    }
  });
});
