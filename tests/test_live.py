"""Tests of the live service's pure logic (server/core.py): who gets an alert and what it says."""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "server"))
import core  # noqa: E402


def alert(cat="air", vs=("lubelskie",), whole=(), updates=1, status="active"):
    ups = [{"time": None, "message": f"komunikat {i}", "ended": False} for i in range(updates)]
    return {"id": "a1", "title": "Alert RCB - test", "category": cat, "status": status, "url": "https://www.gov.pl/x",
            "updates": ups, "regions": {"voivodeships": list(vs), "powiaty": [], "whole": list(whole)}}


class Prefs(unittest.TestCase):
    def test_clean_drops_unknown_and_types(self):
        p = core.clean_prefs({"voivodeships": ["mazowieckie", "atlantyda", 5, "mazowieckie"], "drills": 1})
        self.assertEqual(p, {"voivodeships": ["mazowieckie"], "drills": True})
        self.assertEqual(core.clean_prefs("x"), {"voivodeships": [], "drills": False})
        self.assertEqual(core.clean_prefs({"voivodeships": "mazowieckie"})["voivodeships"], [])

    def test_email(self):
        self.assertTrue(core.valid_email("a.b@example.pl"))
        for bad in ("a@b", "<a@b.pl>", "a b@c.pl", "x" * 70 + "@c.pl", None):
            self.assertFalse(core.valid_email(bad), bad)


class Matching(unittest.TestCase):
    def test_all_of_poland(self):
        self.assertTrue(core.matches({"voivodeships": []}, alert()))

    def test_voivodeship_filter(self):
        self.assertTrue(core.matches({"voivodeships": ["lubelskie"]}, alert()))
        self.assertFalse(core.matches({"voivodeships": ["pomorskie"]}, alert()))

    def test_whole_country_and_unknown_area_always_go(self):
        self.assertTrue(core.matches({"voivodeships": ["pomorskie"]}, alert(vs=(), whole=("Polska",))))
        self.assertTrue(core.matches({"voivodeships": ["pomorskie"]}, alert(vs=())))

    def test_drills_only_when_asked(self):
        self.assertFalse(core.matches({"voivodeships": [], "drills": False}, alert(cat="drill")))
        self.assertTrue(core.matches({"voivodeships": [], "drills": True}, alert(cat="drill")))

    def test_test_alert_goes_to_everyone(self):
        t = core.test_alert("2026-11-22T08:00:00+01:00")
        self.assertTrue(core.matches({"voivodeships": ["pomorskie"], "drills": False}, t))


class Changes(unittest.TestCase):
    def test_diff(self):
        self.assertEqual(core.diff(None, alert()), "new")
        self.assertIsNone(core.diff(alert(), alert()))
        self.assertEqual(core.diff(alert(), alert(updates=2)), "update")
        self.assertEqual(core.diff(alert(), alert(status="ended")), "update")
        self.assertIsNone(core.diff(alert(status="expired"), alert(status="ended")))

    def test_fewer_updates_is_a_bad_page_not_news(self):
        # 24.11.2026: a bad page parsed to 1 update, then the good one re-sent «Odwołanie» 30 times
        good = alert(updates=3, status="ended")
        bad = alert(updates=1, status="expired")
        self.assertTrue(core.regressed(good, bad))
        self.assertFalse(core.regressed(None, bad))
        self.assertFalse(core.regressed(bad, good))
        self.assertIsNone(core.diff(good, bad))


class Messages(unittest.TestCase):
    def test_message_has_category_area_text_and_link(self):
        subject, text, url = core.message(alert(updates=2), "new")
        self.assertEqual(subject, "Nowy alert: Zagrożenie z powietrza · woj. lubelskie")
        self.assertIn("komunikat 0", text)  # the newest update comes first
        self.assertEqual(url, "https://www.gov.pl/x")

    def test_cancellation_and_test_heads(self):
        self.assertTrue(core.message(alert(status="ended"), "update")[0].startswith("Odwołanie alertu"))
        self.assertTrue(core.message(core.test_alert("2026-11-22T08:00:00+01:00"), "test")[0].startswith("TEST"))

    def test_push_payload_is_small_json(self):
        p = json.loads(core.push_payload(alert(), "new"))
        self.assertEqual(set(p), {"title", "body", "url", "tag", "kind"})
        self.assertLess(len(core.push_payload(alert(), "new").encode()), 3000)


if __name__ == "__main__":
    unittest.main()
