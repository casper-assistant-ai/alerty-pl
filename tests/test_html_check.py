"""scripts/html_check.py: the site's pages carry no broken markup a visitor would see."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import html_check

CSP = ('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; '
       'style-src \'self\' \'unsafe-inline\'; img-src \'self\' data: https://example.invalid; '
       'connect-src \'self\' https://example.invalid">')
CSP_EMPTY = '<meta http-equiv="Content-Security-Policy" content="">'
GOOD = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
{CSP}
<meta name="viewport" content="width=device-width"><title>T</title>
<meta name="description" content="Opis strony, także jako powiadomienia."></head>
<body><header class="top"><a href="./">A</a></header><main><p>x<p>y<ul><li>a<li>b</ul></main></body></html>"""

# every host a script of docs/ loads an image from or talks to, and what for. The Content-Security-Policy of
# every page must allow each of them (test_csp_covers_the_hosts_of_the_scripts): a missing host is a request
# the browser refuses on the live site.
HOSTS = {
    "alerty-pl-cao.polandcentral.cloudapp.azure.com": "the live service: fetch() and EventSource (common.js)",
    "gibs.earthdata.nasa.gov": "NASA GIBS tiles (app.js)",
    "nominatim.openstreetmap.org": "the address search (geosearch.js, shelters.js)",
    "planetarycomputer.microsoft.com": "Microsoft Planetary Computer: the Sentinel-2 search, mosaics and tiles (sentinel.js)",
    "s3-us-west-2.amazonaws.com": "Esri's Wayback config (wayback.js)",
    "services.arcgisonline.com": "Esri's grey canvas tiles (app.js, shelters.js)",
    "wayback.maptiles.arcgis.com": "Wayback tiles, tilemap and metadata service (wayback.js)",
}

# a URL that is only a link: an attribution anchor (href="…") or a navigation link (href: `…`) in the scripts
LINK = re.compile(r"""href[=:]\s*["'`]$""")
# links and a namespace too far from their `href:` for LINK to see: the OSM links of the ternary in shelters.js,
# the SVG namespace of analytics.js
LINK_ONLY = {"www.openstreetmap.org", "www.w3.org"}
# a whole line of comment is prose: the home page of Nominatim is named in one (geosearch.js)
COMMENT_LINE = re.compile(r"^[ \t]*//.*$", re.M)


def hosts_in(text: str) -> set[str]:
    """The hosts of the absolute URLs of a script that are neither only a link nor a line of comment."""
    code = COMMENT_LINE.sub("", text)
    hosts = set()
    for m in re.finditer(r"https?://([A-Za-z0-9.-]+)", code):
        if m.group(1) not in LINK_ONLY and not LINK.search(code[max(0, m.start() - 8):m.start()]):
            hosts.add(m.group(1))
    return hosts


def resource_hosts() -> set[str]:
    """The hosts every script of docs/ (not the vendored Leaflet) loads an image from or talks to."""
    hosts = set()
    for f in sorted((ROOT / "docs").glob("*.js")):
        hosts |= hosts_in(f.read_text(encoding="utf-8"))
    return hosts


