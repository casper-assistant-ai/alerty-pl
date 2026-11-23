// Alerty RCB — two satellite images of one place side by side (porownaj.html).
// Both maps show Esri World Imagery Wayback releases (wayback.js): the lists offer the distinct images of
// the centre of the view, and each side keeps its own. The map the visitor touches drives the other one,
// so dragging, the wheel, pinching and the +/- buttons move both, and the cursor shows on both.
// URL: ?srodek=lat,lng&zoom=z&lewa=YYYY-MM-DD&prawa=YYYY-MM-DD (release dates; the newest image of the
// spot on or before each date is shown), so the address bar is always a link to the same comparison.
"use strict";

const { $, h } = RCB;
const WB = RCBWayback;
RCB.strip();
setInterval(RCB.strip, 60000);

const POLAND = [[49.0, 14.1], [54.85, 24.15]];
const ISO = /^\d{4}-\d\d-\d\d$/;
const fmtISO = (iso) => iso.split("-").reverse().join(".");

// each side: its map, its layer, the release it shows and the date it was asked for (null: the default)
const side = {
  l: { key: "l", map: null, layer: null, rel: null, want: null, cursor: null },
  r: { key: "r", map: null, layer: null, rel: null, want: null, cursor: null },
};
let rels = [], local = [], seq = 0;

function makeMap(s) {
  const map = L.map(`map-${s.key}`, { zoomSnap: 0.25, minZoom: 4, maxZoom: 19 });
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
  // the other map's cursor: a cross that never takes a click
  s.cursor = L.marker([0, 0], {
    interactive: false, keyboard: false,
    icon: L.divIcon({ className: "cmp-cursor", iconSize: [24, 24], iconAnchor: [12, 12] }),
  });
  s.map = map;
  new ResizeObserver(() => map.invalidateSize()).observe(map.getContainer());
  return map;
}

function show(s, rel) {
  if (!rel || (s.rel && s.rel.id === rel.id && s.layer)) { s.rel = rel || s.rel; return; }
  s.rel = rel;
  // a new layer rather than setUrl(): Leaflet 1.9 redraws at a fractional zoom and asks for wrong tiles
  const next = WB.layer(rel.id).addTo(s.map);
  if (s.layer) { const old = s.layer; next.once("load", () => s.map.removeLayer(old)); setTimeout(() => s.map.hasLayer(old) && s.map.removeLayer(old), 4000); }
  s.layer = next;
}

// the image of a side: the asked date (the newest image on or before it), else newest right, the one before left
function pick(s) {
  const list = local.length ? local : rels;
  if (s.want) return WB.onOrBefore(list, s.want);
  return s.key === "r" ? list[0] : list[Math.min(1, list.length - 1)];
}

function fill(s) {
  const sel = $(`#sel-${s.key}`), list = local.length ? local : [s.rel];
  sel.replaceChildren(...list.map((r) => h("option", { value: r.id, text: "zdjęcie z " + fmtISO(r.date) })));
  sel.value = s.rel.id;
}

// when the picture in the middle of the view was taken (the metadata service is slow, so it comes later)
function caption(s) {
  const cap = $(`#cap-${s.key}`), rel = s.rel, n = seq;
  cap.textContent = `wydanie Esri z ${fmtISO(rel.date)}`;
  WB.captured(rel, s.map.getCenter(), s.map.getZoom()).then((m) => {
    if (!m || n !== seq || s.rel !== rel) return;
    const res = m.res ? String(m.res).replace(".", ",") + " m" : "";
    cap.textContent = `zdjęcie wykonane ${fmtISO(m.day)}` + (m.source || res ? ` · ${[m.source, res].filter(Boolean).join(", ")}` : "");
  }).catch(() => {});
}

function url() {
  const m = side.r.map, c = m.getCenter(), u = new URL(location.href);
  u.searchParams.set("srodek", `${c.lat.toFixed(5)},${c.lng.toFixed(5)}`);
  u.searchParams.set("zoom", String(+m.getZoom().toFixed(2)));
  if (side.l.rel) u.searchParams.set("lewa", side.l.rel.date);
  if (side.r.rel) u.searchParams.set("prawa", side.r.rel.date);
  history.replaceState(null, "", u);
  const back = new URLSearchParams({ podklad: "esri", srodek: u.searchParams.get("srodek"), zoom: u.searchParams.get("zoom") });
  if (side.r.rel) back.set("zdjecie", side.r.rel.date);
  $("#back").href = "./?" + back;
}

