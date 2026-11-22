import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import shelters  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "punkty_schronienia.csv"


class Parse(unittest.TestCase):
    def setUp(self):
        self.rows, self.skipped = shelters.parse(FIXTURE.read_text(encoding="utf-8"))

    def test_reads_points_and_skips_bad_coordinates(self):
        self.assertEqual(len(self.rows), 10)
        self.assertEqual(self.skipped, 2)  # one without coordinates, one at 0,0

    def test_row_fields_and_access_codes(self):
        nysa = next(r for r in self.rows if r[3] == "Nysa")
        self.assertEqual(nysa, [50.47912, 17.32245, "ul. Tadeusza Kościuszki 9, Nysa", "Nysa", 1])
        self.assertEqual(sorted({r[4] for r in self.rows}), [0, 1, 2])

    def test_rejects_unknown_columns(self):
        with self.assertRaises(ValueError):
            shelters.parse("a,b,c\n1,2,3\n")


class Build(unittest.TestCase):
    def test_cells_and_index(self):
        rows, skipped = shelters.parse(FIXTURE.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "shelters"
            self.assertTrue(shelters.write(str(out), rows, skipped, shelters.CSV_URL))
            index = json.loads((out / "index.json").read_text(encoding="utf-8"))
            self.assertEqual(index["count"], 10)
            self.assertEqual(index["license"], "CC BY 4.0")
            self.assertEqual(sum(c[0] for c in index["cells"].values()), 10)
            key = shelters.cell_of(50.47912, 17.32245)
            self.assertIn(key, index["cells"])
            tile = json.loads((out / "t" / f"{key}.json").read_text(encoding="utf-8"))
            self.assertIn("Nysa", [r[3] for r in tile])
            # the same data again changes nothing
            self.assertFalse(shelters.write(str(out), rows, skipped, shelters.CSV_URL))
            # a file with far fewer points is refused and the old cells stay
            with self.assertRaises(SystemExit):
                shelters.write(str(out), rows[:3], 0, shelters.CSV_URL)
            self.assertEqual(json.loads((out / "index.json").read_text(encoding="utf-8"))["count"], 10)

    def test_cell_of_handles_cell_edges(self):
        self.assertEqual(shelters.cell_of(52.0, 21.0), "208_84")
        self.assertEqual(shelters.cell_of(51.9999, 20.9999), "207_83")


if __name__ == "__main__":
    unittest.main()
