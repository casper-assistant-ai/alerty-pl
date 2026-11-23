// Node test of the period logic of the map page (docs/common.js: periodFromQuery, clampPeriod, span, isISO).
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
