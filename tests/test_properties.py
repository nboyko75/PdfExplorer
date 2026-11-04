"""Properties command selection, native invocation and failure handling."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from file_operations import properties
from localization import available_locales


class PropertiesTests(unittest.TestCase):
    def context(self, paths, source="list", target=None):
        return SimpleNamespace(owner=None, source=source, selected_paths=paths,
                               target_path=target)

    def test_files_folders_and_tree_target(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "document.txt"
            file.touch()
            for path in (str(file), folder):
                self.assertEqual(properties.selected_path(self.context([path])), path)
            context = self.context([str(file)], source="tree", target=folder)
            self.assertEqual(properties.selected_path(context), folder)

    def test_invalid_selection_does_not_open_dialog(self):
        with tempfile.TemporaryDirectory() as folder:
            for paths in ([], [folder, folder], [None], [folder + "/missing"]):
                with self.subTest(paths=paths), mock.patch.object(properties, "open_properties") as launch:
                    properties.show_properties(self.context(paths))
                    launch.assert_not_called()

    def test_shell_receives_unicode_path_and_no_modal_owner(self):
        import pythoncom
        from win32com.shell import shell, shellcon
        path = os.path.abspath("\u0444\u0430\u0439\u043b with spaces.lnk")
        with mock.patch.object(pythoncom, "CoInitialize") as initialize, \
             mock.patch.object(pythoncom, "CoUninitialize") as uninitialize, \
             mock.patch.object(shell, "ShellExecuteEx") as execute:
            properties.open_properties(path)
        initialize.assert_called_once_with()
        uninitialize.assert_called_once_with()
        execute.assert_called_once_with(
            fMask=shellcon.SEE_MASK_INVOKEIDLIST | shellcon.SEE_MASK_FLAG_NO_UI,
            hwnd=0, lpVerb="properties", lpFile=path, nShow=1)

    def test_shell_failure_balances_com_and_reports_error(self):
        import pythoncom
        from win32com.shell import shell
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(pythoncom, "CoInitialize"), \
             mock.patch.object(pythoncom, "CoUninitialize") as uninitialize, \
             mock.patch.object(shell, "ShellExecuteEx", side_effect=OSError("denied")), \
             mock.patch.object(properties.wx, "MessageBox") as message:
            properties.show_properties(self.context([folder]))
            uninitialize.assert_called_once_with()
            self.assertIn(folder, message.call_args.args[0])
            self.assertIn("denied", message.call_args.args[0])

    def test_all_locales_have_properties_translations(self):
        for locale in available_locales():
            with self.subTest(locale=locale):
                values = importlib.import_module("localization.localization_" + locale).TRANSLATIONS
                self.assertTrue(values["context_properties"].strip())
                self.assertNotIn("?", values["context_properties"])
                message = values["properties_failed"].format(path="example.txt", error="denied")
                self.assertIn("example.txt", message)
                self.assertIn("denied", message)


if __name__ == "__main__":
    unittest.main()
