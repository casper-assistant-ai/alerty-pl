// Alerty RCB — the map page. A zoomable Leaflet map of powiaty (geo/poland.geojson) coloured by the
// alerts of one day: today from data/alerts.json, any day since 2021 from data/archive.json.
// Under it: a street map (Esri grey canvas), Esri World Imagery Wayback (the imagery dates of the visible area)
// or NASA GIBS true colour of the chosen day, and NASA FIRMS fires (VIIRS 375 m) of that day.
"use strict";
const { CAT, PRIORITY, $, h, swatch, getJSON, fmtShort, fmtDay, hasTime, duration, regionText, plural } = RCB;

// ---------- days ----------
const DAY_MS = 86400000;
const todayISO = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(new Date());
const toDate = (iso) => new Date(iso + "T12:00:00Z");
const toISO = (d) => d.toISOString().slice(0, 10);
const addDays = (iso, n) => toISO(new Date(toDate(iso).getTime() + n * DAY_MS));
const dayDiff = (a, b) => Math.round((toDate(b) - toDate(a)) / DAY_MS);
const fmtISO = (iso) => iso.split("-").reverse().join(".");
const WEEKDAY = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];

// an archived alert lasts from the day it started to the day of its last update (or today, if still on)
function span(a, today) {
  const start = a.started_at.slice(0, 10);
  let end = a.last_at && a.last_at.slice(0, 10) > start ? a.last_at.slice(0, 10) : start;
  if (a.status === "active" || a.status === "planned") end = today;
  return [start, end];
}

// ---------- layers ----------
const GIBS = "https://gibs.earthdata.nasa.gov";
// fires: one WMS layer per satellite, each only from the day it has data (a missing one fails the request)
const FIRE_LAYERS = [
  ["VIIRS_SNPP_Thermal_Anomalies_375m_All", "2012-01-20"],
  ["VIIRS_NOAA20_Thermal_Anomalies_375m_All", "2020-01-01"],
  ["VIIRS_NOAA21_Thermal_Anomalies_375m_All", "2024-01-17"],
];
const WAYBACK_CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json";
const WAYBACK = "https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery";
const ESRI_ATTR = '<a href="https://livingatlas.arcgis.com/wayback/">Esri World Imagery Wayback</a>: Esri, Maxar, Earthstar Geographics';
const NASA_ATTR = '<a href="https://www.earthdata.nasa.gov/gibs">NASA GIBS</a>';

const dark = matchMedia("(prefers-color-scheme: dark)");
// the street map: Esri's grey canvas (no key needed), its place names on top of the alerts
const CANVAS = "https://services.arcgisonline.com/ArcGIS/rest/services/Canvas";
const CANVAS_ATTR = "Esri, HERE, Garmin, © OpenStreetMap";
function canvasLayer() {
  const tone = dark.matches ? "Dark" : "Light";
  return L.layerGroup([
    L.tileLayer(`${CANVAS}/World_${tone}_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, attribution: CANVAS_ATTR }),
    L.tileLayer(`${CANVAS}/World_${tone}_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, pane: "labels" }),
  ]);
}

const S = {
  today: todayISO(), start: "2021-01-01", day: null, base: "mapa", fires: false,
  archive: [], live: null, liveActive: [], geo: null,
  map: null, pow: null, baseLayer: null, fireLayers: [],
  wayback: null, wbRelease: null, wbLocal: null, wbSeq: 0,
};

// ---------- alerts of a day ----------
function alertsOf(day) {
  if (day === S.today && S.live) return S.liveActive;
  return S.archive.filter((a) => { const [s, e] = span(a, S.today); return s <= day && day <= e; });
}
const regionsOf = (a) => a.regions || { voivodeships: a.voivodeships, powiaty: a.powiaty, whole: a.whole };

