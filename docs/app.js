// Alerty RCB — the map page. A zoomable Leaflet map of powiaty (geo/poland.geojson) coloured by the
// alerts of a period: today from data/alerts.json, any day or period since 2021 from data/archive.json.
// The period is picked with two handles over the histogram of alerts, quick buttons (24 h, 7 dni, 30 dni, rok,
// wszystko; they end today), two dates and ◀ ▶ that shift it by its length; it lives in the URL (?od=…&do=…).
// Under it: a street map (Esri grey canvas), Esri World Imagery Wayback (the newest image of the visible area
// taken on or before the period's end, switched with the period) or NASA GIBS true colour of the period's last
// day, and NASA FIRMS fires (VIIRS 375 m) of that day. The view lives in the URL too (?srodek=lat,lng&zoom=z), and so
// does a hand-picked Esri image (&zdjecie=<release date>); porownaj.html shows two images of the view side by side.
"use strict";
const { CAT, PRIORITY, isISO, periodFromQuery, clampPeriod, span, historyLink, $, h, swatch, getJSON, fmtShort, fmtDay, hasTime, duration, regionText, plural } = RCB;

// ---------- days ----------
const DAY_MS = 86400000;
const todayISO = () => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Warsaw" }).format(new Date());
const toDate = (iso) => new Date(iso + "T12:00:00Z");
const toISO = (d) => d.toISOString().slice(0, 10);
const addDays = (iso, n) => toISO(new Date(toDate(iso).getTime() + n * DAY_MS));
const dayDiff = (a, b) => Math.round((toDate(b) - toDate(a)) / DAY_MS);
const fmtISO = (iso) => iso.split("-").reverse().join(".");
const WEEKDAY = ["niedziela", "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota"];

// ---------- layers ----------
const GIBS = "https://gibs.earthdata.nasa.gov";
// fires: one WMS layer per satellite, each only from the day it has data (a missing one fails the request)
const FIRE_LAYERS = [
  ["VIIRS_SNPP_Thermal_Anomalies_375m_All", "2012-01-20"],
  ["VIIRS_NOAA20_Thermal_Anomalies_375m_All", "2020-01-01"],
  ["VIIRS_NOAA21_Thermal_Anomalies_375m_All", "2024-01-17"],
];
const WB = RCBWayback; // wayback.js
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
  today: todayISO(), start: "2021-01-01", from: null, to: null, base: "mapa", fires: false, cat: null,
  archive: [], live: null, liveActive: [], geo: null,
  map: null, pow: null, baseLayer: null, fireLayers: [],
  wayback: null, wbRelease: null, wbLocal: null, wbSeq: 0, wbPin: null,
};

// ---------- alerts of a period ----------
// today alone shows what is on now (the live list); a past day or a period, every alert that touched it
const isToday = () => S.from === S.today && S.to === S.today;
function alertsOf(from = S.from, to = S.to) {
  if (from === S.today && to === S.today && S.live) return S.liveActive;
  return S.archive.filter((a) => { const [s, e] = span(a, S.today); return s <= to && e >= from; })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
}
const regionsOf = (a) => a.regions || { voivodeships: a.voivodeships, powiaty: a.powiaty, whole: a.whole };

