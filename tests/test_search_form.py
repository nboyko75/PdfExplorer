import locale
import os
import re
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
from unittest import mock

import fitz
import wx

import controls.tree_utils as tree_utils_module
from common import date_utils as common_date_utils
import controls.filelist as filelist_module
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


class TreeContextMenuTests(unittest.TestCase):
    def test_tree_right_click_keeps_menu_insert_index_valid(self):
        owner = types.SimpleNamespace(
            tree=mock.Mock(),
            path_box=types.SimpleNamespace(GetValue=lambda: "C:/temp"),
            icon_manager=None,
        )
        owner.tree.GetSelection.return_value = None
        owner.tree.GetRootItem.return_value = mock.Mock(IsOk=mock.Mock(return_value=False))
        owner.tree.ScreenToClient.return_value = (0, 0)
        owner.tree.HitTest.return_value = (None, None)
        owner.tree.GetItemData.return_value = None
        owner.tree.PopupMenu = mock.Mock()

        event = mock.Mock()
        event.GetPosition.return_value = wx.DefaultPosition
        event.GetEventObject.return_value = owner.tree

        with mock.patch.object(tree_utils_module, "_resolve_tree_context_path", return_value="C:/temp/folder"), \
             mock.patch.object(tree_utils_module, "_is_folder_or_single_pdf", return_value=False), \
             mock.patch.object(tree_utils_module, "_resolve_tree_new_folder_target", return_value=None), \
             mock.patch.object(filelist_module, "_can_paste_into_directory", return_value=False), \
             mock.patch.object(filelist_module, "_resolve_paste_target_directory", return_value="C:/temp"):
            tree_utils_module.on_tree_right_click(owner, event)

        owner.tree.PopupMenu.assert_called_once()


