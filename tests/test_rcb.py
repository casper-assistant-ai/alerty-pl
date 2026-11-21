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

    def test_warsaw_area_flares_page(self):
        a = rcb.parse_detail(page("komunikat-1811.html"), GAZ)
        self.assertEqual(a["regions"]["voivodeships"], ["mazowieckie"])
        self.assertEqual(a["regions"]["powiaty"],
                         ["mazowieckie/legionowski", "mazowieckie/warszawa", "mazowieckie/wolominski"])
        self.assertEqual(a["regions"]["whole"], [])  # towns named, not the whole voivodeship

    def test_palatalized_locative_towns(self):
        # locative of Zielonka/Kobyłka palatalizes k -> c: "w Zielonce", "w Kobyłce"
        r = GAZ.regions("testy odbędą się w Zielonce i Kobyłce")
        self.assertEqual(r["powiaty"], ["mazowieckie/wolominski"])

    def test_town_does_not_mark_voivodeship(self):
        self.assertEqual(GAZ.regions("Biała Podlaska i Ruda Śląska")["whole"], [])


class WaterAlert(unittest.TestCase):
    def test_genitive_powiat(self):
        a = rcb.parse_detail(page("alert-rcb---woda-niezdatna-do-spozycia-pow-zabkowicki-1911.html"), GAZ)
        self.assertEqual(a["category"], "water")
        self.assertEqual(a["regions"]["powiaty"], ["dolnoslaskie/zabkowicki"])
        self.assertEqual(a["regions"]["whole"], [])


class WeatherAlert(unittest.TestCase):
    """Meteo alert with no timed update: active for the 24 h weather TTL, then expired."""
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---ostrzezenie-przed-silnym-wiatrem-2511.html"), GAZ,
                                  title="Alert RCB - ostrzeżenie przed silnym wiatrem (25.10)",
                                  date="2026-10-25")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "weather")
        self.assertEqual(self.a["regions"]["voivodeships"], ["slaskie"])
        self.assertEqual(self.a["regions"]["powiaty"],
                         ["slaskie/bielski", "slaskie/cieszynski", "slaskie/zywiecki"])
        self.assertEqual(self.a["regions"]["whole"], [])

    def test_updates(self):
        self.assertEqual(len(self.a["updates"]), 1)
        self.assertIsNone(self.a["updates"][0]["time"])
        self.assertFalse(self.a["updates"][0]["ended"])

    def test_status_ttl(self):
        self.a.update(id="x", url="u", intro="")
        start = dt.datetime(2026, 10, 25, 0, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=23))[0], "active")
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=25))[0], "expired")


class OrdnanceAlert(unittest.TestCase):
    """Niewybuch named by city and street only: the whole voivodeship is alerted, no powiat."""
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---neutralizacja-niewybuchu-0711.html"), GAZ,
                                  title="Alert RCB - neutralizacja niewybuchu (07.11)", date="2026-11-07")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "ordnance")
        self.assertEqual(self.a["regions"]["voivodeships"], ["zachodniopomorskie"])
        self.assertEqual(self.a["regions"]["powiaty"], [])
        self.assertEqual(self.a["regions"]["whole"], ["zachodniopomorskie"])

    def test_updates(self):
        self.assertEqual(len(self.a["updates"]), 1)
        self.assertFalse(self.a["updates"][0]["ended"])

    def test_status_ttl(self):
        self.a.update(id="x", url="u", intro="")
        start = dt.datetime(2026, 11, 7, 0, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=23))[0], "active")
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=25))[0], "expired")


class DrillAlert(unittest.TestCase):
    """Drill with a time window 'w godz. 08:00-12:00': planned before, active during, ended after."""
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---trening-systemow-alarmowania-2111.html"), GAZ,
                                  title="Alert RCB - trening systemów alarmowania (21.11)",
                                  date="2026-11-21")
        self.a.update(id="x", url="u", intro="")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "drill")
        self.assertEqual(self.a["regions"]["voivodeships"], ["wielkopolskie"])
        self.assertEqual(self.a["regions"]["powiaty"], ["wielkopolskie/gostynski"])
        self.assertEqual(self.a["regions"]["whole"], [])

    def test_updates(self):
        self.assertEqual(len(self.a["updates"]), 1)
        self.assertIn("w godz. 08:00-12:00", self.a["updates"][0]["message"])
        self.assertFalse(self.a["updates"][0]["ended"])

    def test_status_window(self):
        at = lambda h, m: dt.datetime(2026, 11, 21, h, m, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, at(7, 0))[0], "planned")
        self.assertEqual(rcb.status(self.a, at(10, 0))[0], "active")
        self.assertEqual(rcb.status(self.a, at(13, 0))[0], "ended")

    def test_status_window_sets_start(self):
        st, started, last = rcb.status(self.a, dt.datetime(2026, 11, 21, 10, 0, tzinfo=rcb.TZ))
        self.assertEqual(started, "2026-11-21T08:00:00+01:00")  # the window start, not midnight


class Archive(unittest.TestCase):
    def test_archive_keeps_old_and_adds_new(self):
        import tempfile
        now = dt.datetime(2026, 11, 21, 12, 0, tzinfo=rcb.TZ)
        a = rcb.parse_detail(page("alert-rcb---atak-z-powietrza-2011.html"), GAZ,
                             title="Alert RCB - atak z powietrza (20.11)", date="2026-11-20")
        a.update({"id": "new", "url": "https://www.gov.pl/web/rcb/new", "intro": ""})
        a["status"], a["started_at"], a["last_at"] = rcb.status(a, now)
        with tempfile.TemporaryDirectory() as d:
            old = dict(rcb.compact(a), id="old", date="2024-05-01", started_at="2024-05-01T10:00:00+02:00")
            json.dump({"alerts": [old]}, open(os.path.join(d, "archive.json"), "w"))
            self.assertEqual(rcb.update_archive(d, [a]), 2)
            rows = json.load(open(os.path.join(d, "archive.json")))["alerts"]
        self.assertEqual([r["id"] for r in rows], ["new", "old"])
        self.assertEqual(rows[0]["category"], "air")
        self.assertIn("podkarpackie", rows[0]["voivodeships"])
        self.assertLessEqual(len(rows[0]["message"]), 400)


class Gazetteer(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(GEO["voivodeships"]), 16)
        self.assertEqual(len(GEO["powiaty"]), 380)


if __name__ == "__main__":
    unittest.main()
