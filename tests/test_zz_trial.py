import unittest


class CiDoctorTrial(unittest.TestCase):
    def test_fails_on_purpose(self):
        self.fail("deliberate failure: trial of the CI doctor on pull requests; this PR is closed unmerged")
