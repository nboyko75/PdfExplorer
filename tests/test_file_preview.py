import importlib
import os
import sys
import tempfile
import types
import unittest
from unittest import mock


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


def _import_file_preview_with_mocked_wx():
    fake_wx = mock.MagicMock(name="wx")
    with mock.patch.dict(sys.modules, {"wx": fake_wx}):
        sys.modules.pop("controls.file_preview", None)
        return importlib.import_module("controls.file_preview")


class FilePreviewManualZoomTests(unittest.TestCase):
    def test_manual_zoom_scales_target_width_in_wide_layout(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            pdf_page_view_mode=file_preview.PAGE_VIEW_MODE_MANUAL,
            pdf_page_view_selected_mode=file_preview.PAGE_VIEW_MODE_1_WIDE,
            pdf_preview_zoom=2.0,
        )

        with mock.patch.object(file_preview, "_get_average_pdf_page_dimensions", return_value=(600.0, 800.0)):
            target_width, target_height, _target_zoom, _avg_width, _avg_height = file_preview._get_preview_target_size_for_mode(
                owner,
                "ignored.pdf",
                300,
                1000,
            )

        self.assertEqual(target_width, 600)
        self.assertEqual(target_height, 800)

    def test_switching_to_different_pdf_resets_manual_zoom_to_selected_wide_mode(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="first.pdf",
            selected_pdf_page_panel=None,
            current_image_preview=None,
            current_image_zoom=1.0,
            pdf_page_view_mode=file_preview.PAGE_VIEW_MODE_MANUAL,
            pdf_page_view_selected_mode=file_preview.PAGE_VIEW_MODE_1_WIDE,
            pdf_preview_zoom=0.6,
            preview_text=types.SimpleNamespace(Show=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Hide=mock.MagicMock()),
            pdf_preview_container=types.SimpleNamespace(Hide=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "update_page_buttons_state"), \
             mock.patch.object(file_preview, "update_pdf_save_button_state"), \
             mock.patch.object(file_preview, "update_preview_toolbar_visibility"), \
             mock.patch.object(file_preview, "show_pdf_feed") as mocked_show_pdf_feed, \
             mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=False), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False), \
             mock.patch("controls.file_preview.os.path.isdir", return_value=False), \
             mock.patch("controls.file_preview.os.path.isfile", return_value=True):
            file_preview.show_file_preview(owner, "second.pdf")

        self.assertEqual(owner.pdf_page_view_mode, file_preview.PAGE_VIEW_MODE_1_WIDE)
        self.assertEqual(owner.pdf_preview_zoom, 1.0)
        mocked_show_pdf_feed.assert_called_once_with(owner, "second.pdf")

    def test_page_view_button_visible_for_image_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.png",
            preview_save_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_cancel_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_rotate_menu_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_optimize_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_adjust_page_width_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_import_from_file_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_export_pages_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_move_page_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_remove_page_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_page_view_mode_btn=types.SimpleNamespace(Show=mock.MagicMock()),
            preview_toolbar=types.SimpleNamespace(Layout=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )

        with mock.patch("controls.file_preview.os.path.isfile", return_value=True), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=True), \
             mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=False), \
             mock.patch.object(file_preview, "update_pdf_save_button_state"):
            file_preview.update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)

        owner.preview_page_view_mode_btn.Show.assert_called_once_with(True)

    def test_refresh_preview_for_page_view_mode_reloads_image_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(current_preview_path="sample.png")

        with mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=True), \
             mock.patch.object(file_preview.image_utils, "show_image_preview") as mocked_show_image_preview:
            file_preview.refresh_preview_for_page_view_mode(owner, "sample.png")

        mocked_show_image_preview.assert_called_once_with(owner, "sample.png", file_preview.tr)

    def test_update_page_buttons_state_restricts_adjust_and_optimize_to_pdf(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.pdf",
            selected_pdf_page_panel=object(),
            preview_rotate_menu_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_import_from_file_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_export_pages_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_move_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_remove_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_adjust_page_width_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_optimize_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "is_pdf_file", return_value=True), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False):
            file_preview.update_page_buttons_state(owner)

        owner.preview_adjust_page_width_btn.Enable.assert_called_once_with(True)
        owner.preview_optimize_btn.Enable.assert_called_once_with(True)

        owner.current_preview_path = "sample.png"
        owner.preview_adjust_page_width_btn.Enable.reset_mock()
        owner.preview_optimize_btn.Enable.reset_mock()

        with mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False):
            file_preview.update_page_buttons_state(owner)

        owner.preview_adjust_page_width_btn.Enable.assert_called_once_with(False)
        owner.preview_optimize_btn.Enable.assert_called_once_with(False)

    def test_manual_zoom_works_for_office_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.docx",
            pdf_preview_zoom=1.0,
            pdf_page_view_mode=file_preview.PAGE_VIEW_MODE_1_WIDE,
            busy_cursor=lambda: file_preview.nullcontext(),
        )

        with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner), \
             mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(file_preview.office_preview, "convert_office_to_preview_pdf", return_value="converted.pdf"), \
             mock.patch.object(file_preview, "show_pdf_feed") as mocked_show_pdf_feed:
            file_preview.on_preview_zoom_in(types.SimpleNamespace())

        self.assertEqual(owner.pdf_preview_zoom, 1.25)
        self.assertEqual(owner.pdf_page_view_mode, file_preview.PAGE_VIEW_MODE_MANUAL)
        mocked_show_pdf_feed.assert_called_once_with(owner, "converted.pdf")

    def test_manual_zoom_works_for_html_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.html",
            current_html_zoom=1.0,
            busy_cursor=lambda: file_preview.nullcontext(),
            pdf_preview_container=types.SimpleNamespace(Show=mock.MagicMock(), Hide=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_text=types.SimpleNamespace(Show=mock.MagicMock(), SetValue=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Show=mock.MagicMock(), Hide=mock.MagicMock(), Layout=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
            html_preview=types.SimpleNamespace(SetZoom=mock.MagicMock(), SetPage=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner), \
             mock.patch.object(file_preview, "can_preview_html", return_value=True), \
             mock.patch.object(file_preview, "show_html_preview") as mocked_show_html_preview:
            file_preview.on_preview_zoom_in(types.SimpleNamespace())

        self.assertEqual(owner.current_html_zoom, 1.25)
        mocked_show_html_preview.assert_called_once_with(owner, "sample.html")

    def test_tree_file_selection_does_not_preview_file(self):
        tree_utils = __import__("controls.tree_utils", fromlist=["on_tree_select"])
        owner = types.SimpleNamespace(
            tree=types.SimpleNamespace(GetItemData=lambda _item: "sample.html"),
            show_file_preview=mock.MagicMock(),
            open_path=mock.MagicMock(),
            confirm_preview_change=lambda path: True,
        )
        event = types.SimpleNamespace(GetItem=lambda: object(), Veto=mock.MagicMock())

        with mock.patch("controls.tree_utils.os.path.isdir", return_value=False):
            tree_utils.on_tree_select(owner, event)

        owner.show_file_preview.assert_not_called()
        owner.open_path.assert_not_called()

    def test_shared_open_path_or_file_opens_folders_and_files(self):
        filelist = __import__("controls.filelist", fromlist=["open_path_or_file"])
        folder_owner = types.SimpleNamespace(open_path=mock.MagicMock())
        file_owner = types.SimpleNamespace()

        with mock.patch("controls.filelist.os.path.isdir", return_value=True), \
             mock.patch("controls.filelist.os.path.isfile", return_value=False):
            result = filelist.open_path_or_file(folder_owner, "folder")

        self.assertTrue(result)
        folder_owner.open_path.assert_called_once_with("folder")

        with mock.patch("controls.filelist.os.path.isdir", return_value=False), \
             mock.patch("controls.filelist.os.path.isfile", return_value=True), \
             mock.patch("controls.filelist.os.startfile") as mocked_startfile:
            result = filelist.open_path_or_file(file_owner, "file.pdf")

        self.assertTrue(result)
        mocked_startfile.assert_called_once_with("file.pdf")

    def test_shared_open_path_or_file_does_nothing_for_already_open_office_file(self):
        filelist = __import__("controls.filelist", fromlist=["open_path_or_file"])
        file_owner = types.SimpleNamespace()

        with mock.patch("controls.filelist.os.path.isdir", return_value=False), \
             mock.patch("controls.filelist.os.path.isfile", return_value=True), \
             mock.patch("controls.filelist.is_office_file_open", return_value=True), \
             mock.patch("controls.filelist.os.startfile") as mocked_startfile:
            result = filelist.open_path_or_file(file_owner, "file.docx")

        self.assertTrue(result)
        mocked_startfile.assert_not_called()

    def test_preview_checkbox_toggle_does_not_restore_last_preview_when_reenabled(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="last_selected.pdf",
            preview_enabled=False,
            preview_text=types.SimpleNamespace(Show=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Hide=mock.MagicMock()),
            pdf_preview_container=types.SimpleNamespace(Hide=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "show_file_preview") as mocked_show_file_preview:
            event = types.SimpleNamespace(GetEventObject=lambda: types.SimpleNamespace(GetValue=lambda: True))
            with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner):
                file_preview.on_preview_checkbox_toggle(event)

        self.assertTrue(owner.preview_enabled)
        mocked_show_file_preview.assert_called_once_with(owner, None)

    def test_preview_checkbox_toggle_disables_office_preview_when_global_preview_is_off(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_enabled=True,
            office_preview_enabled=True,
            preview_checkbox=types.SimpleNamespace(GetValue=lambda: False),
            office_preview_checkbox=types.SimpleNamespace(Enable=mock.MagicMock(), SetValue=mock.MagicMock(), GetValue=lambda: True),
            preview_text=types.SimpleNamespace(Show=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Hide=mock.MagicMock()),
            pdf_preview_container=types.SimpleNamespace(Hide=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "show_file_preview") as mocked_show_file_preview:
            event = types.SimpleNamespace(GetEventObject=lambda: owner.preview_checkbox)
            with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner):
                file_preview.on_preview_checkbox_toggle(event)

        self.assertFalse(owner.preview_enabled)
        owner.office_preview_checkbox.Enable.assert_called_once_with(False)
        mocked_show_file_preview.assert_called_once_with(owner, None)

    def test_preview_toggle_checkbox_defaults_to_checked(self):
        file_preview = _import_file_preview_with_mocked_wx()

        class _FakePanel:
            def __init__(self, *args, **kwargs):
                self.SetSizer = mock.MagicMock()
                self.Hide = mock.MagicMock()
                self.Show = mock.MagicMock()
                self.Layout = mock.MagicMock()
                self.SetScrollRate = mock.MagicMock()
                self.Bind = mock.MagicMock()
                self.SetMinSize = mock.MagicMock()
                self.SetValue = mock.MagicMock()

        class _FakeButton:
            def __init__(self, *args, **kwargs):
                self.Enable = mock.MagicMock()
                self.Bind = mock.MagicMock()

        class _FakeCheckBox:
            def __init__(self, *args, **kwargs):
                self.SetValue = mock.MagicMock()
                self.GetValue = mock.MagicMock(return_value=True)
                self.Bind = mock.MagicMock()

        class _FakeSplitter:
            def __init__(self):
                self.SplitHorizontally = mock.MagicMock()

        owner = types.SimpleNamespace(
            icon_manager=mock.MagicMock(),
            filePreview=None,
            list_host_panel=mock.MagicMock(),
            list=mock.MagicMock(),
        )

        with mock.patch.object(file_preview.image_utils, "create_bitmap_button2", return_value=_FakeButton()), \
             mock.patch.object(file_preview.image_utils, "create_bitmap_button", return_value=_FakeButton()), \
             mock.patch.object(file_preview, "tr", side_effect=lambda key, **kwargs: key), \
             mock.patch.object(file_preview.wx, "Panel", side_effect=_FakePanel), \
             mock.patch.object(file_preview.wx, "ScrolledWindow", side_effect=_FakePanel), \
             mock.patch.object(file_preview.wx, "StaticBitmap", side_effect=_FakePanel), \
             mock.patch.object(file_preview.wx, "TextCtrl", return_value=_FakePanel()), \
             mock.patch.object(file_preview.wx, "CheckBox", return_value=_FakeCheckBox()), \
             mock.patch.object(file_preview.wx, "BoxSizer", return_value=mock.MagicMock(Add=mock.MagicMock())), \
             mock.patch.object(file_preview.wx, "HSCROLL", 0), \
             mock.patch.object(file_preview.wx, "VSCROLL", 0), \
             mock.patch.object(file_preview.wx, "BORDER_SUNKEN", 0), \
             mock.patch.object(file_preview.wx, "ART_FILE_OPEN", 0), \
             mock.patch.object(file_preview.wx, "ART_FILE_SAVE", 0), \
             mock.patch.object(file_preview.wx, "ART_MINUS", 0), \
             mock.patch.object(file_preview.wx, "ART_PLUS", 0), \
             mock.patch.object(file_preview.wx, "ART_LIST_VIEW", 0), \
             mock.patch.object(file_preview.wx, "ART_GO_FORWARD", 0), \
             mock.patch.object(file_preview.wx, "ART_REPORT_VIEW", 0):
            file_preview.build_file_preview_pane(owner, _FakeSplitter())

        self.assertTrue(owner.preview_checkbox.GetValue())

    def test_file_list_drag_out_adds_selected_files_to_drag_data(self):
        filelist = __import__("controls.filelist", fromlist=["on_list_begin_drag", "get_selected_list_paths"])
        owner = types.SimpleNamespace(list=object())
        selected_paths = ["C:/first.txt", "C:/second.txt"]

        with mock.patch.object(filelist, "get_selected_list_paths", return_value=selected_paths), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: path in selected_paths), \
             mock.patch.object(filelist.wx, "FileDataObject") as mocked_file_data, \
             mock.patch.object(filelist.wx, "DropSource") as mocked_drop_source:
            data = mock.MagicMock()
            mocked_file_data.return_value = data
            src = mock.MagicMock()
            mocked_drop_source.return_value = src

            filelist.on_list_begin_drag(owner, None)

        data.AddFile.assert_has_calls([mock.call("C:/first.txt"), mock.call("C:/second.txt")])
        mocked_drop_source.assert_called_once_with(owner.list)
        src.SetData.assert_called_once_with(data)
        src.DoDragDrop.assert_called_once_with(filelist.wx.Drag_AllowMove)

    def test_list_pane_accepts_files_dropped_from_explorer(self):
        filelist = __import__("controls.filelist", fromlist=["FileListDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), list=mock.MagicMock())

        with mock.patch.object(filelist, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(filelist.shutil, "copy2") as mocked_copy, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist.os.path, "isdir", side_effect=lambda path: path == "C:/current"), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: path in {"C:/current", "C:/drop.txt"}):
            drop_target = filelist.FileListDropTarget(owner)
            result = drop_target.OnDropFiles(0, 0, ["C:/drop.txt"])

        expected_destination = os.path.join("C:/current", "drop.txt")
        self.assertTrue(result)
        mocked_copy.assert_called_once_with("C:/drop.txt", expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=["C:/current"])

    def test_handle_file_ops_shortcut_supports_delete_key(self):
        filelist = __import__("controls.filelist", fromlist=["handle_file_ops_shortcut", "on_list_delete", "on_tree_delete"])
        owner = types.SimpleNamespace(
            list=object(),
            tree=object(),
        )
        focus = types.SimpleNamespace(GetParent=lambda: owner.list)
        event = types.SimpleNamespace(ControlDown=mock.MagicMock(return_value=False), GetKeyCode=mock.MagicMock(return_value=filelist.wx.WXK_DELETE))

        with mock.patch.object(filelist.wx.Window, "FindFocus", return_value=focus), \
             mock.patch.object(filelist, "on_list_delete") as mocked_list_delete, \
             mock.patch.object(filelist, "on_tree_delete") as mocked_tree_delete:
            result = filelist.handle_file_ops_shortcut(owner, event)

        self.assertTrue(result)
        mocked_list_delete.assert_called_once_with(owner, None)
        mocked_tree_delete.assert_not_called()

    def test_paste_prompts_before_overwriting_existing_file(self):
        filelist = __import__("controls.filelist", fromlist=["paste_into_path", "_confirm_overwrite_existing_path"])
        owner = types.SimpleNamespace(
            path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"),
            file_clipboard_paths=["C:/source.txt"],
            file_clipboard_mode=filelist.CLIPBOARD_MODE_COPY,
            current_preview_path=None,
        )

        expected_destination = os.path.normpath(os.path.join("C:/current", "source.txt"))
        with mock.patch.object(filelist, "_can_paste_into_directory", return_value=True), \
             mock.patch.object(filelist, "_get_clipboard_mode", return_value=filelist.CLIPBOARD_MODE_COPY), \
             mock.patch.object(filelist, "_get_clipboard_paths", return_value=["C:/source.txt"]), \
             mock.patch.object(filelist.os.path, "isdir", side_effect=lambda path: os.path.normpath(path) == os.path.normpath("C:/current")), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: os.path.normpath(path) in {os.path.normpath("C:/source.txt"), expected_destination}), \
             mock.patch.object(filelist, "_confirm_overwrite_existing_path", return_value=True) as mocked_confirm, \
             mock.patch.object(filelist.os, "remove") as mocked_remove, \
             mock.patch.object(filelist.shutil, "copy2") as mocked_copy, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "update_list_toolbar_buttons"), \
             mock.patch.object(filelist.wx, "MessageBox"):
            filelist.paste_into_path(owner, "C:/current")

        mocked_confirm.assert_called_once_with(owner, expected_destination)
        mocked_remove.assert_called_once_with(expected_destination)
        mocked_copy.assert_called_once_with(os.path.normpath("C:/source.txt"), expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=[os.path.normpath("C:/current")], preferred_preview_path=None)

    def test_paste_cut_refreshes_source_folder_tree(self):
        filelist = __import__("controls.filelist", fromlist=["paste_into_path", "CLIPBOARD_MODE_CUT"])
        owner = types.SimpleNamespace(
            path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"),
            file_clipboard_paths=["C:/source/old.txt"],
            file_clipboard_mode=filelist.CLIPBOARD_MODE_CUT,
            current_preview_path=None,
        )

        with mock.patch.object(filelist, "_can_paste_into_directory", return_value=True), \
             mock.patch.object(filelist, "_get_clipboard_mode", return_value=filelist.CLIPBOARD_MODE_CUT), \
             mock.patch.object(filelist, "_get_clipboard_paths", return_value=["C:/source/old.txt"]), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: os.path.normpath(path) in {os.path.normpath("C:/source/old.txt")}), \
             mock.patch.object(filelist.os.path, "isdir", side_effect=lambda path: os.path.normpath(path) in {os.path.normpath("C:/current"), os.path.normpath("C:/source")}), \
             mock.patch.object(filelist.shutil, "move") as mocked_move, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "update_list_toolbar_buttons"), \
             mock.patch.object(filelist.wx, "MessageBox"):
            filelist.paste_into_path(owner, "C:/current")

        mocked_move.assert_called_once_with(os.path.normpath("C:/source/old.txt"), os.path.normpath(os.path.join("C:/current", "old.txt")))
        mocked_refresh.assert_called_once_with(owner, affected_dirs=[os.path.normpath("C:/current"), os.path.normpath("C:/source")], preferred_preview_path=None)

    def test_list_rename_refreshes_selected_tree_folder(self):
        filelist = __import__("controls.filelist", fromlist=["on_list_rename", "_refresh_after_fs_change"])
        owner = types.SimpleNamespace(
            list=mock.MagicMock(),
            path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"),
            load_folder=mock.MagicMock(),
            tree=mock.MagicMock(),
            current_preview_path=None,
        )
        owner.list.GetFirstSelected.return_value = 0
        owner.list.GetItemText.return_value = "old.txt"
        owner.list.GetNextSelected.return_value = filelist.wx.NOT_FOUND
        owner.tree.GetSelection.return_value = None

        dialog = mock.MagicMock()
        dialog.ShowModal.return_value = filelist.wx.ID_OK
        dialog.GetValue.return_value = "new.txt"

        with mock.patch.object(filelist.os, "rename") as mocked_rename, \
             mock.patch.object(filelist.wx, "TextEntryDialog", return_value=dialog), \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh:
            filelist.on_list_rename(owner, None)

        expected_old = os.path.join("C:/current", "old.txt")
        expected_new = os.path.join("C:/current", "new.txt")
        mocked_rename.assert_called_once_with(expected_old, expected_new)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=["C:/current"])

    def test_list_panel_allows_multiple_selection_style(self):
        filelist = __import__("controls.filelist", fromlist=["build_list_panel"])

        class _FakePanel:
            def __init__(self, *args, **kwargs):
                self.SetSizer = mock.MagicMock()

        class _FakeIconManager:
            def get_bitmap(self, _name, size=(16, 16)):
                return mock.MagicMock(IsOk=mock.MagicMock(return_value=True))

        owner = types.SimpleNamespace(
            icon_manager=_FakeIconManager(),
            list_host_panel=None,
            list_toolbar=None,
            list_scan_btn=None,
            list_open_btn=None,
            list_rename_btn=None,
            list_new_folder_btn=None,
            list_copy_btn=None,
            list_cut_btn=None,
            list_paste_btn=None,
            list_delete_btn=None,
            filter_label=None,
            search_box=None,
        )

        with mock.patch.object(filelist, "update_list_toolbar_buttons"), \
             mock.patch.object(filelist.image_utils, "create_bitmap_button2", return_value=mock.MagicMock()), \
             mock.patch.object(filelist.image_utils, "create_bitmap_button", return_value=mock.MagicMock()), \
             mock.patch.object(filelist.image_utils, "init_list_images"), \
             mock.patch.object(filelist, "tr", side_effect=lambda key, **kwargs: key), \
             mock.patch.object(filelist.wx, "Panel", side_effect=_FakePanel), \
             mock.patch.object(filelist.wx, "BoxSizer", return_value=mock.MagicMock(Add=mock.MagicMock())), \
             mock.patch.object(filelist.wx, "StaticText", return_value=mock.MagicMock()), \
             mock.patch.object(filelist.wx, "TextCtrl", return_value=mock.MagicMock(SetHint=mock.MagicMock())), \
             mock.patch.object(filelist.wx, "ListCtrl") as mocked_list_ctrl:
            filelist.build_list_panel(owner, object())

        style = mocked_list_ctrl.call_args.kwargs["style"]
        self.assertFalse(style & filelist.wx.LC_SINGLE_SEL)

    def test_on_pdf_page_drag_motion_ignores_non_pdf_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.png",
            _pdf_drag_start_panel=object(),
            _pdf_drag_start_pos=types.SimpleNamespace(x=10, y=10),
        )
        event = types.SimpleNamespace(
            Dragging=mock.MagicMock(return_value=True),
            LeftIsDown=mock.MagicMock(return_value=True),
            GetPosition=mock.MagicMock(return_value=types.SimpleNamespace(x=20, y=20)),
        )
        page_panel = object()

        with mock.patch.object(file_preview.pdf_dragdrop, "start_pdf_page_drag") as mocked_start_drag, \
             mock.patch.object(file_preview, "get_pdf_page_panel_from_event", return_value=page_panel), \
             mock.patch.object(file_preview, "is_pdf_file", return_value=False):
            file_preview.on_pdf_page_drag_motion(owner, event)

        mocked_start_drag.assert_not_called()

    def test_load_all_click_regenerates_full_office_preview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.docx",
            preview_load_all_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            busy_cursor=lambda: file_preview.nullcontext(),
        )

        with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner), \
             mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(file_preview.office_preview, "get_office_document_page_count", return_value=18), \
             mock.patch.object(file_preview.office_preview, "convert_office_to_preview_pdf") as mocked_convert, \
             mock.patch.object(file_preview, "show_pdf_feed") as mocked_show_pdf_feed, \
             mock.patch.object(file_preview, "get_pdf_page_count", return_value=18), \
             mock.patch("controls.file_preview.os.path.isfile", return_value=True), \
             mock.patch.object(file_preview.pdf_utils, "_get_show_pages_limit_for_path", return_value=10):
            mocked_convert.return_value = "full_preview.pdf"
            file_preview.on_preview_load_all_pages(types.SimpleNamespace())

        mocked_convert.assert_called_once_with("sample.docx", max_pages=18)
        mocked_show_pdf_feed.assert_called_once_with(owner, "full_preview.pdf", force_all_pages=True)
        owner.preview_load_all_btn.Enable.assert_any_call(False)

    def test_import_from_file_imports_all_selected_files_in_sequence(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="target.pdf",
            busy_cursor=lambda: file_preview.nullcontext(),
        )

        with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner), \
             mock.patch.object(file_preview, "is_pdf_file", return_value=True), \
             mock.patch.object(file_preview, "_show_import_pdf_dialog", return_value={
                 "source_paths": ["first.pdf", "second.pdf"],
                 "insert_at_index": 2,
             }), \
             mock.patch.object(file_preview, "get_pdf_page_count", side_effect=[10, 3, 5]), \
             mock.patch.object(file_preview, "show_pdf_feed") as mocked_show_pdf_feed, \
             mock.patch.object(file_preview, "update_pdf_save_button_state") as mocked_update_save, \
             mock.patch.object(file_preview, "import_pdf_pages") as mocked_import:
            file_preview.on_preview_import_from_file(types.SimpleNamespace())

        self.assertEqual(mocked_import.call_args_list, [
            mock.call("target.pdf", "first.pdf", 2),
            mock.call("target.pdf", "second.pdf", 5),
        ])
        mocked_show_pdf_feed.assert_called_once_with(owner, "target.pdf")
        mocked_update_save.assert_called_once_with(owner)

    def test_load_all_button_enabled_for_office_preview_when_limit_active(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="sample.docx",
            selected_pdf_page_panel=None,
            preview_rotate_menu_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_import_from_file_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_export_pages_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_move_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_remove_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_adjust_page_width_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_optimize_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_load_all_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(file_preview.office_preview, "get_office_document_page_count", return_value=3), \
             mock.patch.object(file_preview.pdf_utils, "_get_show_pages_limit_for_path", return_value=2):
            file_preview.update_page_buttons_state(owner)

        owner.preview_load_all_btn.Enable.assert_called_once_with(True)

    def test_office_document_page_count_uses_power_shell_before_export(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["get_office_document_page_count"])

        with mock.patch.object(office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(office_preview.subprocess, "run") as mocked_run, \
             mock.patch.object(office_preview, "_safe_remove_file"):
            mocked_run.return_value.returncode = 0
            mocked_run.return_value.stdout = "12\n"
            self.assertEqual(office_preview.get_office_document_page_count("sample.docx"), 12)

        mocked_run.assert_called_once()

    def test_is_office_file_open_uses_timeout_guard_for_hung_office_check(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["is_office_file_open"])

        with mock.patch.object(office_preview.sys, "platform", "win32"), \
             mock.patch.object(office_preview, "win32_client", mock.Mock()), \
             mock.patch.object(office_preview.threading, "Thread") as mocked_thread:
            worker = mock.Mock()
            worker.is_alive.return_value = True
            mocked_thread.return_value = worker
            with mock.patch("controls.file_preview.os.path.isfile", return_value=True):
                self.assertFalse(office_preview.is_office_file_open("sample.docx"))

        mocked_thread.assert_called_once()
        worker.start.assert_called_once()
        worker.join.assert_called_once_with(timeout=office_preview._OFFICE_OPEN_CHECK_TIMEOUT)


class OfficePreviewLimitTests(unittest.TestCase):
    def test_export_word_to_pdf_limits_page_range(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["_export_word_to_pdf"])

        fake_app = mock.Mock()
        fake_doc = mock.Mock()
        fake_app.Documents.Open.return_value = fake_doc

        with mock.patch.object(office_preview, "win32_client", mock.Mock()), \
             mock.patch.object(office_preview, "_get_show_pages_limit_for_path", return_value=3):
            office_preview.win32_client.DispatchEx.return_value = fake_app
            office_preview._export_word_to_pdf("report.docx", "preview.pdf")

        fake_doc.ExportAsFixedFormat.assert_called_once_with("preview.pdf", 17, False, 0, 3, 1, 3)

    def test_convert_office_to_preview_pdf_limits_pages_after_export(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["convert_office_to_preview_pdf"])

        calls = {"isfile": 0}

        def fake_isfile(path):
            calls["isfile"] += 1
            return calls["isfile"] >= 2

        with mock.patch.object(office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(office_preview, "_build_cached_preview_pdf_path", return_value="preview.pdf"), \
             mock.patch.object(office_preview.os.path, "isfile", side_effect=fake_isfile), \
             mock.patch.object(office_preview.os.path, "exists", return_value=True), \
             mock.patch.object(office_preview, "_export_word_to_pdf"), \
             mock.patch.object(office_preview, "_limit_preview_pdf_pages") as mocked_limit, \
             mock.patch.object(office_preview.os, "replace"), \
             mock.patch.object(office_preview, "pythoncom", None), \
             mock.patch.object(office_preview.sys, "platform", "win32"):
            result = office_preview.convert_office_to_preview_pdf("report.docx")

        self.assertEqual(result, "preview.pdf")
        mocked_limit.assert_called_once_with("preview.pdf", __import__("file_operations.pdf_utils", fromlist=["DEFAULT_SHOW_PAGES_LIMIT"]).DEFAULT_SHOW_PAGES_LIMIT)

    def test_powerpoint_export_opens_document_read_only(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["_export_powerpoint_to_pdf"])

        fake_app = mock.Mock()
        fake_presentation = mock.Mock()
        fake_app.Presentations.Open.return_value = fake_presentation

        with mock.patch.object(office_preview, "win32_client", mock.Mock()), \
             mock.patch.object(office_preview, "pythoncom", mock.Mock()):
            office_preview.win32_client.DispatchEx.return_value = fake_app
            office_preview._export_powerpoint_to_pdf("report.pptx", "preview.pdf")

        fake_app.Presentations.Open.assert_called_once_with("report.pptx", ReadOnly=True, WithWindow=False)
        fake_presentation.Close.assert_called_once_with()
        fake_app.Quit.assert_called_once()

    def test_office_ps_scripts_open_files_read_only(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["_build_office_ps_script"])

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as word_file, \
             tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as excel_file, \
             tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as ppt_file:
            word_script = office_preview._build_office_ps_script(word_file.name, output_pdf="preview.pdf")
            excel_script = office_preview._build_office_ps_script(excel_file.name, output_pdf="preview.pdf")
            ppt_script = office_preview._build_office_ps_script(ppt_file.name, output_pdf="preview.pdf")

        self.assertIn("Documents.Open($src, $false, $true)", word_script)
        self.assertIn("Workbooks.Open($src, $false, $true)", excel_script)
        self.assertIn("Presentations.Open($src, $true, $false, $false)", ppt_script)

        for path in (word_file.name, excel_file.name, ppt_file.name):
            if os.path.exists(path):
                os.remove(path)

    def test_export_word_to_pdf_releases_com_objects_on_exit(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["_export_word_to_pdf"])

        fake_app = mock.Mock()
        fake_doc = mock.Mock()
        fake_app.Documents.Open.return_value = fake_doc

        with mock.patch.object(office_preview, "win32_client", mock.Mock()), \
             mock.patch.object(office_preview, "pythoncom", mock.Mock()), \
             mock.patch.object(office_preview, "_get_show_pages_limit_for_path", return_value=3):
            office_preview.win32_client.DispatchEx.return_value = fake_app
            office_preview._export_word_to_pdf("report.docx", "preview.pdf")

            fake_doc.Close.assert_called_once_with(False)
            fake_app.Quit.assert_called_once()
            office_preview.pythoncom.CoUninitialize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