// after every move: the images of the new centre, both sides re-picked, captions and the URL
async function refresh() {
  const n = ++seq, note = $("#cmp-note");
  url();
  try {
    note.textContent = "Szukam zdjęć tego miejsca…";
    const found = await WB.atView(side.r.map);
    if (n !== seq) return;
    local = found;
    for (const s of [side.l, side.r]) { show(s, pick(s)); fill(s); caption(s); }
    url();
    note.textContent = local.length > 1
      ? `${local.length} różnych zdjęć środka widoku w archiwum Esri Wayback. Daty na listach to wydania archiwum; obok listy data wykonania zdjęcia. Przesuń lub przybliż jedną mapę, a druga pójdzie za nią.`
      : "W archiwum Esri jest tylko jedno zdjęcie środka widoku. Oddal mapę albo przesuń ją, by znaleźć miejsce z kilkoma zdjęciami.";
  } catch (e) {
    if (n === seq) note.textContent = "Nie udało się pobrać listy zdjęć Esri Wayback: " + e.message;
  }
}

// the map the visitor touches drives; the other follows without echo
function sync(a, b) {
  const el = a.map.getContainer();
  const take = () => { driver = a; };
  for (const ev of ["pointerdown", "wheel", "touchstart", "mouseenter", "focusin", "keydown"]) el.addEventListener(ev, take, { passive: true });
  a.map.on("move", () => { if (driver === a) b.map.setView(a.map.getCenter(), a.map.getZoom(), { animate: false }); });
  a.map.on("zoomanim", (e) => { if (driver === a) b.map.setView(e.center, e.zoom, { animate: true }); });
  a.map.on("moveend", () => {
    if (driver !== a) return;
    b.map.setView(a.map.getCenter(), a.map.getZoom(), { animate: false });
    clearTimeout(timer);
    timer = setTimeout(refresh, 400);
  });
  a.map.on("mousemove", (e) => { if ($("#cursor").checked) b.cursor.setLatLng(e.latlng).addTo(b.map); });
  a.map.on("mouseout", () => b.cursor.remove());
}
let driver = null, timer = null;

async function main() {
  await RCB.leaflet();
  const q = new URLSearchParams(location.search);
  if (ISO.test(q.get("lewa") || "")) side.l.want = q.get("lewa");
  if (ISO.test(q.get("prawa") || "")) side.r.want = q.get("prawa");
  makeMap(side.l); makeMap(side.r);
  const ll = (q.get("srodek") || "").split(",").map(Number), z = Number(q.get("zoom"));
  const ok = ll.length === 2 && ll.every(Number.isFinite) && Math.abs(ll[0]) <= 85 && Math.abs(ll[1]) <= 180;
  for (const s of [side.l, side.r]) {
    if (ok) s.map.setView(ll, q.get("zoom") && Number.isFinite(z) ? Math.max(4, Math.min(19, z)) : 13);
    else s.map.fitBounds(POLAND);
  }
  sync(side.l, side.r);
  sync(side.r, side.l);

  rels = await WB.config();
  // until the images of this spot are known, the release of the asked date (or the newest) shows the same picture
  for (const s of [side.l, side.r]) show(s, s.want ? WB.onOrBefore(rels, s.want) : rels[s.key === "r" ? 0 : 1]);

  for (const s of [side.l, side.r]) {
    $(`#sel-${s.key}`).addEventListener("change", (e) => {
      const rel = (local.length ? local : rels).find((r) => r.id === +e.target.value);
      if (!rel) return;
      s.want = rel.date;
      show(s, rel);
      caption(s);
      url();
    });
  }
  $("#swap").addEventListener("click", () => {
    [side.l.want, side.r.want] = [side.r.rel && side.r.rel.date, side.l.rel && side.l.rel.date];
    for (const s of [side.l, side.r]) { show(s, pick(s)); fill(s); caption(s); }
    url();
  });
  $("#cursor").addEventListener("change", (e) => { if (!e.target.checked) { side.l.cursor.remove(); side.r.cursor.remove(); } });
  await refresh();
}

main().catch((e) => {
  $("#cmp-note").textContent = "Nie udało się wczytać porównania: " + e.message;
  console.error(e);
});
