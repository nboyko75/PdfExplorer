"""Batch selection and submission checks without sending jobs to a printer."""
import importlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz

from common import menu_utils
from controls import filelist, print_form
from localization import DEFAULT_TRANSLATIONS, available_locales


class BatchPrintTests(unittest.TestCase):
    def test_descending_order_label_is_translated_in_every_locale(self):
        for locale in available_locales():
            with self.subTest(locale=locale):
                translations = importlib.import_module(f"localization.localization_{locale}").TRANSLATIONS
                if locale == "en":
                    self.assertEqual(translations.get("print_descending_order", DEFAULT_TRANSLATIONS["print_descending_order"]),
                                     "In descending order")
                    continue
                self.assertTrue(translations["print_descending_order"].strip())
                self.assertNotEqual(translations["print_descending_order"], "In descending order")

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = [str(Path(directory.name) / name) for name in ("first.pdf", "second.pdf", "third.pdf")]
        for path, count in zip(self.paths, (3, 2, 1)):
            with fitz.open() as document:
                for _ in range(count):
                    document.new_page()
                document.save(path)

    def test_selection_enables_print_in_menu_and_toolbar(self):
        owner = SimpleNamespace(list=Mock(), path_box=Mock(), list_print_btn=Mock())
        context = menu_utils._build_menu_command_context(owner, selected_paths=self.paths)
        self.assertTrue(menu_utils.FILE_COMMANDS["print"].can_execute(context))
        with patch.object(filelist, "get_selected_list_paths", return_value=self.paths):
            filelist.update_list_toolbar_buttons(owner)
        owner.list_print_btn.Enable.assert_called_once_with(True)
        for paths in ([], [str(Path(self.paths[0]).parent)], [self.paths[0], "missing.pdf"]):
            context.selected_paths = paths
            self.assertFalse(menu_utils.FILE_COMMANDS["print"].can_execute(context))

    def test_list_action_passes_entire_selection_instead_of_preview(self):
        owner = SimpleNamespace(current_preview_path="unrelated.pdf")
        with patch.object(filelist, "get_selected_list_paths", return_value=self.paths), \
                patch.object(print_form, "show_print_form") as show:
            filelist.on_list_print(owner, None)
        show.assert_called_once_with(owner, self.paths)

    def test_batch_submits_in_selection_order_with_shared_options(self):
        with patch.object(print_form, "_print_with_selected_printer", return_value="Printer") as submit:
            result = print_form._execute_print_request(self.paths[:2], "Printer", copies=3,
                                                       is_selected_pages=True, page_text="2,1")
        self.assertEqual(result, "Printer")
        self.assertEqual([call.args for call in submit.call_args_list],
                         [(path, "Printer") for path in self.paths[:2]])
        for call in submit.call_args_list:
            self.assertEqual(call.kwargs, dict(copies=3, page_numbers=[1, 0], duplex=1))

    def test_batch_keeps_office_and_excel_preparation(self):
        word = str(Path(self.paths[0]).with_suffix(".docx"))
        excel = str(Path(self.paths[0]).with_suffix(".xlsx"))
        Path(word).touch()
        Path(excel).touch()
        layout = {"orientation": 2}
        with patch.object(print_form, "_print_with_selected_printer", return_value="Printer") as submit, \
                patch.object(print_form, "_export_excel_active_sheet", return_value=(self.paths[0], layout)) as export:
            print_form._execute_print_request([word, excel], "Printer", copies=2)
        export.assert_called_once_with(excel)
        self.assertEqual(submit.call_args_list[0].args, (word, "Printer"))
        self.assertEqual(submit.call_args_list[1].args, (self.paths[0], "Printer"))
        self.assertEqual(submit.call_args_list[1].kwargs["page_setup"], layout)

    def test_missing_file_is_detected_before_first_submission(self):
        Path(self.paths[1]).unlink()
        with patch.object(print_form, "_print_with_selected_printer") as submit:
            with self.assertRaises(FileNotFoundError):
                print_form._execute_print_request(self.paths, "Printer")
        submit.assert_not_called()

    def test_failure_names_file_and_stops_remaining_files(self):
        with patch.object(print_form, "_print_with_selected_printer",
                          side_effect=["Printer", OSError("offline")]) as submit:
            with self.assertRaisesRegex(RuntimeError, "second.pdf: offline"):
                print_form._execute_print_request(self.paths, "Printer")
        self.assertEqual(submit.call_count, 2)

    def test_page_range_is_validated_against_each_document(self):
        with patch.object(print_form, "_print_with_selected_printer", return_value="Printer") as submit:
            with self.assertRaisesRegex(RuntimeError, "second.pdf"):
                print_form._execute_print_request(self.paths, "Printer", is_selected_pages=True, page_text="3")
        submit.assert_called_once_with(self.paths[0], "Printer", copies=1, page_numbers=[2], duplex=1)

    def test_manual_duplex_prompts_identify_file_and_cancellation_stops_batch(self):
        confirm = Mock(side_effect=[True, False])

        def manual(path, printer, **options):
            self.assertEqual(options["duplex"], 3)
            self.assertEqual(options["copies"], 2)
            return printer if options["confirm_reload"]("Reload sheets") else None

        with patch.object(print_form, "_print_manual_duplex", side_effect=manual) as submit:
            result = print_form._execute_print_request(self.paths, "Printer", duplex=3, copies=2,
                                                       confirm_reload=confirm)
        self.assertIsNone(result)
        self.assertEqual(submit.call_count, 2)
        self.assertEqual([call.args[0] for call in confirm.call_args_list],
                         ["first.pdf\n\nReload sheets", "second.pdf\n\nReload sheets"])

    def test_closing_form_stops_batch_after_current_submission(self):
        connection = Mock()
        connection.poll.side_effect = [False, True]
        connection.recv.side_effect = EOFError
        with patch.object(print_form, "_print_with_selected_printer", return_value="Printer") as submit:
            print_form._print_worker(connection, dict(document_path=self.paths, selected_printer="Printer"), {})
        submit.assert_called_once_with(self.paths[0], "Printer", copies=1, page_numbers=None, duplex=1)
        connection.send.assert_called_once_with(("done", None))


if __name__ == "__main__":
    unittest.main()