function paint(alerts) {
  const fill = {}; // powiat id -> the categories covering it
  const put = (id, cat) => (fill[id] = fill[id] || new Set()).add(cat);
  for (const a of alerts) {
    const r = regionsOf(a);
    for (const p of r.powiaty) put(p, a.category);
    for (const v of r.whole) S.geo.powByV[v]?.forEach((id) => put(id, a.category));
  }
  // with a chosen category only its powiaty stay lit; otherwise the most urgent one wins
  const on = (id) => S.cat ? (fill[id]?.has(S.cat) ? S.cat : null) : PRIORITY.find((c) => fill[id]?.has(c));
  S.pow.eachLayer((l) => {
    const el = l.getElement();
    if (!el) return;
    const cat = on(l.feature.properties.id);
    el.setAttribute("class", "pow leaflet-interactive" + (cat ? " hit c-" + cat : "") + (cat === "air" && isToday() ? " blink" : ""));
  });
  const used = new Set(Object.values(fill).flatMap((s) => [...s]));
  let cats = used.size ? PRIORITY.filter((c) => used.has(c)) : ["air", "water", "weather", "drill"];
  if (S.cat && !cats.includes(S.cat)) cats = PRIORITY.filter((c) => c === S.cat || cats.includes(c));
  // the legend doubles as a filter: one click isolates a category, the second clears it
  const leg = $("#legend");
  const refocus = leg.contains(document.activeElement) ? document.activeElement.textContent : null;
  const items = cats.map((c) => {
    const b = h("button", { type: "button", "aria-pressed": S.cat === c ? "true" : "false" }, swatch(c), CAT[c]);
    b.addEventListener("click", () => setCat(S.cat === c ? null : c));
    return h("li", {}, b);
  });
  if (S.fires) items.push(h("li", {}, h("i", { class: "sw fire-dot", "aria-hidden": "true" }), "Pożar lub anomalia termiczna (VIIRS)"));
  leg.replaceChildren(...items);
  if (refocus) { // the legend is rebuilt on every paint: keep the keyboard where it was
    const btns = [...leg.querySelectorAll("button")];
    (btns.find((b) => b.textContent === refocus) || btns[0])?.focus();
  }
}

function setCat(c, push = true) {
  S.cat = c;
  if (push) {
    const u = new URL(location.href);
    if (c) u.searchParams.set("kategoria", c); else u.searchParams.delete("kategoria");
    history.replaceState(null, "", u);
  }
  paint(alertsOf());
  panel();
}

function tooltip(layer) {
  const p = layer.feature.properties;
  const hits = alertsOf().filter((a) => { const r = regionsOf(a); return r.powiaty.includes(p.id) || r.whole.includes(p.v); });
  const box = h("div", {}, h("b", { text: (p.city ? "" : "powiat ") + p.name }));
  const n = {};
  for (const a of hits) n[a.category] = (n[a.category] || 0) + 1;
  const one = S.from === S.to;
  box.append(h("div", { text: hits.length ? PRIORITY.filter((c) => n[c]).map((c) => CAT[c] + (one ? "" : " × " + n[c])).join(", ") : "brak alertów" }));
  return box;
}

// ---------- the panel ----------
function activeRow(a) {
  const msg = (a.updates[0] && a.updates[0].message) || a.intro;
  const since = a.status === "planned" ? "planowany od " + fmtShort(new Date(a.started_at)) : "trwa " + duration(a.started_at);
  return h("li", {},
    h("div", { class: "row-head" }, swatch(a.category), CAT[a.category]),
    h("p", { class: "row-msg", text: msg.replace(/^"|"$/g, "") }),
    h("div", { class: "row-meta mono" }, h("span", { text: regionText(a.regions.voivodeships, a.regions.powiaty, a.regions.gminy) }), h("span", { text: since }), h("a", { href: a.url, text: "komunikat" })));
}

function archiveRow(a) {
  const [s, e] = span(a, S.today);
  const when = s === e ? (hasTime(a.started_at) ? "od " + fmtShort(new Date(a.started_at)) : fmtISO(s)) : `${fmtISO(s).slice(0, 5)}–${fmtISO(e)}`;
  return h("li", {},
    h("div", { class: "row-head" }, swatch(a.category), CAT[a.category]),
    h("p", { class: "row-msg", text: (a.message || a.title || "").replace(/^"|"$/g, "") }),
    h("div", { class: "row-meta mono" }, h("span", { text: regionText(a.voivodeships, a.powiaty, a.gminy) }), h("span", { text: when }), h("a", { href: a.url, text: "komunikat" })));
}

