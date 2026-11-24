// tests/site_check.test.mjs — the page checks of scripts/site_check.mjs are template literals that
// run in the browser, so a regex inside one writes its backslashes twice: \. alone is eaten by the
// template and \? becomes a quantifier, which made the hourly site check report a missing
// «Porównaj daty» link on a page that had it (#61). The live notification service's failed requests
// are judged apart from the tile servers (#70), and GIBS's empty tile, a 404 with an image, is not a
// failed request (#94).
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { LIVE, judge, liveLine } from "../scripts/site_check.mjs";

const src = readFileSync(new URL("../scripts/site_check.mjs", import.meta.url), "utf8");

// COMMON, MARKUP and every page's check, as the source spells them between the backticks
const templates = [...src.matchAll(/(?:const (COMMON|MARKUP) = |check: )`((?:[^`\\]|\\.)*)`/g)].map((m) => {
  const names = [...src.slice(0, m.index).matchAll(/name: "([^"]*)"/g)];
  return { name: m[1] || names[names.length - 1][1], raw: m[2] };
});
// the string the browser receives: the template literal evaluated
const inPage = (t) => new Function("return (`" + t.raw + "`)")();
// one check run against a stub page: querySelectorAll answers from the map of lists, querySelector from the map
// of elements or else the first of the selector's list (as in a page; a selector in neither is missing), location
// is the address
const run = (code, els, search, lists = {}) => {
  globalThis.document = { querySelector: (s) => els[s] ?? lists[s]?.[0] ?? null, querySelectorAll: (s) => lists[s] ?? [] };
  globalThis.location = { search };
  return new Function("return (" + code + ")")();
};

test("COMMON, MARKUP and every page check are read from the script", () => {
  assert.equal(templates.length, (src.match(/check: `/g) || []).length + 2);
  for (const t of templates) assert.ok(t.name && t.raw.includes("(() =>"), t.name);
});

test("a regex in a page template writes its backslashes twice, so the browser keeps them", () => {
  // in a template literal \. is just "." and \? is just "?", which in a regex quantifies the
  // letter before it: /porownaj.html?srodek=/ can never match a real link
  for (const t of templates) {
    assert.doesNotMatch(t.raw, /(?<!\\)\\(?!\\)/,
      `${t.name}: a lone backslash in the template is dropped; write two to get one in the page`);
  }
});

test("every check compiles as the browser reads it", () => {
  for (const t of templates) assert.doesNotThrow(() => new Function("return (" + inPage(t) + ")"), t.name);
});

test("the «Porównaj daty» check passes on the link the map page builds, and still catches a missing one", () => {
  const t = templates.find((x) => x.name.startsWith("Mapa, link do miejsca"));
  assert.ok(t, "the page check of the link to a place and its picture is gone");
  const code = inPage(t);
  assert.ok(code.includes("/porownaj\\.html\\?srodek=/"), "the browser must receive the escapes of /porownaj\\.html\\?srodek=/");
  const search = "?podklad=esri&srodek=50.5650,17.9650&zoom=15&zdjecie=2025-04-24";
  const els = {
    "#wayback option:checked": { textContent: "zdjęcie z 24.04.2025" },
    // what compareLink() in docs/app.js writes for this view
    "#compare": { href: "https://casper-assistant-ai.github.io/alerty-pl/porownaj.html?srodek=50.56500%2C17.96500&zoom=15&lewa=2025-03-27&prawa=2025-04-24" },
  };
  assert.deepEqual(run(code, els, search), []);
  assert.deepEqual(run(code, { ...els, "#compare": { href: "porownaj.html" } }, search), ["the «Porównaj daty» link is missing"]);
  assert.deepEqual(run(code, { ...els, "#compare": null }, search), ["the «Porównaj daty» link is missing"]);
});

