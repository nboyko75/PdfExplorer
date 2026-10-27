"""Excel printing uses the active sheet and preserves its physical page layout."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import ImageWin
import wx

from controls import print_form


class ExcelPrintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "workbook.xlsx"
        self.path.touch()
        self.pdf = Path(self.temp.name) / "sheet.pdf"
        self.layout = {"orientation": 2, "paper_size": 9}
        self.sheet = Mock()
        self.sheet.PageSetup = SimpleNamespace(Orientation=2, PaperSize=9, LeftMargin=36, PrintArea="$A$1:$D$12",
                                               Zoom=False, FitToPagesWide=1, FitToPagesTall=0)
        self.workbook = Mock(ActiveSheet=self.sheet)
        self.app = Mock(Visible=True, DisplayAlerts=True)
        self.com = Mock()
        self.addCleanup(patch.stopall)
        patch.object(print_form.ctypes, "OleDLL", return_value=self.com).start()
        patch.object(print_form, "_get_print_temp_directory", return_value=self.temp.name).start()
        self.running = patch.object(print_form, "_get_running_print_office_document",
                                    return_value=(self.app, self.workbook)).start()
        self.owned = patch.object(print_form.office_preview, "preview_document").start()

    def create_pdf(self, path, **kwargs):
        with fitz.open() as document:
            for number in range(3):
                document.new_page(width=842, height=595).insert_text((36, 36), f"Active sheet {number + 1}")
            document.save(path)

    def test_open_workbook_exports_only_its_active_sheet_and_preserves_user_state(self):
        self.sheet.ExportAsFixedFormat.side_effect = lambda *args: self.create_pdf(args[1])
        output, layout = print_form._export_excel_active_sheet(str(self.path))
        self.assertEqual(layout, self.layout)
        self.sheet.ExportAsFixedFormat.assert_called_once_with(0, output, 0, False, False)
        self.workbook.ExportAsFixedFormat.assert_not_called()
        self.owned.assert_not_called()
        self.workbook.Close.assert_not_called()
        self.app.Quit.assert_not_called()
        self.assertTrue(self.app.Visible)
        self.assertTrue(self.app.DisplayAlerts)
        self.assertEqual((self.sheet.PageSetup.LeftMargin, self.sheet.PageSetup.Zoom,
                          self.sheet.PageSetup.FitToPagesWide), (36, False, 1))
        self.com.CoInitializeEx.assert_called_once_with(None, 2)
        self.com.CoUninitialize.assert_called_once()
        with fitz.open(output) as document:
            self.assertEqual(document.page_count, 3)
            self.assertIn("Active sheet", document[0].get_text())

    def test_closed_workbook_uses_saved_active_sheet_in_owned_session(self):
        self.running.return_value = (self.app, None)
        closed = []

        @contextmanager
        def session(*args):
            try:
                yield self.workbook
            finally:
                closed.append(True)

        self.owned.side_effect = session
        self.sheet.ExportAsFixedFormat.side_effect = lambda *args: self.create_pdf(args[1])
        print_form._export_excel_active_sheet(str(self.path))
        self.assertEqual(closed, [True])
        self.sheet.ExportAsFixedFormat.assert_called_once()
        self.app.Quit.assert_not_called()

    def test_export_failure_cleans_temp_and_leaves_open_workbook_alone(self):
        self.sheet.ExportAsFixedFormat.side_effect = RuntimeError("export failed")
        with self.assertRaisesRegex(RuntimeError, "export failed"):
            print_form._export_excel_active_sheet(str(self.path))
        self.assertEqual(list(Path(self.temp.name).glob("pdfexplorer_print_*.pdf")), [])
        self.workbook.Close.assert_not_called()
        self.app.Quit.assert_not_called()
        self.com.CoUninitialize.assert_called_once()

    def test_owned_sheet_restores_saved_print_area_if_excel_does_not_apply_it(self):
        self.running.return_value = (None, None)
        self.owned.return_value.__enter__.return_value = self.workbook
        self.sheet.PageSetup.PrintArea = ""
        self.sheet.Names = [SimpleNamespace(Name="'Active report'!Print_Area",
                                            RefersToRange=SimpleNamespace(Address="$B$2:$F$20"))]
        print_form._export_excel_active_sheet(str(self.path))
        self.assertEqual(self.sheet.PageSetup.PrintArea, "$B$2:$F$20")

    def test_selected_pages_come_from_active_sheet_and_keep_layout(self):
        self.create_pdf(self.pdf)
        with patch.object(print_form, "_export_excel_active_sheet", return_value=(str(self.pdf), self.layout)), \
                patch.object(print_form, "_print_pdf_document") as backend, \
                patch.object(print_form.office_preview, "convert_office_to_preview_pdf") as preview:
            print_form._print_with_selected_printer(str(self.path), "Printer", copies=2, page_numbers=[2, 0])
            preview.assert_not_called()
            self.assertEqual(backend.call_args.kwargs, {"copies": 2, "page_setup": self.layout})
            with fitz.open(backend.call_args.args[0]) as document:
                self.assertEqual([p.get_text().strip() for p in document], ["Active sheet 3", "Active sheet 1"])

    def test_manual_duplex_keeps_active_sheet_layout_on_both_passes(self):
        self.create_pdf(self.pdf)
        with patch.object(print_form, "_export_excel_active_sheet", return_value=(str(self.pdf), self.layout)), \
                patch.object(print_form, "_print_with_selected_printer") as backend, \
                patch.object(wx, "MessageBox", return_value=wx.OK):
            print_form._print_manual_duplex(str(self.path), "Printer")
            self.assertEqual(backend.call_count, 2)
            for call in backend.call_args_list:
                self.assertEqual(call.kwargs["page_setup"], self.layout)

    def test_printer_uses_sheet_paper_and_orientation_without_rescaling_margins(self):
        self.create_pdf(self.pdf)
        constants = print_form.win32con
        mode = SimpleNamespace(Copies=3, Orientation=1, PaperSize=1,
                               Fields=constants.DM_PAPERLENGTH | constants.DM_PAPERWIDTH)
        printer = Mock()
        printer.GetPrinter.return_value = {"pDevMode": mode}
        printer.DocumentProperties.return_value = constants.IDOK
        printer.GetDeviceCaps.side_effect = lambda dc, cap: {
            constants.HORZRES: 3300, constants.VERTRES: 2300,
            constants.LOGPIXELSX: 300, constants.LOGPIXELSY: 300,
            constants.PHYSICALOFFSETX: 50, constants.PHYSICALOFFSETY: 75,
        }[cap]
        gui = Mock()
        gui.CreateDC.return_value = 123
        with patch.object(print_form, "win32print", printer), \
                patch.object(print_form, "win32gui", gui), \
                patch.object(ImageWin, "Dib") as dib:
            print_form._print_pdf_document(str(self.pdf), "Printer", page_setup=self.layout)
            self.assertEqual((mode.Orientation, mode.PaperSize, mode.Copies), (2, 9, 1))
            self.assertFalse(mode.Fields & (constants.DM_PAPERLENGTH | constants.DM_PAPERWIDTH))
            dib.return_value.draw.assert_called_with(123, (-50, -75, round(842 * 300 / 72) - 50,
                                                           round(595 * 300 / 72) - 75))
            printer.SetPrinter.assert_not_called()
            printer.EndDoc.assert_called_once()

    def test_request_validates_pages_against_active_sheet_and_preserves_layout(self):
        self.create_pdf(self.pdf)
        for duplex in (1, 2):
            for page_text in ("3", "4"):
                settings = {"print_form_printer": "Printer", "print_form_page_range": "selection",
                            "print_form_page_numbers": page_text,
                            "print_form_duplex_modes": {"Printer": duplex},
                            "print_form_multiple_pages": "mirrored_margins"}
                with self.subTest(duplex=duplex, page_text=page_text), \
                        patch.object(print_form, "load_settings", return_value=settings), \
                        patch.object(print_form, "update_settings"), \
                        patch.object(print_form, "_save_print_form_geometry"), \
                        patch.object(print_form, "_get_printer_names", return_value=["Printer"]), \
                        patch.object(print_form, "_export_excel_active_sheet", return_value=(str(self.pdf), self.layout)) as export, \
                        patch.object(print_form, "_print_with_selected_printer", return_value="Printer") as direct, \
                        patch.object(print_form, "_print_manual_duplex", return_value="Printer") as manual:
                    request = dict(document_path=str(self.path), selected_printer="Printer",
                                   duplex=duplex, mirrored_margins=True,
                                   is_selected_pages=True, page_text=page_text)
                    if page_text == "4":
                        with self.assertRaises(ValueError):
                            print_form._execute_print_request(**request)
                        direct.assert_not_called()
                        manual.assert_not_called()
                    else:
                        result = print_form._execute_print_request(**request)
                        self.assertTrue(result)
                        backend = direct if duplex == 1 else manual
                        self.assertEqual(backend.call_args.kwargs["page_setup"], self.layout)
                    export.assert_called_once()


if __name__ == "__main__":
    unittest.main()
