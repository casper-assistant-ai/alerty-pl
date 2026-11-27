import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import zai_gate as zg

SAMPLE = """---
on:
  schedule:
    - cron: "5 */2 * * *"
  workflow_dispatch:
if: ${{ github.event_name == 'workflow_dispatch' }}
permissions:
  contents: read
engine:
  id: claude
  env:
    ANTHROPIC_BASE_URL: https://api.z.ai/api/anthropic
---
body
"""


class Gate(unittest.TestCase):
    def test_every_zai_agent_has_the_current_gate(self):
        r = subprocess.run([sys.executable, "-I", "scripts/zai_gate.py", "--check"], cwd=ROOT,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_patch_keeps_the_old_condition_and_is_stable(self):
        once = zg.patch(SAMPLE, "pr-fixer")
        self.assertIn('LIMIT: "90"', once)
        self.assertIn("if: ${{ (github.event_name == 'workflow_dispatch') && "
                      "needs.pre_activation.outputs.zai_quota_result == 'success' }}", once)
        self.assertIn("continue-on-error: true", once)
        self.assertTrue(once.endswith("---\nbody\n"))
        self.assertIn('LIMIT: "60"', zg.patch(SAMPLE, "site-designer"))

    def test_lock_files_carry_the_gate(self):
        for md in zg.zai_agents():
            lock = (md.parent / (md.stem + ".lock.yml")).read_text()
            self.assertIn("id: zai_quota", lock, md.name)
            self.assertIn("zai_quota_result: ${{ steps.zai_quota.outcome }}", lock, md.name)


if __name__ == "__main__":
    unittest.main()