// the fires view as a healthy page shows it (#94): the powiaty, true-colour tiles that loaded, <img>s in the fires
// pane of which some have loaded (Leaflet marks a tile that failed with no class), and #fires-note empty
const many = (n) => Array.from({ length: n }, () => ({}));
const FIRES_ELS = { "#day-label": { textContent: "15.08.2026" }, "#fires-note": { textContent: "" } };
const FIRES_LISTS = { ".leaflet-interactive": many(300), ".leaflet-tile-pane img.leaflet-tile-loaded": many(6),
  ".leaflet-fires-pane img": many(12), ".leaflet-fires-pane img.leaflet-tile-loaded": many(2) };
const firesCheck = (code, lists = {}, els = {}) => run(code, { ...FIRES_ELS, ...els }, "", { ...FIRES_LISTS, ...lists });
const NOTE = "Nie udało się pobrać pożarów z NASA GIBS za dzień 15.08.2026. Pokazane punkty mogą być niepełne.";
const NONE_LOADED = ["NASA FIRMS fire tiles did not load"];
const SOME_FAILED = ["NASA FIRMS: some fire tiles did not load, the page says: " + NOTE];

test("the fires check wants a fire tile that has loaded and an empty #fires-note, not just <img>s in the pane", () => {
  const t = templates.find((x) => x.name.startsWith("Mapa, NASA i pożary"));
  assert.ok(t, "the page check of the NASA view with the fires is gone");
  const code = inPage(t);
  assert.deepEqual(firesCheck(code), []);
  // #73: the <img>s are in the pane but not one of them loaded, a dead layer shown as nothing. The old check
  // (any .leaflet-fires-pane img) passed this; a pane without <img>s at all must fail the same way
  const unloaded = { ".leaflet-fires-pane img.leaflet-tile-loaded": [] };
  assert.deepEqual(firesCheck(code, unloaded), NONE_LOADED);
  assert.deepEqual(firesCheck(code, { ...unloaded, ".leaflet-fires-pane img": [] }), NONE_LOADED);
  // a tile failed while others loaded: fires() in docs/app.js says so in #fires-note, and the check passes it on
  assert.deepEqual(firesCheck(code, {}, { "#fires-note": { textContent: NOTE } }), SOME_FAILED);
  assert.deepEqual(firesCheck(code, unloaded, { "#fires-note": { textContent: NOTE } }), [...NONE_LOADED, ...SOME_FAILED]);
});

// a failed request as visit() records it
const fail = (kind, url, text = "net::ERR_FAILED") => ({ kind, detail: `${text} ${url}`, url });
const EVENTS = LIVE + "events";
const tile = (n) => `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/2026-08-15/GoogleMapsCompatible_Level9/${n}/3/4.jpg`;

test("LIVE is the live service docs/common.js talks to", () => {
  const common = readFileSync(new URL("../docs/common.js", import.meta.url), "utf8");
  const api = common.match(/"(https:\/\/[^"]+\/alerty)"/)[1];
  assert.equal(LIVE, api + "/");
});

test("the live service's failed requests are kept apart from the tiles", () => {
  // the NASA view of 15.08 while the service is down (#70): the stream's reconnects and a few tiles
  const p = [fail("network-3rd", EVENTS), ...Array.from({ length: 7 }, (_, i) => fail("http-3rd", tile(i), "404")),
    fail("network-3rd", EVENTS), fail("network-3rd", EVENTS)];
  const few = judge(p);
  assert.deepEqual(few.problems, [], "7 tiles stay under the limit of 8, whatever the stream does");
  assert.equal(few.live.length, 3);
  assert.equal(few.live[0].url, EVENTS);
  // 9 tiles are reported, by host, without the live service
  const many = judge([...p, fail("http-3rd", tile(8), "404"),
    fail("network-3rd", "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/1/2")]);
  assert.deepEqual(many.problems, [{ kind: "3rd-party",
    detail: `9 failed requests to other sites (8 × gibs.earthdata.nasa.gov, 1 × server.arcgisonline.com), e.g. 404 ${tile(0)}` }]);
  assert.equal(many.live.length, 3);
  // the 5xx of a proxy in front of the service is the service too; the site's own files are neither
  assert.equal(judge([fail("http-3rd", LIVE + "alerts", "502")]).live.length, 1);
  const own = judge([fail("network", "https://casper-assistant-ai.github.io/alerty-pl/data/alerts.json")]);
  assert.deepEqual(own.live, []);
  assert.equal(own.problems.length, 1);
});

