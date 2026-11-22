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
    # Poland, its neighbours and western Russia, where the routes start
    return 44.0 <= lat <= 62.0 and 12.0 <= lon <= 50.0


def in_poland(lat, lon):
    kaliningrad = lat >= 54.35 and 19.6 <= lon <= 22.9
    return 49.0 <= lat <= 54.9 and 14.1 <= lon <= 24.2 and not kaliningrad


LAUNCHERS = {"Russia", "Russia-Kaliningrad", "Belarus"}
TRANSIT = {"Ukraine", "Belarus", None}
# wording that makes a transit country the origin: «wleciała z Ukrainy», «nadleciał z Białorusi»
WRONG_ORIGIN = re.compile(r"\b(?:wleci\w*|nadleci\w*|przylecia\w*|odpalon\w*|wystrzelon\w*|przelot|wlot)\s+z\s+(?:Ukrainy|Białorusi)", re.I)


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

    def test_origin_is_the_launcher(self):
        # from = who launched it, via = whose airspace it crossed before Poland; Ukraine is never the
        # origin of a Russian missile or drone, only of its own air defence (Przewodów, 2022)
        for e in self.events:
            with self.subTest(e["id"]):
                for k in ("title_pl", "summary_pl", "route_note_pl"):
                    self.assertIsNone(WRONG_ORIGIN.search(e.get(k) or ""), k)
                for w in e.get("weapons", []):
                    self.assertIsNone(WRONG_ORIGIN.search(w["label_pl"]))
                    self.assertIn("via", w, "say which country it crossed, or null")
                    self.assertIn(w["via"], TRANSIT)
                    self.assertNotEqual(w["from"], w["via"])
                    if w.get("role") == "air_defense":
                        self.assertEqual(w["from"], "Ukraine")
                        self.assertEqual(e.get("attack_by"), "Russia")
                    else:
                        self.assertIn(w["from"], LAUNCHERS)
                    launch = w["launch"]
                    self.assertTrue(launch["area_pl"].strip())
                    self.assertIsInstance(launch["certain"], bool)
                    lat, lon = w["path"][0]
                    self.assertFalse(in_poland(lat, lon), "the route starts where it was launched")
                    if w["from"] == "Russia":
                        self.assertGreaterEqual(lon, 31.5, "a Russian launch starts in Russia")
                    if w["from"] == "Russia-Kaliningrad":
                        self.assertTrue(54.3 <= lat <= 55.3 and 19.6 <= lon <= 22.9)
                    if not launch["certain"] and w.get("role") != "air_defense":
                        self.assertRegex(e["route_note_pl"], r"umown", "an unnamed launch area is marked as assumed")

    def test_sources(self):
        for e in self.events:
            with self.subTest(e["id"]):
                self.assertGreaterEqual(len(e["sources"]), 1)
                for s in e["sources"]:
                    self.assertTrue(s["url"].startswith("https://"), s["url"])
                    self.assertTrue(s["title"].strip() and s["publisher"].strip())


if __name__ == "__main__":
    unittest.main()
