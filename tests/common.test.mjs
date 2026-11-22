// Node test for the shared helpers of docs/common.js — no npm, just node:test and node:assert.
// CI runs it through tests/test_common_js.py (the Python suite); alone: node --test tests/common.test.mjs
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

// docs/common.js is a plain script: an IIFE over `const RCB` that looks up #ver on load.
// Evaluate it with a document stub whose querySelector answers null, then return RCB.
const load = (doc = { querySelector: () => null }) => {
  const source = readFileSync(new URL("../docs/common.js", import.meta.url), "utf8");
  return new Function("document", `${source}\n;return RCB;`)(doc);
};
const RCB = load();

test("CAT names every category, in Polish", () => {
  assert.deepEqual(Object.keys(RCB.CAT).sort(),
    ["air", "chemical", "drill", "fire", "ordnance", "other", "water", "weather"]);
  assert.equal(RCB.CAT.air, "Zagrożenie z powietrza");
  assert.equal(RCB.CAT.drill, "Ćwiczenia i testy syren");
  assert.equal(RCB.CAT.chemical, "Skażenia");
});

test("PRIORITY covers every category exactly once, air first, other last", () => {
  assert.deepEqual([...RCB.PRIORITY].sort(), Object.keys(RCB.CAT).sort());
  assert.equal(new Set(RCB.PRIORITY).size, RCB.PRIORITY.length);
  assert.equal(RCB.PRIORITY[0], "air");
  assert.equal(RCB.PRIORITY[RCB.PRIORITY.length - 1], "other");
});

test("color turns a category into its CSS variable", () => {
  assert.equal(RCB.color("fire"), "var(--fire)");
});

test("fmtDay, fmtShort and fmtTime pad day, month and clock", () => {
  const when = new Date(2026, 10, 5, 9, 3); // 5 November 2026, 09:03
  assert.equal(RCB.fmtDay(when), "05.11.2026");
  assert.equal(RCB.fmtShort(when), "05.11 09:03");
  assert.equal(RCB.fmtTime(when), "09:03");
});

test("hasTime hides the hour of a day-only alert (midnight start)", () => {
  assert.equal(RCB.hasTime("2026-11-22T00:00:00"), false);
  assert.equal(RCB.hasTime("2026-11-22T08:00:00"), true);
});

test("duration reads in minutes, hours and days, and never goes negative", () => {
  const started = (minutesAgo) => new Date(Date.now() - minutesAgo * 60000).toISOString();
  assert.equal(RCB.duration(started(5)), "5 min");
  assert.equal(RCB.duration(started(90)), "1 h 30 min");
  assert.equal(RCB.duration(started(3 * 24 * 60)), "3 dni");
  assert.equal(RCB.duration(new Date(Date.now() + 60000).toISOString()), "0 min");
});

test("plural picks the Polish form for one, a few and many", () => {
  const f = (n) => RCB.plural(n, "alert", "alerty", "alertów");
  assert.equal(f(1), "alert");
  assert.equal(f(3), "alerty");
  assert.equal(f(12), "alertów"); // 12–14 take the many form like 5–21, despite ending in 2–4
  assert.equal(f(22), "alerty");
  assert.equal(f(25), "alertów");
});

// a document stub for the leaflet() retry path: records the script tag it appends
const retryDoc = (scripts) => ({
  querySelector: () => null,
  createElement: () => ({ src: "", onload: null, onerror: null, remove() {} }),
  head: { append: (s) => scripts.push(s) },
});

test("leaflet() hands back Leaflet at once when the defer load worked", async () => {
  globalThis.L = { here: true };
  try { assert.equal(await RCB.leaflet(), globalThis.L); }
  finally { delete globalThis.L; }
});

test("leaflet() retries the vendored script when the first load was dropped", async () => {
  const scripts = [];
  const p = load(retryDoc(scripts)).leaflet();
  assert.equal(scripts.length, 1); // the retry script tag is appended right away
  assert.equal(scripts[0].src, "vendor/leaflet/leaflet.js");
  globalThis.L = { back: true };
  scripts[0].onload();
  try { assert.equal(await p, globalThis.L); }
  finally { delete globalThis.L; }
});

test("leaflet() fails with a Polish message when the retry is refused too", async () => {
  const scripts = [];
  const p = load(retryDoc(scripts)).leaflet();
  scripts[0].onerror();
  await assert.rejects(p, /biblioteka mapy/);
});
