"""scripts/html_check.py: the site's pages carry no broken markup a visitor would see."""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import html_check  # noqa: E402

CSP = ('<meta http-equiv="Content-Security-Policy" content="default-src \'self\'; script-src \'self\'; '
       'style-src \'self\' \'unsafe-inline\'; img-src \'self\' data: https://example.invalid; '
       'connect-src \'self\' https://example.invalid">')
GOOD = f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
{CSP}
<meta name="viewport" content="width=device-width"><title>T</title>
<meta name="description" content="Opis strony, także jako powiadomienia."></head>
<body><header class="top"><a href="./">A</a></header><main><p>x<p>y<ul><li>a<li>b</ul></main></body></html>"""

# every host docs/*.js (not the vendored Leaflet) fetches from or loads an image from
HOSTS = {
    "alerty-pl-cao.polandcentral.cloudapp.azure.com": "the live service: fetch() and EventSource (common.js, notify.js)",
    "gibs.earthdata.nasa.gov": "NASA GIBS tiles (app.js)",
    "nominatim.openstreetmap.org": "the address search (shelters.js)",
    "s3-us-west-2.amazonaws.com": "Esri's Wayback config (wayback.js)",
    "services.arcgisonline.com": "Esri's grey canvas tiles (app.js, shelters.js)",
    "wayback.maptiles.arcgis.com": "Wayback tiles, tilemap and metadata service (wayback.js)",
}
# a URL that is only a link: an attribution anchor (href="…") or a navigation link (href: `…`) in the scripts
LINK = re.compile(r"""href[=:]\s*["'`]$""")
# links and a namespace too far from their `href:` for LINK to see (the osm ternary of shelters.js, the SVG namespace)
LINK_ONLY = {"www.openstreetmap.org", "www.w3.org"}


def resource_hosts() -> set[str]:
    """The hosts of every absolute URL in docs/*.js that is not only a link."""
    hosts = set()
    for f in sorted((ROOT / "docs").glob("*.js")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"https?://([A-Za-z0-9.-]+)", text):
            if m.group(1) not in LINK_ONLY and not LINK.search(text[max(0, m.start() - 8):m.start()]):
                hosts.add(m.group(1))
    return hosts


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
            (no_csp, GOOD.replace(CSP + "\n", "").replace("<body>", "<body>" + CSP)),  # below <head>
            (no_csp, GOOD.replace(CSP, '<meta http-equiv="Content-Security-Policy" content="">')),
        ]
        for want, page in cases:
            with self.subTest(want=want):
                self.assertIn(want, " | ".join(m for _, m in html_check.check(page)))

    def test_csp_covers_the_hosts_of_the_scripts(self):
        # a host the scripts fetch from that no page allows is a refused request on the live site
        self.assertEqual(resource_hosts(), set(HOSTS))
        pages = sorted((ROOT / "docs").glob("*.html"))
        self.assertTrue(pages)
        for page in pages:
            with self.subTest(page=page.name):
                p = html_check.policy(page.read_text(encoding="utf-8"))
                self.assertEqual(p.get("default-src"), {"'self'"})
                self.assertEqual(p.get("script-src"), {"'self'"})  # no inline script, no eval
                allowed = p.get("img-src", set()) | p.get("connect-src", set())
                self.assertIn("'self'", allowed)  # the data files of GitHub Pages
                self.assertIn("data:", p.get("img-src", set()))  # the favicon of every page
                self.assertEqual({h for h in HOSTS if f"https://{h}" not in allowed}, set())
        # the policy is parsed as the browser reads it: a directive into sources
        self.assertEqual(html_check.policy(GOOD)["connect-src"], {"'self'", "https://example.invalid"})


if __name__ == "__main__":
    unittest.main()
