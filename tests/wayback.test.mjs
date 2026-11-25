// Node test for docs/wayback.js (the Esri World Imagery Wayback releases): a dropped request for the release
// list must not take the map or the comparison page down (issue #152: the mobile audit saw
// "TypeError: Failed to fetch" on porownaj.html). No npm, just node:test and node:assert.
// Run by tests/test_wayback_js.py inside the Python suite, and by `node --test tests/*.test.mjs`.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

// wayback.js is a plain script over `const RCBWayback`; it touches fetch and setTimeout only when called, so it
// runs here with a fake fetch that answers from `replies` (one promise per request) and a setTimeout that
// waits nothing but remembers for how long it was asked to.
const SRC = readFileSync(new URL("../docs/wayback.js", import.meta.url), "utf8");
const CONFIG = "https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json";
const CFG = {
  92340: { itemTitle: "World Imagery (2025-04-24)", metadataLayerUrl: "https://example.invalid/a/MapServer" },
  92160: { itemTitle: "World Imagery (2025-03-27)", metadataLayerUrl: "https://example.invalid/b/MapServer" },
};
const RELS = [
  { id: 92340, date: "2025-04-24", meta: "https://example.invalid/a/MapServer" },
  { id: 92160, date: "2025-03-27", meta: "https://example.invalid/b/MapServer" },
];
// what fetch() hands back: the list, Chrome's message for a dropped request, a server that answers with a status
const ok = () => Promise.resolve({ ok: true, json: () => Promise.resolve(CFG) });
const dropped = () => Promise.reject(new TypeError("Failed to fetch"));
const down = (status) => Promise.resolve({ ok: false, status });

let replies = [];
function load() {
  const calls = [], waits = [];
  const fetch = (url) => { calls.push(url); return replies.shift(); };
  const setTimeout = (fn, ms) => { waits.push(ms); fn(); return 0; };
  const WB = new Function("fetch", "setTimeout", `${SRC}\n;return RCBWayback;`)(fetch, setTimeout);
  return { WB, calls, waits };
}

test("config() asks again when the first request drops, and gives the releases newest first", async () => {
  replies = [dropped(), ok()];
  const { WB, calls, waits } = load();
  const first = WB.config(), second = WB.config();
  assert.equal(second, first); // callers share one request
  const rels = await first;
  assert.deepEqual(rels, RELS);
  assert.deepEqual(calls, [CONFIG, CONFIG]);
  assert.deepEqual(waits, [500]);
  assert.equal(await WB.config(), rels); // the list is kept: nothing is fetched again
  assert.equal(calls.length, 2);
});

test("config() gives up after three dropped requests, and the next call starts again", async () => {
  replies = [dropped(), dropped(), dropped()];
  const { WB, calls, waits } = load();
  await assert.rejects(WB.config(), TypeError);
  assert.deepEqual(calls, [CONFIG, CONFIG, CONFIG]);
  assert.deepEqual(waits, [500, 1000]);
  replies = [dropped(), ok()];
  assert.deepEqual(await WB.config(), RELS);
  assert.equal(calls.length, 5);
});

test("an error status or a broken body is asked again too, and the last status is the error", async () => {
  replies = [down(503), Promise.resolve({ ok: true, json: () => Promise.reject(new SyntaxError("Unexpected end of JSON input")) }), ok()];
  const { WB, calls, waits } = load();
  assert.deepEqual(await WB.config(), RELS);
  assert.equal(calls.length, 3);
  assert.deepEqual(waits, [500, 1000]);
  replies = [down(403), down(503), down(503)];
  await assert.rejects(load().WB.config(), /waybackconfig: 503/);
});
