"""Behaviour tests for the core rules of scripts/rcb.py that the page fixtures do not reach:
the status clock (TTL edges), update splitting, the list page edge cases and what update() keeps.
Offline: every fetch is replaced with a saved page.
"""
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import rcb  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")


def page(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as fh:
        return fh.read()


def alert(category, times, ended=False, date="2026-11-20", extra=""):
    """A parsed alert as status() sees it: updates newest first, the newest one carries `ended`."""
    ups = [{"time": t, "message": extra, "ended": False} for t in sorted(times, reverse=True)]
    if ups:
        ups[0]["ended"] = ended
    else:
        ups = [{"time": None, "message": extra, "ended": ended}]
    return {"date": date, "category": category, "updates": ups}


def at(h, m=0, day=20):
    return dt.datetime(2026, 11, day, h, m, tzinfo=rcb.TZ)


class StatusClock(unittest.TestCase):
    def test_every_category_has_a_ttl_and_air_is_shortest_but_water(self):
        self.assertEqual(set(rcb.TTL), {c for c, _ in rcb.CATEGORIES} | {"other"})
        self.assertEqual((rcb.TTL["air"], rcb.TTL["water"], rcb.TTL["chemical"]), (12, 168, 48))

    def test_air_alert_expires_just_after_twelve_hours(self):
        a = alert("air", ["08:00"])
        self.assertEqual(rcb.status(a, at(20, 0))[0], "active")    # exactly 12 h: still on
        self.assertEqual(rcb.status(a, at(20, 1))[0], "expired")   # one minute more: expired

    def test_water_alert_lasts_a_week_not_a_day(self):
        a = alert("water", ["08:00"])
        self.assertEqual(rcb.status(a, at(8, 0, day=26))[0], "active")   # six days later
        self.assertEqual(rcb.status(a, at(8, 1, day=27))[0], "expired")  # 168 h and a minute

    def test_the_newest_update_decides_not_the_oldest(self):
        ended_then_realerted = alert("air", ["09:00", "10:00"])
        ended_then_realerted["updates"][1]["ended"] = True   # the older update ended it
        self.assertEqual(rcb.status(ended_then_realerted, at(11, 0))[0], "active")
        ended_last = alert("air", ["09:00", "10:00"], ended=True)
        self.assertEqual(rcb.status(ended_last, at(10, 5))[0], "ended")

    def test_ended_beats_ttl(self):
        a = alert("water", ["08:00"], ended=True)
        self.assertEqual(rcb.status(a, at(9, 0))[0], "ended")

    def test_last_update_time_moves_the_expiry(self):
        a = alert("air", ["08:00", "15:00"])  # the clock starts at 15:00, not 08:00
        st, started, last = rcb.status(a, at(21, 0))
        self.assertEqual(st, "active")
        self.assertEqual(started, "2026-11-20T08:00:00+01:00")
        self.assertEqual(last, "2026-11-20T15:00:00+01:00")

    def test_untimed_alert_counts_from_midnight_of_its_day(self):
        a = alert("fire", [])
        st, started, last = rcb.status(a, at(23, 0))
        self.assertEqual((st, started, last), ("active", "2026-11-20T00:00:00+01:00", "2026-11-20T00:00:00+01:00"))
        self.assertEqual(rcb.status(a, at(0, 1, day=21))[0], "expired")  # 24 h and a minute

    def test_summer_time_offset_is_used(self):
        a = alert("air", ["08:00"], date="2026-07-20")
        self.assertEqual(rcb.status(a, dt.datetime(2026, 7, 20, 9, 0, tzinfo=rcb.TZ))[1], "2026-07-20T08:00:00+02:00")

    def test_only_drills_get_a_planned_window(self):
        # the same «w godz.» wording on a non-drill alert must not turn it into a window
        a = alert("air", ["08:00"], extra="ćwiczymy w godz. 10:00-12:00")
        self.assertEqual(rcb.status(a, at(9, 0))[0], "active")

    def test_hour_past_23_does_not_crash(self):
        a = alert("fire", ["24:30"])
        self.assertEqual(rcb.status(a, at(23, 59))[2], "2026-11-20T23:30:00+01:00")


class SplitUpdates(unittest.TestCase):
    def test_dotted_and_colon_times_are_padded(self):
        got = rcb.split_updates("Treść\nAktualizacja - g. 9.05\n„Odwołanie”\nAktualizacja g. 10:15\n„Nowy”")
        self.assertEqual(got, [(None, "Treść"), ("09:05", "„Odwołanie”"), ("10:15", "„Nowy”")])

    def test_a_page_with_no_update_is_one_untimed_chunk(self):
        self.assertEqual(rcb.split_updates("Sama treść bez godzin"), [(None, "Sama treść bez godzin")])

    def test_empty_body_has_no_chunks(self):
        self.assertEqual(rcb.split_updates(""), [])


class ListPageEdges(unittest.TestCase):
    ITEM = ('<span class="date"> {d} </span><div class="title"><a href="/web/rcb/{s}">{t}</a></div>{i}')

    def test_item_without_intro_and_entities_in_title(self):
        html = self.ITEM.format(d="05.11.2026", s="komunikat-0511", t="Komunikat &amp; <b>test</b>", i="")
        self.assertEqual(rcb.parse_list(html), [{
            "slug": "komunikat-0511", "url": "https://www.gov.pl/web/rcb/komunikat-0511",
            "title": "Komunikat & test", "date": "2026-11-05", "intro": ""}])

    def test_layout_change_gives_no_items(self):
        self.assertEqual(rcb.parse_list("<html><body><h1>503</h1></body></html>"), [])

    def test_date_is_iso_for_two_items_in_order(self):
        html = (self.ITEM.format(d="01.02.2026", s="a", t="A", i='<div class="intro">x</div>')
                + self.ITEM.format(d="31.12.2025", s="b", t="B", i=""))
        self.assertEqual([(i["slug"], i["date"], i["intro"]) for i in rcb.parse_list(html)],
                         [("a", "2026-02-01", "x"), ("b", "2025-12-31", "")])


class CategoryChoice(unittest.TestCase):
    def test_air_outranks_fire_and_drill_outranks_fire(self):
        self.assertEqual(rcb.category("Alert RCB", "atak z powietrza, pożar w pobliżu"), "air")
        self.assertEqual(rcb.category("Komunikat", "Trening syren, nie ma pożaru"), "drill")

    def test_unknown_text_is_other(self):
        self.assertEqual(rcb.category("Komunikat (18.11)", "Seminarium o cyberbezpieczeństwie"), "other")

    def test_only_the_title_and_first_400_chars_count(self):
        self.assertEqual(rcb.category("Komunikat", "x" * 400 + " pożar"), "other")


class FakeNow(dt.datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 23, 12, 0, tzinfo=tz)


class UpdateKeeps(unittest.TestCase):
    """update() with a frozen clock (23.11.2026): which pages it fetches again, what it drops
    from alerts.json and what archive.json keeps."""

    def setUp(self):
        self.fetched = []
        self.patches = [mock.patch.object(rcb.dt, "datetime", FakeNow),
                        mock.patch.object(rcb, "fetch", self.fetch)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def fetch(self, url, tries=3):
        self.fetched.append(url)
        if "komunikaty?page=" in url:
            return page("komunikaty-page1.html")
        return page("alert-rcb---atak-z-powietrza-2011.html")

    def load(self, d, name):
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            return json.load(fh)

    def test_non_alert_items_are_not_alerts(self):
        with tempfile.TemporaryDirectory() as d:
            rcb.update(1, d)
            ids = [a["id"] for a in self.load(d, "alerts.json")["alerts"]]
        self.assertEqual(len(ids), 9)  # 10 list items, the seminar is not an alert
        self.assertNotIn("rusza-viii-seminarium-cyberbezpieczenstwa-od-regulacji-do-odpornosci", ids)

    def test_second_run_fetches_only_recent_pages_again(self):
        with tempfile.TemporaryDirectory() as d:
            rcb.update(1, d)
            self.fetched.clear()
            rcb.update(1, d)
        details = [u for u in self.fetched if "komunikaty?page=" not in u]
        # 23.11 minus 2 days = 21.11: only the drill of 21.11 is recent; the rest come from alerts.json
        self.assertEqual(details, ["https://www.gov.pl/web/rcb/alert-rcb---trening-systemow-alarmowania-2111"])

    def test_a_new_parser_version_reparses_the_cache(self):
        with tempfile.TemporaryDirectory() as d:
            rcb.update(1, d)
            self.fetched.clear()
            with mock.patch.object(rcb, "PARSER_VERSION", rcb.PARSER_VERSION + 1):
                rcb.update(1, d)
        self.assertEqual(len([u for u in self.fetched if "komunikaty?page=" not in u]), 9)

    def test_alerts_json_drops_after_60_days_but_archive_keeps_everything(self):
        with tempfile.TemporaryDirectory() as d:
            rcb.update(1, d)
            old = dict(self.load(d, "archive.json")["alerts"][0], id="stary-2026-08", date="2026-08-01",
                       started_at="2026-08-01T10:00:00+02:00", last_at="2026-08-01T12:00:00+02:00",
                       status="ended")
            path = os.path.join(d, "archive.json")
            data = self.load(d, "archive.json")
            data["alerts"].append(old)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            rcb.update(1, d)
            archive_ids = [a["id"] for a in self.load(d, "archive.json")["alerts"]]
            live_ids = [a["id"] for a in self.load(d, "alerts.json")["alerts"]]
            meta = self.load(d, "meta.json")
        self.assertIn("stary-2026-08", archive_ids)
        self.assertNotIn("stary-2026-08", live_ids)
        self.assertEqual(meta["archive"], 10)
        self.assertEqual(meta["count"], 9)

    def test_first_page_without_items_fails_loudly(self):
        with mock.patch.object(rcb, "fetch", lambda url, tries=3: "<html>maintenance</html>"):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaisesRegex(RuntimeError, "layout may have changed"):
                    rcb.update(1, d)
                self.assertEqual(os.listdir(d), [])


class WriteIfChanged(unittest.TestCase):
    def test_writes_once_then_reports_no_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            self.assertTrue(rcb.write_if_changed(p, {"a": "zażółć"}))
            self.assertFalse(rcb.write_if_changed(p, {"a": "zażółć"}))
            self.assertTrue(rcb.write_if_changed(p, {"a": "gęślą"}))
            with open(p, encoding="utf-8") as fh:
                self.assertIn("gęślą", fh.read())  # not \u-escaped


class FetchRetries(unittest.TestCase):
    def test_retries_then_succeeds_and_then_gives_up_loudly(self):
        calls = []

        class Resp:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self): return "zażółć".encode()

        def flaky(req, timeout):
            calls.append(1)
            if len(calls) < 3:
                raise OSError("reset")
            return Resp()

        with mock.patch.object(rcb.time, "sleep"), mock.patch.object(rcb.urllib.request, "urlopen", flaky):
            self.assertEqual(rcb.fetch("https://x/y"), "zażółć")
            self.assertEqual(len(calls), 3)
        with mock.patch.object(rcb.time, "sleep"), mock.patch.object(
                rcb.urllib.request, "urlopen", mock.Mock(side_effect=OSError("down"))):
            with self.assertRaisesRegex(RuntimeError, "fetch failed: https://x/y: down"):
                rcb.fetch("https://x/y")


if __name__ == "__main__":
    unittest.main()
