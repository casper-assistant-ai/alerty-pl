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

// #229: the live service did not answer for one Site check run. Every page's strip waits on it through liveData(),
// and the map page draws its period, incursions and layers only after its strip: with a wait of 6 s the run
// reported «Ładowanie…» on all 26 page views and a map with nothing drawn. The check reads a page 3.5 s after
// its load event, so the wait ends well before that and the copy on Pages takes over.
test("the strip gives up on a live service that does not answer within its wait, and shows the copy on Pages", async () => {
  const part = () => ({ textContent: "", classList: { toggle() {}, add() {}, remove() {} } });
  const parts = { ".state": part(), ".others": part(), ".checked": part() };
  const strip = Object.assign(part(), { querySelector: (x) => parts[x] || null });
  const doc = { title: "Alerty", querySelectorAll: () => [], querySelector: (s) => (s === "#strip" ? strip : null) };
  const alerts = { alerts: [] }, meta = { checked_at: "2026-11-26T12:00:00Z" };
  const real = globalThis.fetch;
  // the service that never answers: like fetch, the stub gives up when the page's AbortSignal does
  globalThis.fetch = (url, init) => (String(url).startsWith(RCB.API)
    ? new Promise((_, bad) => init.signal.addEventListener("abort", () => bad(new DOMException("The operation was aborted.", "TimeoutError"))))
    : Promise.resolve({ ok: true, json: async () => (String(url).startsWith("data/meta.json") ? meta : alerts) }));
  try {
    const read = (p) => readFileSync(new URL("../docs/" + p, import.meta.url), "utf8");
    const page = new Function("document", "window", `${read("i18n.js")}\n${read("common.js")}\n;return RCB;`)(doc, {});
    const t0 = Date.now();
    const res = await page.strip();
    const waited = Date.now() - t0;
    assert.ok(waited < 3000, `${waited} ms: the Site check reads the strip 3.5 s after the load event`);
    assert.equal(res.meta, meta, "the copy on Pages filled the strip");
    assert.equal(res.data, alerts);
    assert.doesNotMatch(parts[".state"].textContent, /Ładowanie/);
  } finally { globalThis.fetch = real; }
});

// #237: the live service was down and on one page view the copy on Pages did not answer either: the Site check
// read «Ładowanie…» with data/alerts.json still pending. The copy had no wait of its own, so a connection that
// stalls holds every page's strip, and the map page's whole drawing, for as long as it hangs. The copy is now
// asked twice and each ask gives up after its wait. A page with a strip whose parts record their text; the
// caller brings fetch and shortens the waits, since the test must not sit out 2.5 s and 10 s.
function stalledPage() {
  const part = () => ({ textContent: "", classList: { toggle() {}, add() {}, remove() {} } });
  const parts = { ".state": part(), ".others": part(), ".checked": part() };
  const strip = Object.assign(part(), { querySelector: (x) => parts[x] || null });
  const doc = { title: "Alerty", querySelectorAll: () => [], querySelector: (s) => (s === "#strip" ? strip : null) };
  const read = (p) => readFileSync(new URL("../docs/" + p, import.meta.url), "utf8");
  return { parts, page: new Function("document", "window", `${read("i18n.js")}\n${read("common.js")}\n;return RCB;`)(doc, {}) };
}
// a request that hangs: like fetch, the stub gives up when the page's AbortSignal does
const stall = (init) => new Promise((_, bad) => init.signal.addEventListener("abort", () => bad(new DOMException("signal timed out", "TimeoutError"))));

test("the strip asks the copy on Pages again when its first ask stalls, and shows the second answer", async () => {
  const alerts = { alerts: [] }, meta = { checked_at: "2026-11-26T12:00:00Z" };
  const real = globalThis.fetch, realTimeout = globalThis.AbortSignal.timeout;
  globalThis.AbortSignal.timeout = (ms) => realTimeout.call(globalThis.AbortSignal, Math.min(ms, 20));
  let asks = 0; // of data/alerts.json
  globalThis.fetch = (url, init) => {
    url = String(url);
    if (url.startsWith(RCB.API)) return stall(init);
    if (url.startsWith("data/alerts.json")) return ++asks === 1 ? stall(init) : Promise.resolve({ ok: true, json: async () => alerts });
    return Promise.resolve({ ok: true, json: async () => meta });
  };
  try {
    const { parts, page } = stalledPage();
    const res = await page.strip();
    assert.equal(asks, 2, "the copy was asked once more");
    assert.equal(res.meta, meta, "the second answer filled the strip");
    assert.equal(res.data, alerts);
    assert.doesNotMatch(parts[".state"].textContent, /Ładowanie|Nie udało/);
  } finally { globalThis.fetch = real; globalThis.AbortSignal.timeout = realTimeout; }
});

test("the strip gives up on a copy on Pages that stalls twice, and says so instead of «Ładowanie…»", async () => {
  const real = globalThis.fetch, realTimeout = globalThis.AbortSignal.timeout;
  globalThis.AbortSignal.timeout = (ms) => realTimeout.call(globalThis.AbortSignal, Math.min(ms, 20));
  let asks = 0; // of the live service and of data/alerts.json
  globalThis.fetch = (url, init) => {
    url = String(url);
    if (url.startsWith(RCB.API) || url.startsWith("data/alerts.json")) { asks++; return stall(init); }
    return Promise.resolve({ ok: true, json: async () => ({ checked_at: "2026-11-26T12:00:00Z" }) });
  };
  try {
    const { parts, page } = stalledPage();
    const res = await page.strip();
    assert.equal(res, null);
    assert.equal(asks, 3, "the service once, the copy twice, and no more");
    assert.equal(parts[".state"].textContent, "Nie udało się pobrać danych");
  } finally { globalThis.fetch = real; globalThis.AbortSignal.timeout = realTimeout; }
});
