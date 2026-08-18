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

    def test_get_configurable_settings_excludes_window_geometry(self):
        settings = {
            "ui_locale": "uk",
            "window_position": [1, 2],
            "window_size": [800, 600],
            "options_form_position": [10, 20],
            "options_form_size": [920, 620],
            "show_hidden": False,
            "preview_enabled": True,
            "search_history": ["needle"],
            "list_sort_direction": 1,
        }

        rows = window_tools.get_configurable_settings_rows(settings)
        keys = [row["key"] for row in rows]

        self.assertIn("ui_locale", keys)
        self.assertIn("show_hidden", keys)
        self.assertIn("preview_enabled", keys)
        self.assertIn("search_history", keys)
        self.assertNotIn("window_position", keys)
        self.assertNotIn("window_size", keys)
        self.assertNotIn("options_form_position", keys)
        self.assertNotIn("options_form_size", keys)
        self.assertNotIn("list_sort_direction", keys)

    def test_optimize_pdf_color_quality_uses_defined_thresholds(self):
        self.assertEqual(window_tools._quality_label_to_value("low"), 20)
        self.assertEqual(window_tools._quality_label_to_value("medium"), 35)
        self.assertEqual(window_tools._quality_label_to_value("high"), 55)
        self.assertEqual(window_tools._quality_value_to_label(20), "low")
        self.assertEqual(window_tools._quality_value_to_label(35), "medium")
        self.assertEqual(window_tools._quality_value_to_label(55), "high")


if __name__ == "__main__":
    unittest.main()
