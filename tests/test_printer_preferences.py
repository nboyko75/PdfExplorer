"""Printer preferences persist per printer without sending physical print jobs."""
from copy import deepcopy
import importlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from controls import print_form
import localization
import wx


class PrinterPreferencesTests(unittest.TestCase):
    def setUp(self):
        self.defaults = SimpleNamespace(Orientation=1, Duplex=1, Fields=0x1000, Copies=1,
                                        DriverData=b"defaults")
        self.saved = {}
        self.printer = Mock()
        self.printer.OpenPrinter.side_effect = lambda name: name
        self.printer.GetPrinter.side_effect = self.get_printer
        self.printer.SetPrinter.side_effect = self.set_printer
        self.printer.DocumentProperties.return_value = 1
        constants = SimpleNamespace(DM_IN_PROMPT=4, DM_OUT_BUFFER=2, DM_IN_BUFFER=8,
                                    IDOK=1, IDCANCEL=2, DM_DUPLEX=0x1000, DM_COPIES=0x100,
                                    DMDUP_SIMPLEX=1, DMDUP_VERTICAL=2, DMDUP_HORIZONTAL=3)
        self.addCleanup(patch.stopall)
        patch.object(print_form, "win32print", self.printer).start()
        patch.object(print_form, "win32con", constants).start()

    def get_printer(self, name, level):
        mode = self.saved.get(name) if level == 9 else self.defaults
        return {"pDevMode": deepcopy(mode)}

    def set_printer(self, name, level, info, command):
        self.assertEqual((level, command), (9, 0))
        self.saved[name] = deepcopy(info["pDevMode"])

    def test_confirmed_parameters_reopen_for_same_printer_only(self):
        def change_parameters(hwnd, handle, name, output, initial, flags):
            self.assertEqual(initial.Orientation, 1)
            output.Orientation = 2
            output.Duplex = 2
            output.DriverData = b"custom driver parameters"
            return 1

        self.printer.DocumentProperties.side_effect = change_parameters
        self.assertTrue(print_form._show_printer_properties("Printer One"))
        self.printer.DocumentProperties.side_effect = None

        self.assertTrue(print_form._show_printer_properties("Printer One"))
        initial = self.printer.DocumentProperties.call_args.args[4]
        self.assertEqual((initial.Orientation, initial.Duplex), (2, 2))
        self.assertEqual(initial.DriverData, b"custom driver parameters")

        self.assertTrue(print_form._show_printer_properties("Printer Two"))
        initial = self.printer.DocumentProperties.call_args.args[4]
        self.assertEqual((initial.Orientation, initial.Duplex), (1, 1))

    def test_cancel_preserves_saved_parameters(self):
        self.saved["Printer One"] = deepcopy(self.defaults)

        def cancel(hwnd, handle, name, output, initial, flags):
            output.Orientation = 2
            return 2

        self.printer.DocumentProperties.side_effect = cancel
        self.assertTrue(print_form._show_printer_properties("Printer One"))
        self.assertEqual(self.saved["Printer One"].Orientation, 1)
        self.printer.SetPrinter.assert_not_called()
        self.printer.ClosePrinter.assert_called_once_with("Printer One")

    def test_unavailable_user_preferences_fall_back_to_printer_defaults(self):
        self.printer.GetPrinter.side_effect = [OSError("No user preferences"),
                                              {"pDevMode": self.defaults}]
        self.assertTrue(print_form._show_printer_properties("Printer One"))
        self.assertEqual(self.saved["Printer One"], self.defaults)

    def test_missing_devmode_does_not_open_unsaveable_dialog(self):
        self.printer.GetPrinter.side_effect = None
        self.printer.GetPrinter.return_value = {"pDevMode": None}
        self.assertFalse(print_form._show_printer_properties("Printer One"))
        self.printer.DocumentProperties.assert_not_called()
        self.printer.SetPrinter.assert_not_called()
        self.printer.ClosePrinter.assert_called_once_with("Printer One")

    def test_driver_failure_does_not_save(self):
        self.printer.DocumentProperties.return_value = -1
        self.assertFalse(print_form._show_printer_properties("Printer One"))
        self.printer.SetPrinter.assert_not_called()
        self.printer.ClosePrinter.assert_called_once_with("Printer One")

    def test_save_failure_is_reported_and_handle_closed(self):
        self.printer.SetPrinter.side_effect = OSError("Access denied")
        self.assertFalse(print_form._show_printer_properties("Printer One"))
        self.printer.ClosePrinter.assert_called_once_with("Printer One")

    def test_each_print_side_mode_round_trips_without_losing_other_parameters(self):
        for duplex in (2, 3, 1):
            with self.subTest(duplex=duplex):
                print_form._set_printer_duplex("Printer One", duplex)
                self.assertEqual(print_form._get_printer_duplex("Printer One"), duplex)
                self.assertEqual(print_form._get_printer_duplex("Printer Two"), 1)
                self.assertEqual(self.saved["Printer One"].DriverData, b"defaults")
                self.assertEqual(self.saved["Printer One"].Orientation, 1)

    def test_simplex_only_printer_rejects_duplex_but_allows_simplex(self):
        self.defaults.Fields = 0
        print_form._set_printer_duplex("Printer One", 1)
        with self.assertRaises(ValueError):
            print_form._set_printer_duplex("Printer One", 2)
        self.printer.SetPrinter.assert_not_called()

    def test_driver_normalizing_duplex_to_simplex_does_not_save(self):
        def normalize(hwnd, handle, name, output, initial, flags):
            output.Duplex = 1
            return 1

        self.printer.DocumentProperties.side_effect = normalize
        with self.assertRaises(ValueError):
            print_form._set_printer_duplex("Printer One", 3)
        self.printer.SetPrinter.assert_not_called()
        self.printer.ClosePrinter.assert_called_once_with("Printer One")

    def test_duplex_applied_before_shell_and_office_handoff(self):
        def check_preferences(*args, **kwargs):
            self.assertEqual(self.saved["Printer One"].Duplex, 3)

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document.pdf"
            path.touch()
            with patch.object(print_form, "win32api", object()), \
                    patch.object(print_form.os, "startfile", side_effect=check_preferences) as shell, \
                    patch.object(print_form.office_preview, "can_preview_office", return_value=True), \
                    patch.object(print_form, "_print_office_document_pages", side_effect=check_preferences) as office:
                for copies in (2, 1):
                    print_form._print_with_selected_printer(str(path), "Printer One", copies=copies, duplex=3)
                    self.assertEqual(self.saved["Printer One"].Copies, copies)
                self.saved.clear()
                print_form._print_with_selected_printer(str(path), "Printer One", page_numbers=[0], duplex=3)
                self.assertEqual(shell.call_count, 2)
                office.assert_called_once()

    def test_form_preserves_manual_duplex_independently_of_driver_parameters(self):
        app = wx.App.Get() or wx.App(False)
        self.saved["Printer One"] = deepcopy(self.defaults)
        self.saved["Printer One"].Duplex = 2

        def select(choice, index):
            choice.SetSelection(index)
            event = wx.CommandEvent(wx.EVT_CHOICE.typeId, choice.GetId())
            event.SetEventObject(choice)
            choice.ProcessWindowEvent(event)

        def modal(dialog):
            choices = [child for child in dialog.GetChildren()[0].GetChildren() if isinstance(child, wx.Choice)]
            printer, duplex, multiple_pages, page_range = choices
            select(page_range, 1)
            panel = dialog.GetChildren()[0]
            for child in panel.GetChildren():
                if child.IsShown():
                    self.assertGreaterEqual(child.GetPosition().x, 0)
                    self.assertGreaterEqual(child.GetPosition().y, 0)
                    self.assertLessEqual(child.GetRect().right, panel.GetClientSize().width)
                    self.assertLessEqual(child.GetRect().bottom, panel.GetClientSize().height)
            self.assertEqual(duplex.GetSelection(), 1)
            self.assertTrue(multiple_pages.IsEnabled())
            select(multiple_pages, 1)
            select(duplex, 0)
            self.assertFalse(multiple_pages.IsEnabled())
            select(duplex, 2)
            self.assertTrue(multiple_pages.IsEnabled())
            self.assertEqual(multiple_pages.GetSelection(), 1)
            self.assertEqual(save_settings.call_args.args[0]["print_form_duplex_modes"]["Printer One"], 3)
            self.assertEqual(self.saved["Printer One"].Duplex, 2)
            select(printer, 1)
            self.assertEqual(duplex.GetSelection(), 0)
            self.assertFalse(multiple_pages.IsEnabled())
            select(printer, 0)
            self.assertEqual(duplex.GetSelection(), 2)
            self.assertTrue(multiple_pages.IsEnabled())
            self.saved["Printer One"].Duplex = 1
            button = next(child for child in dialog.GetChildren()[0].GetChildren()
                          if isinstance(child, wx.Button) and child.GetLabel() == localization.tr("print_parameters_button"))
            button.ProcessWindowEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId()))
            self.assertEqual(duplex.GetSelection(), 2)
            self.assertTrue(multiple_pages.IsEnabled())
            return wx.ID_CANCEL

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "document.pdf"
            path.touch()
            with patch.object(print_form, "_get_printer_names", return_value=["Printer One", "Printer Two"]), \
                    patch.object(print_form, "load_settings", return_value={"print_form_printer": "Printer One"}), \
                    patch.object(print_form, "update_settings") as save_settings, \
                    patch.object(print_form, "_save_print_form_geometry"), \
                    patch.object(print_form, "_show_printer_properties", return_value=True), \
                    patch.object(wx.Dialog, "ShowModal", modal):
                original_translations = localization.TRANSLATIONS.copy()
                try:
                    for locale in localization.available_locales():
                        with self.subTest(locale=locale):
                            localization.load_locale(locale)
                            self.saved["Printer One"].Duplex = 2
                            self.assertFalse(print_form.show_print_form(None, str(path)))
                finally:
                    localization.TRANSLATIONS.clear()
                    localization.TRANSLATIONS.update(original_translations)

    def test_print_side_labels_are_translated_in_every_locale(self):
        keys = ("print_duplex_label", "print_duplex_simplex", "print_duplex_long_edge",
                "print_duplex_short_edge", "print_duplex_unsupported", "print_parameters_error",
                "print_manual_title", "print_manual_reload", "print_manual_reload_long", "print_manual_reload_short")
        for locale in localization.available_locales():
            translations = (localization.DEFAULT_TRANSLATIONS if locale == "en" else
                            importlib.import_module("localization.localization_" + locale).TRANSLATIONS)
            for key in keys:
                with self.subTest(locale=locale, key=key):
                    self.assertTrue(translations[key])


if __name__ == "__main__":
    unittest.main()
