import subprocess
import unittest
from pathlib import Path

NODE_TEST = Path(__file__).resolve().parent / "urls.test.mjs"


class UrlSinks(unittest.TestCase):
    def test_node_suite(self):
        # the node test that pins the https check of every navigation in docs/*.js runs with the Python
        # suite, so CI covers it too (h()'s href and src are covered by test_common_js.py)
        result = subprocess.run(["node", "--test", NODE_TEST], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, f"\n{result.stdout}{result.stderr}")


if __name__ == "__main__":
    unittest.main()
