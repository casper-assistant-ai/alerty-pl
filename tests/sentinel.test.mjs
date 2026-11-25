// Node test for docs/sentinel.js (Copernicus Sentinel-2 under the map, through Microsoft Planetary Computer):
// which day the map shows by itself and which days the list offers. The case that asked for the layer: the
// flood of September 2024 at Lewin Brzeski. The view's centre had scenes on 6 Sept (0% cloud), 8 Sept (15%),
// 11 Sept (95%), none from 12 to 20 Sept (storm Boris), then 21 Sept (0%, the flooded valley); the period
// 12–20 Sept must open the 21 Sept image. Also: a Content-Security-Policy on the map page must let the layer in.
// No npm, just node:test and node:assert. Run by tests/test_sentinel_js.py and by `node --test tests/*.test.mjs`.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const SRC = readFileSync(new URL("../docs/sentinel.js", import.meta.url), "utf8");
const S2 = new Function("L", SRC + "; return RCBSentinel;")({ tileLayer: (url, opt) => ({ url, opt }) });

const scene = (day, cloud) => ({ id: "S2_" + day, properties: { datetime: day + "T10:00:31Z", "eo:cloud_cover": cloud } });
const LEWIN = [
  scene("2024-09-28", 89.3), scene("2024-09-26", 100), scene("2024-09-23", 98.5), scene("2024-09-21", 0.0),
  scene("2024-09-11", 95.5), scene("2024-09-08", 15.0), scene("2024-09-06", 0.0), scene("2024-09-03", 34.4),
];

test("scenes become days, newest first, with the clearest scene of each day", () => {
  const days = S2.daysOf([scene("2024-09-06", 40.2), scene("2024-09-06", 3.6), scene("2024-09-08", 15), { properties: {} }]);
  assert.deepEqual(days, [{ day: "2024-09-08", cloud: 15, n: 1 }, { day: "2024-09-06", cloud: 4, n: 2 }]);
});

test("the flood: no clear scene in 12–20 Sept 2024 opens the clear one nearest after it, 21 Sept", () => {
  const days = S2.daysOf(LEWIN);
  assert.equal(S2.pick(days, "2024-09-12", "2024-09-20").day, "2024-09-21");
  assert.equal(S2.away("2024-09-21", "2024-09-12", "2024-09-20"), 1);
  // the list: the clear days around the period (the cloudy ones only when inside it)
  assert.deepEqual(S2.offer(days, "2024-09-12", "2024-09-20").map((d) => d.day), ["2024-09-21", "2024-09-08", "2024-09-06"]);
});

test("a clear day inside the period wins, the newest of them", () => {
  const days = S2.daysOf(LEWIN);
  assert.equal(S2.pick(days, "2024-09-01", "2024-09-10").day, "2024-09-08");
  assert.equal(S2.pick(days, "2024-09-01", "2024-09-07").day, "2024-09-06");
  // every day inside the period is offered, cloudy or not
  assert.ok(S2.offer(days, "2024-09-01", "2024-09-12").some((d) => d.day === "2024-09-11"));
});

test("before the period when that is nearer; the later one on a tie", () => {
  const days = S2.daysOf(LEWIN);
  assert.equal(S2.pick(days, "2024-09-09", "2024-09-11").day, "2024-09-08");
  const tie = S2.daysOf([scene("2024-05-01", 0), scene("2024-05-09", 0)]);
  assert.equal(S2.pick(tie, "2024-05-03", "2024-05-07").day, "2024-05-09");
});

test("no clear day at all: the least cloudy one; no scene: null", () => {
  const days = S2.daysOf([scene("2024-12-01", 80), scene("2024-12-04", 55), scene("2024-12-09", 97)]);
  assert.equal(S2.pick(days, "2024-12-05", "2024-12-06").day, "2024-12-04");
  assert.equal(S2.pick([], "2024-12-05", "2024-12-06"), null);
});

test("the search asks for one point, the period with its margin, newest first", () => {
  const b = S2.searchBody(50.75123456, 17.60004, "2024-08-13", "2024-10-20");
  assert.deepEqual(b.collections, ["sentinel-2-l2a"]);
  assert.deepEqual(b.intersects, { type: "Point", coordinates: [17.6, 50.7512] });
  assert.equal(b.datetime, "2024-08-13T00:00:00Z/2024-10-20T23:59:59Z");
  assert.equal(b.sortby[0].direction, "desc");
});

test("a day's mosaic: that day only, the clearest scene on top; 10 m tiles with the Copernicus credit", () => {
  const m = S2.mosaicBody("2024-09-21");
  assert.deepEqual(m.filter.args[1], { interval: ["2024-09-21T00:00:00Z", "2024-09-21T23:59:59Z"] });
  assert.deepEqual(m.sortby, [{ field: "eo:cloud_cover", direction: "asc" }]);
  const url = S2.tileURL("pc1.123.abc");
  assert.equal(new URL(url.replace("{z}/{x}/{y}", "1/2/3")).origin, "https://planetarycomputer.microsoft.com");
  assert.match(url, /assets=visual/);
  assert.match(S2.attr("2024-09-21"), /Copernicus Sentinel<\/a> data 2024 \(Sentinel-2 L2A 21\.09\.2024\)/);
});

test("a Content-Security-Policy on the map page lets Planetary Computer in (images and requests)", () => {
  const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
  assert.match(html, /<script src="sentinel\.js" defer><\/script>[\s\S]*<script src="app\.js"/);
  const csp = (html.match(/http-equiv="Content-Security-Policy"\s+content="([^"]+)"/) || [])[1];
  if (!csp) return; // no policy, nothing is blocked
  const dir = (name) => (csp.split(";").map((x) => x.trim().split(/\s+/)).find((x) => x[0] === name) || []).slice(1);
  for (const name of ["img-src", "connect-src"]) {
    assert.ok(dir(name).includes("https://planetarycomputer.microsoft.com"), `${name} must allow https://planetarycomputer.microsoft.com`);
  }
});