function recentRow(a) {
  const d = new Date(a.started_at);
  return h("li", {},
    h("span", { class: "when mono", text: hasTime(a.started_at) ? fmtShort(d) : fmtDay(d).slice(0, 5) }),
    h("a", { class: "what", href: a.url }, swatch(a.category), h("span", { text: `${CAT[a.category]} · ${regionText(a.voivodeships || a.regions.voivodeships, [])}` })));
}

const LIST_MAX = 30;
function panel() {
  const today = isToday(), one = S.from === S.to;
  const all = alertsOf(), list = all.filter((a) => !S.cat || a.category === S.cat);
  $("#now-title").textContent = today ? "Teraz" : one ? `${fmtISO(S.to)}, ${WEEKDAY[toDate(S.to).getUTCDay()]}` : `${fmtISO(S.from)} – ${fmtISO(S.to)}`;
  $("#active-count").textContent = list.length;
  const rows = list.slice(0, LIST_MAX).map((a) => (a.regions ? activeRow : archiveRow)(a));
  // «pełna historia» keeps the day or period on the map; today and the whole archive open the plain page
  const hist = historyLink(S.from, S.to, S.start, S.today), more = $("#more-history");
  more.href = hist;
  more.textContent = hist === "historia.html" ? "Pełna historia od 2021 roku" : `Pełna historia: ${S.from === S.to ? dayText(S.from) : `${dayText(S.from)} – ${dayText(S.to)}`}`;
  if (list.length > LIST_MAX) rows.push(h("li", { class: "empty" }, `i ${list.length - LIST_MAX} starszych — `, h("a", { href: hist, text: "pełna historia" })));
  $("#active").replaceChildren(...(list.length ? rows
    : [h("li", { class: "empty", text: S.cat ? "Brak alertów w tej kategorii." : today ? "Żaden alert RCB nie jest teraz aktywny." : one ? "Tego dnia nie było alertów RCB." : "W tym okresie nie było alertów RCB." })]));
  if (!one) return summary(all);
  // the week before the chosen day, without the alerts already listed above; "other" only when picked
  const from = addDays(S.to, -7), ids = new Set(list.map((a) => a.id));
  const recent = S.archive.filter((a) => { const s = a.started_at.slice(0, 10); return s > from && s <= S.to && !ids.has(a.id) && (S.cat ? a.category === S.cat : a.category !== "other"); })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
  $("#week-title").textContent = today ? "Ostatnie 7 dni" : `7 dni do ${fmtISO(S.to)}`;
  $("#week-count").textContent = recent.length;
  $("#recent").replaceChildren(...(recent.length ? recent.slice(0, 12).map(recentRow)
    : [h("li", { class: "empty", text: S.cat ? "W tym tygodniu nie było alertów w tej kategorii." : today ? "W tym tygodniu nie było alertów." : "W tym tygodniu nie było innych alertów." })]));
}

// a period: the alerts by category (a click filters the map to one) and the days that had an alert
function summary(all) {
  const n = {};
  const days = new Set();
  for (const a of all) {
    n[a.category] = (n[a.category] || 0) + 1;
    let [s, e] = span(a, S.today);
    if (s < S.from) s = S.from;
    if (e > S.to) e = S.to;
    for (let d = s; d <= e; d = addDays(d, 1)) days.add(d);
  }
  const len = dayDiff(S.from, S.to) + 1;
  $("#week-title").textContent = "W tym okresie";
  $("#week-count").textContent = `${days.size} ${plural(days.size, "dzień", "dni", "dni")} z alertem na ${len}`;
  const cats = PRIORITY.filter((c) => n[c]);
  $("#recent").replaceChildren(...(cats.length ? cats.map((c) => {
    const b = h("button", { type: "button", class: "what", "aria-pressed": S.cat === c ? "true" : "false" }, swatch(c), h("span", { text: CAT[c] }));
    b.addEventListener("click", () => setCat(S.cat === c ? null : c));
    return h("li", {}, h("span", { class: "when mono", text: `${n[c]} ${plural(n[c], "alert", "alerty", "alertów")}` }), b);
  }) : [h("li", { class: "empty", text: "Brak alertów." })]));
}

