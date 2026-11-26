#!/usr/bin/env python3
"""Static check of the site's HTML pages (docs/*.html); plain Python, no npm.

It catches markup that a browser repairs silently but that shows to a visitor: a quote inside an
attribute value that ends it early (22.11.2026: a link inside <meta name="description"> printed
'powiadomienia.">' at the top of every page), stray text in <head>, tags that close the wrong
element or stay open, duplicate ids, and a page without lang, title, description, viewport or a
Content-Security-Policy in <head>.

It also refuses what that policy (script-src 'self') forbids and the browser passes over without an
error of the page's own, so that a control is merely dead on the live page: an inline event handler
attribute, a <script> without src and a javascript: URL.

    python3 -I scripts/html_check.py [FILE ...]   (default: docs/*.html)

Prints one line per problem, FILE:LINE: message; exit code 1 when there is any.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
# elements whose end tag may be left out; the browser closes them, so they are not tracked
OPTIONAL_END = {"p", "li", "dt", "dd", "option", "optgroup", "tr", "td", "th", "thead", "tbody", "tfoot", "rt", "rp",
                "colgroup", "caption", "html", "head", "body"}
RAW_TEXT = {"script", "style", "title", "textarea", "template"}
ATTR_NAME = re.compile(r"^[a-z_:][a-z0-9_.:\-]*$")
# an inline event handler (onclick, onsubmit, ...): script-src 'self' refuses it, and the browser says so only in
# its own log, so the control is simply dead on the page
INLINE_HANDLER = re.compile(r"^on[a-z]+$")
# the attributes whose value is a URL that a click or a submit follows or the page loads
URL_ATTR = {"href", "src", "action", "formaction", "xlink:href", "poster", "data", "background", "cite", "longdesc",
            "ping"}


class Checker(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.problems: list[tuple[int, str]] = []
        self.stack: list[tuple[str, int]] = []
        self.ids: dict[str, int] = {}
        self.in_head = False
        self.head_seen = False
        self.raw: str | None = None
        self.has = {"lang": False, "title": False, "description": False, "viewport": False}
        self.csp: str | None = None

    def bad(self, msg: str) -> None:
        self.problems.append((self.getpos()[0], msg))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attrs_of(tag, attrs)
        if tag == "head":
            self.in_head, self.head_seen = True, True
        elif tag == "body":
            self.in_head = False
        if tag in RAW_TEXT:
            self.raw = tag
        if tag not in VOID and tag not in OPTIONAL_END:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.attrs_of(tag, attrs)

    def attrs_of(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {}
        for name, value in attrs:
            if not ATTR_NAME.match(name):
                self.bad(f"<{tag}> has a broken attribute {name!r}: a quote inside an attribute value ended it early")
            if value and ("<" in value or ">" in value) and name not in ("d", "points", "viewbox"):
                self.bad(f"<{tag} {name}=…> holds markup ({value[:60]!r}…); attributes take plain text")
            if INLINE_HANDLER.match(name):
                self.bad(f"<{tag}> has an inline handler {name}=…: the page's Content-Security-Policy refuses it, "
                         "use addEventListener in the page's script")
            if name in URL_ATTR and value and re.sub(r"[\s\x00-\x20]", "", value).lower().startswith("javascript:"):
                self.bad(f'<{tag} {name}="javascript:…">: the page\'s Content-Security-Policy refuses a javascript: URL, '
                         "use a listener in the page's script")
            a[name] = value
        if tag == "script" and not (a.get("src") or "").strip():
            self.bad("<script> without src: the page's Content-Security-Policy refuses an inline script")
        if "id" in a and a["id"]:
            if a["id"] in self.ids:
                self.bad(f"duplicate id {a['id']!r} (first on line {self.ids[a['id']]})")
            else:
                self.ids[a["id"]] = self.getpos()[0]
        if tag == "html" and a.get("lang"):
            self.has["lang"] = True
        if tag == "meta" and a.get("name") == "description" and (a.get("content") or "").strip():
            self.has["description"] = True
        if tag == "meta" and a.get("name") == "viewport":
            self.has["viewport"] = True
        # only one in <head> counts: everything above a policy further down the page loads unchecked
        if (tag == "meta" and self.in_head and (a.get("http-equiv") or "").lower() == "content-security-policy"
                and (a.get("content") or "").strip()):
            self.csp = self.csp or a["content"]

    def handle_endtag(self, tag: str) -> None:
        if self.raw == tag:
            self.raw = None
        if tag == "head":
            self.in_head = False
        if tag in VOID or tag in OPTIONAL_END:
            return
        if not any(t == tag for t, _ in self.stack):
            self.bad(f"</{tag}> closes nothing")
            return
        while self.stack:
            t, line = self.stack.pop()
            if t == tag:
                break
            self.bad(f"<{t}> from line {line} is closed by </{tag}>")

    def handle_data(self, data: str) -> None:
        if self.raw == "title" and data.strip():
            self.has["title"] = True
        if self.in_head and self.raw is None and data.strip():
            self.bad(f"text in <head> shows at the top of the page: {data.strip()[:60]!r}")

    def close(self) -> None:
        super().close()
        for t, line in self.stack:
            self.bad(f"<{t}> from line {line} is never closed")
        for k, msg in (("lang", "<html> has no lang"), ("title", "no <title>"),
                       ("description", 'no <meta name="description">'), ("viewport", 'no <meta name="viewport">')):
            if not self.has[k]:
                self.problems.append((1, msg))
        if self.csp is None:
            self.problems.append((1, 'no <meta http-equiv="Content-Security-Policy"> in <head>'))


def check(text: str) -> list[tuple[int, str]]:
    c = Checker()
    c.feed(text)
    c.close()
    return sorted(c.problems)


def policy(text: str) -> dict[str, set[str]]:
    """The sources of each directive of the page's Content-Security-Policy, split as a browser splits them."""
    c = Checker()
    c.feed(text)
    c.close()
    out: dict[str, set[str]] = {}
    for directive in (c.csp or "").split(";"):
        words = directive.split()
        if words:
            out[words[0]] = set(words[1:])
    return out


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted(Path(__file__).resolve().parent.parent.joinpath("docs").glob("*.html"))
    n = 0
    for f in files:
        for line, msg in check(f.read_text(encoding="utf-8")):
            print(f"{f}:{line}: {msg}")
            n += 1
    print(f"{len(files)} pages, {n} problems" if n else f"{len(files)} pages, no problems")
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