// a tile GIBS has no data for: 404 whose body is a transparent image, which the map shows blank (#94)
const blank = (url) => ({ ...fail("http-3rd", url, "404"), mimeType: "image/png" });
const fire = (sat, n) => `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_${sat}_Thermal_Anomalies_375m_All/default/2026-08-15/GoogleMapsCompatible_Level9/7/${n}/33.png`;

test("GIBS's empty tile, a 404 with an image, is not a failed request; every other failure still counts", () => {
  // the fires view: three layers of 256 px tiles, a dozen empty ones each here
  const empty = ["SNPP", "NOAA20", "NOAA21"].flatMap((sat) => Array.from({ length: 12 }, (_, i) => blank(fire(sat, i))));
  assert.deepEqual(judge(empty), { problems: [], live: [] }, "36 empty tiles are not reported");
  // the 404s with another body among them are counted on their own: 9, not 45
  const html = Array.from({ length: 9 }, (_, i) => ({ ...fail("http-3rd", tile(i), "404"), mimeType: "text/html" }));
  assert.deepEqual(judge([...empty, ...html]).problems, [{ kind: "3rd-party",
    detail: `9 failed requests to other sites (9 × gibs.earthdata.nasa.gov), e.g. 404 ${tile(0)}` }]);
  // #73: GIBS answered every GetMap with a non-image, which the browser blocked; that is still 12 failed requests
  const wms = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?service=WMS&request=GetMap&layers=VIIRS_SNPP_Thermal_Anomalies_375m_All";
  const blocked = Array.from({ length: 12 }, (_, i) => fail("network-3rd", `${wms}&i=${i}`, "net::ERR_BLOCKED_BY_ORB"));
  assert.deepEqual(judge([...empty, ...blocked]).problems, [{ kind: "3rd-party",
    detail: `12 failed requests to other sites (12 × gibs.earthdata.nasa.gov), e.g. ${blocked[0].detail}` }]);
  // a 404 with another body or without a known one, and any other status, an image or not: counted
  for (const [status, mimeType] of [["404", "text/html"], ["404", undefined], ["403", "image/png"], ["503", "image/png"]]) {
    const what = `${status} ${mimeType || "without a mimeType"}`;
    const nine = Array.from({ length: 9 }, (_, i) => ({ ...fail("http-3rd", tile(i), status), mimeType }));
    assert.equal(judge(nine).problems.length, 1, `${what}: 9 failed requests are reported`);
    assert.equal(judge(nine.slice(0, 8)).problems.length, 0, `${what}: 8 stay under the limit`);
  }
});

test("visit() keeps the response's mimeType on an HTTP error, which judge() needs to know an empty tile", () => {
  // without it judge() counts every empty tile again, and the hourly check reports the fires view on every run
  const received = src.slice(src.indexOf('case "Network.responseReceived"'), src.indexOf('case "Network.loadingFailed"'));
  assert.match(received, /mimeType: p\.response\.mimeType/);
});

test("one line for the run when the live service did not answer", () => {
  const view = (live) => ({ page: "Mapa", viewport: "desktop", problems: [], ...(live ? { live } : {}) });
  const views = [view([fail("network-3rd", EVENTS)]), view([fail("network-3rd", EVENTS)]), view(),
    view([fail("network-3rd", EVENTS, "net::ERR_TIMED_OUT")])];
  const line = liveLine(views);
  assert.equal(line.page, "Live notification service");
  assert.equal(line.url, LIVE);
  assert.equal(line.viewport, "-");
  assert.deepEqual(line.problems, [{ kind: "live", detail: `${fail("network-3rd", EVENTS).detail} on 3 of 4 page views; the pages fall back to the Pages copy of the data until it answers (server/, outside this repository)` }]);
  assert.equal(liveLine([view(), view()]), null);
});
