// tests/mobile_audit.test.mjs — the mobile audit's scan runs in the browser as a template literal, so it is
// read from the script like the site check's. #271, 28.11 14:22 UTC: one view of the audit came without
// style.css (GitHub Pages failed that one request; the audit fetches every file anew), and the report
// listed 44 tap-target lines of the browser's default sizes with no address. The scan now names the missing
// sheet, and run() names a stylesheet or a script that got a 4xx/5xx or failed to load.
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const src = readFileSync(new URL("../scripts/mobile_audit.mjs", import.meta.url), "utf8");
const raw = src.match(/const SCAN = `((?:[^`\\]|\\.)*)`/)[1];
// the string the browser receives: the template literal evaluated
const inPage = new Function("return (`" + raw + "`)")();

// one scan against a stub page at 360x740: the stylesheet links, and nothing else to measure
const scan = (links) => {
  globalThis.innerWidth = 360; globalThis.innerHeight = 740;
  globalThis.NodeFilter = { SHOW_TEXT: 4 };
  globalThis.document = {
    documentElement: { scrollWidth: 360 },
    body: { querySelectorAll: () => [] },
    querySelector: () => null,
    querySelectorAll: (s) => (s === 'link[rel="stylesheet"]' ? links : []),
    createTreeWalker: () => ({ nextNode: () => null }),
  };
  return new Function("return (" + inPage + ")")();
};

test("a view whose stylesheet never came is one line naming the sheet, not the browser's default sizes", () => {
  // .skip has min-height 40px and .presets button 30px in the base rules of style.css: at 17 and 21 px no
  // rule of the sheet applied, and the 44 tap-target lines said nothing about the cause
  const lines = scan([{ sheet: null, getAttribute: () => "style.css" }]);
  assert.equal(lines.length, 1);
  assert.match(lines[0], /^stylesheet not applied: style\.css \(its request failed or did not finish/);
});

test("a view with its stylesheet, or a page without one, is measured as before", () => {
  assert.deepEqual(scan([{ sheet: {}, getAttribute: () => "style.css" }]), []);
  assert.deepEqual(scan([]), []);
});

test("run() names a stylesheet or a script that got a 4xx/5xx or failed to load, and lets an abort pass", () => {
  const run = src.slice(src.indexOf("async function run("), src.indexOf("const ev = "));
  assert.match(run, /Network\.requestWillBeSent" && PAGE_FILE\.test\(m\.params\.type\)\) files\.set\(m\.params\.requestId/);
  assert.match(run, /Network\.responseReceived" && PAGE_FILE\.test\(m\.params\.type\) && m\.params\.response\.status >= 400\)\s*problems\.push\(\{ kind: "http"/);
  assert.match(run, /Network\.loadingFailed" && files\.has\(m\.params\.requestId\) && !GIVEN_UP\.test\(m\.params\.errorText\) && !m\.params\.canceled\)\s*problems\.push\(\{ kind: "network"/);
  // only the page's stylesheets and scripts: tiles, fonts and data are the site check's to judge;
  // an abort is the page giving up on purpose (the live service), as in the site check
  assert.match(src, /const PAGE_FILE = \/\^\(Stylesheet\|Script\)\$\/;/);
  assert.match(src, /const GIVEN_UP = \/ERR_ABORTED\|ERR_BLOCKED_BY_CLIENT\/;/);
});
