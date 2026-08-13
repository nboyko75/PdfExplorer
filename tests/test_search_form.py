import os
import re
import shutil
import tempfile
import threading
import unittest

import fitz

from controls.search_form import (
    _collect_search_matches,
    _format_search_status,
    _get_stop_button_label,
    _normalize_file_mask,
    _restore_search_form_state,
    search_files,
)
from localization import load_locale, tr


class SearchFilesTests(unittest.TestCase):
    def setUp(self):
        load_locale("en")
        self.temp_dir = tempfile.mkdtemp(prefix="pdfexplorer-search-")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_search_text_matches_text_file(self):
        file_path = os.path.join(self.temp_dir, "demo.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("Needle in the haystack\n")

        matches = search_files("needle", self.temp_dir, mode="text", include_child_folders=True)

        self.assertEqual(len(matches), 1)
        self.assertEqual(os.path.basename(matches[0]), "demo.txt")

    def test_search_regex_matches_pdf_text(self):
        pdf_path = os.path.join(self.temp_dir, "report.pdf")
        document = fitz.open()
        page = document.new_page()
        page.insert_text((72, 72), "Invoice 12345")
        document.save(pdf_path)
        document.close()

        matches = search_files(r"Invoice\s+\d+", self.temp_dir, mode="regex", include_child_folders=True)

        self.assertEqual(len(matches), 1)
        self.assertEqual(os.path.basename(matches[0]), "report.pdf")

    def test_search_text_ignores_non_matching_file(self):
        file_path = os.path.join(self.temp_dir, "other.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("plain text")

        matches = search_files("needle", self.temp_dir, mode="text", include_child_folders=True)

        self.assertEqual(matches, [])

    def test_stop_button_label_is_used(self):
        self.assertEqual(_get_stop_button_label(), "Stop")

    def test_search_form_labels_are_localized_for_russian(self):
        load_locale("ru")
        self.assertEqual(tr("search_query_label"), "Текст или регулярное выражение")
        self.assertEqual(tr("search_stop_button"), "Стоп")
        self.assertEqual(tr("search_paused_status"), "Поиск остановлен")

    def test_status_bar_uses_current_file_folder_on_left(self):
        left, right = _format_search_status("C:/root/search", "C:/root/search/subdir/report.txt")
        self.assertEqual(left, "Folder: C:/root/search/subdir")
        self.assertEqual(right, "File: report.txt")

    def test_search_loop_stops_when_stop_event_is_set(self):
        first_path = os.path.join(self.temp_dir, "first.txt")
        second_path = os.path.join(self.temp_dir, "second.txt")
        with open(first_path, "w", encoding="utf-8") as handle:
            handle.write("needle\n")
        with open(second_path, "w", encoding="utf-8") as handle:
            handle.write("needle\n")

        stop_event = threading.Event()

        def stop_after_first_status(folder_name, file_name):
            if os.path.basename(file_name) == "first.txt":
                stop_event.set()

        matches = _collect_search_matches(
            "needle",
            self.temp_dir,
            mode="text",
            include_child_folders=True,
            stop_event=stop_event,
            on_status=stop_after_first_status,
        )

        self.assertLessEqual(len(matches), 1)

    def test_file_mask_adds_and_removes_office_extensions(self):
        self.assertEqual(_normalize_file_mask("*.txt *.doc?", True, False), "*.txt *.doc?")
        self.assertEqual(_normalize_file_mask("*.txt", True, True), "*.txt *.doc? *.xls?")
        self.assertEqual(_normalize_file_mask("*.txt *.xls? *.doc?", False, False), "*.txt")

    def test_restore_state_includes_case_sensitive_and_filter_blocks(self):
        state = _restore_search_form_state({
            "search_form_case_sensitive": False,
            "search_form_whole_word": True,
            "search_form_date_mode": 1,
            "search_form_date_from": "2024-01-15",
            "search_form_date_to": "2024-02-10",
            "search_form_size_mode": 1,
            "search_form_size_from": 128,
            "search_form_size_to": 2048,
        })

        self.assertFalse(state["case_sensitive"])
        self.assertTrue(state["whole_word"])
        self.assertEqual(state["date_mode"], 1)
        self.assertEqual(state["date_from"], "2024-01-15")
        self.assertEqual(state["date_to"], "2024-02-10")
        self.assertEqual(state["size_mode"], 1)
        self.assertEqual(state["size_from"], 128)
        self.assertEqual(state["size_to"], 2048)


if __name__ == "__main__":
    unittest.main()
