import importlib
import os
import sys
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


if __name__ == "__main__":
    unittest.main()
