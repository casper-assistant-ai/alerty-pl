// Alerty RCB — the shelter map (schrony.html).
// Shelter points of the State Fire Service (data/shelters/, built weekly by scripts/shelters.py)
// split into 0.25° cells: the overview shows the count of each cell, a closer zoom loads the
// points in view. The user gives a location (the phone's GPS, an address via Nominatim, or a tap
// on the map); the nearest points get a distance and a «Nawiguj» button that offers the map apps
// of the phone (geo: chooser on Android, Apple Maps, Google Maps, Waze).
"use strict";

const { $, h } = RCB;
RCB.strip();
setInterval(RCB.strip, 60000);

const DATA = "data/shelters/";
const ACCESS = ["dostępne całodobowo", "w określonych godzinach", "na żądanie"];
const DETAIL_ZOOM = 12;   // from this zoom on the points themselves are drawn
const NEAREST = 10;
const WALK_KM = 2.5;      // up to this distance the navigation asks for a walking route
const dark = matchMedia("(prefers-color-scheme: dark)");
const CANVAS = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas";
const CANVAS_ATTR = "Esri, HERE, Garmin, © OpenStreetMap";

const UA = navigator.userAgent;
const IOS = /iPad|iPhone|iPod/.test(UA) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const ANDROID = /Android/i.test(UA);

const S = {
  index: null, cells: new Map(), map: null, base: null, overview: null, points: null, renderer: null,
  drawn: new Set(), me: null, meLayer: null, near: [], picking: false, selected: null,
};

// ---------- geometry ----------
const R = 6371.0088;
const rad = (d) => d * Math.PI / 180;
function km(a, b, c, d) {
  const x = Math.sin(rad(c - a) / 2) ** 2 + Math.cos(rad(a)) * Math.cos(rad(c)) * Math.sin(rad(d - b) / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(x)));
}
const fmtKm = (d) => d < 1 ? `${Math.max(10, Math.round(d * 1000 / 10) * 10)} m` : `${d.toFixed(d < 10 ? 1 : 0).replace(".", ",")} km`;
const cellKey = (r, c) => `${r}_${c}`;
const cellOf = (lat, lon) => [Math.floor(lat / S.index.cell), Math.floor(lon / S.index.cell)];

// ---------- data ----------
async function loadIndex() {
  const r = await fetch(DATA + "index.json?t=" + Math.floor(Date.now() / 3600000));
  if (!r.ok) throw new Error("schrony: " + r.status);
  return r.json();
}
function loadCell(key) {
  if (!S.index.cells[key]) return Promise.resolve([]);
  if (!S.cells.has(key)) {
    const v = encodeURIComponent(S.index.updated_at);
    S.cells.set(key, fetch(`${DATA}t/${key}.json?v=${v}`).then((r) => {
      if (!r.ok) throw new Error(`schrony ${key}: ${r.status}`);
      return r.json();
    }).then((rows) => rows.map((p) => ({ lat: p[0], lon: p[1], addr: p[2], gmina: p[3], access: p[4], key }))
    ).catch((e) => { S.cells.delete(key); throw e; }));
  }
  return S.cells.get(key);
}

// The nearest points: rings of cells around the user until the k-th point is closer than any
// cell not read yet (or 8 rings, about 200 km, are read).
async function nearest(lat, lon, k = NEAREST) {
  const [r0, c0] = cellOf(lat, lon);
  const cellKmLat = S.index.cell * 111.2;
  const cellKmLon = S.index.cell * 111.2 * Math.cos(rad(lat));
  let found = [];
  for (let ring = 0; ring <= 8; ring++) {
    const keys = [];
    for (let r = r0 - ring; r <= r0 + ring; r++)
      for (let c = c0 - ring; c <= c0 + ring; c++)
        if (Math.max(Math.abs(r - r0), Math.abs(c - c0)) === ring) keys.push(cellKey(r, c));
    const rows = (await Promise.all(keys.map(loadCell))).flat();
    found = found.concat(rows.map((p) => ({ ...p, d: km(lat, lon, p.lat, p.lon) })));
    found.sort((a, b) => a.d - b.d);
    // everything within this distance is already read
    const safe = ring * Math.min(cellKmLat, cellKmLon);
    if (found.length >= k && found[k - 1].d <= safe) break;
  }
  return found.slice(0, k);
}

