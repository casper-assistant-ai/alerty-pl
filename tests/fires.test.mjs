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
const start = app.indexOf("function fires() {");
assert.notEqual(start, -1, "no fires() in docs/app.js");
const source = app.slice(start, app.indexOf("\n}\n", start) + 3);

// a stub of what fires() touches: L.tileLayer, the #fires-note element, the map and the state
function load(to, fires = true) {
  const made = [], removed = [];
  const note = { textContent: "" };
  const layer = (url, opts) => ({ url, opts, added: false, handlers: {}, on(ev, fn) { this.handlers[ev] = fn; }, addTo() { this.added = true; } });
  const L = {
    tileLayer: (url, opts) => { const l = layer(url, opts); made.push(l); return l; },
  };
  L.tileLayer.wms = () => assert.fail("fires() must not use GIBS WMS (wms.cgi): it answered a non-image on 2026-11-23");
  const S = { to, fires, fireLayers: [], map: { removeLayer: (l) => removed.push(l) } };
  const fmtISO = new Function(`return ${group(/const fmtISO = ([^\n]+);/, "fmtISO")};`)();
  const fires_ = new Function("S", "L", "$", "GIBS", "FIRE_LAYERS", "fmtISO", `${source}\n;return fires;`)(
    S, L, (sel) => { assert.equal(sel, "#fires-note"); return note; }, "https://gibs.earthdata.nasa.gov", FIRE_LAYERS, fmtISO);
  return { run: fires_, S, note, made, removed };
}

test("the fires come from GIBS WMTS, one layer per satellite, on the fires pane up to level 9", () => {
  const { run, made, S } = load("2026-08-15");
  run();
  assert.equal(made.length, 3);
  assert.deepEqual(made.map((l) => l.url), FIRE_LAYERS.map(([name]) =>
    `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${name}/default/2026-08-15/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`));
  for (const l of made) {
    assert.equal(l.opts.pane, "fires");
    assert.equal(l.opts.maxNativeZoom, 9);
    assert.equal(l.opts.maxZoom, 19);
    assert.equal(l.opts.tileSize, undefined, "256 px tiles, like the true-colour layer");
    assert.ok(l.added, "added to the map");
  }
  assert.deepEqual(S.fireLayers, made);
});

test("each satellite only from the day it has data", () => {
  const early = load("2019-06-01"); early.run();
  assert.deepEqual(early.made.map((l) => l.url.split("/best/")[1].split("/")[0]), ["VIIRS_SNPP_Thermal_Anomalies_375m_All"]);
  const mid = load("2021-06-01"); mid.run();
  assert.equal(mid.made.length, 2);
  const edge = load("2024-01-16"); edge.run();
  assert.equal(edge.made.length, 2);
  const all = load("2024-01-17"); all.run();
  assert.equal(all.made.length, 3);
});

test("a tile that fails to load is said once, in #fires-note, with the day", () => {
  const { run, made, note } = load("2026-08-15");
  run();
  assert.equal(note.textContent, "", "nothing is said before a tile fails");
  made[0].handlers.tileerror();
  assert.equal(note.textContent, "Nie udało się pobrać pożarów z NASA GIBS za dzień 15.08.2026. Pokazane punkty mogą być niepełne.");
  made[1].handlers.tileerror();
  made[2].handlers.tileerror();
  assert.equal(note.textContent, "Nie udało się pobrać pożarów z NASA GIBS za dzień 15.08.2026. Pokazane punkty mogą być niepełne.");
});

test("a rebuild removes the old layers, clears the note and ignores a late failure of a removed layer", () => {
  const first = load("2026-08-15");
  first.run();
  first.made[0].handlers.tileerror();
  assert.notEqual(first.note.textContent, "");
  // the period changes: the layers of the old day go, the note with them
  first.S.to = "2026-09-01";
  first.run();
  assert.deepEqual(first.removed, first.made.slice(0, 3));
  assert.equal(first.note.textContent, "");
  first.made[0].handlers.tileerror();
  assert.equal(first.note.textContent, "", "a removed layer's late failure is not shown");
  // the box is unticked: no layer is left and nothing is said
  first.S.fires = false;
  first.run();
  assert.equal(first.S.fireLayers.length, 0);
  first.made[3].handlers.tileerror();
  assert.equal(first.note.textContent, "");
});
