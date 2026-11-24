"""Parser tests on saved gov.pl pages. Run: python3 -m unittest discover -s tests"""
import datetime as dt
import json
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rcb  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
GEO = json.load(open(os.path.join(ROOT, "docs/geo/poland.json"), encoding="utf-8"))
GAZ = rcb.load_gazetteer()


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


class AirAlertSeveralUpdates(unittest.TestCase):
    """Air alert with four updates: the newest update (23:03) ends it even though an earlier
    one (19:45) had already ended it and 21:08 re-alerted; regions accumulate over updates."""
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---zagrozenie-z-powietrza-2111.html"), GAZ,
                                  title="Alert RCB - zagrożenie z powietrza (21.10)",
                                  date="2026-10-21")
        self.a.update(id="x", url="u", intro="")

    def test_updates_newest_first_untimed_last(self):
        self.assertEqual([u["time"] for u in self.a["updates"]],
                         ["23:03", "21:08", "19:45", None])

    def test_ended_flags_follow_the_story(self):
        self.assertTrue(self.a["updates"][0]["ended"])   # 23:03 attack over
        self.assertFalse(self.a["updates"][1]["ended"])  # 21:08 re-alerted after an end
        self.assertTrue(self.a["updates"][2]["ended"])   # 19:45 earlier end

    def test_regions_accumulate_over_updates(self):
        self.assertEqual(self.a["regions"]["voivodeships"], ["lubelskie", "podkarpackie"])
        self.assertEqual(self.a["regions"]["powiaty"], [])
        self.assertEqual(self.a["regions"]["whole"], ["lubelskie", "podkarpackie"])

    def test_status_latest_update_wins(self):
        st, started, last = rcb.status(self.a, dt.datetime(2026, 10, 22, 0, 30, tzinfo=rcb.TZ))
        self.assertEqual(st, "ended")  # the newest update ended the alert, no TTL wait
        self.assertEqual(started, "2026-10-21T19:45:00+02:00")
        self.assertEqual(last, "2026-10-21T23:03:00+02:00")


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


class FireAlert(unittest.TestCase):
    """Fire in Chorzów: cities named without the word 'powiat' still resolve to their city
    powiaty (Chorzów, Bytom, ...); fire alerts expire after the 24 h TTL."""
    def setUp(self):
        self.a = rcb.parse_detail(page("alert-rcb---pozar-w-chorzowie-0709.html"), GAZ,
                                  title="Alert RCB - pożar w Chorzowie (07.09)", date="2026-09-07")
        self.a.update(id="x", url="u", intro="")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "fire")
        self.assertEqual(self.a["regions"]["voivodeships"], ["slaskie"])
        self.assertEqual(self.a["regions"]["powiaty"],
                         ["slaskie/bytom", "slaskie/chorzow", "slaskie/siemianowice-slaskie",
                          "slaskie/swietochlowice"])
        self.assertEqual(self.a["regions"]["whole"], [])

    def test_updates(self):
        self.assertEqual(len(self.a["updates"]), 1)
        self.assertIsNone(self.a["updates"][0]["time"])
        self.assertFalse(self.a["updates"][0]["ended"])
        self.assertIn("Pożar", self.a["updates"][0]["message"])

    def test_status_ttl(self):
        start = dt.datetime(2026, 9, 7, 0, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=23))[0], "active")
        self.assertEqual(rcb.status(self.a, start + dt.timedelta(hours=25))[0], "expired")


