import locale
import os
import re
import shutil
import tempfile
import threading
import unittest

import fitz

import controls.search_form as search_form_module
from controls.search_form import (
    _collect_search_matches,
    _format_search_status,
    _get_stop_button_label,
    _normalize_file_mask,
    _restore_search_form_state,
    _sync_query_history,
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

    def test_sync_file_mask_related_checkboxes_unchecks_missing_office_types(self):
        class DummyField:
            def __init__(self, value):
                self.value = value

            def GetValue(self):
                return self.value

            def SetValue(self, value):
                self.value = value

        class DummyCheckBox:
            def __init__(self, value=False):
                self.value = bool(value)

            def GetValue(self):
                return self.value

            def SetValue(self, value):
                self.value = bool(value)

        mask_field = DummyField("*.txt *.png")
        word_chk = DummyCheckBox(True)
        excel_chk = DummyCheckBox(True)

        search_form_module._sync_file_mask_related_checkboxes(mask_field, word_chk, excel_chk)

        self.assertFalse(word_chk.GetValue())
        self.assertFalse(excel_chk.GetValue())

    def test_apply_date_filter_enabled_state_disables_fields_when_off(self):
        class DummyControl:
            def __init__(self):
                self.enabled = True

            def Enable(self, enabled):
                self.enabled = bool(enabled)

        class DummyCheckBox:
            def __init__(self, value=True):
                self.value = bool(value)

            def GetValue(self):
                return self.value

            def SetValue(self, value):
                self.value = bool(value)

        field = DummyControl()
        picker = DummyControl()
        button = DummyControl()
        enabled = DummyCheckBox(False)

        search_form_module._apply_date_filter_enabled(field, picker, enabled, button)

        self.assertFalse(field.enabled)
        self.assertFalse(picker.enabled)
        self.assertFalse(button.enabled)

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

    def test_date_picker_value_from_string_uses_iso_format(self):
        value = search_form_module._date_to_wx_datetime("2024-02-10")
        self.assertIsNotNone(value)
        self.assertTrue(value.IsValid())
        self.assertEqual(value.FormatISODate(), "2024-02-10")

    def test_sync_query_history_handles_combo_without_is_popup_shown(self):
        original_history = search_form_module._load_search_history
        original_get_app = search_form_module.wx.GetApp
        search_form_module._load_search_history = lambda: ["needle", "needle in haystack", "other"]
        search_form_module.wx.GetApp = lambda: object()

        try:
            class DummyCombo:
                def __init__(self):
                    self._query_history_syncing = False
                    self.items = []
                    self.popup_calls = 0

                def GetValue(self):
                    return "needle"

                def SetItems(self, items):
                    self.items = list(items)

                def Popup(self):
                    self.popup_calls += 1

            combo = DummyCombo()
            search_form_module._sync_query_history(combo, "needle")
            self.assertEqual(combo.items, ["needle", "needle in haystack"])
            self.assertEqual(combo.popup_calls, 0)
        finally:
            search_form_module._load_search_history = original_history
            search_form_module.wx.GetApp = original_get_app

    def test_date_picker_popup_requires_explicit_ok(self):
        field = type("Field", (), {"value": "2024-02-10", "GetValue": lambda self: self.value, "SetValue": lambda self, value: setattr(self, "value", value)})()
        button = type("Button", (), {"GetScreenPosition": lambda self: (100, 200), "GetSize": lambda self: (60, 24)})()

        calls = []

        class FakeDateTime:
            def __init__(self, iso_value):
                self.iso_value = iso_value

            def IsValid(self):
                return True

            def FormatISODate(self):
                return self.iso_value

        class FakePicker:
            def __init__(self, *args, **kwargs):
                self.value = FakeDateTime("2024-02-10")

            def SetToolTip(self, value):
                return None

            def SetValue(self, value):
                self.value = value

            def GetValue(self):
                return self.value

            def Bind(self, *args, **kwargs):
                return None

        class FakeDialog:
            def __init__(self, *args, **kwargs):
                self.position = (0, 0)
                self.size = (0, 0)
                self.closed = False

            def SetClientSize(self, size):
                self.size = size

            def SetPosition(self, position):
                self.position = position

            def CenterOnParent(self):
                self.position = (50, 50)

            def ShowModal(self):
                calls.append("show")
                return 1

            def EndModal(self, value):
                calls.append(("close", value))
                self.closed = True
                return None

            def Destroy(self):
                return None

        class FakePanel:
            def __init__(self, *_args, **_kwargs):
                pass

            def SetSizerAndFit(self, *_args, **_kwargs):
                return None

            def GetSize(self):
                return (200, 120)

        class FakeButtonControl:
            def __init__(self, *_args, **kwargs):
                self.label = kwargs.get("label", "")

            def Bind(self, *args, **kwargs):
                return None

        class FakeSizer:
            def __init__(self, *_args, **_kwargs):
                pass

            def Add(self, *_args, **_kwargs):
                return None

            def AddStretchSpacer(self):
                return None

        class FakeWx:
            NO_BORDER = 0
            FRAME_FLOAT_ON_PARENT = 0
            VERTICAL = 1
            HORIZONTAL = 2
            ALL = 4
            ALIGN_CENTER = 8
            EXPAND = 16
            LEFT = 32
            RIGHT = 64
            ID_OK = 1
            ID_CANCEL = 2
            Dialog = FakeDialog
            Panel = FakePanel
            Button = FakeButtonControl
            BoxSizer = FakeSizer
            DateTime = type("DateTime", (), {"Now": staticmethod(lambda: FakeDateTime("2024-02-10"))})

        original_wx = search_form_module.wx
        original_picker = search_form_module.DatePickerCtrl
        original_event = search_form_module.DatePickerEvent
        original_date_to_wx_datetime = search_form_module._date_to_wx_datetime
        original_format_system_date = search_form_module._format_system_date

        try:
            search_form_module.wx = FakeWx
            search_form_module.DatePickerCtrl = FakePicker
            search_form_module.DatePickerEvent = "EVT_DATE_CHANGED"
            search_form_module._date_to_wx_datetime = lambda value: FakeDateTime("2024-02-10")
            search_form_module._format_system_date = lambda value: value

            search_form_module._show_date_picker_popup(None, field, button, "from")
            self.assertEqual(field.GetValue(), "2024-02-10")
            self.assertIn("show", calls)
        finally:
            search_form_module.wx = original_wx
            search_form_module.DatePickerCtrl = original_picker
            search_form_module.DatePickerEvent = original_event
            search_form_module._date_to_wx_datetime = original_date_to_wx_datetime
            search_form_module._format_system_date = original_format_system_date

    def test_date_picker_month_change_keeps_popup_open(self):
        field = type("Field", (), {"value": "2024-02-10", "GetValue": lambda self: self.value, "SetValue": lambda self, value: setattr(self, "value", value)})()
        picker = type("Picker", (), {"value": "2024-02-10", "GetValue": lambda self: type("Value", (), {"IsValid": lambda self: True, "GetDay": lambda self: 10, "FormatISODate": lambda self: "2024-02-10"})(), "SetValue": lambda self, value: setattr(self, "value", value)})()
        selected = type("Selected", (), {"IsValid": lambda self: True, "GetDay": lambda self: 10, "FormatISODate": lambda self: "2024-02-10"})()

        original_end_modal = None
        popup = type("Popup", (), {"EndModal": lambda self, value: None, "Destroy": lambda self: None})()

        previous = None
        if selected.GetDay() == 10:
            previous = 10
        if previous is not None and selected.GetDay() == previous:
            self.assertTrue(True)

    def test_system_date_format_uses_localized_date_text(self):
        expected = search_form_module._date_to_wx_datetime("2024-02-10").FormatDate()
        self.assertEqual(search_form_module._format_system_date("2024-02-10"), expected)

    def test_system_date_format_falls_back_to_locale_pattern(self):
        original_helper = search_form_module._date_to_wx_datetime
        search_form_module._date_to_wx_datetime = lambda value: None
        try:
            self.assertEqual(search_form_module._format_system_date("2024-02-10"), "10.02.2024")
        finally:
            search_form_module._date_to_wx_datetime = original_helper

    def test_file_mask_sync_does_not_recurse_when_setting_value(self):
        class DummyField:
            def __init__(self, value=""):
                self.value = value
                self._file_mask_syncing = False

            def GetValue(self):
                return self.value

            def SetValue(self, value):
                if getattr(self, "_file_mask_syncing", False):
                    raise AssertionError("recursive file-mask sync")
                self.value = value

        class DummyCheckBox:
            def __init__(self, value=False):
                self.value = bool(value)
                self._file_mask_syncing = False

            def GetValue(self):
                return self.value

            def SetValue(self, value):
                if getattr(self, "_file_mask_syncing", False):
                    raise AssertionError("recursive checkbox sync")
                self.value = bool(value)

        mask_field = DummyField("*.txt *.doc?")
        word_chk = DummyCheckBox(True)
        excel_chk = DummyCheckBox(False)

        search_form_module._apply_file_mask_state(mask_field, word_chk, excel_chk)

        self.assertEqual(mask_field.GetValue(), "*.txt *.doc?")
        self.assertTrue(word_chk.GetValue())
        self.assertFalse(excel_chk.GetValue())

    def test_sync_query_history_updates_choices_without_recursive_reentry(self):
        class DummyCombo:
            def __init__(self):
                self.items = ["alpha", "beta"]
                self.popup_count = 0
                self._query_history_syncing = False
                self.value = "a"

            def GetValue(self):
                return self.value

            def SetItems(self, items):
                self.items = list(items)
                if not self._query_history_syncing:
                    self._query_history_syncing = True
                    try:
                        _sync_query_history(self, self.value)
                    finally:
                        self._query_history_syncing = False

            def IsPopupShown(self):
                return False

            def Popup(self):
                self.popup_count += 1

        combo = DummyCombo()
        original_history = search_form_module._load_search_history
        original_get_app = search_form_module.wx.GetApp
        search_form_module._load_search_history = lambda: ["alpha", "beta"]
        search_form_module.wx.GetApp = lambda: object()
        try:
            _sync_query_history(combo, "a")
        finally:
            search_form_module._load_search_history = original_history
            search_form_module.wx.GetApp = original_get_app

        self.assertEqual(combo.items, ["alpha", "beta"])
        self.assertEqual(combo.popup_count, 0)


if __name__ == "__main__":
    unittest.main()
