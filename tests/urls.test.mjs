// tests/urls.test.mjs — pins that no page follows a URL from the live service, or writes one into a link,
// without checking that it is https (security audit #146, hardening).
// docs/notify.js goes to the link the service names for Telegram (w.location = url): a script or a data URL
// there would run in the site's origin. docs/common.js h() builds every link of every page: a href or a src
// the browser would run as code is never written. Run by tests/test_urls_js.py inside the Python suite,
// and by `node --test tests/*.test.mjs`.
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const DOCS = new URL("../docs/", import.meta.url);
const read = (f) => readFileSync(new URL(f, DOCS), "utf8");
// the pages' own scripts (docs/vendor/ is not theirs)
const SOURCES = Object.fromEntries(readdirSync(DOCS).filter((f) => f.endsWith(".js")).sort()
  .map((f) => [f, read(f)]));

// the navigation sinks of the pages: a URL handed to the browser to open (an assignment to location,
// or location.replace(…)). The form's end is at the end of the match.
const SINK = /\b(?:[\w$.]*location(?:\.href)?\s*=\s*|location\.replace\s*\()/g;

// The navigation of docs/notify.js: the line that opens the service's link, and the lines above it in the
// same function. Each sink must have, within the five lines before it, the https check of new URL(...).
function guarded(src, at) {
  const lines = src.slice(0, at).split("\n");
  const before = lines.slice(Math.max(0, lines.length - 5)).join("\n");
  return /new URL\([^)]*\)\.protocol\s*!==?\s*"https:"/.test(before);
}

test("the pin knows a guarded navigation from an unguarded one", () => {
  const ok = 'const { url } = await post("/telegram/link", {});\n' +
    '  if (new URL(url).protocol !== "https:") throw new Error("not https");\n' +
    '  if (w) w.location = url; else location.href = url;\n';
  for (const m of ok.matchAll(SINK)) assert.ok(guarded(ok, m.index + m[0].length), m[0]);
  const bad = 'const { url } = await post("/telegram/link", {});\n  location.href = url;\n';
  for (const m of bad.matchAll(SINK)) assert.equal(guarded(bad, m.index + m[0].length), false, m[0]);
});

test("every navigation of every page to a URL checks that it is https", () => {
  const sinks = [];
  for (const [f, src] of Object.entries(SOURCES)) {
    for (const m of src.matchAll(SINK)) sinks.push({ f, line: src.slice(0, m.index).split("\n").length, m, src });
  }
  assert.ok(sinks.length >= 2, `${sinks.length} navigations found: the pages changed, check the sink list`);
  // common.js moves plain-http visitors to https with a link it builds itself (location.replace): nothing to check
  const checked = sinks.filter((s) => !s.m[0].includes("replace"));
  assert.ok(checked.length >= 1, "notify.js follows the service's link: the sink list lost it");
  for (const s of checked) {
    assert.ok(guarded(s.src, s.m.index + s.m[0].length),
      `${s.f}:${s.line}: ${s.m[0]} opens a URL without new URL(…).protocol === "https:" right before it`);
  }
});

test("h() refuses the schemes a browser runs as code, for href and for src", () => {
  const common = SOURCES["common.js"];
  const guard = /if \(\(k === "href" \|\| k === "src"\) && UNSAFE_URL\.test\(v\)\) continue;/.test(common);
  assert.ok(guard, 'common.js h(): the href and src check is gone');
  assert.match(common, /const UNSAFE_URL = \/\^\\s\*\(javascript\|data\|vbscript\):\/i;/);
});
