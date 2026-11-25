// Node test for the shared helpers of docs/common.js — no npm, just node:test and node:assert.
// CI runs it through tests/test_common_js.py (the Python suite); alone: node --test tests/common.test.mjs
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

// docs/common.js is a plain script: an IIFE over `const RCB` that looks up #ver on load. The pages load
// docs/i18n.js before it (the texts of the shared helpers); no ?lang and no stored choice is Polish.
// Evaluate both with a document stub whose querySelector answers null, then return RCB.
const load = (doc = { querySelector: () => null }) => {
  const read = (p) => readFileSync(new URL("../docs/" + p, import.meta.url), "utf8");
  return new Function("document", `${read("i18n.js")}\n${read("common.js")}\n;return RCB;`)(doc);
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

test("fmtDay, fmtShort, fmtTime and fmtISO pad day, month and clock", () => {
  const when = new Date(2026, 10, 5, 9, 3); // 5 November 2026, 09:03
  assert.equal(RCB.fmtDay(when), "05.11.2026");
  assert.equal(RCB.fmtShort(when), "05.11 09:03");
  assert.equal(RCB.fmtTime(when), "09:03");
  assert.equal(RCB.fmtISO("2026-11-05"), "05.11.2026"); // a day straight from the URL or an archive row
});

test("fmtStamp shows day and clock of a full ISO stamp in Warsaw time", () => {
  assert.equal(RCB.fmtStamp("2026-11-21T21:32:05+01:00"), "21.11.2026, 21:32");
  assert.equal(RCB.fmtStamp("2026-11-21T23:30:00Z"), "22.11.2026, 00:30"); // 23:30 UTC is 00:30 in Warsaw (+1, winter)
  assert.equal(RCB.fmtStamp("2026-07-01T22:30:00Z"), "02.07.2026, 00:30"); // CEST (+2) moves it to the next day
  assert.equal(RCB.fmtStamp("nie-data"), ""); // unreadable input: empty, so the caller can fall back to the day
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

// a document stub for h(): every element records the attributes set on it
const attrDoc = () => ({
  querySelector: () => null,
  createElement: () => {
    const attrs = {};
    return { attrs, style: {}, textContent: "", setAttribute: (k, v) => { attrs[k] = v; }, append() {} };
  },
});

test("h() never writes a URL the browser would run as code into href or src", () => {
  const { h } = load(attrDoc());
  // the browser reads an href or a src after dropping every tab, LF and CR and trimming the leading C0 controls
  // and spaces, so "java\tscript:" and "\x01javascript:" run too; the URL parser of the test reads them the same way
  const bad = ["javascript:alert(1)", " JAVASCRIPT:alert(1)", "java\tscript:alert(1)", "\x01javascript:alert(1)",
    "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)"];
  for (const url of bad) {
    assert.ok(["javascript:", "data:", "vbscript:"].includes(new URL(url, "https://alerty.pl/").protocol), url);
    assert.equal(h("a", { href: url }).attrs.href, undefined, url);
    assert.equal(h("script", { src: url }).attrs.src, undefined, url);
  }
});

test("h() keeps https links, relative links and other schemes such as the shelters' geo:", () => {
  const { h } = load(attrDoc());
  for (const good of ["https://t.me/alerty_pl_bot?start=abc", "historia.html?od=2026-11-01&do=2026-11-25", "geo:52.23,21.01?q=52.23,21.01(Schron)", "mailto:a@b.pl", "#top"]) {
    assert.equal(h("a", { href: good }).attrs.href, good, good);
  }
  assert.equal(h("script", { src: "vendor/leaflet/leaflet.js" }).attrs.src, "vendor/leaflet/leaflet.js");
});
