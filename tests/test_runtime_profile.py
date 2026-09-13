import unittest
from runtime.runtime_profile import get_profile

class TestRuntimeProfile(unittest.TestCase):
    def test_balanced_is_8gb_friendly(self):
        p = get_profile("balanced")
        self.assertEqual(p.max_workers, 4)
        self.assertLessEqual(p.analyst_tokens, 2000)
        self.assertEqual(p.factor_window, 60)

    def test_lite_is_smaller(self):
        p = get_profile("lite")
        b = get_profile("balanced")
        self.assertLessEqual(p.max_workers, b.max_workers)
        self.assertLess(p.factor_window, b.factor_window)

    def test_invalid_profile_falls_back(self):
        self.assertEqual(get_profile("not-a-profile").name, "balanced")

if __name__ == "__main__":
    unittest.main()
