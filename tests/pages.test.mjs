// Node test for the head of every page in docs/ — no npm, just node:test and node:assert.
// CI runs it through tests/test_pages.py (the Python suite); alone: node --test tests/pages.test.mjs
import { readFileSync } from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";

const PAGES = ["index.html", "historia.html", "analityka.html", "powiadomienia.html", "zmiany.html"];

test("every page declares its favicon before any other link", () => {
  // Chrome asks the page for favicon candidates very early in the load — before the
  // parser reliably reaches a <link> that sits behind stylesheets or a preload. When
  // no candidate is visible yet, it falls back to the origin-root /favicon.ico, which
  // a GitHub Pages project site cannot serve and which 404s (site check issue #30:
  // https://casper-assistant-ai.github.io/favicon.ico). The icon link therefore has
  // to be the first <link> in the document, right after <meta charset>.
  for (const page of PAGES) {
    const html = readFileSync(new URL("../docs/" + page, import.meta.url), "utf8");
    const head = html.slice(0, html.indexOf("</head>"));
    const links = [...head.matchAll(/<link\s[^>]*>/g)].map((m) => m[0]);
    assert.ok(links.length > 0, `${page}: no <link> elements found in head`);
    assert.equal(links[0].includes('rel="icon"'), true,
      `${page}: the first <link> must be the favicon, found: ${links[0]}`);
    assert.equal(links.filter((l) => l.includes('rel="icon"')).length, 1,
      `${page}: exactly one favicon link expected`);
  }
});

test("the favicon is inline, so no request is needed before it can be used", () => {
  for (const page of PAGES) {
    const html = readFileSync(new URL("../docs/" + page, import.meta.url), "utf8");
    const icon = html.match(/<link rel="icon" href="([^"]*)"/);
    assert.ok(icon, `${page}: missing favicon link`);
    assert.ok(icon[1].startsWith("data:"), `${page}: favicon should be a data URI`);
  }
});
