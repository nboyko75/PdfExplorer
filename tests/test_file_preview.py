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


if __name__ == "__main__":
    unittest.main()
