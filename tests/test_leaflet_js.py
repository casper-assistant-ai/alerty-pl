import subprocess
import unittest
from pathlib import Path

NODE_TEST = Path(__file__).resolve().parent / "leaflet.test.mjs"


class LeafletContent(unittest.TestCase):
    def test_node_suite(self):
        # the node test that pins Leaflet tooltip and popup content of docs/*.js runs with the Python
        # suite, so CI covers it too
        result = subprocess.run(["node", "--test", NODE_TEST], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"\n{result.stdout}{result.stderr}")


if __name__ == "__main__":
    unittest.main()
