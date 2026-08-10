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


if __name__ == "__main__":
    unittest.main()
