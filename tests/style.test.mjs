// Node test for the mobile rules of docs/style.css — no npm, just node:test and node:assert.
// The mobile audit (issues #35–#41) found these four defects on phone screens; the test keeps
// them fixed while the sheet is refactored. CI runs it through tests/test_style_css.py.
// Alone: node --test tests/style.test.mjs
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const css = readFileSync(new URL("../docs/style.css", import.meta.url), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

// A small reader for this sheet: rules inside any number of @media blocks (rules may nest
// their own @media, like .blink). Returns { media, selectors, decls } for every plain rule.
function parseRules(text, media = "") {
  const rules = [];
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf("{", i);
    if (open < 0) break;
    const head = text.slice(i, open).trim();
    let depth = 1, close = open + 1;
    while (close < text.length && depth) {
      if (text[close] === "{") depth++;
      else if (text[close] === "}") depth--;
      close++;
    }
    const body = text.slice(open + 1, close - 1);
    if (head.startsWith("@media")) rules.push(...parseRules(body, head.slice(6).trim()));
    else if (!head.startsWith("@")) {
      const direct = body.replace(/\{[^{}]*\{[^{}]*\}[^{}]*\}/g, " ").replace(/\{[^{}]*\}/g, " ");
      const decls = new Map(direct.split(";").map((s) => s.trim()).filter((s) => s.includes(":"))
        .map((s) => [s.slice(0, s.indexOf(":")).trim(), s.slice(s.indexOf(":") + 1).trim()]));
      rules.push({ media, selectors: head.split(",").map((s) => s.trim()), decls });
    }
    i = close;
  }
  return rules;
}

const rules = parseRules(css);
const px = (v) => {
  const m = /^([\d.]+)(px|rem|em)?$/.exec(v || "");
  return m ? parseFloat(m[1]) * (m[2] ? 16 : 1) : NaN; // rem and em of this sheet are 16px body units
};
const where = (pred, what) => {
  const hit = rules.find(pred);
  assert.ok(hit, what + " — no such rule in docs/style.css");
  return hit;
};

test("form fields are at least 16px on touch screens (iOS zooms into anything smaller)", () => {
  const r = where((x) => /pointer:\s*coarse/.test(x.media) && x.selectors.includes("select")
    && x.selectors.includes('input[type="search"]'), "a pointer:coarse rule for select and input[type=search]");
  assert.ok(px(r.decls.get("font-size")) >= 16, `font-size ${r.decls.get("font-size")} is under 16px`);
});

test("the header wraps its tabs up to the width its one row needs (~797px), so nothing scrolls sideways", () => {
  const r = where((x) => x.selectors.includes("nav.tabs") && x.decls.get("flex") === "1 1 100%",
    "a media block that puts nav.tabs on its own row");
  const max = px((/max-width:\s*([\d.]+px)/.exec(r.media) || [])[1]);
  assert.ok(max >= 797, `the wrap applies only up to ${r.media || "?"} — a landscape phone still overflows`);
  const top = rules.find((x) => x.media === r.media && x.selectors.includes(".top"));
  assert.ok(top && top.decls.get("flex-wrap") === "wrap", ".top does not wrap its contents in that block");
});

test("the komunikat link of a history row is a tap target at least 24px tall", () => {
  const hs = rules.filter((x) => x.selectors.includes(".hist .src") && x.decls.has("min-height"));
  assert.ok(hs.length, "no .hist .src rule sets min-height");
  assert.ok(Math.max(...hs.map((x) => px(x.decls.get("min-height")))) >= 24, "min-height is under 24px");
});

test("the x of the powiat chip is a tap target at least 24px wide and tall", () => {
  const r = where((x) => x.selectors.includes(".chip button"), "the .chip button rule");
  assert.ok(px(r.decls.get("min-height")) >= 24 && px(r.decls.get("min-width")) >= 24,
    `min-height ${r.decls.get("min-height")}, min-width ${r.decls.get("min-width")} — one is under 24px`);
});

test("the source link in the header is a tap target at least 24px tall", () => {
  const r = where((x) => x.selectors.includes(".top .src"), "the .top .src rule");
  assert.ok(px(r.decls.get("min-height")) >= 24, `min-height ${r.decls.get("min-height")} is under 24px`);
});
