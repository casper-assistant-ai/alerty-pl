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

test("on a phone the header's source link is a tap target of at least 24 px, and stays hidden on a narrow screen", () => {
  // .top .src is one line of 13 px text, 20 px tall. Up to 640 px wide it is hidden; on a phone held
  // sideways (844x390) it shows, and the mobile audit listed it at 172x20 on every page (#140).
  const phone = mediaBlock(PHONE);
  const rule = phone.match(/\.top \.src \{[^}]*\}/);
  assert.ok(rule, "no .top .src rule in the phone block");
  const min = rule[0].match(/min-height:\s*([\d.]+)px/);
  assert.ok(min, "the phone rule gives .top .src a min-height");
  assert.ok(Number(min[1]) >= 24, `min-height ${min[1]}px is under the 24 px of a tap target`);
  // the rule that hides the link up to 640 px has the same specificity and comes earlier: a display
  // here would bring it back on a narrow phone, where it does not fit next to the logo
  assert.doesNotMatch(rule[0], /display/, "the phone rule for .top .src must not set display");
});