function paint(alerts) {
  const fill = {};
  const put = (id, cat) => { if (!fill[id] || PRIORITY.indexOf(cat) < PRIORITY.indexOf(fill[id])) fill[id] = cat; };
  for (const a of alerts) {
    const r = regionsOf(a);
    for (const p of r.powiaty) put(p, a.category);
    for (const v of r.whole) S.geo.powByV[v]?.forEach((id) => put(id, a.category));
  }
  S.pow.eachLayer((l) => {
    const el = l.getElement();
    if (!el) return;
    const cat = fill[l.feature.properties.id];
    el.setAttribute("class", "pow leaflet-interactive" + (cat ? " hit c-" + cat : "") + (cat === "air" && S.day === S.today ? " blink" : ""));
  });
  const used = new Set(Object.values(fill));
  const cats = used.size ? PRIORITY.filter((c) => used.has(c)) : ["air", "water", "weather", "drill"];
  const items = cats.map((c) => h("li", {}, swatch(c), CAT[c]));
  if (S.fires) items.push(h("li", {}, h("i", { class: "sw fire-dot", "aria-hidden": "true" }), "Pożar lub anomalia termiczna (VIIRS)"));
  $("#legend").replaceChildren(...items);
}

function tooltip(layer) {
  const p = layer.feature.properties;
  const hits = alertsOf(S.day).filter((a) => { const r = regionsOf(a); return r.powiaty.includes(p.id) || r.whole.includes(p.v); });
  const box = h("div", {}, h("b", { text: (p.city ? "" : "powiat ") + p.name }));
  box.append(h("div", { text: hits.length ? [...new Set(hits.map((a) => CAT[a.category]))].join(", ") : "brak alertów" }));
  return box;
}

// ---------- the panel ----------
function activeRow(a) {
  const msg = (a.updates[0] && a.updates[0].message) || a.intro;
  const since = a.status === "planned" ? "planowany od " + fmtShort(new Date(a.started_at)) : "trwa " + duration(a.started_at);
  return h("li", {},
    h("div", { class: "row-head" }, swatch(a.category), CAT[a.category]),
    h("p", { class: "row-msg", text: msg.replace(/^"|"$/g, "") }),
    h("div", { class: "row-meta mono" }, h("span", { text: regionText(a.regions.voivodeships, a.regions.powiaty) }), h("span", { text: since }), h("a", { href: a.url, text: "komunikat" })));
}

function archiveRow(a) {
  const [s, e] = span(a, S.today);
  const when = s === e ? (hasTime(a.started_at) ? "od " + fmtShort(new Date(a.started_at)) : fmtISO(s)) : `${fmtISO(s).slice(0, 5)}–${fmtISO(e)}`;
  return h("li", {},
    h("div", { class: "row-head" }, swatch(a.category), CAT[a.category]),
    h("p", { class: "row-msg", text: (a.message || a.title || "").replace(/^"|"$/g, "") }),
    h("div", { class: "row-meta mono" }, h("span", { text: regionText(a.voivodeships, a.powiaty) }), h("span", { text: when }), h("a", { href: a.url, text: "komunikat" })));
}

function recentRow(a) {
  const d = new Date(a.started_at);
  return h("li", {},
    h("span", { class: "when mono", text: hasTime(a.started_at) ? fmtShort(d) : fmtDay(d).slice(0, 5) }),
    h("a", { class: "what", href: a.url }, swatch(a.category), h("span", { text: `${CAT[a.category]} · ${regionText(a.voivodeships || a.regions.voivodeships, [])}` })));
}

function panel() {
  const today = S.day === S.today;
  const list = alertsOf(S.day);
  $("#now-title").textContent = today ? "Teraz" : `${fmtISO(S.day)}, ${WEEKDAY[toDate(S.day).getUTCDay()]}`;
  $("#active-count").textContent = list.length;
  $("#active").replaceChildren(...(list.length ? list.map(today && S.live ? activeRow : archiveRow)
    : [h("li", { class: "empty", text: today ? "Żaden alert RCB nie jest teraz aktywny." : "Tego dnia nie było alertów RCB." })]));
  // the week before the chosen day, without the alerts already listed above
  const from = addDays(S.day, -7), ids = new Set(list.map((a) => a.id));
  const recent = S.archive.filter((a) => { const s = a.started_at.slice(0, 10); return s > from && s <= S.day && !ids.has(a.id) && a.category !== "other"; })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  $("#week-title").textContent = today ? "Ostatnie 7 dni" : `7 dni do ${fmtISO(S.day)}`;
  $("#week-count").textContent = recent.length;
  $("#recent").replaceChildren(...(recent.length ? recent.slice(0, 12).map(recentRow)
    : [h("li", { class: "empty", text: today ? "W tym tygodniu nie było alertów." : "W tym tygodniu nie było innych alertów." })]));
}

