"""Parser tests on saved gov.pl pages. Run: python3 -m unittest discover -s tests"""
import datetime as dt
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rcb  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
GEO = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
GAZ = rcb.Gazetteer(GEO)


def page(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


class ListPage(unittest.TestCase):
    def test_items(self):
        items = rcb.parse_list(page("komunikaty-page1.html"))
        self.assertEqual(len(items), 10)
        self.assertEqual(items[1]["slug"], "alert-rcb---atak-z-powietrza-2011")
        self.assertEqual(items[1]["date"], "2026-11-20")
        self.assertTrue(items[1]["intro"].startswith("„UWAGA!"))


class AirAlert(unittest.TestCase):
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---atak-z-powietrza-2011.html"), GAZ,
                                  title="Alert RCB - atak z powietrza (20.11)", date="2026-11-20")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "air")
        self.assertEqual(self.a["regions"]["voivodeships"], ["lubelskie", "podkarpackie"])
        self.assertIn("podkarpackie/bieszczadzki", self.a["regions"]["powiaty"])
        self.assertIn("lubelskie/lublin", self.a["regions"]["powiaty"])

    def test_latest_update_ends_alert(self):
        self.assertEqual(self.a["updates"][0]["time"], "09:48")
        self.assertTrue(self.a["updates"][0]["ended"])

    def test_status(self):
        self.a.update(id="x", url="u", intro="")
        now = dt.datetime(2026, 11, 20, 10, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, now)[0], "ended")


class CityNames(unittest.TestCase):
    def test_biala_podlaska_is_not_podlaskie(self):
        a = rcb.parse_detail(page("alert-rcb---zagrozenie-z-powietrza-1011.html"), GAZ)
        self.assertEqual(a["regions"]["voivodeships"], ["lubelskie"])
        self.assertIn("lubelskie/biala-podlaska", a["regions"]["powiaty"])
        self.assertEqual(len(a["regions"]["powiaty"]), 13)

    def test_ambiguous_powiat_goes_to_named_voivodeship(self):
        r = GAZ.regions("na terenie województwa lubelskiego - powiaty: opolski, świdnicki")
        self.assertEqual(r["powiaty"], ["lubelskie/opolski", "lubelskie/swidnicki"])


class Towns(unittest.TestCase):
    def test_warsaw_area_flares(self):
        r = GAZ.regions("Dziś w godz. 16.00-18.30 w Warszawie, Markach, Zielonce, Kobyłce, Wołominie i Legionowie odbędą się testy pocisków oświetlających.")
        self.assertEqual(r["powiaty"], ["mazowieckie/legionowski", "mazowieckie/warszawa", "mazowieckie/wolominski"])

    def test_town_does_not_mark_voivodeship(self):
        self.assertEqual(GAZ.regions("Biała Podlaska i Ruda Śląska")["whole"], [])


class WaterAlert(unittest.TestCase):
    def test_genitive_powiat(self):
        a = rcb.parse_detail(page("alert-rcb---woda-niezdatna-do-spozycia-pow-zabkowicki-1911.html"), GAZ)
        self.assertEqual(a["category"], "water")
        self.assertEqual(a["regions"]["powiaty"], ["dolnoslaskie/zabkowicki"])
        self.assertEqual(a["regions"]["whole"], [])


class Gazetteer(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(GEO["voivodeships"]), 16)
        self.assertEqual(len(GEO["powiaty"]), 380)


if __name__ == "__main__":
    unittest.main()