class ChemicalAlert(unittest.TestCase):
    """The two chemical alerts since 2021 (Bóbr 2026-07-04, Warta 2026-05-27) have no saved
    gov.pl page, so classification runs on their real archived wording. The Bóbr text says
    'Woda nie może być wykorzystywana...' — river wording the water patterns do not catch,
    so 'skażenie' decides: chemical."""
    def test_bobr(self):
        t = "Alert RCB - możliwe skażenie rzeki Bóbr wzdłuż gminy Wleń i Lwówek Śl (04.07)"
        body = ("Uwaga! Możliwe skażenie rzeki Bóbr, wzdłuż gminy Wleń i Lwówek Śl. Woda nie może "
                "być wykorzystywana do celów rekreacyjnych, gospodarczych i pojenia zwierząt.")
        self.assertEqual(rcb.category(t, body), "chemical")

    def test_warta(self):
        t = "Alert RCB - możliwe skażenie i zanieczyszczenie rzeki Warta w pow. obornickim"
        body = ("Uwaga! Możliwe skażenie i zanieczyszczenie rzeki Warta w pow. obornickim. "
                "Ogranicz wszelką aktywność w rejonie rzeki.")
        self.assertEqual(rcb.category(t, body), "chemical")

    def test_chemical_fire_is_fire(self):
        # 'pożar' is checked before chemical: the archived 2024-05-10 'pożar substancji
        # chemicznych' alert is a fire alert, not chemical
        t = "Alert RCB - pożar substancji chemicznych (10.05.2024)"
        body = ("Uwaga! Pożar substancji chemicznych w Siemianowicach Śląskich. Nie zbliżaj się "
                "do miejsca pożaru. Jeśli możesz, zostań w domu i zamknij okna.")
        self.assertEqual(rcb.category(t, body), "fire")

    def test_ttl_48h(self):
        a = {"date": "2026-07-04", "category": "chemical",
             "updates": [{"time": None, "ended": False, "message": "Uwaga!"}]}
        start = dt.datetime(2026, 7, 4, 0, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(a, start + dt.timedelta(hours=47))[0], "active")
        self.assertEqual(rcb.status(a, start + dt.timedelta(hours=49))[0], "expired")


class OtherAlert(unittest.TestCase):
    """Zrzut szczepionek dla lisów (2026-09-19, archived wording): no category pattern
    matches, so it falls through to other, with the 24 h other TTL."""
    def test_fallthrough(self):
        t = "Alert RCB - zrzut szczepionek dla lisów (19.09)"
        body = ("KOMUNIKAT: 20-30.09 w woj. małopolskim planowane zrzuty szczepionek dla lisów "
                "przeciw wściekliźnie. Nie dotykaj kapsułki i nie dopuszczaj do niej zwierząt!")
        self.assertEqual(rcb.category(t, body), "other")

    def test_ttl_24h(self):
        a = {"date": "2026-09-19", "category": "other",
             "updates": [{"time": None, "ended": False, "message": "KOMUNIKAT"}]}
        start = dt.datetime(2026, 9, 19, 0, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(a, start + dt.timedelta(hours=23))[0], "active")
        self.assertEqual(rcb.status(a, start + dt.timedelta(hours=25))[0], "expired")


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


class NationwideDrillAlert(unittest.TestCase):
    """Siren test for the whole country ('na terenie całego kraju'): no voivodeship is named,
    so regions stay empty and the site treats the alert as nationwide. Dotted window times
    ('w godz. 7.00-19.00') open the drill window."""
    def setUp(self):
        self.a = rcb.parse_detail(
            page("alert-rcb---cwiczenie-systemu-alarmowania-z-wykorzystaniem-syren.html"), GAZ,
            title="Alert RCB - ćwiczenia systemu alarmowania z wykorzystaniem syren (20.07)",
            date="2026-07-20")
        self.a.update(id="x", url="u", intro="")

    def test_category_and_regions(self):
        self.assertEqual(self.a["category"], "drill")
        self.assertEqual(self.a["regions"],
                         {"voivodeships": [], "powiaty": [], "whole": [], "gminy": []})
        self.assertIn("całego kraju", self.a["updates"][0]["message"])

    def test_updates(self):
        self.assertEqual(len(self.a["updates"]), 1)
        self.assertFalse(self.a["updates"][0]["ended"])

    def test_status_window_from_dotted_times(self):
        st, started, last = rcb.status(self.a, dt.datetime(2026, 7, 20, 8, 0, tzinfo=rcb.TZ))
        self.assertEqual(st, "active")  # inside 7.00-19.00 on the publication day
        self.assertEqual(started, "2026-07-20T07:00:00+02:00")
        self.assertEqual(rcb.status(self.a, dt.datetime(2026, 7, 20, 6, 0, tzinfo=rcb.TZ))[0],
                         "planned")

    @unittest.expectedFailure
    def test_status_jutro_shifts_window_to_next_day(self):
        # BUG: the message says 'Jutro (21.07) w godz. 7.00-19.00' but status() anchors the
        # window to the publication date (20.07), so during the real drill (21.07 morning)
        # the map already shows the alert as ended. See the PR body.
        now = dt.datetime(2026, 7, 21, 8, 0, tzinfo=rcb.TZ)
        self.assertEqual(rcb.status(self.a, now)[0], "active")


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


