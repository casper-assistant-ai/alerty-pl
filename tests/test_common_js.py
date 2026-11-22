import subprocess
import unittest
from pathlib import Path

NODE_TEST = Path(__file__).resolve().parent / "common.test.mjs"


class CommonJsHelpers(unittest.TestCase):
    def test_node_suite(self):
        # the node test of docs/common.js runs with the Python suite, so CI covers it
        result = subprocess.run(["node", "--test", NODE_TEST], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"\n{result.stdout}{result.stderr}")


if __name__ == "__main__":
    unittest.main()
