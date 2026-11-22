"""scripts/html_check.py: the site's pages carry no broken markup a visitor would see."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import html_check  # noqa: E402

GOOD = """<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width"><title>T</title>
<meta name="description" content="Opis strony, także jako powiadomienia."></head>
<body><header class="top"><a href="./">A</a></header><main><p>x<p>y<ul><li>a<li>b</ul></main></body></html>"""


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
        cases = {
            "duplicate id": GOOD.replace('<main>', '<main id="a"><div id="a"></div>'),
            "is closed by": GOOD.replace('<main>', '<main><div><span></div>'),
            "closes nothing": GOOD.replace('</main>', '</main></div>'),
            "has no lang": GOOD.replace(' lang="pl"', ''),
            "no <title>": GOOD.replace('<title>T</title>', ''),
            'no <meta name="description">': GOOD.replace('name="description"', 'name="x"'),
        }
        for want, page in cases.items():
            with self.subTest(want=want):
                self.assertIn(want, " | ".join(m for _, m in html_check.check(page)))


if __name__ == "__main__":
    unittest.main()