// ---------- the period: a brush over the histogram ----------
const nDays = () => dayDiff(S.start, S.today) + 1;
function spark() {
  const n = nDays();
  const counts = new Array(n).fill(0);
  for (const a of S.archive) {
    if (a.category === "other") continue;
    let [s, e] = span(a, S.today);
    if (e < S.start) continue;
    if (s < S.start) s = S.start;
    const i0 = dayDiff(S.start, s), i1 = Math.min(n - 1, dayDiff(S.start, e));
    for (let i = i0; i <= i1; i++) counts[i]++;
  }
  // a week per bar keeps the bars visible on a phone; the view box is in days, so a bar sits under its days
  const W = Math.ceil(n / 7), max = Math.max(1, ...Array.from({ length: W }, (_, w) => Math.max(...counts.slice(w * 7, w * 7 + 7))));
  const svg = $("#spark");
  svg.setAttribute("viewBox", `0 0 ${n} 20`);
  let d = "";
  for (let w = 0; w < W; w++) {
    const v = Math.max(...counts.slice(w * 7, w * 7 + 7));
    if (v) { const y = 20 - Math.max(2, Math.round(20 * v / max)); d += `M${w * 7} 20V${y}h5.6V20z`; }
  }
  svg.innerHTML = `<path d="${d}"/>`;
  // the years under the bars
  const axis = $("#brush-axis");
  const ticks = [];
  for (let y = +S.start.slice(0, 4) + 1; y <= +S.today.slice(0, 4); y++) {
    const at = dayDiff(S.start, `${y}-01-01`) / n;
    ticks.push(h("span", { style: `--at:${at}`, text: String(y) }));
  }
  axis.replaceChildren(...ticks);
}

// the period keeps its length when it moves; it never leaves the archive
function place(from, to) {
  const len = dayDiff(from, to);
  if (from < S.start) { from = S.start; to = addDays(from, len); }
  if (to > S.today) { to = S.today; from = addDays(to, -len); }
  setPeriod(from < S.start ? S.start : from, to);
}

const PRESETS = { "1": 1, "7": 7, "30": 30, "365": 365 };
const dayText = (iso) => (iso === S.today ? "dziś, " + fmtISO(iso) : fmtISO(iso));

