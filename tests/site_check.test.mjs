// tests/site_check.test.mjs — the page checks of scripts/site_check.mjs are template literals that
// run in the browser, so a regex inside one writes its backslashes twice: \. alone is eaten by the
// template and \? becomes a quantifier, which made the hourly site check report a missing
// «Porównaj daty» link on a page that had it (#61). The live notification service's failed requests
// are judged apart from the tile servers (#70), and GIBS's empty tile, a 404 with an image, is not a
// failed request (#94).
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";
import { LIVE, SETTLE, STRIP_WAIT, judge, liveLine, ownOrigins, settle } from "../scripts/site_check.mjs";

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

// #229: GitHub Pages answers the github.io address with a 301 to the site's domain, the pages load their data
// there, and the check took that host for a third party's: a 503 of data/shelters/index.json was dropped as one
// tile, and the report said «Ładowanie…» on 26 page views without one address of the site's own.
const GH = "https://casper-assistant-ai.github.io/alerty-pl/";
const SITE = "https://alerty.klioba.com/";

test("the site's own files are recognised on the domain GitHub Pages redirects to", () => {
  const site = ownOrigins(GH);
  assert.equal(site.isOwn(GH + "data/meta.json"), true);
  assert.equal(site.isOwn(SITE + "data/shelters/index.json"), false, "not before the redirect is seen");
  site.redirected(SITE + "schrony.html", GH + "schrony.html"); // Network.requestWillBeSent with redirectResponse
  assert.equal(site.isOwn(SITE + "data/shelters/index.json"), true);
  assert.equal(site.isOwn("https://alerty.klioba.com.evil.example/data/shelters/index.json"), false, "another host with the same prefix");
  assert.equal(site.isOwn("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/1/2/3"), false);
  site.redirected("https://gibs.earthdata.nasa.gov/wms.cgi?x=1", "https://gibs.earthdata.nasa.gov/wms.cgi");
  site.redirected("data:text/html,1", GH + "index.html");
  assert.equal(site.isOwn("https://gibs.earthdata.nasa.gov/wms.cgi?x=1"), false, "a redirect of another site makes nothing the site's own");
  assert.equal(site.isOwn("data:text/html,1"), false);
  // visit() files by it: a failed request of the site's own is an http or network problem on every count
  const v = src.slice(src.indexOf("async function visit("), src.indexOf("// The HTML of each page"));
  assert.match(v, /const site = ownOrigins\(BASE\)/);
  assert.match(v, /const own = site\.isOwn\(p\.response\.url\)/);
  assert.match(v, /kind: site\.isOwn\(url\) \? "network" : "network-3rd"/);
  assert.match(v, /if \(p\.redirectResponse\) site\.redirected\(p\.request\.url, p\.redirectResponse\.url\)/);
  assert.equal(judge([{ kind: "http", detail: "503 " + SITE + "data/shelters/index.json", url: SITE + "data/shelters/index.json" }]).problems.length, 1);
});

test("a request the page still waits for when its checks ran is named, and so is the live service the page gave up on", () => {
  // the map page waits on RCB.strip(), which waits on the live service: everything after it is «not drawn»
  const v = src.slice(src.indexOf("async function visit("), src.indexOf("// The HTML of each page"));
  const wired = (code) => assert.ok(v.includes(code), "visit() no longer has: " + code);
  wired('case "Network.loadingFinished": pending.delete(p.requestId);'); // a request that answered is not waited for
  wired('if (/^(Image|Font)$/.test(type) || /\\/events$/.test(url)) continue;'); // tiles, fonts and the stream: the page checks' business
  wired('kind: service ? "network-3rd" : "network", detail: `no answer while the page was checked ');
  // a hung /alerts fetch is aborted by docs/common.js after its wait: an abort the check used to drop with the rest
  wired('const gaveUp = url.startsWith(LIVE) && !/\\/events$/.test(url) && /ERR_ABORTED/.test(p.errorText);');
  wired('if (gaveUp || (!/ERR_ABORTED|ERR_BLOCKED_BY_CLIENT/.test(p.errorText) && !p.canceled))');
  wired('no answer before the page gave up on the service: ');
  // judged like the service's other failures: one line for the run, the site's own file on its page view
  const alerts = LIVE + "alerts";
  const waiting = { kind: "network-3rd", detail: "no answer while the page was checked " + alerts, url: alerts };
  const view = (live, problems = []) => ({ page: "Mapa", viewport: "desktop", problems, ...(live ? { live } : {}) });
  const line = liveLine([view([waiting]), view([waiting], [{ kind: "network", detail: "no answer while the page was checked " + SITE + "data/alerts.json" }]), view()]);
  assert.equal(line.problems[0].detail, `${waiting.detail} on 2 of 3 page views; the pages fall back to the Pages copy of the data until it answers (server/, outside this repository)`);
  const own = judge([view([waiting], [{ kind: "network", detail: "no answer while the page was checked " + SITE + "data/alerts.json" }]).problems[0]]);
  assert.equal(own.problems.length, 1);
  assert.deepEqual(own.live, []);
  assert.deepEqual(judge([waiting]).problems, [], "the service's own wait is not a failed tile of another site");
});

