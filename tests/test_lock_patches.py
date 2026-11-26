import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import lock_patches

SAMPLE = """jobs:
  agent:
    steps:
      - name: Parse agent logs for step summary
        if: always()
        uses: actions/github-script@x
        with:
          script: |
            await main();
      - name: Next
        run: true
  conclusion:
"""


class LockPatchesTest(unittest.TestCase):
    def test_adds_continue_on_error_once(self):
        new, changed = lock_patches.patch(SAMPLE)
        self.assertTrue(changed)
        self.assertEqual(new.count("continue-on-error: true"), 1)
        self.assertIn("Parse agent logs for step summary\n        continue-on-error: true\n        if: always()", new)
        again, changed2 = lock_patches.patch(new)
        self.assertFalse(changed2)
        self.assertEqual(again, new)

    def test_repository_locks_are_patched(self):
        root = Path(__file__).resolve().parent.parent
        locks = sorted((root / ".github/workflows").glob("*.lock.yml"))
        unpatched = [p.name for p in locks if lock_patches.patch(p.read_text())[1]]
        self.assertEqual(unpatched, [], "run python3 scripts/lock_patches.py after gh aw compile")


if __name__ == "__main__":
    unittest.main()