function setPeriod(from, to, push = true) {
  ({ from, to } = clampPeriod(from, to, S.start, S.today));
  const moved = from !== S.from || to !== S.to;
  S.from = from; S.to = to;
  const n = nDays(), len = dayDiff(from, to) + 1;
  const b = $("#brush");
  b.style.setProperty("--a", dayDiff(S.start, from) / n);
  b.style.setProperty("--b", (dayDiff(S.start, to) + 1) / n);
  for (const [id, iso, name] of [["#h-from", from, "Początek okresu"], ["#h-to", to, "Koniec okresu"]]) {
    const el = $(id);
    el.setAttribute("aria-valuenow", dayDiff(S.start, iso));
    el.setAttribute("aria-valuemax", n - 1);
    el.setAttribute("aria-valuetext", `${name}: ${fmtISO(iso)}`);
  }
  const label = from === to ? dayText(to) : `${fmtISO(from)} – ${dayText(to)} · ${len} ${plural(len, "dzień", "dni", "dni")}`;
  $("#day-label").textContent = label;
  for (const [id, v] of [["#from", from], ["#to", to]]) {
    const el = $(id);
    el.min = S.start; el.max = S.today;
    if (el.value !== v) el.value = v;
  }
  $("#prev").disabled = from === S.start;
  $("#next").disabled = to === S.today;
  document.querySelectorAll("#presets button").forEach((x) => {
    const on = to === S.today && (x.dataset.days === "all" ? from === S.start : PRESETS[x.dataset.days] === len);
    x.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (push) {
    const u = new URL(location.href);
    u.searchParams.delete("dzien");
    if (from === S.today && to === S.today) { u.searchParams.delete("od"); u.searchParams.delete("do"); }
    else { u.searchParams.set("od", from); u.searchParams.set("do", to); }
    history.replaceState(null, "", u);
  }
  paint(alertsOf());
  panel();
  if (!moved) return;
  if (S.base === "nasa") setBase("nasa");
  if (S.fires) fires();
  // a new period lets Wayback follow its end again, even after a hand-picked image (one from the URL stays at the start)
  if (push && S.wbPin) { S.wbPin = null; viewURL(); }
  clearTimeout(S.wbTimer);
  S.wbTimer = setTimeout(waybackFollow, 250);
  dispatchEvent(new CustomEvent("rcb:day", { detail: { day: S.from === S.to ? S.to : null, from: S.from, to: S.to } }));
}

function brush() {
  const el = $("#brush"), PAD = 14;
  const dayAt = (ev) => {
    const r = el.getBoundingClientRect(), n = nDays();
    const f = Math.min(1, Math.max(0, (ev.clientX - r.left - PAD) / (r.width - 2 * PAD)));
    return addDays(S.start, Math.min(n - 1, Math.floor(f * n)));
  };
  let drag = null;
  el.addEventListener("pointerdown", (ev) => {
    if (ev.button !== 0) return;
    const id = ev.target.id, d = dayAt(ev);
    if (id === "h-from" || id === "h-to") drag = { kind: S.from === S.to ? "either" : id.slice(2) };
    else {
      // a tap beside the period moves it there, its end on the tapped day; a drag inside moves it along
      if (id !== "brush-sel") place(addDays(d, -dayDiff(S.from, S.to)), d);
      drag = { kind: "move", at: d, from: S.from, to: S.to };
    }
    el.setPointerCapture(ev.pointerId);
    el.classList.add("dragging");
    ev.preventDefault();
  });
  el.addEventListener("pointermove", (ev) => {
    if (!drag) return;
    const d = dayAt(ev);
    if (drag.kind === "either") { if (d < S.from) drag.kind = "from"; else if (d > S.to) drag.kind = "to"; else return; }
    if (drag.kind === "from") setPeriod(d < S.to ? d : S.to, S.to);
    else if (drag.kind === "to") setPeriod(S.from, d > S.from ? d : S.from);
    else { const off = dayDiff(drag.at, d); place(addDays(drag.from, off), addDays(drag.to, off)); }
  });
  const end = () => { drag = null; el.classList.remove("dragging"); };
  el.addEventListener("pointerup", end);
  el.addEventListener("pointercancel", end);
  // the handles are sliders for the keyboard: arrows a day, Page keys a month, Home/End the ends
  for (const which of ["from", "to"]) {
    $("#h-" + which).addEventListener("keydown", (ev) => {
      const step = { ArrowLeft: -1, ArrowDown: -1, ArrowRight: 1, ArrowUp: 1, PageDown: -30, PageUp: 30 }[ev.key];
      const cur = which === "from" ? S.from : S.to;
      let d = step ? addDays(cur, step) : ev.key === "Home" ? S.start : ev.key === "End" ? S.today : null;
      if (!d) return;
      ev.preventDefault();
      if (which === "from") setPeriod(d > S.to ? S.to : d, S.to); else setPeriod(S.from, d < S.from ? S.from : d);
    });
  }
}

// ---------- base layers ----------
// NASA true colour: the period's last day; today's swaths come in through the day, so today shows yesterday
const nasaDay = () => (S.to === S.today ? addDays(S.today, -1) : S.to);

function setBase(kind) {
  // Wayback needs its list of releases before the first tile
  if (kind === "esri" && !S.wayback) {
    S.base = kind;
    WB.config().then((rel) => { S.wayback = rel; if (!S.wbRelease) S.wbRelease = rel[0].id; if (S.base === "esri") setBase("esri"); })
      .catch((e) => { $("#base-note").textContent = "Nie udało się pobrać archiwum Esri Wayback: " + e.message; });
    return;
  }
  S.base = kind;
  if (S.baseLayer) S.map.removeLayer(S.baseLayer);
  $("#map").classList.toggle("sat", kind !== "mapa");
  $("#wb-wrap").hidden = kind !== "esri";
  $("#compare").hidden = kind !== "esri";
  const note = $("#base-note");
  if (kind === "mapa") {
    S.baseLayer = canvasLayer();
    note.textContent = "";
  } else if (kind === "nasa") {
    const d = nasaDay();
    S.baseLayer = L.tileLayer(`${GIBS}/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/${d}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`, {
      maxNativeZoom: 9, maxZoom: 19, attribution: NASA_ATTR + " · VIIRS NOAA-20 " + fmtISO(d),
    });
    note.textContent = `Zdjęcie z satelity NOAA-20 (VIIRS) z ${fmtISO(d)}${S.to === S.today ? " (dzisiejsze jeszcze się zbiera)" : ""}. Rozdzielczość ok. 250 m, w pochmurne dni widać chmury.`;
  } else {
    S.baseLayer = WB.layer(S.wbRelease);
    waybackList();
  }
  S.baseLayer.addTo(S.map);
}

// ---------- Esri Wayback: the images of the visible area (wayback.js) ----------
// a new layer rather than setUrl(): Leaflet 1.9's redraw() asks for tiles at a fractional zoom (6.25)
function useRelease(id) {
  S.wbRelease = id;
  if (S.base !== "esri") return;
  S.map.removeLayer(S.baseLayer);
  S.baseLayer = WB.layer(id).addTo(S.map);
}

async function waybackList() {
  const seq = ++S.wbSeq;
  const sel = $("#wayback"), note = $("#base-note");
  try {
    S.wayback = await WB.config();
    note.textContent = "Szukam zdjęć tego miejsca…";
    const local = await WB.atView(S.map);
    if (seq !== S.wbSeq || S.base !== "esri") return;
    S.wbLocal = local;
    const list = local.length ? local : S.wayback.slice(0, 1);
    sel.replaceChildren(...list.map((r) => h("option", { value: r.id, text: "zdjęcie z " + fmtISO(r.date) })));
    S.wbNote = `${local.length} ${plural(local.length, "zdjęcie", "różne zdjęcia", "różnych zdjęć")} środka widoku w archiwum Esri Wayback (wydania z datą publikacji). Przybliż mapę, by zobaczyć zdjęcia konkretnego miejsca.`;
    waybackFollow();
  } catch (e) {
    if (seq === S.wbSeq) note.textContent = "Nie udało się pobrać listy zdjęć Esri Wayback: " + e.message;
  }
}

// the image follows the period: the newest one of this spot taken on or before its end (the oldest, when
// the period is older than all of them), unless one was picked by hand or in the URL (&zdjecie=<release date>)
function waybackFollow() {
  if (S.base !== "esri" || !S.wayback) return;
  const list = S.wbLocal && S.wbLocal.length ? S.wbLocal : S.wayback.slice(0, 1);
  const pick = WB.onOrBefore(list, S.wbPin || S.to);
  if (pick.id !== S.wbRelease) useRelease(pick.id);
  $("#wayback").value = S.wbRelease;
  const why = S.wbPin ? `Wybrane wydanie Esri Wayback: ${fmtISO(pick.date)}. `
    : pick.date <= S.to ? `Najnowsze zdjęcie z dnia ${fmtISO(S.to)} lub wcześniej: ${fmtISO(pick.date)}. ` : `Brak zdjęcia sprzed ${fmtISO(S.to)}, pokazuję najstarsze: ${fmtISO(pick.date)}. `;
  const note = $("#base-note");
  note.textContent = why + (S.wbNote || "");
  compareLink();
  // the date on the release is when Esri published it; the metadata says when the picture was taken
  const seq = S.wbSeq, c = S.map.getCenter();
  WB.captured(pick, c, S.map.getZoom()).then((m) => {
    if (!m || seq !== S.wbSeq || S.wbRelease !== pick.id || S.base !== "esri") return;
    note.textContent = why + `Zdjęcie środka widoku wykonano ${fmtISO(m.day)} (${[m.source, m.res ? String(m.res).replace(".", ",") + " m" : ""].filter(Boolean).join(", ")}). ` + (S.wbNote || "");
  }).catch(() => {});
}

// ---------- the view in the URL ----------
// ?srodek=lat,lng&zoom=z, &podklad, &zdjecie: a link opens this very place and picture
function viewURL() {
  const u = new URL(location.href), m = S.map, c = m.getCenter();
  u.searchParams.set("srodek", `${c.lat.toFixed(5)},${c.lng.toFixed(5)}`);
  u.searchParams.set("zoom", String(+m.getZoom().toFixed(2)));
  if (S.base === "mapa") u.searchParams.delete("podklad"); else u.searchParams.set("podklad", S.base);
  if (S.base === "esri" && S.wbPin) u.searchParams.set("zdjecie", S.wbPin); else u.searchParams.delete("zdjecie");
  history.replaceState(null, "", u);
}
function readView(q) {
  const ll = (q.get("srodek") || "").split(",").map(Number), z = Number(q.get("zoom"));
  if (ll.length !== 2 || !ll.every(Number.isFinite) || Math.abs(ll[0]) > 85 || Math.abs(ll[1]) > 180) return null;
  return { center: ll, zoom: Number.isFinite(z) && q.get("zoom") ? Math.max(4, Math.min(19, z)) : 13 };
}

// «Porównaj» opens the same view on porownaj.html: the shown image on the right, the one before it on the left
function compareLink() {
  const a = $("#compare");
  if (!a || !S.map) return;
  const c = S.map.getCenter(), list = S.wbLocal && S.wbLocal.length ? S.wbLocal : [];
  const i = list.findIndex((r) => r.id === S.wbRelease);
  const q = new URLSearchParams({ srodek: `${c.lat.toFixed(5)},${c.lng.toFixed(5)}`, zoom: String(+S.map.getZoom().toFixed(2)) });
  if (i >= 0) { q.set("lewa", list[Math.min(i + 1, list.length - 1)].date); q.set("prawa", list[i].date); }
  a.href = "porownaj.html?" + q;
}

// ---------- NASA FIRMS fires of the period's last day ----------
function fires() {
  S.fireLayers.forEach((l) => S.map.removeLayer(l));
  S.fireLayers = [];
  if (!S.fires) return;
  for (const [layer, from] of FIRE_LAYERS) {
    if (S.to < from) continue;
    const l = L.tileLayer.wms(`${GIBS}/wms/epsg3857/best/wms.cgi`, {
      layers: layer, format: "image/png", transparent: true, version: "1.1.1", TIME: S.to,
      pane: "fires", tileSize: 512, maxZoom: 19, attribution: '<a href="https://firms.modaps.eosdis.nasa.gov/">NASA FIRMS</a>',
    });
    l.addTo(S.map);
    S.fireLayers.push(l);
  }
}

// ---------- start ----------
async function main() {
  await RCB.leaflet(); // a dropped request for leaflet.js gets one retry here, not "L is not defined"
  const [geo, archive] = await Promise.all([getJSON("geo/poland.geojson"), getJSON("data/archive.json"), RCB.names()]);
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
  // ?srodek=lat,lng&zoom=z opens that place; otherwise the whole country
  const q = new URLSearchParams(location.search);
  const view = readView(q);
  if (view) map.setView(view.center, view.zoom); else map.fitBounds(S.pow.getBounds(), { padding: [4, 4] });
  new ResizeObserver(() => map.invalidateSize()).observe($("#map"));

  setBase("mapa");
  dark.addEventListener("change", () => S.base === "mapa" && setBase("mapa"));
  document.querySelectorAll('input[name="base"]').forEach((r) => r.addEventListener("change", () => { setBase(r.value); viewURL(); }));
  $("#wayback").addEventListener("change", (e) => {
    const r = (S.wbLocal || S.wayback || []).find((x) => x.id === +e.target.value);
    S.wbPin = r ? r.date : null;
    useRelease(+e.target.value);
    waybackFollow();
    viewURL();
  });
  let wbTimer;
  map.on("moveend", () => {
    if (S.base === "esri") { clearTimeout(wbTimer); wbTimer = setTimeout(waybackList, 500); compareLink(); }
  });
  $("#fires").addEventListener("change", (e) => { S.fires = e.target.checked; fires(); paint(alertsOf()); });

  // ◀ ▶ shift the period by its length; the quick buttons end today
  const len = () => dayDiff(S.from, S.to) + 1;
  $("#prev").addEventListener("click", () => place(addDays(S.from, -len()), addDays(S.to, -len())));
  $("#next").addEventListener("click", () => place(addDays(S.from, len()), addDays(S.to, len())));
  document.querySelectorAll("#presets button").forEach((x) => x.addEventListener("click", () => {
    if (x.dataset.days === "all") setPeriod(S.start, S.today);
    else place(addDays(S.today, 1 - PRESETS[x.dataset.days]), S.today);
  }));
  $("#from").addEventListener("change", (e) => { if (isISO(e.target.value)) setPeriod(e.target.value, S.to); });
  $("#to").addEventListener("change", (e) => { if (isISO(e.target.value)) setPeriod(S.from, e.target.value); });
  brush();
  spark();

  // ?od=YYYY-MM-DD&do=YYYY-MM-DD opens a period (?dzien= one day, as the old links do);
  // &podklad=esri|nasa and &pozary=1 open the layers; &kategoria=<cat> filters the map and the lists;
  // &zdjecie=YYYY-MM-DD keeps the Esri image of that release (the newest one of the spot on or before it)
  const { from: wantFrom, to: wantTo } = periodFromQuery(location.search, S.today);
  if (CAT[q.get("kategoria")]) S.cat = q.get("kategoria");
  if (q.get("pozary") === "1") { S.fires = true; $("#fires").checked = true; }
  if (["esri", "nasa"].includes(q.get("podklad"))) { document.querySelector(`input[name="base"][value="${q.get("podklad")}"]`).checked = true; }
  if (q.get("podklad") === "esri" && isISO(q.get("zdjecie"))) S.wbPin = q.get("zdjecie");

  async function refresh() {
    const res = await RCB.strip();
    const t = todayISO();
    const was = S.today;
    if (t !== S.today) { S.today = t; spark(); dispatchEvent(new Event("rcb:range")); }
    if (res) { S.live = res.data; S.liveActive = res.active; }
    // a period that ended today keeps ending today after midnight
    if (S.to === null) setPeriod(wantFrom, wantTo, false);
    else if (S.to === was) place(addDays(S.from, dayDiff(was, t)), t);
  }
  await refresh();
  // attacks.js (missiles and drones over Poland) draws on the same map and slider through this
  window.RCBMap = { map, setDay: (d) => setPeriod(d, d), day: () => (S.from === S.to ? S.to : null), today: () => S.today,
    frac: (d) => (dayDiff(S.start, d) + 0.5) / nDays() };
  dispatchEvent(new CustomEvent("rcb:ready", { detail: window.RCBMap }));
  if (q.get("podklad") && q.get("podklad") !== "mapa") setBase(q.get("podklad"));
  if (S.fires) fires();
  // from here on the URL follows the view, so the address bar is always a link to what is on the screen
  map.on("moveend", viewURL);
  if (view) viewURL();
  setInterval(refresh, 60000);
  // a new alert from the live service redraws today's map at once
  document.addEventListener("rcb:alert", (e) => { if (e.detail.kind !== "test") refresh(); });
}

main().catch((e) => {
  const st = $("#strip .state");
  if (st) st.textContent = "Nie udało się wczytać mapy: " + e.message;
  console.error(e);
});
