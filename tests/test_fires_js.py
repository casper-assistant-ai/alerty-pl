import subprocess
import unittest
from pathlib import Path

NODE_TEST = Path(__file__).resolve().parent / "fires.test.mjs"


class FiresLayers(unittest.TestCase):
    def test_node_suite(self):
        # the node test of fires() in docs/app.js runs with the Python suite, so CI covers it too
        result = subprocess.run(["node", "--test", NODE_TEST], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"\n{result.stdout}{result.stderr}")


if __name__ == "__main__":
    unittest.main()
