// Node test for fires() in docs/app.js — the NASA FIRMS layers of the map page (no npm, just node:test).
// CI runs it through tests/test_fires_js.py (the Python suite); alone: node --test tests/fires.test.mjs
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

// docs/app.js is a plain script that needs Leaflet and the page on load, so only its fires() is
// evaluated: the function's own source and the constants it reads, with a stub Leaflet and a stub note.
const app = readFileSync(new URL("../docs/app.js", import.meta.url), "utf8");
const group = (re, what) => { const m = app.match(re); assert.ok(m, `no ${what} in docs/app.js`); return m[1]; };
const FIRE_LAYERS = new Function(`return ${group(/const FIRE_LAYERS = (\[[\s\S]*?\]);/, "FIRE_LAYERS")};`)();
const GIBS = group(/const GIBS = "([^"]+)";/, "GIBS");
const fmtISO = new Function(`return ${group(/const fmtISO = ([^\n]+);/, "fmtISO")};`)();
const start = app.indexOf("function fires() {");
assert.notEqual(start, -1, "no fires() in docs/app.js");
const source = app.slice(start, app.indexOf("\n}\n", start) + 3);

// a stub of what fires() touches: L.tileLayer, the #fires-note element, the map and the state.
// The note counts the messages written to it: it is a status line, so one failure is announced once.
function load(to, fires = true) {
  const made = [], removed = [];
  const note = { messages: 0 };
  let text = "";
  Object.defineProperty(note, "textContent", { get: () => text, set: (v) => { if (v) note.messages++; text = v; } });
  const layer = (url, opts) => ({
    url, opts, added: false, handlers: {},
    on(ev, fn) { this.handlers[ev] = fn; },
    addTo() { this.added = true; },
  });
  const L = { tileLayer: (url, opts) => { const l = layer(url, opts); made.push(l); return l; } };
  L.tileLayer.wms = () => assert.fail("fires() must not use GIBS WMS (wms.cgi): it answered a non-image on 2026-11-23 (#73)");
  const S = { to, fires, fireLayers: [], map: { removeLayer: (l) => removed.push(l) } };
  const $ = (sel) => { assert.equal(sel, "#fires-note"); return note; };
  const fires_ = new Function("S", "L", "$", "GIBS", "FIRE_LAYERS", "fmtISO", `${source}\n;return fires;`)(S, L, $, GIBS, FIRE_LAYERS, fmtISO);
  return { run: fires_, S, note, made, removed };
}
// the GIBS layer identifier in a tile URL
const names = (made) => made.map((l) => l.url.split("/best/")[1].split("/")[0]);
const MESSAGE = (day) => `Nie udało się pobrać pożarów z NASA GIBS za dzień ${day}. Pokazane punkty mogą być niepełne.`;

test("the fires come from GIBS WMTS, one layer per satellite, on the fires pane up to level 9", () => {
  assert.equal(GIBS, "https://gibs.earthdata.nasa.gov");
  const { run, made, S } = load("2026-08-15");
  run();
  assert.equal(made.length, 3);
  assert.deepEqual(made.map((l) => l.url), [
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_Thermal_Anomalies_375m_All/default/2026-08-15/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_Thermal_Anomalies_375m_All/default/2026-08-15/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA21_Thermal_Anomalies_375m_All/default/2026-08-15/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",
  ]);
  for (const l of made) {
    assert.equal(l.opts.pane, "fires");
    assert.equal(l.opts.maxNativeZoom, 9, "the GoogleMapsCompatible_Level9 matrix set ends at level 9");
    assert.equal(l.opts.maxZoom, 19);
    assert.equal(l.opts.tileSize, undefined, "256 px tiles, like the true-colour layer");
    assert.match(l.opts.attribution, /firms\.modaps\.eosdis\.nasa\.gov/);
    assert.ok(l.added, "added to the map");
  }
  assert.deepEqual(S.fireLayers, made);
});

test("each satellite only from the day it has data", () => {
  const SNPP = "VIIRS_SNPP_Thermal_Anomalies_375m_All", N20 = "VIIRS_NOAA20_Thermal_Anomalies_375m_All", N21 = "VIIRS_NOAA21_Thermal_Anomalies_375m_All";
  for (const [day, layers] of [
    ["2012-01-19", []], ["2012-01-20", [SNPP]], ["2019-12-31", [SNPP]],
    ["2020-01-01", [SNPP, N20]], ["2024-01-16", [SNPP, N20]], ["2024-01-17", [SNPP, N20, N21]], ["2026-08-15", [SNPP, N20, N21]],
  ]) {
    const { run, made } = load(day);
    run();
    assert.deepEqual(names(made), layers, day);
    assert.ok(made.every((l) => l.url.includes(`/default/${day}/`)), `${day}: each layer is asked for that day`);
  }
});

test("a tile that fails to load is said once, in #fires-note, with the day", () => {
  const { run, made, note } = load("2026-08-15");
  run();
  assert.equal(note.textContent, "", "nothing is said before a tile fails");
  for (const l of made) assert.equal(typeof l.handlers.tileerror, "function", "each layer listens for its tiles failing");
  made[0].handlers.tileerror();
  assert.equal(note.textContent, MESSAGE("15.08.2026"));
  made[0].handlers.tileerror(); // a second tile of the same layer
  made[1].handlers.tileerror();
  made[2].handlers.tileerror();
  assert.equal(note.textContent, MESSAGE("15.08.2026"));
  assert.equal(note.messages, 1, "written once per rebuild");
});

test("a rebuild removes the old layers, clears the note and ignores a late failure of a removed layer", () => {
  const first = load("2026-08-15");
  first.run();
  first.made[0].handlers.tileerror();
  assert.equal(first.note.textContent, MESSAGE("15.08.2026"));
  // the period changes: the layers of the old day go, the note with them
  first.S.to = "2026-09-01";
  first.run();
  assert.deepEqual(first.removed, first.made.slice(0, 3));
  assert.equal(first.made.length, 6);
  assert.deepEqual(names(first.made.slice(3)), names(first.made.slice(0, 3)));
  assert.ok(first.made.slice(3).every((l) => l.url.includes("/default/2026-09-01/")));
  assert.equal(first.note.textContent, "");
  first.made[0].handlers.tileerror();
  assert.equal(first.note.textContent, "", "a removed layer's late failure is not shown");
  first.made[3].handlers.tileerror();
  assert.equal(first.note.textContent, MESSAGE("01.09.2026"), "a failure of the new day is said with that day");
  // the box is unticked: no layer is left, none is made and nothing is said
  first.S.fires = false;
  first.run();
  assert.deepEqual(first.removed, first.made, "every layer is removed from the map");
  assert.equal(first.S.fireLayers.length, 0);
  assert.equal(first.made.length, 6, "unticked: no layer is made");
  assert.equal(first.note.textContent, "");
  first.made[3].handlers.tileerror();
  assert.equal(first.note.textContent, "");
});

test("nothing is made when the box is unticked", () => {
  const { run, made, note, S } = load("2026-08-15", false);
  run();
  assert.equal(made.length, 0);
  assert.equal(S.fireLayers.length, 0);
  assert.equal(note.textContent, "");
});

test("the page has the status line #fires-note above #base-note", () => {
  // fires() writes to it on every period change, so the map page breaks without it
  const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.match(html, /<p class="base-note mono" id="fires-note" role="status"><\/p>\s*<p class="base-note mono" id="base-note"><\/p>/);
});
