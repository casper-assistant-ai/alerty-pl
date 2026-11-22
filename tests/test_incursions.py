"""docs/events/incursions.json: the hand-kept list of missiles and drones that entered Polish airspace.

The map page (docs/attacks.js) animates each case and marks its day red on the slider, so every
case must have a date, a route or a place inside the map, and at least one source with a link.
"""
import json
import re
import unittest
from datetime import date
from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "docs" / "events" / "incursions.json"
KINDS = {"missile", "drone"}
ENDS = {"explosion", "crash", "shotdown", "debris", "left_airspace", "not_found"}
POINTS = {"explosion", "crash", "shotdown", "debris"}


def inside(lat, lon):
    # Poland and its neighbours, where the routes start
    return 47.0 <= lat <= 57.0 and 12.0 <= lon <= 30.0


class Incursions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events = json.loads(FILE.read_text(encoding="utf-8"))["events"]

    def test_has_cases(self):
        self.assertGreaterEqual(len(self.events), 5)
        ids = [e["id"] for e in self.events]
        self.assertEqual(len(ids), len(set(ids)), "ids repeat")

    def test_each_case(self):
        for e in self.events:
            with self.subTest(e["id"]):
                self.assertTrue(re.fullmatch(r"\d{4}-\d\d-\d\d", e["date"]))
                self.assertLessEqual(date.fromisoformat(e["date"]), date.today())
                if e.get("time_local"):
                    self.assertTrue(re.fullmatch(r"\d\d:\d\d", e["time_local"]))
                self.assertTrue(e["title_pl"].strip() and e["summary_pl"].strip())
                self.assertTrue(e.get("weapons") or e.get("points"), "nothing to draw")
                for w in e.get("weapons", []):
                    self.assertIn(w["kind"], KINDS)
                    self.assertGreaterEqual(w.get("count", 1), 1)
                    self.assertGreaterEqual(len(w["path"]), 2, "a route needs two points")
                    for lat, lon in w["path"]:
                        self.assertTrue(inside(lat, lon), (lat, lon))
                    if w.get("end"):
                        self.assertIn(w["end"]["type"], ENDS)
                        if w["end"].get("lat") is not None:
                            self.assertTrue(inside(w["end"]["lat"], w["end"]["lon"]))
                for p in e.get("points", []):
                    self.assertIn(p["type"], POINTS)
                    self.assertTrue(inside(p["lat"], p["lon"]), p)
                    self.assertTrue(p["place"].strip())

    def test_sources(self):
        for e in self.events:
            with self.subTest(e["id"]):
                self.assertGreaterEqual(len(e["sources"]), 1)
                for s in e["sources"]:
                    self.assertTrue(s["url"].startswith("https://"), s["url"])
                    self.assertTrue(s["title"].strip() and s["publisher"].strip())


if __name__ == "__main__":
    unittest.main()