// ---------- the day slider ----------
function spark() {
  const n = dayDiff(S.start, S.today) + 1;
  const counts = new Array(n).fill(0);
  for (const a of S.archive) {
    if (a.category === "other") continue;
    let [s, e] = span(a, S.today);
    if (e < S.start) continue;
    if (s < S.start) s = S.start;
    const i0 = dayDiff(S.start, s), i1 = Math.min(n - 1, dayDiff(S.start, e));
    for (let i = i0; i <= i1; i++) counts[i]++;
  }
  // a week per bar keeps the bars visible on a phone
  const W = Math.ceil(n / 7), max = Math.max(1, ...Array.from({ length: W }, (_, w) => Math.max(...counts.slice(w * 7, w * 7 + 7))));
  const svg = $("#spark");
  svg.setAttribute("viewBox", `0 0 ${W} 20`);
  let d = "";
  for (let w = 0; w < W; w++) {
    const v = Math.max(...counts.slice(w * 7, w * 7 + 7));
    if (v) { const y = 20 - Math.max(2, Math.round(20 * v / max)); d += `M${w} 20V${y}h.8V20z`; }
  }
  svg.innerHTML = `<path d="${d}"/>`;
}

function setDay(iso, push = true) {
  if (iso < S.start) iso = S.start;
  if (iso > S.today) iso = S.today;
  S.day = iso;
  $("#day").value = dayDiff(S.start, iso);
  const label = iso === S.today ? "dziś, " + fmtISO(iso) : fmtISO(iso);
  $("#day-label").textContent = label;
  $("#day").setAttribute("aria-valuetext", label);
  $("#prev").disabled = iso === S.start;
  $("#next").disabled = $("#today").disabled = iso === S.today;
  if (push) {
    const u = new URL(location.href);
    if (iso === S.today) u.searchParams.delete("dzien"); else u.searchParams.set("dzien", iso);
    history.replaceState(null, "", u);
  }
  paint(alertsOf(iso));
  panel();
  if (S.base === "nasa") setBase("nasa");
  if (S.fires) fires();
}

// ---------- base layers ----------
// NASA true colour: the chosen day; today's swaths come in through the day, so today shows yesterday
const nasaDay = () => (S.day === S.today ? addDays(S.today, -1) : S.day);

function setBase(kind) {
  // Wayback needs its list of releases before the first tile
  if (kind === "esri" && !S.wayback) {
    S.base = kind;
    waybackConfig().then(() => S.base === "esri" && setBase("esri"))
      .catch((e) => { $("#base-note").textContent = "Nie udało się pobrać archiwum Esri Wayback: " + e.message; });
    return;
  }
  S.base = kind;
  if (S.baseLayer) S.map.removeLayer(S.baseLayer);
  $("#map").classList.toggle("sat", kind !== "mapa");
  $("#wb-wrap").hidden = kind !== "esri";
  const note = $("#base-note");
  if (kind === "mapa") {
    S.baseLayer = canvasLayer();
    note.textContent = "";
  } else if (kind === "nasa") {
    const d = nasaDay();
    S.baseLayer = L.tileLayer(`${GIBS}/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/${d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`, {
      maxNativeZoom: 9, maxZoom: 19, attribution: NASA_ATTR + " · VIIRS NOAA-20 " + fmtISO(d),
    });
    note.textContent = `Zdjęcie z satelity NOAA-20 (VIIRS) z ${fmtISO(d)}${S.day === S.today ? " (dzisiejsze jeszcze się zbiera)" : ""}. Rozdzielczość ok. 250 m, w pochmurne dni widać chmury.`;
  } else {
    S.baseLayer = esriLayer();
    waybackList();
  }
  S.baseLayer.addTo(S.map);
}

