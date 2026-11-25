// tests/leaflet.test.mjs — pins that no page hands Leaflet a string as tooltip or popup content.
// Leaflet writes string content through innerHTML (DivOverlay._updateContent), so the "you are here" dot of
// the shelter map ran markup as the name of an OpenStreetMap object (security audit #146), and the start of a
// missile's route ran markup as the launch area of events/incursions.json through a dictionary text (RCB.t
// fills {param} with the page's data without escaping it; security audit #173). Content is an element of h()
// (its text goes through textContent), a function that returns one, or a helper of the same file that does —
// never a string: not a name, not a value built at runtime, not a dictionary text.
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

// The first argument of the call whose "(" is at `open - 1`: up to the comma or the ")" at depth 0, with
// strings and brackets stepped over.
function firstArg(src, open) {
  let depth = 0, quote = null;
  for (let i = open; i < src.length; i++) {
    const c = src[i];
    if (quote) {
      if (c === "\\") i++;
      else if (c === quote) quote = null;
    } else if (c === '"' || c === "'" || c === "`") quote = c;
    else if ("([{".includes(c)) depth++;
    else if (c === ")" && depth === 0) return src.slice(open, i).trim();
    else if (")]}".includes(c)) depth--;
    else if (c === "," && depth === 0) return src.slice(open, i).trim();
  }
  return "";
}

// the forms content may take, and what each one is. A dictionary text is a string too: RCB.t, RCB.tn and tr
// fill {param} from the page's data without escaping it, so it goes in with h("span", { text }).
const FORMS = [
  [/^h\(/, "an element of h()"],
  [/^(?:\([^()]*\)|[\w$]+)\s*=>/, "a function"],
  [/^function\b/, "a function"],
];
// a name the file itself defines as a function: its result is what that function built
const isFunctionOf = (src, name) => RegExp(`^(?:async\\s+)?function\\s+${name}\\s*\\(`, "m").test(src)
  || RegExp(`^\\s*(?:const|let|var)\\s+${name}\\s*=\\s*(?:async\\s*)?(?:\\([^)]*\\)|[\\w$]+)\\s*=>`, "m").test(src);

// what makes `arg` safe as content in `src`, or null when it is a string of data
function kind(arg, src) {
  for (const [re, what] of FORMS) if (re.test(arg)) return what;
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
  assert.equal(kind('RCB.tn(n, "shel.places", { n })', src), null, "a dictionary text with a value of the page in it");
  assert.equal(kind('tr(w.launch.certain ? "map.raid.start" : "map.raid.startApprox", { area: w.launch.area_pl })', src),
    null, "a dictionary text with the launch area of incursions.json in it (security audit #173)");
  // the argument ends at the comma outside its own strings and brackets
  const call = 'bindTooltip(h("span", { text: a || T("x, y") }), { direction: "top" })';
  assert.equal(firstArg(call, call.indexOf("(") + 1), 'h("span", { text: a || T("x, y") })');
  assert.equal(firstArg("bindPopup('a', 'b')", 10), "'a'");
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
    assert.ok(what, `${s.at}: ${s.call}(${s.arg.slice(0, 40)}…) takes ${what || "a string"}: build it with h(), or with a function that returns one`);
  }
});