def local_api() -> str:
    """The address the README gives for a local run of the live service: common.js reads it from
    localStorage "alerty-api" in place of the live host, so connect-src of every page has to allow it."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    found = re.search(r'localStorage\.setItem\("alerty-api", "([^"]+)"\)', readme)
    if not found:
        raise ValueError('README.md no longer sets localStorage "alerty-api"')
    return found.group(1)


class HtmlCheck(unittest.TestCase):
    def test_site_pages_are_clean(self):
        pages = sorted((ROOT / "docs").glob("*.html"))
        self.assertTrue(pages)
        for page in pages:
            with self.subTest(page=page.name):
                self.assertEqual(html_check.check(page.read_text(encoding="utf-8")), [])

    def test_broken_meta_of_0423ed9_is_caught(self):
        text = (ROOT / "tests/fixtures/page-broken-meta.html").read_text(encoding="utf-8")
        msgs = " | ".join(m for _, m in html_check.check(text))
        self.assertIn("broken attribute", msgs)
        self.assertIn("holds markup", msgs)
        self.assertIn("text in <head>", msgs)

    def test_good_page_passes(self):
        self.assertEqual(html_check.check(GOOD), [])

    def test_other_defects(self):
        no_csp = 'no <meta http-equiv="Content-Security-Policy"> in <head>'
        cases = [
            ("duplicate id", GOOD.replace('<main>', '<main id="a"><div id="a"></div>')),
            ("is closed by", GOOD.replace('<main>', '<main><div><span></div>')),
            ("closes nothing", GOOD.replace('</main>', '</main></div>')),
            ("has no lang", GOOD.replace(' lang="pl"', '')),
            ("no <title>", GOOD.replace('<title>T</title>', '')),
            ('no <meta name="description">', GOOD.replace('name="description"', 'name="x"')),
            (no_csp, GOOD.replace(CSP + "\n", "")),
            (no_csp, GOOD.replace(CSP + "\n", "").replace("</head>", "</head>" + CSP)),
            (no_csp, GOOD.replace(CSP, CSP_EMPTY)),
            # what script-src 'self' forbids: the browser skips it with a line in its own log, and the control is dead
            ("inline handler", GOOD.replace('<main>', '<main onload="alert(1)">')),
            ("<script> without src", GOOD.replace("</body>", "<script>alert(1)</script></body>")),
            ("javascript:", GOOD.replace('<a href="./">', '<a href="javascript:void(0)">')),
            ("javascript:", GOOD.replace('<a href="./">', '<a href="  JaVa\nscript:void(0)">')),
        ]
        for want, page in cases:
            with self.subTest(want=want):
                self.assertIn(want, " | ".join(m for _, m in html_check.check(page)))

    def test_hosts_in_skips_links_and_comments(self):
        js = ('// the home page, https://prose.example, is named here\n'
              'const NS = "http://www.w3.org/2000/svg";\n'
              'const attr = \'<a href="https://link.example/notice">Notice</a>\';\n'
              'const nav = { href: `https://nav.example/?a=1` };\n'
              'const osm = walk ? `https://www.openstreetmap.org/directions` : "";\n'
              'const api = "https://api.example/v1";\n')
        self.assertEqual(hosts_in(js), {"api.example"})

    def test_csp_covers_the_hosts_of_the_scripts(self):
        # a host the scripts talk to that is not in HOSTS was never looked at: read it, then add it above
        # and to the policy of every page (a branch may lack a script main has, so HOSTS can know more hosts)
        self.assertEqual(resource_hosts() - set(HOSTS), set())
        # the README's address is read, not copied, and may only be a loopback address: the README cannot widen the policy
        local = local_api()
        self.assertRegex(local, r"^http://127\.0\.0\.1:\d+$")
        pages = sorted((ROOT / "docs").glob("*.html"))
        self.assertTrue(pages)
        for page in pages:
            with self.subTest(page=page.name):
                p = html_check.policy(page.read_text(encoding="utf-8"))
                self.assertEqual(p.get("default-src"), {"'self'"})
                self.assertEqual(p.get("script-src"), {"'self'"})  # no inline script and no eval
                allowed = p.get("img-src", set()) | p.get("connect-src", set())
                self.assertIn("'self'", allowed)  # the data files of GitHub Pages
                self.assertIn("data:", p.get("img-src", set()))  # the favicon of every page
                self.assertEqual({h for h in HOSTS if f"https://{h}" not in allowed}, set())
                self.assertIn(local, p.get("connect-src", set()))  # the README's local run of the live service
        # the policy is split into directives and sources as the browser splits it
        self.assertEqual(html_check.policy(GOOD)["connect-src"], {"'self'", "https://example.invalid"})


if __name__ == "__main__":
    unittest.main()
