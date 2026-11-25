// tests/leaflet.test.mjs — pins that no page hands Leaflet a string of data as tooltip or popup content.
// Leaflet writes string content through innerHTML (DivOverlay._updateContent), so the "you are here" dot of
// the shelter map ran markup as the name of an OpenStreetMap object (security audit #146). Content is an
// element of h() (its text goes through textContent), a function that returns one, a helper of the same file
// that does, or a text of the interface dictionaries — never a string built from data. A dictionary text
// with a value put in is such a string: t() replaces {area} with the value as it is (common.js), so the
// launch area of events/incursions.json ran as markup in the tooltip of a raid's start (security audit #173).
// Run by tests/test_leaflet_js.py inside the Python suite, and by `node --test tests/*.test.mjs`.
import { readFileSync, readdirSync } from "node:fs";
import { test } from "node:test";
import assert from "node:assert/strict";

const DOCS = new URL("../docs/", import.meta.url);
// the pages' own scripts (docs/vendor/ is not theirs)
const SOURCES = Object.fromEntries(readdirSync(DOCS).filter((f) => f.endsWith(".js")).sort()
  .map((f) => [f, readFileSync(new URL(f, DOCS), "utf8")]));
// Leaflet's content sinks: the content is the first argument of each
const SINK = /\.(bindTooltip|bindPopup|setTooltipContent|setPopupContent|setContent)\(/g;

// The arguments of the call whose first argument starts at `open`: each up to the comma or the ")" at
// depth 0, with strings and brackets stepped over.
function callArgs(src, open) {
  const args = [];
  let depth = 0, quote = null, start = open;
  for (let i = open; i < src.length; i++) {
    const c = src[i];
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
    } else if (c === '"' || c === "'" || c === "`") quote = c;
    else if ("([{".includes(c)) depth++;
    else if (c === ")" && depth === 0) {
      if (src.slice(start, i).trim()) args.push(src.slice(start, i).trim());
      return args;
    } else if (")]}".includes(c)) depth--;
    else if (c === "," && depth === 0) {
      args.push(src.slice(start, i).trim());
      start = i + 1;
    }
  }
  return args;
}
const firstArg = (src, open) => callArgs(src, open)[0] || "";

// the forms content may take, and what each one is
const TEXT = /^(?:RCB\.t|tr|T)\(/;
const FORMS = [
  [/^h\(/, "an element of h()"],
  [/^(?:\([^()]*\)|[\w$]+)\s*=>/, "a function"],
  [/^function\b/, "a function"],
  [/^RCB\.tn\(/, "a count in words of the interface dictionaries"],
  [TEXT, "a text of the interface dictionaries"],
];
// a name the file itself defines as a function: its result is what that function built
const isFunctionOf = (src, name) => RegExp(`^(?:async\\s+)?function\\s+${name}\\s*\\(`, "m").test(src)
  || RegExp(`^\\s*(?:const|let|var)\\s+${name}\\s*=\\s*(?:async\\s*)?(?:\\([^)]*\\)|[\\w$]+)\\s*=>`, "m").test(src);

// what makes `arg` safe as content in `src`, or null when it is a string of data
function kind(arg, src) {
  for (const [re, what] of FORMS) {
    if (!re.test(arg)) continue;
    // a text of the dictionaries is content only while nothing is put into it: tr("key") is the
    // dictionary's own text, tr("key", { area: data }) is a string of data. A count is a number.
    if (re === TEXT && callArgs(arg, arg.indexOf("(") + 1).length > 1) return null;
    return what;
  }
  const name = /^([\w$]+)/.exec(arg);
  if (name && isFunctionOf(src, name[1])) return "a function of the file";
  return null;
}

test("the pin refuses the forms of the audit and admits the forms the pages use", () => {
  const src = 'function tooltip(layer) {\n  return h("div");\n}\n';
  assert.equal(kind('label || T("shel.me")', src), null, "a name of OpenStreetMap as a string");
  assert.equal(kind('"×" + f.label', src), null, "a string built at runtime");
  assert.equal(kind("", src), null, "no content");
  assert.equal(kind('h("span", { text: label })', src), "an element of h()");
  assert.equal(kind("() => tipFor(p, ev)", src), "a function");
  assert.equal(kind("tooltip", src), "a function of the file");
  assert.equal(kind('RCB.tn(n, "shel.places", { n: n.toLocaleString(RCB.loc()) })', src), "a count in words of the interface dictionaries");
  // a dictionary text is content only while nothing is put into it (#173)
  assert.equal(kind('T("shel.me")', src), "a text of the interface dictionaries");
  assert.equal(kind('tr(w.launch.certain ? "map.raid.start" : "map.raid.startApprox", { area: w.launch.area_pl })', src), null,
    "a text with a value of the data put in");
  // the argument ends at the comma outside its own strings and brackets
  const call = 'bindTooltip(h("span", { text: a || T("x, y") }), { direction: "top" })';
  assert.equal(firstArg(call, call.indexOf("(") + 1), 'h("span", { text: a || T("x, y") })');
  assert.equal(firstArg("bindPopup('a', 'b')", 10), "'a'");
  assert.deepEqual(callArgs("tr('a', { b: c }, d)", 3), ["'a'", "{ b: c }", "d"]);
});

test("every Leaflet tooltip and popup of every page is built, never a string of data", () => {
  const sites = [];
  for (const [f, src] of Object.entries(SOURCES)) {
    for (const m of src.matchAll(SINK)) {
      sites.push({ at: `${f}:${src.slice(0, m.index).split("\n").length}`, call: m[1], arg: firstArg(src, m.index + m[0].length) });
    }
  }
  assert.ok(sites.length >= 8, `${sites.length} content calls found: the pages changed, check the sink list`);
  for (const s of sites) {
    const what = kind(s.arg, SOURCES[s.at.split(":")[0]]);
    assert.ok(what, `${s.at}: ${s.call}(${s.arg.slice(0, 40)}…) takes ${what || "a string of data"}: build it with h(), a function or a dictionary text`);
  }
});
