import os
import sys
import unittest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import controls.window_tools as window_tools


class WindowToolsSettingsPathTests(unittest.TestCase):
    def test_settings_file_is_stored_in_project_root(self):
        settings_path = window_tools._get_settings_file_path()
        self.assertEqual(os.path.dirname(settings_path), PROJECT_ROOT)
        self.assertTrue(settings_path.endswith(".pdf_explorer_settings.json"))


if __name__ == "__main__":
    unittest.main()
