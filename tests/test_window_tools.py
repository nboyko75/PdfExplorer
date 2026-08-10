import os
import sys
import unittest
from unittest import mock

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import controls.window_tools as window_tools


class WindowToolsSettingsPathTests(unittest.TestCase):
    def test_settings_file_is_stored_in_project_root(self):
        settings_path = window_tools._get_settings_file_path()
        self.assertEqual(os.path.dirname(settings_path), PROJECT_ROOT)
        self.assertTrue(settings_path.endswith(".pdf_explorer_settings.json"))

    def test_settings_file_is_stored_next_to_executable_when_frozen(self):
        fake_executable = os.path.join(PROJECT_ROOT, "dist", "PdfExplorer.exe")
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "executable", fake_executable):
            settings_path = window_tools._get_settings_file_path()

        self.assertEqual(os.path.dirname(settings_path), os.path.dirname(fake_executable))
        self.assertTrue(settings_path.endswith(".pdf_explorer_settings.json"))


if __name__ == "__main__":
    unittest.main()