class UpdateFailingPage(unittest.TestCase):
    """update() when a detail page fails to load: the old archive.json entries survive.
    A normal run fails loudly before writing anything; a backfill (--keep-going) skips the
    broken page but still merges the pages that did load into the old archive."""
    BROKEN = "https://www.gov.pl/web/rcb/alert-rcb---atak-z-powietrza-2011"

    def setUp(self):
        # one saved page stands for every alert here, so skip the check of whose page it is
        p = mock.patch.object(rcb, "is_alert_page", return_value=True)
        p.start()
        self.addCleanup(p.stop)

    def fetch(self, url, tries=3):
        """The saved list page for every list request, one saved detail page for the rest —
        except BROKEN, which fails to load."""
        if url == self.BROKEN:
            raise RuntimeError(f"fetch failed: {url}: timed out")
        if "komunikaty?page=" in url:
            return page("komunikaty-page1.html")
        return page("alert-rcb---trening-systemow-alarmowania-2111.html")

    def records(self):
        a = rcb.parse_detail(page("alert-rcb---atak-z-powietrza-2011.html"), GAZ,
                             title="Alert RCB - atak z powietrza (20.11)", date="2026-11-20")
        a.update({"id": "alert-rcb---atak-z-powietrza-2011", "url": self.BROKEN, "intro": ""})
        a["status"], a["started_at"], a["last_at"] = rcb.status(
            a, dt.datetime(2026, 11, 20, 10, 0, tzinfo=rcb.TZ))
        broken = rcb.compact(a)  # the record of the page that is about to fail
        older = dict(broken, id="woda-2024", url="https://www.gov.pl/web/rcb/woda-2024",
                     title="Alert RCB - woda niezdatna do spożycia (01.05.2024)", date="2024-05-01",
                     started_at="2024-05-01T10:00:00+02:00", last_at="2024-05-01T12:00:00+02:00")
        return broken, older

    def seed(self, d):
        broken, older = self.records()
        path = os.path.join(d, "archive.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"alerts": [broken, older]}, fh, ensure_ascii=False)
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_failing_page_fails_the_run_and_writes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            seeded = self.seed(d)
            with mock.patch.object(rcb, "fetch", self.fetch):
                with self.assertRaises(RuntimeError):
                    rcb.update(1, d)
            with open(os.path.join(d, "archive.json"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), seeded)  # nothing was written over the history
            self.assertFalse(os.path.exists(os.path.join(d, "alerts.json")))
            self.assertFalse(os.path.exists(os.path.join(d, "meta.json")))

    def test_keep_going_skips_the_page_and_keeps_the_old_entries(self):
        import tempfile
        broken, _ = self.records()
        with tempfile.TemporaryDirectory() as d:
            self.seed(d)
            with mock.patch.object(rcb, "fetch", self.fetch):
                rcb.update(1, d, keep_going=True)
            with open(os.path.join(d, "archive.json"), encoding="utf-8") as fh:
                rows = json.load(fh)["alerts"]
        ids = [r["id"] for r in rows]
        self.assertEqual(len(ids), 10)  # the 8 pages that loaded + the 2 old records
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(broken, rows)          # the skipped page kept its own record, not re-parsed
        self.assertIn("woda-2024", ids)      # an entry older than the fetched pages stayed
        self.assertIn("komunikat-1811", ids)  # the pages that did load were parsed in


class Gazetteer(unittest.TestCase):
    def test_counts(self):
        self.assertEqual(len(GEO["voivodeships"]), 16)
        self.assertEqual(len(GEO["powiaty"]), 380)


class Gminy(unittest.TestCase):
    def test_list(self):
        gm = json.load(open(os.path.join(ROOT, "docs/geo/gminy.json"), encoding="utf-8"))["gminy"]
        self.assertGreater(len(gm), 2400)
        pids = {p["id"] for p in GEO["powiaty"]}
        self.assertTrue(all(g["powiat"] in pids for g in gm))

    def test_after_gmina_word(self):
        s = "Woda w części gminy Chęciny, Morawica i Piekoszów (wodociąg Chęciny) nie nadaje się do spożycia."
        self.assertEqual(GAZ.gminy(s, ["swietokrzyskie"], []), ["Chęciny", "Morawica", "Piekoszów"])
        s = "woda w Gaworzycach, Kłobuczynie (gm. Gaworzyce) nadaje się do spożycia tylko po przegotowaniu"
        self.assertEqual(GAZ.gminy(s, ["dolnoslaskie"], []), ["Gaworzyce"])

    def test_town_of_the_powiat(self):
        s = "Woda z wodociągu Złoty Stok nie nadaje się do celów spożywczych w miejscowościach: Złoty Stok, Płonica"
        self.assertEqual(GAZ.gminy(s, ["dolnoslaskie"], ["dolnoslaskie/zabkowicki"]), ["Złoty Stok"])
        self.assertEqual(GAZ.gminy(s, ["dolnoslaskie"], []), [])  # no powiat: a bare town is not enough

    def test_longer_name_and_city_powiat(self):
        s = "na terenie gm. Kamienna Góra odbędzie się trening"
        self.assertEqual(GAZ.gminy(s, ["dolnoslaskie"], []), ["Kamienna Góra"])
        s = "na terenie gminy Wrocław odbędzie się trening"
        self.assertEqual(GAZ.gminy(s, ["dolnoslaskie"], ["dolnoslaskie/wroclaw"]), [])

    def test_alert_page(self):
        a = rcb.parse_detail(page("alert-rcb---woda-niezdatna-do-spozycia-pow-zabkowicki-1911.html"), GAZ)
        self.assertEqual(a["regions"]["gminy"], ["Złoty Stok"])

    def test_backfill_old_records(self):
        a = {"regions": {"voivodeships": ["wielkopolskie"], "powiaty": ["wielkopolskie/gostynski"], "whole": []},
             "updates": [{"message": "na terenie gminy Gostyń odbędzie się trening", "region_text": "",
                          "regions": {"voivodeships": ["wielkopolskie"], "powiaty": ["wielkopolskie/gostynski"],
                                      "whole": []}}]}
        rcb.add_gminy(a, GAZ)
        self.assertEqual(a["regions"]["gminy"], ["Gostyń"])
        self.assertEqual(a["updates"][0]["regions"]["gminy"], ["Gostyń"])


if __name__ == "__main__":
    unittest.main()


class WrongPage(unittest.TestCase):
    """24.11.2026: gov.pl now and then answered an alert's URL with its home page."""
    URL = rcb.BASE + "/web/rcb/alert-rcb---atak-z-powietrza-2011"

    def test_home_page_is_not_the_alert(self):
        self.assertTrue(rcb.is_alert_page(page("alert-rcb---atak-z-powietrza-2011.html"), self.URL))
        self.assertFalse(rcb.is_alert_page(page("page-gov-home.html"), self.URL))

    def test_fetch_detail_retries_past_the_home_page(self):
        answers = [page("page-gov-home.html"), page("alert-rcb---atak-z-powietrza-2011.html")]
        with mock.patch.object(rcb, "fetch", side_effect=answers), mock.patch.object(rcb.time, "sleep"):
            self.assertIn("atak-z-powietrza-2011", rcb.fetch_detail(self.URL))

    def test_fetch_detail_gives_up(self):
        with mock.patch.object(rcb, "fetch", return_value=page("page-gov-home.html")), \
                mock.patch.object(rcb.time, "sleep"):
            with self.assertRaises(RuntimeError):
                rcb.fetch_detail(self.URL)

    def test_update_keeps_the_saved_alert_when_the_page_is_wrong(self):
        import tempfile
        slug = "alert-rcb---atak-z-powietrza-2011"
        item = {"slug": slug, "url": self.URL, "title": "Alert RCB - atak z powietrza (20.11)",
                "date": dt.date.today().isoformat(), "intro": ""}
        saved = rcb.build_alert(item, page(slug + ".html"), GAZ, dt.datetime.now(rcb.TZ))
        saved["parser"] = rcb.PARSER_VERSION
        self.assertGreater(len(saved["updates"]), 1)
        with tempfile.TemporaryDirectory() as out:
            with open(os.path.join(out, "alerts.json"), "w", encoding="utf-8") as fh:
                json.dump({"alerts": [saved]}, fh, ensure_ascii=False)
            with mock.patch.object(rcb, "fetch", return_value=page("page-gov-home.html")), \
                    mock.patch.object(rcb, "parse_list", return_value=[item]), \
                    mock.patch.object(rcb.time, "sleep"), mock.patch("builtins.print"):
                rcb.update(1, out)
            got = {a["id"]: a for a in json.load(open(os.path.join(out, "alerts.json"), encoding="utf-8"))["alerts"]}
        self.assertEqual(len(got[slug]["updates"]), len(saved["updates"]))
