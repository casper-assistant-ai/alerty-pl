// tests/style.test.mjs — pins the phone rules of docs/style.css that the mobile audit found
// missing (run by tests/test_style_css.py inside the Python suite, like common.test.mjs).
import { readFileSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const css = readFileSync(new URL("../docs/style.css", import.meta.url), "utf8");
const PHONE = "@media (max-width: 640px), (max-height: 500px), (pointer: coarse)";

// the body of a media query, with braces matched (the sheet has no nested queries in it)
function mediaBlock(query) {
  const open = css.indexOf(query);
  assert.notEqual(open, -1, `missing media query "${query}"`);
  const start = css.indexOf("{", open);
  let depth = 0;
  for (let i = start; i < css.length; i++) {
    if (css[i] === "{") depth++;
    else if (css[i] === "}") { depth--; if (!depth) return css.slice(start + 1, i); }
  }
  assert.fail(`unbalanced media query "${query}"`);
}

test("the month heading sticks on desktop", () => {
  const at = css.indexOf(".month h2 {");
  assert.notEqual(at, -1, "no .month h2 rule in the sheet");
  assert.match(css.slice(at), /position:\s*sticky/, "desktop keeps the sticky month heading");
});

test("on a phone the month heading is static, so it cannot cover a row's link", () => {
  // .month h2 { position: sticky; top: 0 } rides over the topmost rows of its month while it
  // is stuck, and a tap on the covered "komunikat" link hits the heading instead (mobile audit,
  // historia.html): on touch screens the heading scrolls away with its rows.
  const phone = mediaBlock(PHONE);
  const rule = phone.match(/\.month h2 \{[^}]*\}/);
  assert.ok(rule, `no .month h2 rule in the phone block`);
  assert.match(rule[0], /position:\s*static/);
  // same specificity as the base rule, so the phone rule must come later to win the cascade
  assert.ok(css.indexOf(rule[0]) > css.indexOf(".month h2 {"), "the phone rule must follow the base rule");
});
