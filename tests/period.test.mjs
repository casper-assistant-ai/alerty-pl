// Node test of the period logic of the map and history pages (docs/common.js: periodFromQuery, clampPeriod,
// span, isISO; historyPeriod, inPeriod, historyLink) and of the map page's ?podklad= (baseFromQuery).
// Alone: node --test tests/period.test.mjs ; CI runs every tests/*.test.mjs in its "Node tests" step.
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const source = readFileSync(new URL("../docs/common.js", import.meta.url), "utf8");
const RCB = new Function("document", `${source}\n;return RCB;`)({ querySelector: () => null });
const TODAY = "2026-11-23", START = "2021-01-01";

test("isISO accepts real calendar days only", () => {
  for (const ok of ["2026-11-23", "2024-02-29", "2021-01-01"]) assert.equal(RCB.isISO(ok), true, ok);
  for (const bad of ["2026-02-31", "2026-13-01", "2025-02-29", "23.11.2026", "2026-11-2", "", null, undefined]) {
    assert.equal(RCB.isISO(bad), false, String(bad));
  }
});

test("no query opens today alone", () => {
  assert.deepEqual(RCB.periodFromQuery("", TODAY), { from: TODAY, to: TODAY });
  assert.deepEqual(RCB.periodFromQuery("?kategoria=air", TODAY), { from: TODAY, to: TODAY });
});

test("?od=&do= opens a period; ?od alone runs to today", () => {
  assert.deepEqual(RCB.periodFromQuery("?od=2026-11-01&do=2026-11-10", TODAY), { from: "2026-11-01", to: "2026-11-10" });
  assert.deepEqual(RCB.periodFromQuery("?od=2026-11-01", TODAY), { from: "2026-11-01", to: TODAY });
  assert.deepEqual(RCB.periodFromQuery("?do=2026-11-10", TODAY), { from: "2026-11-10", to: "2026-11-10" });
});

test("old ?dzien= links open one day, and ?do= wins over ?dzien=", () => {
  assert.deepEqual(RCB.periodFromQuery("?dzien=2026-10-21", TODAY), { from: "2026-10-21", to: "2026-10-21" });
  assert.deepEqual(RCB.periodFromQuery("?dzien=2026-10-21&od=2026-10-01", TODAY), { from: "2026-10-01", to: "2026-10-21" });
  assert.deepEqual(RCB.periodFromQuery("?dzien=2026-10-21&do=2026-10-25", TODAY).to, "2026-10-25");
});

test("garbage in the query falls back to today instead of breaking the page", () => {
  assert.deepEqual(RCB.periodFromQuery("?od=wczoraj&do=2026-02-31", TODAY), { from: TODAY, to: TODAY });
  assert.deepEqual(RCB.periodFromQuery("?od=%3Cscript%3E&dzien=", TODAY), { from: TODAY, to: TODAY });
});

test("clampPeriod swaps a backwards period and cuts it to the archive", () => {
  assert.deepEqual(RCB.clampPeriod("2026-11-10", "2026-11-01", START, TODAY), { from: "2026-11-01", to: "2026-11-10" });
  assert.deepEqual(RCB.clampPeriod("2019-05-01", "2026-11-10", START, TODAY), { from: START, to: "2026-11-10" });
  assert.deepEqual(RCB.clampPeriod("2026-11-01", "2027-03-01", START, TODAY), { from: "2026-11-01", to: TODAY });
});

test("clampPeriod keeps a period that lies wholly outside the archive as a one-day period at its edge", () => {
  assert.deepEqual(RCB.clampPeriod("2030-01-01", "2030-02-01", START, TODAY), { from: TODAY, to: TODAY });
  assert.deepEqual(RCB.clampPeriod("2010-01-01", "2010-02-01", START, TODAY), { from: START, to: START });
});

// ---------- the base layer of the map page: ?podklad= (#178) ----------

test("baseFromQuery: no ?podklad=, an empty one or mapa is the grey canvas; a known value is that base", () => {
  assert.equal(RCB.baseFromQuery(""), "mapa");
  assert.equal(RCB.baseFromQuery("?srodek=50.06140,19.93808&zoom=6&pozary=1"), "mapa");
  assert.equal(RCB.baseFromQuery("?podklad="), "mapa");
  assert.equal(RCB.baseFromQuery("?podklad=mapa"), "mapa");
  for (const b of ["esri", "nasa", "sentinel"]) assert.equal(RCB.baseFromQuery(`?podklad=${b}&srodek=50.06140,19.93808`), b, b);
});

test("baseFromQuery: a value that names no base is null, so the page keeps its default base instead of a layer", () => {
  for (const bad of ["xyz", "ESRI", "esri%20", "map", "wayback", "sentinel-2", "%3Cscript%3E"]) {
    assert.equal(RCB.baseFromQuery(`?podklad=${bad}`), null, bad);
  }
  assert.equal(RCB.baseFromQuery("?podklad=esri&podklad=xyz"), "esri"); // a repeated parameter: the first one counts, as URLSearchParams.get reads it
  assert.equal(RCB.baseFromQuery("?podklad=xyz&podklad=nasa"), null);
});

test("BASES is the list of the page's radio boxes, in their order: a new base is known to ?podklad= or fails here", () => {
  const html = readFileSync(new URL("../docs/index.html", import.meta.url), "utf8");
  const radios = [...html.matchAll(/<input type="radio" name="base" value="([^"]+)"/g)].map((m) => m[1]);
  assert.deepEqual(RCB.BASES, radios);
  assert.equal(RCB.BASES[0], "mapa"); // the default, the one viewURL leaves out of the URL
});