// ---------- Esri Wayback: the releases that changed the visible area ----------
const esriLayer = () => L.tileLayer(`${WAYBACK}/WMTS/1.0.0/default028mm/MapServer/tile/${S.wbRelease}/{z}/{y}/{x}`, {
  maxZoom: 19, maxNativeZoom: 19, attribution: ESRI_ATTR,
});

// a new layer rather than setUrl(): Leaflet 1.9's redraw() asks for tiles at a fractional zoom (6.25)
function useRelease(id) {
  S.wbRelease = id;
  if (S.base !== "esri") return;
  S.map.removeLayer(S.baseLayer);
  S.baseLayer = esriLayer().addTo(S.map);
}
async function waybackConfig() {
  if (!S.wayback) {
    const r = await fetch(WAYBACK_CONFIG);
    const cfg = await r.json();
    S.wayback = Object.entries(cfg).map(([k, v]) => ({ id: +k, date: (v.itemTitle.match(/\d{4}-\d\d-\d\d/) || [""])[0] }))
      .filter((x) => x.date).sort((a, b) => b.date.localeCompare(a.date));
    if (!S.wbRelease) S.wbRelease = S.wayback[0].id;
  }
  return S.wayback;
}

// the tilemap of a release says which release the tile at (z, y, x) really comes from; walking from the
// newest release back gives every distinct image of that spot (about 5 at country zoom, 20+ in a town)
const wbCache = new Map();
async function waybackLocal(z, y, x) {
  const key = `${z}/${y}/${x}`;
  if (wbCache.has(key)) return wbCache.get(key);
  const rel = await waybackConfig();
  const out = [];
  let i = 0;
  while (i < rel.length && out.length < 40) {
    const j = await (await fetch(`${WAYBACK}/MapServer/tilemap/${rel[i].id}/${key}`)).json();
    if (!j.data || !j.data[0]) break;
    const id = (j.select && j.select[0]) || rel[i].id;
    const k = rel.findIndex((r) => r.id === id);
    if (k < 0) break;
    out.push(rel[k]);
    i = k + 1;
  }
  wbCache.set(key, out);
  return out;
}

async function waybackList() {
  const seq = ++S.wbSeq;
  const sel = $("#wayback"), note = $("#base-note");
  try {
    await waybackConfig();
    const z = Math.max(4, Math.min(17, Math.round(S.map.getZoom())));
    const c = S.map.getCenter(), n = 2 ** z;
    const x = Math.floor((c.lng + 180) / 360 * n);
    const lat = c.lat * Math.PI / 180;
    const y = Math.floor((1 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / Math.PI) / 2 * n);
    note.textContent = "Szukam zdjęć tego miejsca…";
    const local = await waybackLocal(z, y, x);
    if (seq !== S.wbSeq || S.base !== "esri") return;
    S.wbLocal = local;
    const list = local.length ? local : S.wayback.slice(0, 1);
    if (!list.some((r) => r.id === S.wbRelease)) {
      // keep the date closest to the chosen day: the newest image taken on or before it
      const pick = list.find((r) => r.date <= S.day) || list[list.length - 1];
      useRelease(pick.id);
    }
    sel.replaceChildren(...list.map((r) => h("option", { value: r.id, text: "zdjęcie z " + fmtISO(r.date) })));
    sel.value = S.wbRelease;
    note.textContent = `${local.length} ${plural(local.length, "zdjęcie", "różne zdjęcia", "różnych zdjęć")} środka widoku w archiwum Esri Wayback (wydania z datą publikacji). Przybliż mapę, by zobaczyć zdjęcia konkretnego miejsca.`;
  } catch (e) {
    if (seq === S.wbSeq) note.textContent = "Nie udało się pobrać listy zdjęć Esri Wayback: " + e.message;
  }
}

// ---------- NASA FIRMS fires of the chosen day ----------
function fires() {
  S.fireLayers.forEach((l) => S.map.removeLayer(l));
  S.fireLayers = [];
  if (!S.fires) return;
  for (const [layer, from] of FIRE_LAYERS) {
    if (S.day < from) continue;
    const l = L.tileLayer.wms(`${GIBS}/wms/epsg3857/best/wms.cgi`, {
      layers: layer, format: "image/png", transparent: true, version: "1.1.1", TIME: S.day,
      pane: "fires", tileSize: 512, maxZoom: 19, attribution: '<a href="https://firms.modaps.eosdis.nasa.gov/">NASA FIRMS</a>',
    });
    l.addTo(S.map);
    S.fireLayers.push(l);
  }
}