// ---------- the map ----------
function canvasLayer() {
  const tone = dark.matches ? "Dark" : "Light";
  return L.layerGroup([
    L.tileLayer(`${CANVAS}/World_${tone}_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, attribution: CANVAS_ATTR }),
    L.tileLayer(`${CANVAS}/World_${tone}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, pane: "labels" }),
  ]);
}
function setBase() {
  if (S.base) S.map.removeLayer(S.base);
  S.base = canvasLayer().addTo(S.map);
}

// canvas markers cannot read CSS light-dark() colours: the same values as --acc-* in style.css
const COLORS = {
  light: { 0: "#2f7a4f", 1: "#b07a12", 2: "#2667ad", cell: "#2667ad" },
  dark: { 0: "#5cbf86", 1: "#e2ad3b", 2: "#5ea0e6", cell: "#5ea0e6" },
};
const accColor = (a) => COLORS[dark.matches ? "dark" : "light"][a];

function drawOverview() {
  S.overview = L.layerGroup();
  const max = Math.max(...Object.values(S.index.cells).map((c) => c[0]));
  for (const [key, [n, lat, lon]] of Object.entries(S.index.cells)) {
    const m = L.circleMarker([lat, lon], {
      renderer: S.renderer, radius: 2.5 + 12 * Math.sqrt(n / max), weight: 1,
      className: "cell", color: accColor("cell"), fillColor: accColor("cell"), fillOpacity: 0.28, opacity: 0.6,
    });
    m.bindTooltip(`${n.toLocaleString("pl-PL")} ${RCB.plural(n, "punkt", "punkty", "punktów")} schronienia`, { className: "tip", direction: "top" });
    m.on("click", () => S.map.setView([lat, lon], DETAIL_ZOOM));
    m.cellKey = key;
    S.overview.addLayer(m);
  }
}

async function drawPoints() {
  const z = S.map.getZoom();
  const detail = z >= DETAIL_ZOOM;
  if (!detail) {
    if (S.map.hasLayer(S.points)) S.map.removeLayer(S.points);
    if (!S.map.hasLayer(S.overview)) S.overview.addTo(S.map);
    return;
  }
  if (S.map.hasLayer(S.overview)) S.map.removeLayer(S.overview);
  if (!S.map.hasLayer(S.points)) S.points.addTo(S.map);
  const b = S.map.getBounds();
  const [r1, c1] = cellOf(b.getSouth(), b.getWest());
  const [r2, c2] = cellOf(b.getNorth(), b.getEast());
  const keys = [];
  for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) if (S.index.cells[cellKey(r, c)]) keys.push(cellKey(r, c));
  for (const key of keys.slice(0, 40)) {
    if (S.drawn.has(key)) continue;
    S.drawn.add(key);
    try {
      for (const p of await loadCell(key)) pointMarker(p).addTo(S.points);
    } catch (e) { S.drawn.delete(key); console.warn(e.message); }
  }
}

function pointMarker(p) {
  const m = L.circleMarker([p.lat, p.lon], {
    renderer: S.renderer, radius: 6, weight: 1.5, color: "#fff", opacity: 0.9,
    fillColor: accColor(p.access), fillOpacity: 0.95,
  });
  m.on("click", () => openPopup(p, m.getLatLng()));
  return m;
}

function popupBody(p) {
  const d = S.me ? km(S.me.lat, S.me.lon, p.lat, p.lon) : null;
  const nav = h("button", { type: "button", class: "btn primary" }, "Nawiguj");
  nav.addEventListener("click", () => navigate(p));
  return h("div", { class: "pop" },
    h("b", { text: p.addr || "Punkt schronienia" }),
    h("span", { class: "muted", text: [p.gmina && "gm. " + p.gmina, ACCESS[p.access], d != null && fmtKm(d) + " od Ciebie"].filter(Boolean).join(" · ") }),
    nav);
}
function openPopup(p, ll) {
  L.popup({ className: "pop-wrap", maxWidth: 280, autoPanPadding: [16, 16] }).setLatLng(ll || [p.lat, p.lon]).setContent(popupBody(p)).openOn(S.map);
}