test("the map page gives setBase only a base that baseFromQuery named, never the raw ?podklad= value", () => {
  const app = readFileSync(new URL("../docs/app.js", import.meta.url), "utf8");
  // an unknown value once reached setBase and fell through to its last branch, the Wayback imagery, while the
  // radio still said «Mapa» (#178)
  assert.doesNotMatch(app, /setBase\([^)]*q\.get\(/);
  assert.match(app, /const wantBase = baseFromQuery\(location\.search\);/);
  assert.match(app, /if \(wantBase && wantBase !== "mapa"\) setBase\(wantBase\);/);
});

// ---------- the history page: the same ?od=&do=, with the whole archive as the default (#52) ----------

test("historyPeriod reads ?od=&do= as the map does; no date is the whole archive", () => {
  assert.deepEqual(RCB.historyPeriod(""), { from: null, to: null });
  assert.deepEqual(RCB.historyPeriod("?powiat=dolnoslaskie%2Fzgorzelecki&cat=air"), { from: null, to: null });
  assert.deepEqual(RCB.historyPeriod("?od=2026-11-01&do=2026-11-07"), { from: "2026-11-01", to: "2026-11-07" });
  assert.deepEqual(RCB.historyPeriod("?od=2026-11-01"), { from: "2026-11-01", to: null }); // od alone runs on
  assert.deepEqual(RCB.historyPeriod("?do=2026-11-07"), { from: "2026-11-07", to: "2026-11-07" }); // do alone is that day
  assert.deepEqual(RCB.historyPeriod("?dzien=2026-11-07"), { from: "2026-11-07", to: "2026-11-07" }); // the old one-day link, as on the map
});

test("historyPeriod ignores a date that is not a real day and swaps a backwards pair", () => {
  assert.deepEqual(RCB.historyPeriod("?od=wczoraj&do=2026-02-31"), { from: null, to: null });
  assert.deepEqual(RCB.historyPeriod("?od=%3Cscript%3E&do="), { from: null, to: null });
  assert.deepEqual(RCB.historyPeriod("?od=bad&do=2026-11-07"), { from: "2026-11-07", to: "2026-11-07" }); // the good end still counts
  assert.deepEqual(RCB.historyPeriod("?od=2026-11-07&do=2026-11-01"), { from: "2026-11-01", to: "2026-11-07" });
});

test("inPeriod keeps the alerts published on the period's days, both ends included; no period keeps all", () => {
  const week = RCB.historyPeriod("?od=2026-11-01&do=2026-11-07");
  const kept = (per, date) => RCB.inPeriod({ date }, per);
  for (const d of ["2026-11-01", "2026-11-04", "2026-11-07"]) assert.equal(kept(week, d), true, d);
  for (const d of ["2026-10-31", "2026-11-08"]) assert.equal(kept(week, d), false, d);
  const whole = RCB.historyPeriod("?q=Gostyń");
  for (const d of ["2019-01-01", "2026-11-07", "2026-11-23"]) assert.equal(kept(whole, d), true, d);
  const open = RCB.historyPeriod("?od=2026-11-01");
  assert.equal(kept(open, "2026-11-23"), true);
  assert.equal(kept(open, "2026-10-31"), false);
});

test("historyLink: the map's «pełna historia» keeps a chosen day or period, and opens the plain page today and on the whole archive", () => {
  const link = (from, to) => RCB.historyLink(from, to, START, TODAY);
  assert.equal(link(TODAY, TODAY), "historia.html");
  assert.equal(link(START, TODAY), "historia.html");
  assert.equal(link("2026-11-07", "2026-11-07"), "historia.html?od=2026-11-07&do=2026-11-07");
  assert.equal(link("2026-11-01", "2026-11-07"), "historia.html?od=2026-11-01&do=2026-11-07");
  assert.equal(link("2026-11-17", TODAY), "historia.html?od=2026-11-17&do=2026-11-23"); // a preset that ends today is a period too
  // what a link carries is what the archive page reads back
  const carried = link("2026-11-01", "2026-11-07").slice("historia.html".length);
  assert.deepEqual(RCB.historyPeriod(carried), { from: "2026-11-01", to: "2026-11-07" });
});

test("span: an ended alert covers its days; an active or planned one runs to today", () => {
  const a = (status, s, l) => ({ status, started_at: s, last_at: l });
  assert.deepEqual(RCB.span(a("ended", "2026-11-20T10:00:00+01:00", "2026-11-20T12:00:00+01:00"), TODAY), ["2026-11-20", "2026-11-20"]);
  assert.deepEqual(RCB.span(a("expired", "2026-11-19T23:00:00+01:00", "2026-11-21T01:00:00+01:00"), TODAY), ["2026-11-19", "2026-11-21"]);
  assert.deepEqual(RCB.span(a("active", "2026-11-19T10:00:00+01:00", "2026-11-19T12:00:00+01:00"), TODAY), ["2026-11-19", TODAY]);
  assert.deepEqual(RCB.span(a("planned", "2026-11-23T08:00:00+01:00", "2026-11-23T08:00:00+01:00"), TODAY), [TODAY, TODAY]);
});

test("span: a missing last_at or one before the start never gives an end before the start", () => {
  assert.deepEqual(RCB.span({ status: "ended", started_at: "2026-11-20T10:00:00+01:00" }, TODAY), ["2026-11-20", "2026-11-20"]);
  assert.deepEqual(RCB.span({ status: "ended", started_at: "2026-11-20T10:00:00+01:00", last_at: "2026-11-19T10:00:00+01:00" }, TODAY),
    ["2026-11-20", "2026-11-20"]);
});