// ---------- start ----------
async function main() {
  const [geo, archive] = await Promise.all([getJSON("geo/poland.geojson"), getJSON("data/archive.json")]);
  S.archive = archive.alerts;
  S.start = S.archive.map((a) => a.started_at.slice(0, 10)).filter((d) => d >= "2021-01-01").sort()[0] || "2021-01-01";
  S.geo = { powByV: {} };
  for (const f of geo.features) if (f.properties.kind === "pow") (S.geo.powByV[f.properties.v] = S.geo.powByV[f.properties.v] || []).push(f.properties.id);

  const map = S.map = L.map("map", { zoomSnap: 0.25, minZoom: 4, maxZoom: 19, preferCanvas: false, attributionControl: true });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
  map.createPane("labels").style.zIndex = 420;
  map.getPane("labels").style.pointerEvents = "none";
  map.createPane("fires").style.zIndex = 450;
  map.getPane("fires").style.pointerEvents = "none";
  S.pow = L.geoJSON(geo, {
    filter: (f) => f.properties.kind === "pow",
    style: () => ({ className: "pow", weight: 0.6 }),
    onEachFeature: (f, l) => l.bindTooltip(tooltip, { sticky: true, className: "tip", direction: "top", offset: [0, -8] }),
  }).addTo(map);
  L.geoJSON(geo, { filter: (f) => f.properties.kind === "woj", interactive: false, style: () => ({ className: "woj", weight: 1.6, fill: false }) }).addTo(map);
  const fit = () => map.fitBounds(S.pow.getBounds(), { padding: [4, 4] });
  fit();
  new ResizeObserver(() => map.invalidateSize()).observe($("#map"));

  setBase("mapa");
  dark.addEventListener("change", () => S.base === "mapa" && setBase("mapa"));
  document.querySelectorAll('input[name="base"]').forEach((r) => r.addEventListener("change", () => setBase(r.value)));
  $("#wayback").addEventListener("change", (e) => {
    useRelease(+e.target.value);
  });
  let wbTimer;
  map.on("moveend", () => { if (S.base === "esri") { clearTimeout(wbTimer); wbTimer = setTimeout(waybackList, 500); } });
  $("#fires").addEventListener("change", (e) => { S.fires = e.target.checked; fires(); paint(alertsOf(S.day)); });

  const range = $("#day");
  range.max = dayDiff(S.start, S.today);
  range.addEventListener("input", () => setDay(addDays(S.start, +range.value)));
  $("#prev").addEventListener("click", () => setDay(addDays(S.day, -1)));
  $("#next").addEventListener("click", () => setDay(addDays(S.day, 1)));
  $("#today").addEventListener("click", () => setDay(S.today));
  spark();

  // ?dzien=YYYY-MM-DD opens a past day; &podklad=esri|nasa and &pozary=1 open the layers
  const q = new URLSearchParams(location.search);
  const want = /^\d{4}-\d\d-\d\d$/.test(q.get("dzien") || "") ? q.get("dzien") : S.today;
  if (q.get("pozary") === "1") { S.fires = true; $("#fires").checked = true; }
  if (["esri", "nasa"].includes(q.get("podklad"))) { document.querySelector(`input[name="base"][value="${q.get("podklad")}"]`).checked = true; }

  async function refresh() {
    const res = await RCB.strip();
    const t = todayISO();
    if (t !== S.today) { S.today = t; range.max = dayDiff(S.start, S.today); }
    if (res) { S.live = res.data; S.liveActive = res.active; }
    if (S.day === null) setDay(want, false); else if (S.day === S.today) setDay(S.today, false);
  }
  await refresh();
  if (q.get("podklad") && q.get("podklad") !== "mapa") setBase(q.get("podklad"));
  if (S.fires) fires();
  setInterval(refresh, 60000);
}

main().catch((e) => {
  const st = $("#strip .state");
  if (st) st.textContent = "Nie udało się wczytać mapy: " + e.message;
  console.error(e);
});