// ---------- the user's location ----------
function note(text, warn = false) {
  const el = $("#find-note");
  el.textContent = text || "";
  el.classList.toggle("warn", warn);
}

async function setMe(lat, lon, label, accuracy) {
  S.me = { lat, lon, label };
  if (S.meLayer) S.map.removeLayer(S.meLayer);
  const parts = [];
  if (accuracy && accuracy > 30) parts.push(L.circle([lat, lon], { radius: accuracy, className: "me-acc", interactive: false, weight: 1 }));
  parts.push(L.circleMarker([lat, lon], { radius: 8, className: "me", weight: 3, fillOpacity: 1 }).bindTooltip(label || "Twoja lokalizacja", { className: "tip", direction: "top" }));
  S.meLayer = L.layerGroup(parts).addTo(S.map);
  const q = new URLSearchParams(location.search);
  q.set("lat", lat.toFixed(5)); q.set("lon", lon.toFixed(5));
  history.replaceState(null, "", "?" + q.toString());
  note("Szukam najbliższych punktów…");
  try {
    S.near = await nearest(lat, lon);
  } catch (e) {
    note("Nie udało się wczytać punktów schronienia: " + e.message, true);
    return;
  }
  renderNear();
  if (!S.near.length) { note("W promieniu 200 km nie ma punktów schronienia w danych PSP.", true); return; }
  note((label ? label + ": " : "") + `najbliższe schronienie ${fmtKm(S.near[0].d)} stąd.`);
  const pts = [[lat, lon], ...S.near.slice(0, 5).map((p) => [p.lat, p.lon])];
  S.map.fitBounds(L.latLngBounds(pts), { padding: [56, 56], maxZoom: 16 });
}

function renderNear() {
  const ol = $("#near");
  ol.replaceChildren();
  $("#near-count").textContent = S.near.length ? String(S.near.length) : "";
  S.near.forEach((p, i) => {
    const show = h("button", { type: "button", class: "btn" }, "Pokaż");
    show.addEventListener("click", () => {
      S.map.setView([p.lat, p.lon], Math.max(S.map.getZoom(), 16));
      openPopup(p);
      if (matchMedia("(max-width: 1080px)").matches) $("#map").scrollIntoView({ behavior: "smooth", block: "center" });
    });
    const nav = h("button", { type: "button", class: "btn primary" }, "Nawiguj");
    nav.addEventListener("click", () => navigate(p));
    ol.append(h("li", {},
      h("div", { class: "sh-head" },
        h("span", { class: "sh-n mono", text: String(i + 1) }),
        h("span", { class: "sh-addr", text: p.addr || "Punkt schronienia" }),
        h("span", { class: "sh-d mono", text: fmtKm(p.d) })),
      h("div", { class: "sh-meta" },
        h("i", { class: `sw acc-${p.access}`, "aria-hidden": "true" }),
        h("span", { text: [ACCESS[p.access], p.gmina && "gm. " + p.gmina].filter(Boolean).join(" · ") })),
      h("div", { class: "sh-act" }, show, nav)));
  });
}

// A denial that comes back at once means the browser did not ask: the
// setting blocks it, so say where that setting is on this kind of phone.
function deniedHint(silent) {
  const ua = navigator.userAgent;
  const ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
  const head = silent ? "Telefon nie pyta o zgodę, bo lokalizacja jest zablokowana w ustawieniach. " : "Brak zgody na lokalizację. ";
  if (ios) return head + "iPhone: Ustawienia → Prywatność i ochrona → Usługi lokalizacji → Witryny Safari → „Podczas używania aplikacji”; w Safari też aA → Ustawienia witryny → Lokalizacja → Pytaj. Potem odśwież stronę albo wpisz adres.";
  if (/Android/.test(ua)) return head + "Android: ikona przy adresie strony → Uprawnienia → Lokalizacja → Zezwól; w telefonie włącz też Lokalizację. Potem odśwież stronę albo wpisz adres.";
  return head + "Zezwól na nią w ustawieniach witryny (ikona przy adresie strony), odśwież stronę albo wpisz adres.";
}

