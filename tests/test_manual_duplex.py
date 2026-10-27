"""Exercise real duplex PDFs while mocking printer handoff and confirmation."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
import wx
from PIL import Image

from controls import print_form


class ManualDuplexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.pdf"
        with fitz.open() as document:
            for number in range(1, 6):
                document.new_page(width=300, height=450).insert_text((40, 40), str(number))
            document.save(self.path)
        self.original = self.path.read_bytes()
        self.events = []
        self.jobs = []
        self.addCleanup(patch.stopall)
        patch.object(print_form, "_get_print_temp_directory", return_value=self.temp.name).start()
        self.print_job = patch.object(print_form, "_print_with_selected_printer", side_effect=self.handoff).start()
        self.confirm = patch.object(print_form.wx, "MessageBox", side_effect=self.confirm_reload).start()

    def handoff(self, path, printer, copies=1, duplex=None):
        self.assertEqual(printer, "Printer One")
        self.assertEqual((copies, duplex), (1, 1))
        with fitz.open(path) as document:
            self.jobs.append([page.get_text().strip() for page in document])
        self.events.append("print")
        return printer

    def confirm_reload(self, message, title, style):
        self.assertEqual(self.events, ["print"])
        self.assertTrue(style & wx.CANCEL)
        self.events.append("confirm")
        return wx.OK

    def run_print(self, **kwargs):
        return print_form._print_manual_duplex(str(self.path), "Printer One", **kwargs)

    def test_odd_pages_then_confirmation_then_even_pages_with_blank_last_back(self):
        self.assertEqual(self.run_print(), "Printer One")
        self.assertEqual(self.jobs, [["1", "3", "5"], ["2", "4", ""]])
        self.assertEqual(self.events, ["print", "confirm", "print"])
        self.assertEqual(self.path.read_bytes(), self.original)
        for call in self.print_job.call_args_list:
            self.assertTrue(Path(call.args[0]).exists())

    def test_cancel_after_fronts_does_not_print_backs(self):
        self.confirm.side_effect = None
        self.confirm.return_value = wx.CANCEL
        self.assertIsNone(self.run_print())
        self.assertEqual(self.jobs, [["1", "3", "5"]])

    def test_multiple_copies_keep_blank_backs_between_copies(self):
        self.run_print(copies=2)
        self.assertEqual(self.jobs, [["1", "3", "5", "1", "3", "5"],
                                     ["2", "4", "", "2", "4", ""]])

    def test_selected_pages_keep_requested_order_and_exclude_unselected_pages(self):
        self.run_print(page_numbers=[4, 0, 3, 1])
        self.assertEqual(self.jobs, [["5", "4"], ["1", "2"]])

    def test_single_page_selection_needs_no_reload(self):
        self.run_print(page_numbers=[2], copies=2)
        self.assertEqual(self.jobs, [["3", "3"]])
        self.confirm.assert_not_called()

    def test_short_edge_instructions_differ_from_long_edge(self):
        self.run_print(duplex=3)
        self.assertIn(print_form.tr("print_manual_reload_short"), self.confirm.call_args.args[0])
        self.assertNotIn(print_form.tr("print_manual_reload_long"), self.confirm.call_args.args[0])

    def test_first_pass_failure_does_not_prompt_or_submit_backs(self):
        self.print_job.side_effect = RuntimeError("Print failed")
        with self.assertRaises(RuntimeError):
            self.run_print()
        self.confirm.assert_not_called()
        self.print_job.assert_called_once()

    def test_invalid_selection_never_prints(self):
        for pages in ([], [5], [-1]):
            with self.subTest(pages=pages), self.assertRaises(ValueError):
                self.run_print(page_numbers=pages)
        self.print_job.assert_not_called()

    def test_office_exports_all_pages_before_splitting(self):
        with patch.object(print_form.office_preview, "can_preview_office", return_value=True), \
                patch.object(print_form.office_preview, "get_office_document_page_count", return_value=5), \
                patch.object(print_form.office_preview, "convert_office_to_preview_pdf", return_value=str(self.path)) as convert:
            print_form._print_manual_duplex("document.docx", "Printer One")
            convert.assert_called_once_with("document.docx", max_pages=5)
        self.assertEqual(self.jobs, [["1", "3", "5"], ["2", "4", ""]])

    def test_multipage_image_is_split_into_pdf_passes(self):
        path = Path(self.temp.name) / "scan.tiff"
        with Image.new("RGB", (100, 200), "red") as first, Image.new("RGB", (100, 200), "blue") as second:
            first.save(path, save_all=True, append_images=[second])
        front, back = print_form._create_manual_duplex_passes(str(path))
        for pdf, expected in ((front, (255, 0, 0)), (back, (0, 0, 255))):
            with fitz.open(pdf) as document:
                self.assertEqual(document.page_count, 1)
                pix = document[0].get_pixmap()
                self.assertEqual(pix.pixel(pix.width // 2, pix.height // 2), expected)

    def test_form_restores_saved_side_option_and_dispatches_manual_printing(self):
        app = wx.App.Get() or wx.App(False)
        for mode in (1, 2, 3):
            with self.subTest(mode=mode):
                settings = {"print_form_printer": "Printer One",
                            "print_form_duplex_modes": {"Printer One": mode}}

                def modal(dialog):
                    choices = [child for child in dialog.GetChildren()[0].GetChildren()
                               if isinstance(child, wx.Choice)]
                    self.assertEqual(choices[1].GetSelection(), mode - 1)
                    return wx.ID_OK

                with patch.object(print_form, "load_settings", return_value=settings), \
                        patch.object(print_form, "update_settings") as save, \
                        patch.object(print_form, "_get_printer_names", return_value=["Printer One"]), \
                        patch.object(print_form, "_save_print_form_geometry"), \
                        patch.object(print_form, "_print_manual_duplex", return_value=None) as manual, \
                        patch.object(print_form, "_print_with_selected_printer", return_value="Printer One") as direct, \
                        patch.object(print_form, "_PrintJob") as job, \
                        patch.object(wx, "MessageBox") as message:
                    dialog = print_form.show_print_form(None, str(self.path))
                    try:
                        modal(dialog)
                        dialog.ProcessWindowEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, wx.ID_OK))
                        result = print_form._execute_print_request(**job.call_args.args[0])
                    finally:
                        dialog.Close()
                    self.assertEqual(save.call_args.args[0]["print_form_duplex_modes"]["Printer One"], mode)
                    if mode == 1:
                        self.assertTrue(result)
                        direct.assert_called_once_with(str(self.path), "Printer One", copies=1,
                                                       page_numbers=None, duplex=1)
                        manual.assert_not_called()
                    else:
                        # Cancellation between passes must not report success.
                        self.assertFalse(result)
                        manual.assert_called_once_with(str(self.path), "Printer One", copies=1,
                                                       page_numbers=None, duplex=mode, confirm_reload=None)
                        direct.assert_not_called()
                        message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