test("the checks wait for a strip that is still loading, and no longer than STRIP_WAIT", async () => {
  // #271: while the live service is down every strip lives on the copy on Pages, which the page asks for only
  // once the service's 2.5 s are over. On one view of 54 it had not answered when the checks ran, 3.5 s after
  // the load event, and the report filed the fallback at work as «status strip: Ładowanie…».
  // The page is asked for its strip through the real expression, answered from a stub document at each poll.
  const doc = (strip, checked) => ({ querySelector: (s) => (s === "#strip" ? strip : s === "#strip .checked" ? checked : null) });
  const loading = doc({}, { textContent: "  " }), done = doc({}, { textContent: "sprawdzono 17:31" });
  const failed = doc({}, { textContent: "data/alerts.json: 503" }), noStrip = doc(null, null);
  const page = (states) => {
    let polls = 0;
    return { get polls() { return polls; }, send: async (_m, p) => {
      assert.equal(p.returnByValue, true);
      const value = new Function("document", "return " + p.expression)(states[Math.min(polls++, states.length - 1)]);
      return { result: { value } };
    } };
  };
  const slow = page([loading, loading, loading, done]); // the copy answers on the third poll
  await settle(slow, 1, { wait: 1000, every: 5 });
  assert.equal(slow.polls, 4, "asked again until the strip is filled in");
  for (const [name, state] of [["filled in", done], ["failed", failed], ["absent", noStrip]]) {
    const once = page([state]);
    await settle(once, 1, { wait: 1000, every: 5 });
    assert.equal(once.polls, 1, `a strip that is ${name} is not waited for`);
  }
  const gone = { polls: 0, send: async () => { gone.polls++; return { exceptionDetails: { text: "Cannot find context with specified id" } }; } };
  await settle(gone, 1, { wait: 1000 });
  assert.equal(gone.polls, 1, "a page that went away is not asked again");
  const dead = page([loading]);
  const t0 = Date.now();
  const wait = 60, every = 5;
  await settle(dead, 1, { wait, every });
  assert.ok(Date.now() - t0 >= 55, `a strip that never fills: the whole wait, then the checks (${Date.now() - t0} ms)`);
  // half the polls the cadence allows, not its ideal count: a 5 ms timer a few ms late on a loaded runner
  // (CI runs the test files in parallel) is no defect of settle(), and one or two polls still fail this
  assert.ok(dead.polls >= Math.floor(wait / every / 2) && dead.polls <= 20, `asked every ${every} ms for ${wait} ms: ${dead.polls} polls`);
});

test("SETTLE and STRIP_WAIT follow the waits of docs/common.js and stay bounded", () => {
  const common = readFileSync(new URL("../docs/common.js", import.meta.url), "utf8");
  const liveWait = Number(common.match(/fetch\(API \+ "\/alerts"[^\n]*AbortSignal\.timeout\((\d+)\)/)[1]);
  const copyWait = Number(common.match(/const COPY_WAIT = (\d+)/)[1]);
  // the copy on Pages, asked once the service's wait is over, gets a few seconds to answer before it is judged...
  assert.ok(SETTLE + STRIP_WAIT >= liveWait + 5000, `${SETTLE} + ${STRIP_WAIT} ms is not the service's ${liveWait} ms and five seconds more`);
  // ...but not its whole wait: a copy that uses that up is a problem to report
  assert.ok(STRIP_WAIT < copyWait, `${STRIP_WAIT} ms waits out the copy's whole wait of ${copyWait} ms`);
  // 54 views of a strip that never fills add under eight minutes to the run, inside the workflow's limit of 25
  assert.ok(54 * STRIP_WAIT < 8 * 60000, `${STRIP_WAIT} ms on 54 views is more than eight minutes`);
  // wired after the load event's settle and before the checks
  const v = src.slice(src.indexOf("async function visit("), src.indexOf("// The HTML of each page"));
  const settleAt = v.indexOf("await settle(cdp, sid);");
  assert.ok(v.indexOf("await sleep(SETTLE);") < settleAt && settleAt < v.indexOf("for (const [kind, expr] of"), "visit() no longer settles the strip between SETTLE and the checks");
});