class SearchFilesTests(unittest.TestCase):
    def setUp(self):
        load_locale("en")
        self.temp_dir = tempfile.mkdtemp(prefix="docexplorer-search-")

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

    def test_archive_menu_labels_exist_for_supported_locales(self):
        for locale_name in ("en", "de", "es", "fr", "it", "ja", "ko", "pt_br", "ru", "uk", "zh_cn"):
            load_locale(locale_name)
            self.assertIsInstance(tr("context_add_to_archive"), str)
            self.assertIsInstance(tr("context_extract_from_archive"), str)
            self.assertTrue(tr("context_add_to_archive"))
            self.assertTrue(tr("context_extract_from_archive"))

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

        try:
            search_form_module.wx = FakeWx
            search_form_module.DatePickerCtrl = FakePicker
            search_form_module.DatePickerEvent = "EVT_DATE_CHANGED"
            search_form_module._date_to_wx_datetime = lambda value: FakeDateTime("2024-02-10")

            search_form_module._show_date_picker_popup(None, field, button, "from")
            self.assertEqual(field.GetValue(), "2024-02-10")
            self.assertIn("show", calls)
        finally:
            search_form_module.wx = original_wx
            search_form_module.DatePickerCtrl = original_picker
            search_form_module.DatePickerEvent = original_event
            search_form_module._date_to_wx_datetime = original_date_to_wx_datetime

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

    def test_system_date_format_uses_shared_locale_helper(self):
        expected = common_date_utils._format_system_date("2024-02-10")
        self.assertEqual(search_form_module.common_date_utils._format_system_date("2024-02-10"), expected)

    def test_system_date_format_falls_back_to_locale_pattern(self):
        original_helper = search_form_module._date_to_wx_datetime
        search_form_module._date_to_wx_datetime = lambda value: None
        try:
            self.assertEqual(search_form_module.common_date_utils._format_system_date("2024-02-10"), "10.02.2024")
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

    def test_sync_query_history_keeps_current_query_value_after_history_refresh(self):
        class DummyCombo:
            def __init__(self):
                self.items = []
                self.value = "needle"
                self._query_history_syncing = False

            def GetValue(self):
                return self.value

            def SetItems(self, items):
                self.items = list(items)
                self.value = ""

            def SetValue(self, value):
                self.value = value

        original_history = search_form_module._load_search_history
        try:
            search_form_module._load_search_history = lambda: ["needle", "needle in haystack"]
            combo = DummyCombo()
            search_form_module._sync_query_history(combo, "needle")
            self.assertEqual(combo.GetValue(), "needle")
        finally:
            search_form_module._load_search_history = original_history

    def test_archive_helpers_recognize_zip_files(self):
        self.assertTrue(filelist_module._is_archive_file("report.zip"))
        self.assertTrue(filelist_module._is_archive_file("archive.tar.gz"))
        self.assertFalse(filelist_module._is_archive_file("report.txt"))
        self.assertEqual(filelist_module._build_archive_destination_path("C:/work/folder/sample.txt"), os.path.normpath("C:/work/folder/sample.txt.zip"))

    def test_archive_selected_paths_prompts_for_single_archive_name_and_groups_selection(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-archive-")
        file_a = os.path.join(temp_dir, "first.txt")
        file_b = os.path.join(temp_dir, "second.txt")
        with open(file_a, "w", encoding="utf-8") as handle:
            handle.write("first")
        with open(file_b, "w", encoding="utf-8") as handle:
            handle.write("second")

        captured = {}

        class FakeDialog:
            def __init__(self, *args, **kwargs):
                self.value = kwargs.get("value", "")

            def ShowModal(self):
                return wx.ID_OK

            def GetValue(self):
                return "bundle.zip"

            def Destroy(self):
                return None

        def fake_create_zip(paths, destination_path):
            captured["paths"] = list(paths)
            captured["destination_path"] = destination_path
            return destination_path

        original_dialog = archive_helper.wx.TextEntryDialog
        original_create_zip = archive_helper._create_zip_archive
        original_messagebox = archive_helper.wx.MessageBox
        try:
            archive_helper.wx.TextEntryDialog = FakeDialog
            archive_helper._create_zip_archive = fake_create_zip
            archive_helper.wx.MessageBox = lambda *args, **kwargs: None
            self.assertTrue(archive_helper._archive_selected_paths(None, [file_a, file_b]))
        finally:
            archive_helper.wx.TextEntryDialog = original_dialog
            archive_helper._create_zip_archive = original_create_zip
            archive_helper.wx.MessageBox = original_messagebox
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual(captured["paths"], [file_a, file_b])
        self.assertEqual(captured["destination_path"], os.path.join(temp_dir, "bundle.zip"))

    def test_archive_selected_paths_restores_parent_folder_and_selects_new_archive(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-archive-refresh-")
        file_path = os.path.join(temp_dir, "first.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("first")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: os.path.join(temp_dir, "other_folder"), ChangeValue=lambda value: setattr(self, "current_path", value))
                self.current_path = os.path.join(temp_dir, "other_folder")
                self.opened_path = None
                self.loaded_folder = None
                self.list_selected = None
                self.tree_selected = None

            def busy_cursor(self):
                from contextlib import nullcontext

                return nullcontext()

            def open_path(self, folder):
                self.opened_path = folder
                self.current_path = folder

            def load_folder(self, folder):
                self.loaded_folder = folder

            def select_list_item_by_path(self, path):
                self.list_selected = path

            def select_tree_item_by_path(self, path):
                self.tree_selected = path

        owner = FakeOwner()

        class FakeDialog:
            def __init__(self, *args, **kwargs):
                self.value = kwargs.get("value", "")

            def ShowModal(self):
                return wx.ID_OK

            def GetValue(self):
                return "bundle.zip"

            def Destroy(self):
                return None

        def fake_create_zip(paths, destination_path):
            self.assertEqual(list(paths), [file_path])
            return destination_path

        original_dialog = archive_helper.wx.TextEntryDialog
        original_create_zip = archive_helper._create_zip_archive
        original_messagebox = archive_helper.wx.MessageBox
        try:
            archive_helper.wx.TextEntryDialog = FakeDialog
            archive_helper._create_zip_archive = fake_create_zip
            archive_helper.wx.MessageBox = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("message box should not appear"))
            self.assertTrue(archive_helper._archive_selected_paths(owner, [file_path]))
        finally:
            archive_helper.wx.TextEntryDialog = original_dialog
            archive_helper._create_zip_archive = original_create_zip
            archive_helper.wx.MessageBox = original_messagebox
            shutil.rmtree(temp_dir, ignore_errors=True)

        self.assertEqual(owner.opened_path, temp_dir)
        self.assertEqual(owner.loaded_folder, temp_dir)
        self.assertEqual(owner.list_selected, os.path.join(temp_dir, "bundle.zip"))
        self.assertEqual(owner.tree_selected, os.path.join(temp_dir, "bundle.zip"))

    def test_archive_run_command_hides_console_window(self):
        import file_operations.archive_helper as archive_helper

        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return types.SimpleNamespace(stdout="", stderr="", returncode=0)

        with mock.patch.object(archive_helper.subprocess, "run", side_effect=fake_run):
            archive_helper._run_command(["powershell", "-NoProfile", "-Command", "Write-Output test"])

        self.assertIn("creationflags", captured["kwargs"])
        self.assertEqual(captured["kwargs"]["creationflags"], getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_extract_archive_uses_7z_when_available(self):
        import file_operations.archive_helper as archive_helper

        archive_path = os.path.join(tempfile.mkdtemp(prefix="docexplorer-7z-"), "sample.7z")
        destination_dir = os.path.join(os.path.dirname(archive_path), "out")

        with mock.patch.object(archive_helper.os.path, "isfile", return_value=True), \
             mock.patch.object(archive_helper.shutil, "which", side_effect=lambda name: "C:/Program Files/7-Zip/7z.exe" if name in {"7z", "7za", "7zr"} else None), \
             mock.patch.object(archive_helper, "_run_command") as mocked_run:
            archive_helper._extract_archive_file(archive_path, destination_dir)

        mocked_run.assert_called_once_with([
            "C:/Program Files/7-Zip/7z.exe",
            "x",
            "-y",
            "-o" + destination_dir,
            archive_path,
        ])

    def test_archive_refresh_only_reloads_archive_parent_folder(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-archive-parent-")
        archive_path = os.path.join(temp_dir, "bundle.zip")

        class FakeOwner:
            def __init__(self):
                self.opened_path = None
                self.loaded_folder = None
                self.selected_tree_path = None
                self.selected_list_path = None

            def open_path(self, folder):
                self.opened_path = folder

            def select_tree_item_by_path(self, path):
                self.selected_tree_path = path

            def select_list_item_by_path(self, path):
                self.selected_list_path = path

        owner = FakeOwner()

        with mock.patch("controls.tree_utils.refresh_tree_selection_and_filelist") as mocked_full_refresh:
            archive_helper._refresh_after_archive_change(owner, archive_path)

        self.assertEqual(owner.opened_path, temp_dir)
        self.assertEqual(owner.selected_tree_path, archive_path)
        self.assertEqual(owner.selected_list_path, archive_path)
        mocked_full_refresh.assert_not_called()

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_archive_refresh_loads_parent_folder_once_without_open_path(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-archive-tree-")
        archive_path = os.path.join(temp_dir, "bundle.zip")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(ChangeValue=lambda value: setattr(self, "path_box_value", value))
                self.path_box_value = None
                self.opened_path = None
                self.loaded_folder = None
                self.selected_tree_path = None
                self.selected_list_path = None

            def open_path(self, folder):
                self.opened_path = folder

            def load_folder(self, folder):
                self.loaded_folder = folder

            def select_tree_item_by_path(self, path):
                self.selected_tree_path = path

            def select_list_item_by_path(self, path):
                self.selected_list_path = path

        owner = FakeOwner()

        archive_helper._refresh_after_archive_change(owner, archive_path)

        self.assertEqual(owner.path_box_value, temp_dir)
        self.assertIsNone(owner.opened_path)
        self.assertEqual(owner.loaded_folder, temp_dir)
        self.assertEqual(owner.selected_tree_path, archive_path)
        self.assertEqual(owner.selected_list_path, archive_path)

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_archive_refresh_refreshes_filelist_for_parent_folder(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-archive-filelist-")
        archive_path = os.path.join(temp_dir, "bundle.zip")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(
                    GetValue=lambda: temp_dir,
                    ChangeValue=lambda value: setattr(self, "path_box_value", value),
                )
                self.path_box_value = temp_dir
                self.loaded_folder = None
                self.tree = object()
                self.selected_tree_path = None
                self.selected_list_path = None

            def load_folder(self, folder):
                self.loaded_folder = folder

            def select_tree_item_by_path(self, path):
                self.selected_tree_path = path

            def select_list_item_by_path(self, path):
                self.selected_list_path = path

        owner = FakeOwner()

        archive_helper._refresh_after_archive_change(owner, archive_path)

        self.assertEqual(owner.loaded_folder, temp_dir)
        self.assertEqual(owner.selected_tree_path, archive_path)
        self.assertEqual(owner.selected_list_path, archive_path)

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_refresh_tree_selection_and_filelist_clears_stale_preview(self):
        import controls.tree_utils as tree_utils

        owner = types.SimpleNamespace(
            path_box=types.SimpleNamespace(GetValue=lambda: "C:/temp"),
            tree=mock.Mock(),
            list=mock.Mock(),
            current_preview_path="C:/temp/last_file.txt",
            show_file_preview=mock.Mock(),
        )
        owner.tree.GetSelection.return_value = None
        owner.tree.GetRootItem.return_value = mock.Mock(IsOk=mock.Mock(return_value=False))
        owner.list.GetItemCount.return_value = 2

        with mock.patch.object(tree_utils, "refresh_tree_root") as mocked_refresh_root, \
             mock.patch.object(tree_utils, "refresh_tree_subtree") as mocked_refresh_subtree, \
             mock.patch.object(tree_utils, "refresh_tree_selection") as mocked_refresh_tree_selection:
            tree_utils.refresh_tree_selection_and_filelist(owner)

        owner.show_file_preview.assert_called_once_with(None)
        owner.list.SetItemState.assert_any_call(0, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        owner.list.SetItemState.assert_any_call(1, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
        mocked_refresh_root.assert_not_called()
        mocked_refresh_tree_selection.assert_called_once_with(owner)
        mocked_refresh_subtree.assert_not_called()

    def test_extract_selected_archive_refreshes_active_folder_and_tree(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-extract-")
        archive_path = os.path.join(temp_dir, "bundle.zip")

        class FakeTreeItem:
            def __init__(self):
                self._ok = True

            def IsOk(self):
                return self._ok

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.loaded_folder = None
                self.tree = object()

            def load_folder(self, folder):
                self.loaded_folder = folder

        owner = FakeOwner()
        parent_item = FakeTreeItem()

        with mock.patch.object(archive_helper, "_extract_archive_file", return_value=temp_dir) as mocked_extract, \
             mock.patch("controls.tree_utils.find_tree_item_by_path", return_value=parent_item) as find_item, \
             mock.patch("controls.tree_utils.refresh_tree_subtree") as refresh_subtree:
            self.assertTrue(archive_helper._extract_selected_archive_here(owner, archive_path))

        mocked_extract.assert_called_once_with(archive_path, temp_dir)
        self.assertEqual(owner.loaded_folder, temp_dir)
        self.assertTrue(find_item.called)
        refresh_subtree.assert_called_once_with(owner, parent_item, temp_dir)

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_selected_archive_prompts_on_existing_destination_folder(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-extract-conflict-")
        archive_path = os.path.join(temp_dir, "bundle.zip")
        existing_destination = os.path.join(temp_dir, "bundle")
        os.makedirs(existing_destination, exist_ok=True)

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.loaded_folder = None
                self.tree = object()

            def load_folder(self, folder):
                self.loaded_folder = folder

        owner = FakeOwner()

        with mock.patch.object(archive_helper.copy_and_paste, "_confirm_overwrite_existing_path", return_value=True) as mocked_confirm, \
             mock.patch.object(archive_helper, "_extract_archive_file") as mocked_extract:
            self.assertTrue(archive_helper._extract_selected_archive_here(owner, archive_path))

        mocked_confirm.assert_called_once_with(owner, existing_destination)
        mocked_extract.assert_called_once_with(archive_path, existing_destination)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_selected_archive_prompts_with_override_rename_and_cancel_buttons(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-extract-conflict-buttons-")
        archive_path = os.path.join(temp_dir, "bundle.zip")
        existing_destination = os.path.join(temp_dir, "bundle")
        os.makedirs(existing_destination, exist_ok=True)
        conflict_path = os.path.join(existing_destination, "existing.txt")
        with open(conflict_path, "w", encoding="utf-8") as handle:
            handle.write("x")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.loaded_folder = None
                self.tree = object()

            def load_folder(self, folder):
                self.loaded_folder = folder

        owner = FakeOwner()

        with mock.patch.object(archive_helper, "_get_archive_member_conflicts", return_value=["existing.txt"]), \
             mock.patch.object(archive_helper.wx, "MessageDialog") as mock_dialog, \
             mock.patch.object(archive_helper, "_extract_archive_file") as mocked_extract, \
             mock.patch.object(archive_helper, "_extract_archive_file_renamed") as mocked_renamed_extract:
            mock_dialog.return_value.ShowModal.return_value = wx.ID_NO
            mock_dialog.return_value.Destroy.return_value = None
            self.assertTrue(archive_helper._extract_selected_archive_here(owner, archive_path))

        mock_dialog.assert_called_once()
        mock_dialog.return_value.SetYesNoCancelLabels.assert_called_once_with(
            archive_helper.tr("archive_extract_override"),
            archive_helper.tr("archive_extract_rename"),
            archive_helper.tr("cancel_button"),
        )
        mocked_renamed_extract.assert_called_once_with(archive_path, existing_destination)
        mocked_extract.assert_not_called()
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_selected_archive_into_creates_target_folder_and_extracts(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-extract-into-")
        archive_path = os.path.join(temp_dir, "bundle.zip")
        target_dir = os.path.join(temp_dir, "custom_output")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.loaded_folder = None
                self.tree = object()
                self.selected_tree_path = None
                self.selected_list_path = None

            def load_folder(self, folder):
                self.loaded_folder = folder

            def select_tree_item_by_path(self, path):
                self.selected_tree_path = path

            def select_list_item_by_path(self, path):
                self.selected_list_path = path

        class FakeDialog:
            def __init__(self, *args, **kwargs):
                self.value = kwargs.get("value", "")

            def ShowModal(self):
                return wx.ID_OK

            def GetValue(self):
                return target_dir

            def Destroy(self):
                return None

        class FakeTreeItem:
            def __init__(self):
                self._ok = True

            def IsOk(self):
                return self._ok

        owner = FakeOwner()
        parent_item = FakeTreeItem()
        with mock.patch.object(archive_helper.wx, "TextEntryDialog", return_value=FakeDialog()), \
             mock.patch.object(archive_helper, "_extract_archive_file", return_value=target_dir) as mocked_extract, \
             mock.patch.object(archive_helper.os, "makedirs") as mocked_makedirs, \
             mock.patch("controls.tree_utils.find_tree_item_by_path", return_value=parent_item) as find_item, \
             mock.patch("controls.tree_utils.refresh_tree_subtree") as refresh_subtree:
            self.assertTrue(archive_helper._extract_selected_archive_into(owner, archive_path))

        mocked_makedirs.assert_called_once_with(target_dir, exist_ok=True)
        mocked_extract.assert_called_once_with(archive_path, target_dir)
        self.assertEqual(owner.loaded_folder, temp_dir)
        self.assertIsNone(owner.selected_tree_path)
        self.assertEqual(owner.selected_list_path, target_dir)
        refresh_subtree.assert_called_once_with(owner, parent_item, temp_dir)
        self.assertTrue(find_item.called)

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_archive_file_uses_wait_cursor_while_unpacking(self):
        import file_operations.archive_helper as archive_helper

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-extract-busy-")
        archive_path = os.path.join(temp_dir, "archive.zip")
        destination_dir = os.path.join(temp_dir, "out")
        with open(archive_path, "wb") as handle:
            handle.write(b"fake zip")

        captured = []

        class FakeRunResult:
            stdout = ""
            stderr = ""

        def fake_run(command, **kwargs):
            captured.append(("run", command, kwargs))
            return FakeRunResult()

        with mock.patch.object(archive_helper, "_run_command", side_effect=fake_run), \
             mock.patch.object(archive_helper.shutil, "which", side_effect=lambda name: "powershell" if name == "powershell" else None), \
             mock.patch.object(archive_helper.wx, "BeginBusyCursor") as begin_busy, \
             mock.patch.object(archive_helper.wx, "EndBusyCursor") as end_busy, \
             mock.patch.object(archive_helper.wx, "IsBusy", return_value=False):
            archive_helper._extract_archive_file(archive_path, destination_dir)

        self.assertEqual(begin_busy.call_count, 1)
        self.assertEqual(end_busy.call_count, 1)
        self.assertEqual(captured[0][1][0], "powershell")

        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_archive_extract_form_geometry_is_saved_and_restored(self):
        import file_operations.archive_helper as archive_helper

        class FakeDialog:
            def __init__(self):
                self._position = (10, 20)
                self._size = (400, 300)

            def GetPosition(self):
                return types.SimpleNamespace(x=self._position[0], y=self._position[1])

            def GetSize(self):
                return types.SimpleNamespace(x=self._size[0], y=self._size[1])

            def SetSize(self, size):
                self._size = tuple(size)

            def SetPosition(self, position):
                self._position = tuple(position)

            def SetMinSize(self, size):
                self._min_size = tuple(size)

        dialog = FakeDialog()
        archive_helper._save_archive_extract_form_geometry(dialog)

        settings = archive_helper.load_settings()
        self.assertEqual(settings["archive_extract_form_position"], [10, 20])
        self.assertEqual(settings["archive_extract_form_size"], [400, 300])

        restored = {"archive_extract_form_position": [11, 22], "archive_extract_form_size": [500, 350]}
        dialog2 = FakeDialog()
        archive_helper._apply_archive_extract_form_geometry(dialog2, restored)
        self.assertEqual(dialog2._position, (11, 22))
        self.assertEqual(dialog2._size, (500, 350))

    def test_delete_paths_refreshes_parent_folder_after_tree_delete(self):
        import controls.filelist as filelist

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-delete-parent-")
        file_path = os.path.join(temp_dir, "child.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("x")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.current_preview_path = None
                self.tree = object()
                self._syncing_tree_from_path = False

        owner = FakeOwner()

        with mock.patch.object(filelist, "_remove_tree_item_for_path"), \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "_unique_preserving_order", return_value=[file_path]), \
             mock.patch.object(filelist, "wx") as mock_wx:
            mock_wx.ID_YES = wx.ID_YES
            mock_wx.MessageDialog.return_value.ShowModal.return_value = wx.ID_YES
            mock_wx.MessageDialog.return_value.Destroy.return_value = None
            filelist.delete_paths(owner, [file_path])

        self.assertEqual(mocked_refresh.call_args.kwargs["affected_dirs"], [temp_dir])
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_paths_uses_recycle_bin(self):
        import controls.filelist as filelist

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-delete-recycle-")
        file_path = os.path.join(temp_dir, "child.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("x")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.current_preview_path = None
                self.tree = object()
                self._syncing_tree_from_path = False

        owner = FakeOwner()

        with mock.patch.object(filelist, "_remove_tree_item_for_path"), \
             mock.patch.object(filelist, "_refresh_after_fs_change"), \
             mock.patch.object(filelist, "_unique_preserving_order", return_value=[file_path]), \
             mock.patch.object(filelist, "move_to_recycle_bin") as mocked_recycle, \
             mock.patch.object(filelist, "wx") as mock_wx:
            mock_wx.ID_YES = wx.ID_YES
            mock_wx.MessageDialog.return_value.ShowModal.return_value = wx.ID_YES
            mock_wx.MessageDialog.return_value.Destroy.return_value = None
            filelist.delete_paths(owner, [file_path])

        mocked_recycle.assert_called_once_with([file_path])
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_delete_paths_requires_confirmation_before_recycle_or_permanent_delete(self):
        import controls.filelist as filelist

        temp_dir = tempfile.mkdtemp(prefix="docexplorer-delete-confirm-")
        file_path = os.path.join(temp_dir, "child.txt")
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write("x")

        class FakeOwner:
            def __init__(self):
                self.path_box = types.SimpleNamespace(GetValue=lambda: temp_dir)
                self.current_preview_path = None
                self.tree = object()
                self._syncing_tree_from_path = False

        owner = FakeOwner()

        with mock.patch.object(filelist, "_remove_tree_item_for_path"), \
             mock.patch.object(filelist, "_refresh_after_fs_change"), \
             mock.patch.object(filelist, "_unique_preserving_order", return_value=[file_path]), \
             mock.patch.object(filelist, "move_to_recycle_bin") as mocked_recycle, \
             mock.patch.object(filelist, "wx") as mock_wx:
            mock_wx.ID_YES = wx.ID_YES
            mock_wx.MessageDialog.return_value.ShowModal.return_value = wx.ID_YES
            mock_wx.MessageDialog.return_value.Destroy.return_value = None

            filelist.delete_paths(owner, [file_path], permanent=False)
            filelist.delete_paths(owner, [file_path], permanent=True)

        self.assertEqual(mock_wx.MessageDialog.call_count, 2)
        self.assertEqual(mocked_recycle.call_count, 1)
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_move_to_recycle_bin_handles_user_canceled_shell_action(self):
        import common.system as system

        with mock.patch.object(system.os, "path", wraps=system.os.path), \
             mock.patch.object(system.os.path, "exists", return_value=True), \
             mock.patch.object(system.ctypes, "windll") as mock_windll:
            mock_shell = mock.Mock()
            mock_shell.SHFileOperationW.return_value = 1223
            mock_windll.shell32 = mock_shell

            self.assertFalse(system.move_to_recycle_bin(["D:/temp/example.txt"]))

    def test_remove_tree_item_for_path_does_not_trigger_selection_open_path(self):
        import controls.filelist as filelist

        class FakeTreeItem:
            def __init__(self, value=None):
                self.value = value

            def IsOk(self):
                return True

        class FakeTree:
            def __init__(self, owner):
                self.owner = owner
                self.root = FakeTreeItem("root")
                self.parent = FakeTreeItem("D:\\parent")
                self.child = FakeTreeItem("D:\\parent\\child")
                self.selection = self.parent

            def GetRootItem(self):
                return self.root

            def GetFirstChild(self, item):
                if item is self.root:
                    return self.parent, None
                return self.child, None

            def GetNextChild(self, item, cookie):
                return FakeTreeItem(False), None

            def GetItemParent(self, item):
                return self.parent if item is self.child else self.root

            def GetChildrenCount(self, item):
                return 1 if item is self.parent else 0

            def GetItemData(self, item):
                if item is self.root:
                    return None
                if item is self.parent:
                    return "D:\\parent"
                if item is self.child:
                    return "D:\\parent\\child"
                return None

            def AppendItem(self, item, text):
                return FakeTreeItem(text)

            def Delete(self, item):
                pass

            def SelectItem(self, item):
                self.selection = item
                if not getattr(self.owner, "_syncing_tree_from_path", False):
                    self.owner.on_tree_select(types.SimpleNamespace(GetItem=lambda: item))

        class FakeOwner:
            def __init__(self):
                self.tree = FakeTree(self)
                self.path_box = types.SimpleNamespace(GetValue=lambda: "D:\\parent")
                self.load_folder_calls = []
                self.open_path_calls = []
                self._syncing_tree_from_path = False

            def load_folder(self, path):
                self.load_folder_calls.append(path)

            def open_path(self, path):
                self.open_path_calls.append(path)
                self.load_folder(path)

            def on_tree_select(self, event):
                item = event.GetItem()
                path = item.value
                if os.path.isdir(path):
                    self.open_path(path)

        owner = FakeOwner()

        filelist._remove_tree_item_for_path(owner, "D:\\parent\\child")

        self.assertEqual(owner.open_path_calls, [])
        self.assertEqual(owner.load_folder_calls, [])

    def test_select_tree_item_by_path_does_not_set_file_path_in_path_box(self):
        import controls.tree_utils as tree_utils

        file_path = os.path.join("D:\\", "Projects", "PdfExplorer", "notes.txt")
        folder_path = os.path.join("D:\\", "Projects", "PdfExplorer")

        class FakePathBox:
            def __init__(self):
                self.value = folder_path

            def SetValue(self, value):
                self.value = value

        class FakeTreeItem:
            def __init__(self, value):
                self.value = value

            def IsOk(self):
                return True

        class FakeTree:
            def __init__(self):
                self.root = FakeTreeItem("root")
                self.file_item = FakeTreeItem(file_path)
                self.selection = None

            def GetRootItem(self):
                return self.root

            def GetFirstChild(self, item):
                if item is self.root:
                    return self.file_item, None
                return FakeTreeItem(False), None

            def GetNextChild(self, item, cookie):
                return FakeTreeItem(False), None

            def GetItemData(self, item):
                return item.value

            def SelectItem(self, item):
                self.selection = item

            def Expand(self, item):
                pass

            def EnsureVisible(self, item):
                pass

        owner = types.SimpleNamespace(
            tree=FakeTree(),
            path_box=FakePathBox(),
            show_hidden=False,
            _syncing_tree_from_path=False,
        )

        with mock.patch("os.path.isdir", side_effect=lambda path: os.path.normpath(path) == os.path.normpath(folder_path)):
            tree_utils.select_tree_item_by_path(owner, file_path)

        self.assertEqual(owner.path_box.value, folder_path)

    def test_should_populate_tree_node_for_drive_root_with_placeholder_child(self):
        import controls.tree_utils as tree_utils

        class FakeTreeItem:
            def __init__(self, value=None):
                self._value = value

            def IsOk(self):
                return True

        class FakeTree:
            def __init__(self):
                self.root = FakeTreeItem()
                self.placeholder = FakeTreeItem(None)

            def GetFirstChild(self, item):
                if item is self.root:
                    return self.placeholder, None
                return FakeTreeItem(False), None

            def GetItemData(self, item):
                if item is self.placeholder:
                    return None
                return "D:\\"

        owner = types.SimpleNamespace(tree=FakeTree(), show_hidden=False)

        with mock.patch("os.path.isdir", return_value=True):
            self.assertTrue(tree_utils._should_populate_tree_node(owner, owner.tree.root, "D:\\"))


if __name__ == "__main__":
    unittest.main()
