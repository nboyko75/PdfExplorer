"""Verify submission and failures without sending anything to a physical printer."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import ImageWin

from controls import print_form


class PrintSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "document.pdf"
        with fitz.open() as document:
            for color in ((1, 0, 0), (0, 0, 1)):
                page = document.new_page(width=72, height=144)
                page.draw_rect(page.rect, color=color, fill=color)
            document.save(self.path)
        self.printer = Mock()
        self.mode = SimpleNamespace(Copies=7, Fields=0)
        self.printer.GetPrinter.return_value = {"pDevMode": self.mode}
        constants = print_form.win32con
        self.printer.GetDeviceCaps.side_effect = lambda dc, cap: {
            constants.HORZRES: 600, constants.VERTRES: 900,
            constants.LOGPIXELSX: 300, constants.LOGPIXELSY: 300,
        }[cap]
        self.gui = Mock()
        self.gui.CreateDC.return_value = 123
        self.colors = []
        self.dib = Mock()

        def capture_bitmap(bitmap):
            self.colors.append(bitmap.getpixel((bitmap.width // 2, bitmap.height // 2)))
            return self.dib

        self.addCleanup(patch.stopall)
        patch.object(print_form, "win32print", self.printer).start()
        patch.object(print_form, "win32gui", self.gui).start()
        patch.object(ImageWin, "Dib", side_effect=capture_bitmap).start()
        self.shell = patch.object(print_form.os, "startfile").start()

    def test_pdf_submits_collated_copies_to_selected_printer(self):
        result = print_form._print_with_selected_printer(str(self.path), "Selected printer", copies=2)
        self.assertEqual(result, "Selected printer")
        self.gui.CreateDC.assert_called_once_with("WINSPOOL", "Selected printer", self.mode)
        self.assertEqual(self.mode.Copies, 1)
        self.assertEqual(self.colors, [(255, 0, 0), (0, 0, 255)] * 2)
        self.printer.StartDoc.assert_called_once_with(123, ("document.pdf", None, None, 0))
        self.assertEqual(self.printer.StartPage.call_count, 4)
        self.assertEqual(self.printer.EndPage.call_count, 4)
        self.dib.draw.assert_called_with(123, (150, 150, 450, 750))
        self.printer.EndDoc.assert_called_once_with(123)
        self.printer.AbortDoc.assert_not_called()
        self.gui.DeleteDC.assert_called_once_with(123)
        self.printer.SetDefaultPrinter.assert_not_called()
        self.printer.SetPrinter.assert_not_called()
        self.shell.assert_not_called()

    def test_failed_submission_or_rendering_never_reports_success(self):
        for method in ("StartDoc", "StartPage", "EndPage", "EndDoc"):
            with self.subTest(method=method):
                self.printer.reset_mock(side_effect=False)
                self.gui.reset_mock()
                failing = getattr(self.printer, method)
                failing.side_effect = OSError("spooler failed")
                try:
                    with self.assertRaisesRegex(OSError, "spooler failed"):
                        print_form._print_with_selected_printer(str(self.path), "Selected printer")
                    self.gui.DeleteDC.assert_called_once_with(123)
                    if method == "StartDoc":
                        self.printer.AbortDoc.assert_not_called()
                    else:
                        self.printer.AbortDoc.assert_called_once_with(123)
                    self.shell.assert_not_called()
                finally:
                    failing.side_effect = None

    def test_drawing_failure_aborts_job(self):
        self.dib.draw.side_effect = OSError("render failed")
        with self.assertRaisesRegex(OSError, "render failed"):
            print_form._print_pdf_document(str(self.path), "Selected printer")
        self.printer.AbortDoc.assert_called_once_with(123)
        self.printer.EndDoc.assert_not_called()
        self.gui.DeleteDC.assert_called_once_with(123)

    def test_driver_failure_closes_printer_without_submitting(self):
        self.gui.CreateDC.side_effect = OSError("driver unavailable")
        with self.assertRaisesRegex(OSError, "driver unavailable"):
            print_form._print_pdf_document(str(self.path), "Selected printer")
        self.printer.ClosePrinter.assert_called_once_with(self.printer.OpenPrinter.return_value)
        self.printer.StartDoc.assert_not_called()

    def test_other_file_types_pass_selected_printer_to_shell(self):
        path = self.path.with_suffix(".txt")
        path.touch()
        with patch.object(print_form, "win32api") as api:
            print_form._print_with_selected_printer(str(path), "Selected printer")
            api.ShellExecute.assert_called_once_with(0, "printto", str(path), '"Selected printer"', ".", 0)
        self.printer.SetDefaultPrinter.assert_not_called()

    def test_office_all_pages_and_selected_pages_use_complete_pdf_export(self):
        for suffix in (".docx", ".pptx"):
            path = self.path.with_suffix(suffix)
            path.touch()
            for selection, expected in ((None, [(255, 0, 0), (0, 0, 255)]),
                                        ([1, 0], [(0, 0, 255), (255, 0, 0)])):
                with self.subTest(suffix=suffix, selection=selection), \
                        patch.object(print_form.office_preview, "get_office_document_page_count", return_value=2), \
                        patch.object(print_form.office_preview, "convert_office_to_preview_pdf", return_value=str(self.path)) as office, \
                        patch.object(print_form, "_get_print_temp_directory", return_value=self.temp.name):
                    self.colors.clear()
                    print_form._print_with_selected_printer(str(path), "Selected printer", copies=2,
                                                            page_numbers=selection)
                    office.assert_called_once_with(str(path), max_pages=2)
                    self.assertEqual(self.colors, expected * 2)
        self.shell.assert_not_called()
        self.printer.SetDefaultPrinter.assert_not_called()

    def test_empty_selection_never_submits_a_job(self):
        with patch.object(print_form, "_get_print_temp_directory", return_value=self.temp.name):
            with self.assertRaises(ValueError):
                print_form._print_with_selected_printer(str(self.path), "Selected printer", page_numbers=[])
        self.printer.StartDoc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