function locate() {
  if (!("geolocation" in navigator)) { note("Ta przeglądarka nie podaje lokalizacji. Wpisz adres.", true); return; }
  note("Pytam telefon o lokalizację…");
  $("#locate").disabled = true;
  const asked = Date.now();
  navigator.geolocation.getCurrentPosition(
    (pos) => { $("#locate").disabled = false; setMe(pos.coords.latitude, pos.coords.longitude, "Twoja lokalizacja", pos.coords.accuracy); },
    (err) => {
      $("#locate").disabled = false;
      note(err.code === 1 ? deniedHint(Date.now() - asked < 1500)
        : "Nie udało się ustalić lokalizacji. Wpisz adres albo wskaż miejsce na mapie.", true);
    },
    { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
}

async function geocode(q) {
  const url = "https://nominatim.openstreetmap.org/search?" + new URLSearchParams({
    q, format: "jsonv2", countrycodes: "pl", limit: "5", "accept-language": "pl", addressdetails: "0",
  });
  const r = await fetch(url, { headers: { Accept: "application/json" } });
  if (!r.ok) throw new Error("wyszukiwarka adresów: " + r.status);
  return (await r.json()).map((x) => ({ lat: +x.lat, lon: +x.lon, name: x.display_name.split(", ").filter((t) => !/^(Polska|województwo |\d\d-\d{3}$)/.test(t)).slice(0, 3).join(", ") }));
}

async function onSearch(e) {
  e.preventDefault();
  const q = $("#addr").value.trim();
  const list = $("#addr-results");
  list.hidden = true;
  if (q.length < 3) { note("Wpisz co najmniej 3 znaki adresu.", true); return; }
  note("Szukam adresu…");
  let res;
  try { res = await geocode(q); } catch (err) { note("Nie udało się wyszukać adresu: " + err.message, true); return; }
  if (!res.length) { note("Nie znalazłem tego adresu w Polsce. Spróbuj z nazwą miejscowości.", true); return; }
  $("#addr").blur();
  setMe(res[0].lat, res[0].lon, res[0].name);
  if (res.length > 1) {
    list.replaceChildren(h("li", { class: "muted", text: "Inne wyniki:" }), ...res.slice(1).map((x) => {
      const b = h("button", { type: "button", class: "link" }, x.name);
      b.addEventListener("click", () => { list.hidden = true; setMe(x.lat, x.lon, x.name); });
      return h("li", {}, b);
    }));
    list.hidden = false;
  }
}

function togglePick(on = !S.picking) {
  S.picking = on;
  $("#pick").setAttribute("aria-pressed", String(on));
  $("#map").classList.toggle("picking", on);
  if (on) note("Dotknij mapy w miejscu, w którym jesteś.");
}

// ---------- navigation ----------
// iOS has no system chooser for map apps, so the sheet is the chooser; on Android the geo: link
// opens the system chooser of the installed map apps.
function navApps(p) {
  const ll = `${p.lat},${p.lon}`;
  const d = S.me ? km(S.me.lat, S.me.lon, p.lat, p.lon) : null;
  const walk = d != null && d <= WALK_KM;
  const name = p.addr || "Punkt schronienia";
  const apple = { name: "Apple Maps", href: `https://maps.apple.com/?daddr=${ll}&dirflg=${walk ? "w" : "d"}&q=${encodeURIComponent(name)}` };
  const google = { name: "Google Maps", href: `https://www.google.com/maps/dir/?api=1&destination=${ll}&travelmode=${walk ? "walking" : "driving"}` };
  const waze = { name: "Waze", href: `https://waze.com/ul?ll=${ll}&navigate=yes` };
  const osm = { name: "OpenStreetMap", href: S.me
    ? `https://www.openstreetmap.org/directions?engine=${walk ? "fossgis_osrm_foot" : "fossgis_osrm_car"}&route=${S.me.lat.toFixed(5)},${S.me.lon.toFixed(5)};${ll}`
    : `https://www.openstreetmap.org/?mlat=${p.lat}&mlon=${p.lon}#map=18/${p.lat}/${p.lon}` };
  if (ANDROID) return [{ name: "Aplikacja z telefonu…", sub: "system zapyta: Google Maps, Waze, Mapy.com i inne", href: `geo:${ll}?q=${ll}(${encodeURIComponent(name)})`, main: true }, google, waze, osm];
  if (IOS) return [{ ...apple, main: true }, google, waze];
  return [{ ...google, main: true }, osm, apple];
}

function navigate(p) {
  const dlg = $("#nav-sheet");
  const d = S.me ? km(S.me.lat, S.me.lon, p.lat, p.lon) : null;
  $("#nav-to").textContent = (p.addr || "Punkt schronienia") + (d != null ? ` · ${fmtKm(d)}` : "") + (d != null ? (d <= WALK_KM ? " · trasa piesza" : " · trasa samochodem") : "");
  const ul = $("#nav-apps");
  ul.replaceChildren(...navApps(p).map((a) => {
    const link = h("a", { href: a.href, class: "app" + (a.main ? " main" : ""), target: a.href.startsWith("http") ? "_blank" : "_self", rel: "noopener" },
      h("span", { text: a.name }), a.sub ? h("small", { text: a.sub }) : null);
    link.addEventListener("click", () => setTimeout(() => dlg.close(), 300));
    return h("li", {}, link);
  }), (() => {
    const copy = h("button", { type: "button", class: "app" }, h("span", { text: "Kopiuj współrzędne" }), h("small", { class: "mono", text: `${p.lat}, ${p.lon}` }));
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(`${p.lat}, ${p.lon}`); copy.querySelector("span").textContent = "Skopiowano"; } catch { /* no clipboard */ }
    });
    return h("li", {}, copy);
  })());
  if (typeof dlg.showModal === "function") dlg.showModal(); else window.open(navApps(p)[0].href, "_blank");
}

