import importlib
import os
import sys
import tempfile
import types
import unittest
import wx
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

    def test_show_file_preview_for_plain_text_file(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path=None,
            preview_enabled=True,
            preview_text=types.SimpleNamespace(Show=mock.MagicMock(), SetValue=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            pdf_preview_container=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as temp_file:
            temp_file.write("hello from text preview")
            temp_path = temp_file.name

        try:
            with mock.patch("controls.file_preview.os.path.isdir", return_value=False), \
                 mock.patch("controls.file_preview.os.path.isfile", return_value=True), \
                 mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
                 mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False), \
                 mock.patch.object(file_preview, "is_office_preview_allowed", return_value=False), \
                 mock.patch.object(file_preview, "can_preview_html", return_value=False), \
                 mock.patch.object(file_preview, "update_preview_toolbar_visibility"), \
                 mock.patch.object(file_preview, "update_page_buttons_state"), \
                 mock.patch.object(file_preview, "update_pdf_save_button_state"):
                file_preview.show_file_preview(owner, temp_path)

            owner.preview_text.SetValue.assert_called_once_with("hello from text preview")
            owner.preview_text.Show.assert_any_call(True)
        finally:
            os.unlink(temp_path)

    def test_update_page_buttons_disables_zoom_when_preview_not_supported(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="unsupported.txt",
            selected_pdf_page_panel=None,
            preview_rotate_menu_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_import_from_file_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_export_pages_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_move_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_remove_page_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_adjust_page_width_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_optimize_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_zoom_in_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
            preview_zoom_out_btn=types.SimpleNamespace(Enable=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False), \
             mock.patch.object(file_preview, "is_office_preview_allowed", return_value=False), \
             mock.patch.object(file_preview, "can_preview_html", return_value=False), \
             mock.patch.object(file_preview, "can_preview_text_file", return_value=False):
            file_preview.update_page_buttons_state(owner)

        owner.preview_zoom_in_btn.Enable.assert_called_once_with(False)
        owner.preview_zoom_out_btn.Enable.assert_called_once_with(False)

    def test_toggle_preview_tab_pin_keeps_active_tab_and_moves_single_unpinned_to_right(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_tabs=[
                {"path": "left.pdf", "pinned": True},
                {"path": "mid.pdf", "pinned": True},
                {"path": "right.pdf", "pinned": False},
            ],
            preview_active_tab_index=0,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        file_preview._toggle_preview_tab_pin(owner, 0)

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["mid.pdf", "right.pdf", "left.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 2)
        self.assertFalse(owner.preview_tabs[2]["pinned"])

    def test_normalize_preview_tabs_allows_multiple_unpinned_tabs_and_keeps_active_unpinned_last(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_tabs=[
                {"path": "first.pdf", "pinned": True},
                {"path": "second.pdf", "pinned": False},
                {"path": "third.pdf", "pinned": False},
                {"path": "fourth.pdf", "pinned": True},
            ],
            preview_active_tab_index=1,
        )

        file_preview._normalize_preview_tabs(owner)

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["first.pdf", "fourth.pdf", "third.pdf", "second.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 3)
        self.assertFalse(owner.preview_tabs[-1]["pinned"])
        self.assertEqual(sum(1 for tab in owner.preview_tabs if not tab.get("pinned", False)), 2)

    def test_sync_preview_tab_for_path_reuses_first_unpinned_tab_or_creates_new_one(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_tabs=[
                {"path": "pinned.pdf", "pinned": True, "caption": "pinned.pdf", "hint": "pinned.pdf"},
                {"path": "old-right.pdf", "pinned": False, "caption": "old-right.pdf", "hint": "old-right.pdf"},
                {"path": "other-right.pdf", "pinned": False, "caption": "other-right.pdf", "hint": "other-right.pdf"},
            ],
            preview_active_tab_index=0,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        file_preview._sync_preview_tab_for_path(owner, "new-file.pdf")

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["pinned.pdf", "old-right.pdf", "new-file.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 2)

        owner = types.SimpleNamespace(
            preview_tabs=[
                {"path": "pinned.pdf", "pinned": True, "caption": "pinned.pdf", "hint": "pinned.pdf"},
            ],
            preview_active_tab_index=0,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        file_preview._sync_preview_tab_for_path(owner, "fresh.pdf")

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["pinned.pdf", "fresh.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 1)

    def test_sync_preview_tab_for_path_respects_preview_settings(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_enabled=False,
            office_preview_enabled=False,
            preview_tabs=[],
            preview_active_tab_index=None,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        file_preview._sync_preview_tab_for_path(owner, "report.docx")

        self.assertEqual(owner.preview_tabs, [])
        self.assertIsNone(owner.preview_active_tab_index)

        owner = types.SimpleNamespace(
            preview_enabled=True,
            office_preview_enabled=False,
            preview_tabs=[],
            preview_active_tab_index=None,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        with mock.patch.object(file_preview.office_preview, "can_preview_office", return_value=True), \
             mock.patch.object(file_preview, "is_office_preview_allowed", return_value=False):
            file_preview._sync_preview_tab_for_path(owner, "report.docx")

        self.assertEqual(owner.preview_tabs, [])
        self.assertIsNone(owner.preview_active_tab_index)

    def test_sync_preview_tab_for_path_ignores_folder_paths(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_enabled=True,
            office_preview_enabled=False,
            preview_tabs=[
                {"path": "folder", "pinned": False, "caption": "folder", "hint": "folder"},
                {"path": "keep.pdf", "pinned": False, "caption": "keep.pdf", "hint": "keep.pdf"},
            ],
            preview_active_tab_index=1,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        with mock.patch("controls.file_preview.os.path.isdir", side_effect=lambda path: path == "folder"):
            file_preview._sync_preview_tab_for_path(owner, "folder")

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["keep.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 0)

    def test_sync_preview_tab_for_path_removes_unpinned_tabs_for_unpreviewable_file(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_enabled=True,
            office_preview_enabled=False,
            preview_tabs=[
                {"path": "pinned.pdf", "pinned": True, "caption": "pinned.pdf", "hint": "pinned.pdf"},
                {"path": "stale.pdf", "pinned": False, "caption": "stale.pdf", "hint": "stale.pdf"},
                {"path": "other.pdf", "pinned": False, "caption": "other.pdf", "hint": "other.pdf"},
            ],
            preview_active_tab_index=2,
            preview_tab_pane=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            preview_tab_sizer=types.SimpleNamespace(Clear=mock.MagicMock(), Add=mock.MagicMock()),
            preview_content_panel=types.SimpleNamespace(Layout=mock.MagicMock(), Refresh=mock.MagicMock()),
        )

        with mock.patch.object(file_preview, "is_office_preview_allowed", return_value=False), \
             mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False), \
             mock.patch.object(file_preview, "can_preview_html", return_value=False), \
             mock.patch.object(file_preview, "can_preview_text_file", return_value=False), \
             mock.patch("controls.file_preview.os.path.isfile", return_value=True):
            file_preview._sync_preview_tab_for_path(owner, "report.docx")

        self.assertEqual([tab["path"] for tab in owner.preview_tabs], ["pinned.pdf"])
        self.assertEqual(owner.preview_active_tab_index, 0)

    def test_unavailable_zoom_action_does_not_show_message_box(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_preview_path="unsupported.txt",
            preview_zoom_in_btn=types.SimpleNamespace(),
            preview_zoom_out_btn=types.SimpleNamespace(),
        )

        with mock.patch.object(file_preview, "is_pdf_file", return_value=False), \
             mock.patch.object(file_preview.image_utils, "can_preview_image", return_value=False), \
             mock.patch.object(file_preview, "is_office_preview_allowed", return_value=False), \
             mock.patch.object(file_preview, "can_preview_html", return_value=False), \
             mock.patch.object(file_preview, "can_preview_text_file", return_value=False), \
             mock.patch.object(file_preview.wx, "MessageBox") as mocked_message_box:
            file_preview.on_preview_zoom_in(types.SimpleNamespace())

        mocked_message_box.assert_not_called()

    def test_show_html_preview_uses_integer_zoom_percent_for_webview(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            current_html_zoom=1.25,
            preview_text=types.SimpleNamespace(Show=mock.MagicMock(), SetValue=mock.MagicMock()),
            pdf_pages_panel=types.SimpleNamespace(Hide=mock.MagicMock(), Show=mock.MagicMock(), Layout=mock.MagicMock()),
            pdf_preview_container=types.SimpleNamespace(
                Show=mock.MagicMock(),
                Hide=mock.MagicMock(),
                Layout=mock.MagicMock(),
                GetClientSize=lambda: (800, 600),
                GetSizer=lambda: None,
                SetSizer=mock.MagicMock(),
            ),
            filePreview=types.SimpleNamespace(Layout=mock.MagicMock()),
        )
        html_preview = types.SimpleNamespace(
            SetZoom=mock.MagicMock(),
            LoadURL=mock.MagicMock(),
            SetPage=mock.MagicMock(),
            SetMinSize=mock.MagicMock(),
            SetSize=mock.MagicMock(),
        )

        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as temp_file:
            temp_file.write("<html><body>test</body></html>")
            temp_path = temp_file.name

        try:
            with mock.patch.object(file_preview, "_ensure_html_preview_widget", return_value=html_preview):
                file_preview.show_html_preview(owner, temp_path)
        finally:
            os.unlink(temp_path)

        html_preview.SetZoom.assert_called_once_with(125)

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

    def test_office_preview_toggle_reloads_selected_file_when_enabled(self):
        file_preview = _import_file_preview_with_mocked_wx()
        owner = types.SimpleNamespace(
            preview_enabled=True,
            office_preview_enabled=False,
            current_preview_path="report.docx",
            preview_checkbox=types.SimpleNamespace(GetValue=lambda: True),
            office_preview_checkbox=types.SimpleNamespace(GetValue=lambda: True),
        )

        with mock.patch.object(file_preview, "show_file_preview") as mocked_show_file_preview:
            event = types.SimpleNamespace(GetEventObject=lambda: owner.office_preview_checkbox)
            with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner):
                file_preview.on_office_preview_checkbox_toggle(event)

        self.assertTrue(owner.office_preview_enabled)
        self.assertEqual(mocked_show_file_preview.call_count, 2)
        mocked_show_file_preview.assert_any_call(owner, None)
        mocked_show_file_preview.assert_any_call(owner, "report.docx")

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
             mock.patch.object(filelist.wx, "TextDataObject") as mocked_text_data, \
             mock.patch.object(filelist.wx, "DataObjectComposite") as mocked_composite, \
             mock.patch.object(filelist.wx, "DropSource") as mocked_drop_source, \
             mock.patch.object(filelist.wx, "Drag_AllowMove", create=True, new=object()) as drag_allow_move:
            data = mock.MagicMock()
            marker_data = mock.MagicMock()
            composite_data = mock.MagicMock()
            mocked_file_data.return_value = data
            mocked_text_data.return_value = marker_data
            mocked_composite.return_value = composite_data
            src = mock.MagicMock()
            mocked_drop_source.return_value = src

            filelist.on_list_begin_drag(owner, None)

        data.AddFile.assert_has_calls([mock.call("C:/first.txt"), mock.call("C:/second.txt")])
        composite_data.Add.assert_any_call(data, filelist.wx.DATADOBJECT_PREFERRED)
        composite_data.Add.assert_any_call(marker_data)
        mocked_drop_source.assert_called_once_with(owner.list)
        src.SetData.assert_called_once_with(composite_data)
        src.DoDragDrop.assert_called_once_with(drag_allow_move)

    def test_file_list_drag_out_marks_internal_moves_for_folder_drops(self):
        filelist = __import__("controls.filelist", fromlist=["on_list_begin_drag", "get_selected_list_paths"])
        owner = types.SimpleNamespace(list=object())
        selected_paths = ["C:/first.txt"]

        with mock.patch.object(filelist, "get_selected_list_paths", return_value=selected_paths), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: path in selected_paths), \
             mock.patch.object(filelist.wx, "FileDataObject") as mocked_file_data, \
             mock.patch.object(filelist.wx, "TextDataObject") as mocked_text_data, \
             mock.patch.object(filelist.wx, "DataObjectComposite") as mocked_composite, \
             mock.patch.object(filelist.wx, "DropSource") as mocked_drop_source, \
             mock.patch.object(filelist.wx, "Drag_AllowMove", create=True, new=object()) as drag_allow_move:
            file_data = mock.MagicMock()
            marker_data = mock.MagicMock()
            composite_data = mock.MagicMock()
            mocked_file_data.return_value = file_data
            mocked_text_data.return_value = marker_data
            mocked_composite.return_value = composite_data
            src = mock.MagicMock()
            mocked_drop_source.return_value = src

            filelist.on_list_begin_drag(owner, None)

        composite_data.Add.assert_any_call(file_data, filelist.wx.DATADOBJECT_PREFERRED)
        composite_data.Add.assert_any_call(marker_data)
        mocked_drop_source.assert_called_once_with(owner.list)
        src.SetData.assert_called_once_with(composite_data)
        src.DoDragDrop.assert_called_once_with(drag_allow_move)
        marker_data.SetText.assert_called_once_with(filelist.drag_and_drop.INTERNAL_DRAG_MARKER)

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

    def test_list_pane_drops_into_folder_row_target(self):
        filelist = __import__("controls.filelist", fromlist=["FileListDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), list=mock.MagicMock())
        owner.list.HitTest.return_value = (0, 0)
        owner.list.GetItemText.return_value = "folder"

        with mock.patch.object(filelist, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(filelist.shutil, "copy2") as mocked_copy, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist.os.path, "isdir", side_effect=lambda path: path == os.path.join("C:/current", "folder")), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: path in {os.path.join("C:/current", "folder"), "C:/drop.txt"}):
            drop_target = filelist.FileListDropTarget(owner)
            result = drop_target.OnDropFiles(10, 20, ["C:/drop.txt"])

        expected_destination = os.path.join("C:/current", "folder", "drop.txt")
        self.assertTrue(result)
        mocked_copy.assert_called_once_with("C:/drop.txt", expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=[os.path.join("C:/current", "folder")])

    def test_tree_pane_drops_into_folder_node_target(self):
        filelist = __import__("controls.filelist", fromlist=["_refresh_after_fs_change"])
        drag_and_drop = __import__("controls.drag_and_drop", fromlist=["TreeDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), tree=mock.MagicMock())
        target_item = mock.MagicMock()
        target_item.IsOk.return_value = True
        owner.tree.HitTest.return_value = (target_item, 0)
        owner.tree.GetItemData.return_value = os.path.join("C:/current", "folder")

        with mock.patch.object(drag_and_drop, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(drag_and_drop.shutil, "copy2") as mocked_copy, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(drag_and_drop.os.path, "isdir", side_effect=lambda path: path == os.path.join("C:/current", "folder")), \
             mock.patch.object(drag_and_drop.os.path, "exists", side_effect=lambda path: path in {os.path.join("C:/current", "folder"), "C:/drop.txt"}):
            drop_target = drag_and_drop.TreeDropTarget(owner)
            result = drop_target.OnDropFiles(10, 20, ["C:/drop.txt"])

        expected_destination = os.path.join("C:/current", "folder", "drop.txt")
        self.assertTrue(result)
        mocked_copy.assert_called_once_with("C:/drop.txt", expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=[os.path.join("C:/current", "folder")])

    def test_drop_targets_prompt_before_overwriting_existing_file(self):
        drag_and_drop = __import__("controls.drag_and_drop", fromlist=["FileListDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), list=mock.MagicMock())
        owner.list.HitTest.return_value = (wx.NOT_FOUND, 0)

        with mock.patch.object(drag_and_drop.copy_and_paste, "_confirm_overwrite_existing_path", return_value=True) as mocked_confirm, \
             mock.patch.object(drag_and_drop, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(drag_and_drop.shutil, "copy2") as mocked_copy, \
             mock.patch.object(drag_and_drop, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(drag_and_drop.os.path, "isdir", side_effect=lambda path: os.path.normpath(path) == os.path.normpath("C:/current")), \
             mock.patch.object(drag_and_drop.os.path, "exists", side_effect=lambda path: os.path.normpath(path) in {os.path.normpath("C:/current"), os.path.normpath("C:/drop.txt"), os.path.normpath(os.path.join("C:/current", "drop.txt"))}):
            drop_target = drag_and_drop.FileListDropTarget(owner)
            result = drop_target.OnDropFiles(10, 20, ["C:/drop.txt"])

        expected_destination = os.path.join("C:/current", "drop.txt")
        self.assertTrue(result)
        mocked_confirm.assert_called_once_with(owner, expected_destination)
        mocked_copy.assert_called_once_with("C:/drop.txt", expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=["C:/current"])

    def test_tree_pane_drag_move_refreshes_source_and_target_folders(self):
        filelist = __import__("controls.filelist", fromlist=["_refresh_after_fs_change"])
        drag_and_drop = __import__("controls.drag_and_drop", fromlist=["TreeDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), tree=mock.MagicMock())
        target_item = mock.MagicMock()
        target_item.IsOk.return_value = True
        owner.tree.HitTest.return_value = (target_item, 0)
        owner.tree.GetItemData.return_value = os.path.join("C:/current", "folder")

        with mock.patch.object(drag_and_drop, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(drag_and_drop.shutil, "move") as mocked_move, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(drag_and_drop.os.path, "isdir", side_effect=lambda path: path in {"C:/source", os.path.join("C:/current", "folder")}), \
             mock.patch.object(drag_and_drop.os.path, "exists", side_effect=lambda path: path == "C:/source/old.txt"):
            drop_target = drag_and_drop.TreeDropTarget(owner)
            drop_target.text_data.GetText = mock.MagicMock(return_value=drag_and_drop.INTERNAL_DRAG_MARKER + "\nC:/source/old.txt")
            with mock.patch.object(drop_target, "GetData", return_value=True):
                result = drop_target.OnDrop(10, 20)

        expected_destination = os.path.join("C:/current", "folder", "old.txt")
        self.assertTrue(result)
        mocked_move.assert_called_once_with("C:/source/old.txt", expected_destination)
        mocked_refresh.assert_called_once_with(owner, affected_dirs=[os.path.join("C:/current", "folder"), "C:/source"])

    def test_drop_targets_implement_ondata_for_wx_drag_transfer(self):
        filelist = __import__("controls.filelist", fromlist=["FileListDropTarget"])
        drag_and_drop = __import__("controls.drag_and_drop", fromlist=["TreeDropTarget", "FileListDropTarget"])
        owner = types.SimpleNamespace(path_box=types.SimpleNamespace(GetValue=lambda: "C:/current"), list=mock.MagicMock())
        owner.list.HitTest.return_value = (wx.NOT_FOUND, 0)

        drop_target = filelist.FileListDropTarget(owner)
        drop_target.file_data.GetFilenames = mock.MagicMock(return_value=["C:/drop.txt"])
        drop_target.text_data.GetText = mock.MagicMock(return_value=drag_and_drop.INTERNAL_DRAG_MARKER + "\nC:/drop.txt")
        with mock.patch.object(drop_target, "GetData", return_value=True), \
             mock.patch.object(filelist, "_build_non_conflicting_path", side_effect=lambda path: path), \
             mock.patch.object(filelist.shutil, "move") as mocked_move, \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist.os.path, "isdir", side_effect=lambda path: path == "C:/current"), \
             mock.patch.object(filelist.os.path, "exists", side_effect=lambda path: path in {"C:/current", "C:/drop.txt"}):
            result = drop_target.OnData(0, 0, wx.DragCopy)

        self.assertEqual(result, wx.DragMove)
        mocked_move.assert_called_once_with("C:/drop.txt", os.path.join("C:/current", "drop.txt"))
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

    def test_handle_file_ops_shortcut_supports_shift_delete_key(self):
        filelist = __import__("controls.filelist", fromlist=["handle_file_ops_shortcut", "on_list_delete_permanent", "on_tree_delete_permanent"])
        owner = types.SimpleNamespace(
            list=object(),
            tree=object(),
        )
        focus = types.SimpleNamespace(GetParent=lambda: owner.list)
        event = types.SimpleNamespace(ControlDown=mock.MagicMock(return_value=False), ShiftDown=mock.MagicMock(return_value=True), GetKeyCode=mock.MagicMock(return_value=ord("D")))

        with mock.patch.object(filelist.wx.Window, "FindFocus", return_value=focus), \
             mock.patch.object(filelist, "on_list_delete_permanent") as mocked_delete_permanent, \
             mock.patch.object(filelist, "on_tree_delete_permanent") as mocked_tree_delete_permanent:
            result = filelist.handle_file_ops_shortcut(owner, event)

        self.assertTrue(result)
        mocked_delete_permanent.assert_called_once_with(owner, None)
        mocked_tree_delete_permanent.assert_not_called()

    def test_handle_file_ops_shortcut_supports_print_key(self):
        filelist = __import__("controls.filelist", fromlist=["handle_file_ops_shortcut", "on_list_print", "on_tree_delete"])
        owner = types.SimpleNamespace(
            list=object(),
            tree=object(),
        )
        focus = types.SimpleNamespace(GetParent=lambda: owner.list)
        event = types.SimpleNamespace(ControlDown=mock.MagicMock(return_value=True), GetKeyCode=mock.MagicMock(return_value=ord("P")))

        with mock.patch.object(filelist.wx.Window, "FindFocus", return_value=focus), \
             mock.patch.object(filelist, "on_list_print") as mocked_list_print, \
             mock.patch.object(filelist, "on_tree_delete") as mocked_tree_delete:
            result = filelist.handle_file_ops_shortcut(owner, event)

        self.assertTrue(result)
        mocked_list_print.assert_called_once_with(owner, None)
        mocked_tree_delete.assert_not_called()

    def test_remove_tree_item_for_path_selects_immediate_parent_folder(self):
        filelist = __import__("controls.filelist", fromlist=["_remove_tree_item_for_path"])
        owner = types.SimpleNamespace(tree=mock.MagicMock())
        root = mock.MagicMock()
        root.IsOk.return_value = True
        parent = mock.MagicMock()
        parent.IsOk.return_value = True
        deleted_item = mock.MagicMock()
        deleted_item.IsOk.return_value = True
        owner.tree.GetRootItem.return_value = root
        owner.tree.GetItemParent.return_value = parent
        owner.tree.GetChildrenCount.return_value = 1

        with mock.patch.object(filelist, "_find_tree_item_without_expanding", return_value=deleted_item):
            filelist._remove_tree_item_for_path(owner, "C:/folder/file.txt")

        owner.tree.SelectItem.assert_called_once_with(parent)

    def test_copy_and_paste_reads_native_explorer_clipboard(self):
        copy_and_paste = __import__("file_operations.copy_and_paste", fromlist=["_get_clipboard_paths", "_get_clipboard_mode", "CLIPBOARD_MODE_COPY"])
        owner = types.SimpleNamespace(file_clipboard_paths=[], file_clipboard_mode=None)
        fake_clipboard = mock.MagicMock()
        fake_clipboard.Open.return_value = True
        fake_data = mock.MagicMock()
        fake_data.GetFilenames.return_value = ["C:/explorer/source.txt"]
        fake_clipboard.GetData.return_value = True

        with mock.patch.object(copy_and_paste.wx, "TheClipboard", fake_clipboard), \
             mock.patch.object(copy_and_paste.wx, "FileDataObject", return_value=fake_data):
            self.assertEqual(copy_and_paste._get_clipboard_paths(owner), [os.path.normpath("C:/explorer/source.txt")])
            self.assertEqual(copy_and_paste._get_clipboard_mode(owner), copy_and_paste.CLIPBOARD_MODE_COPY)

    def test_copy_and_paste_writes_native_explorer_clipboard(self):
        copy_and_paste = __import__("file_operations.copy_and_paste", fromlist=["_set_clipboard", "CLIPBOARD_MODE_COPY"])
        owner = types.SimpleNamespace(file_clipboard_paths=[], file_clipboard_mode=None)
        fake_clipboard = mock.MagicMock()
        fake_clipboard.Open.return_value = True
        fake_data = mock.MagicMock()

        with mock.patch.object(copy_and_paste.wx, "TheClipboard", fake_clipboard), \
             mock.patch.object(copy_and_paste.wx, "FileDataObject", return_value=fake_data):
            copy_and_paste._set_clipboard(owner, ["C:/source.txt"], copy_and_paste.CLIPBOARD_MODE_COPY)

        fake_clipboard.SetData.assert_called_once_with(fake_data)
        fake_clipboard.Flush.assert_called_once()

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

    def test_list_rename_refreshes_only_renamed_item(self):
        filelist = __import__("controls.filelist", fromlist=["on_list_rename", "_refresh_after_fs_change", "select_list_item_by_path"])
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
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "select_list_item_by_path") as mocked_select_list:
            filelist.on_list_rename(owner, None)

        expected_old = os.path.join("C:/current", "old.txt")
        expected_new = os.path.join("C:/current", "new.txt")
        mocked_rename.assert_called_once_with(expected_old, expected_new)
        mocked_refresh.assert_not_called()
        mocked_select_list.assert_called_once_with(owner, expected_new)

    def test_tree_rename_uses_selected_tree_path_without_parent_refresh(self):
        filelist = __import__("controls.filelist", fromlist=["on_tree_rename", "_refresh_after_fs_change"])
        owner = types.SimpleNamespace(tree=mock.MagicMock())
        tree_path = os.path.join("C:/current", "old.txt")

        dialog = mock.MagicMock()
        dialog.ShowModal.return_value = filelist.wx.ID_OK
        dialog.GetValue.return_value = "new.txt"

        with mock.patch.object(filelist.os, "rename") as mocked_rename, \
             mock.patch.object(filelist.wx, "TextEntryDialog", return_value=dialog), \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "_resolve_tree_selection_path", return_value=tree_path), \
             mock.patch.object(filelist, "_find_tree_item_without_expanding", return_value=None):
            filelist.on_tree_rename(owner, None)

        expected_old = tree_path
        expected_new = os.path.join("C:/current", "new.txt")
        mocked_rename.assert_called_once_with(expected_old, expected_new)
        mocked_refresh.assert_not_called()

    def test_list_rename_keeps_renamed_item_selected(self):
        filelist = __import__("controls.filelist", fromlist=["on_list_rename", "_refresh_after_fs_change", "select_list_item_by_path"])
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

        dialog = mock.MagicMock()
        dialog.ShowModal.return_value = filelist.wx.ID_OK
        dialog.GetValue.return_value = "new.txt"

        with mock.patch.object(filelist.os, "rename") as mocked_rename, \
             mock.patch.object(filelist.wx, "TextEntryDialog", return_value=dialog), \
             mock.patch.object(filelist, "_refresh_after_fs_change") as mocked_refresh, \
             mock.patch.object(filelist, "select_list_item_by_path") as mocked_select_list:
            filelist.on_list_rename(owner, None)

        expected_old = os.path.join("C:/current", "old.txt")
        expected_new = os.path.join("C:/current", "new.txt")
        mocked_rename.assert_called_once_with(expected_old, expected_new)
        mocked_refresh.assert_not_called()
        mocked_select_list.assert_called_once_with(owner, expected_new)

    def test_delete_tree_item_keeps_parent_selected_instead_of_root(self):
        filelist = __import__("controls.filelist", fromlist=["_remove_tree_item_for_path"])

        class FakeItem:
            def __init__(self, ok=True):
                self._ok = ok
                self.parent = None

            def IsOk(self):
                return self._ok

        class FakeTree:
            def __init__(self):
                self.selected = None
                self.deleted = None
                self.root = FakeItem()
                self.parent = FakeItem()
                self.item = FakeItem()
                self.item.parent = self.parent

            def GetRootItem(self):
                return self.root

            def GetItemParent(self, item):
                return item.parent if item.parent is not None else FakeItem(ok=False)

            def GetChildrenCount(self, item):
                return 0

            def AppendItem(self, parent, label):
                return FakeItem()

            def Delete(self, item):
                self.deleted = item

            def SelectItem(self, item):
                self.selected = item

        tree = FakeTree()
        owner = types.SimpleNamespace(tree=tree)

        with mock.patch.object(filelist, "_find_tree_item_without_expanding", return_value=tree.item):
            filelist._remove_tree_item_for_path(owner, "C:/current/old.txt")

        self.assertIs(tree.selected, tree.parent)
        self.assertIs(tree.deleted, tree.item)

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

    def test_office_exports_reuse_already_open_document(self):
        office_preview = __import__("file_operations.office_preview", fromlist=["_export_word_to_pdf", "_export_excel_to_pdf", "_export_powerpoint_to_pdf"])

        cases = [
            ("Word.Application", ".docx", "Documents", "_export_word_to_pdf", "ExportAsFixedFormat"),
            ("Excel.Application", ".xlsx", "Workbooks", "_export_excel_to_pdf", "ExportAsFixedFormat"),
            ("PowerPoint.Application", ".pptx", "Presentations", "_export_powerpoint_to_pdf", "SaveAs"),
        ]

        for app_name, ext, collection_name, export_name, export_method in cases:
            with self.subTest(app_name=app_name):
                target_path = f"C:/temp/report{ext}"
                existing_app = mock.Mock()
                existing_document = mock.Mock()
                existing_document.FullName = target_path
                setattr(existing_app, collection_name, [existing_document])

                with mock.patch.object(office_preview, "win32_client", mock.Mock()), \
                     mock.patch.object(office_preview, "pythoncom", mock.Mock()), \
                     mock.patch.object(office_preview.win32_client, "GetActiveObject", return_value=existing_app), \
                     mock.patch.object(office_preview.win32_client, "DispatchEx") as mocked_dispatch:
                    getattr(office_preview, export_name)(target_path, "preview.pdf")

                mocked_dispatch.assert_not_called()
                getattr(existing_document, export_method).assert_called_once()
                existing_document.Close.assert_not_called()
                existing_app.Quit.assert_not_called()


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