// ---------- start ----------
async function main() {
  await RCB.leaflet(); // a dropped request for leaflet.js gets one retry here, not "L is not defined"
  S.index = await loadIndex();
  const upd = new Date(S.index.updated_at);
  $("#about-data").textContent = `${S.index.count.toLocaleString("pl-PL")} punktów, dane z ${RCB.fmtDay(upd)}: ${S.index.source} (dane.gov.pl, ${S.index.license}).`;

  const map = S.map = L.map("map", { zoomSnap: 0.5, minZoom: 5, maxZoom: 19, attributionControl: true });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
  map.attributionControl.addAttribution('<a href="https://dane.gov.pl/pl/dataset/28058">KG PSP</a>');
  map.createPane("labels").style.zIndex = 420;
  map.getPane("labels").style.pointerEvents = "none";
  S.renderer = L.canvas({ padding: 0.3, tolerance: 6 });
  S.points = L.layerGroup();
  map.fitBounds([[49.0, 14.1], [54.85, 24.15]]);
  setBase();
  dark.addEventListener("change", () => {
    setBase();
    S.map.removeLayer(S.overview); drawOverview();
    S.points.clearLayers(); S.drawn.clear(); drawPoints();
  });
  new ResizeObserver(() => map.invalidateSize()).observe($("#map"));
  drawOverview();
  map.on("zoomend moveend", drawPoints);
  map.on("click", (e) => { if (S.picking) { togglePick(false); setMe(e.latlng.lat, e.latlng.lng, "Wskazane miejsce"); } });
  drawPoints();

  $("#locate").addEventListener("click", locate);
  $("#addr-form").addEventListener("submit", onSearch);
  $("#pick").addEventListener("click", () => togglePick());
  $("#nav-sheet").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });

  // ?lat=..&lon=.. opens a place (a shared link, the site check)
  const q = new URLSearchParams(location.search);
  const lat = parseFloat(q.get("lat")), lon = parseFloat(q.get("lon"));
  if (lat > 48 && lat < 56 && lon > 13 && lon < 25) setMe(lat, lon, "Wskazane miejsce");
}

main().catch((e) => {
  note("Nie udało się wczytać mapy schronień: " + e.message, true);
  console.error(e);
});
