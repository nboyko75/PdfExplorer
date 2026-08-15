import os
import shutil
import tempfile
import unittest
import uuid
from unittest import mock

import fitz

from file_operations import pdf_utils


class OptimizePdfDefaultsTests(unittest.TestCase):
    @mock.patch("file_operations.pdf_utils.load_settings", return_value={})
    def test_advanced_settings_use_balanced_defaults(self, _mock_settings):
        settings = pdf_utils._get_optimize_pdf_advanced_settings()

        self.assertEqual(settings["color_target_dpi"], 110)
        self.assertEqual(settings["color_threshold_dpi"], 140)
        self.assertEqual(settings["color_quality"], 35)
        self.assertEqual(settings["mono_target_dpi"], 110)
        self.assertEqual(settings["mono_threshold_dpi"], 140)


class AdjustPageWidthTests(unittest.TestCase):
    def _create_pdf(self, page_sizes, include_images=None, text=None):
        temp_dir = tempfile.mkdtemp(prefix="pdf-utils-test-", dir=os.getcwd())
        path = os.path.join(temp_dir, f"{uuid.uuid4().hex}.pdf")
        doc = fitz.open()
        try:
            for index, (page_width, page_height) in enumerate(page_sizes):
                page = doc.new_page(width=page_width, height=page_height)
                if include_images and include_images[index]:
                    pix = fitz.Pixmap(fitz.csRGB, 100, 100, b"\x00" * (100 * 100 * 3), 0)
                    page.insert_image(page.rect, stream=pix.tobytes("png"))
                if text:
                    page.insert_text((72, 72), text)
            doc.save(path)
        finally:
            doc.close()

        self.addCleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True) if os.path.isdir(temp_dir) else None)
        return path

    def test_scanned_single_image_pdf_is_adjusted(self):
        path = self._create_pdf([(612, 792), (612, 792), (842, 595)], include_images=[True, True, True])

        with fitz.open(path) as doc:
            self.assertEqual([round(page.rect.width) for page in doc], [612, 612, 842])

        pdf_utils.adjust_page_width(path)
        pdf_utils.save_pdf(path)

        with fitz.open(path) as doc:
            self.assertEqual([round(page.rect.width) for page in doc], [612, 612, 612])

    def test_non_scanned_pdf_is_not_adjusted(self):
        path = self._create_pdf([(612, 792), (842, 595)], text="hello")

        with fitz.open(path) as doc:
            widths_before = [round(page.rect.width) for page in doc]

        pdf_utils.adjust_page_width(path)
        pdf_utils.save_pdf(path)

        with fitz.open(path) as doc:
            widths_after = [round(page.rect.width) for page in doc]
            self.assertEqual(widths_after, widths_before)


class ShowPagesLimitTests(unittest.TestCase):
    def test_get_pdf_page_previews_uses_configured_show_pages_limit(self):
        doc = type(
            "Doc",
            (),
            {
                "__len__": lambda self: 5,
                "__getitem__": lambda self, index: type("Page", (), {"rect": type("Rect", (), {"height": 800.0, "width": 600.0})(), "get_pixmap": lambda *args, **kwargs: type("Pix", (), {"n": 3, "alpha": False, "width": 100, "height": 100, "samples": b"\x00" * 300})()})(),
                "close": lambda self: None,
            },
        )()

        with mock.patch("file_operations.pdf_utils.load_settings", return_value={"pdf_show_pages_limit": 2}), \
             mock.patch("file_operations.pdf_utils._open_pdf_document", return_value=doc), \
             mock.patch("file_operations.pdf_utils.fitz.Matrix", side_effect=lambda sx, sy: (sx, sy)), \
             mock.patch("file_operations.pdf_utils.wx.Bitmap.FromBuffer", side_effect=lambda width, height, samples: type("Bitmap", (), {"width": width, "height": height})()):
            page_count, shown_pages, previews = pdf_utils.get_pdf_page_previews("dummy.pdf")

        self.assertEqual(page_count, 5)
        self.assertEqual(shown_pages, 2)
        self.assertEqual(len(previews), 2)

    def test_get_show_pages_limit_for_path_uses_document_category(self):
        settings = {
            "pdf_show_pages_limit": 2,
            "word_show_pages_limit": 3,
            "excel_show_pages_limit": 4,
            "other_show_pages_limit": 5,
        }

        with mock.patch("file_operations.pdf_utils.load_settings", return_value=settings):
            self.assertEqual(pdf_utils._get_show_pages_limit_for_path("report.pdf"), 2)
            self.assertEqual(pdf_utils._get_show_pages_limit_for_path("report.docx"), 3)
            self.assertEqual(pdf_utils._get_show_pages_limit_for_path("report.xlsx"), 4)
            self.assertEqual(pdf_utils._get_show_pages_limit_for_path("archive.pptx"), 5)

    def test_get_pdf_page_previews_can_force_all_pages(self):
        doc = type(
            "Doc",
            (),
            {
                "__len__": lambda self: 5,
                "__getitem__": lambda self, index: type("Page", (), {"rect": type("Rect", (), {"height": 800.0, "width": 600.0})(), "get_pixmap": lambda *args, **kwargs: type("Pix", (), {"n": 3, "alpha": False, "width": 100, "height": 100, "samples": b"\x00" * 300})()})(),
                "close": lambda self: None,
            },
        )()

        with mock.patch("file_operations.pdf_utils.load_settings", return_value={"show_pages_limit": 2}), \
             mock.patch("file_operations.pdf_utils._open_pdf_document", return_value=doc), \
             mock.patch("file_operations.pdf_utils.fitz.Matrix", side_effect=lambda sx, sy: (sx, sy)), \
             mock.patch("file_operations.pdf_utils.wx.Bitmap.FromBuffer", side_effect=lambda width, height, samples: type("Bitmap", (), {"width": width, "height": height})()):
            page_count, shown_pages, previews = pdf_utils.get_pdf_page_previews("dummy.pdf", force_all_pages=True)

        self.assertEqual(page_count, 5)
        self.assertEqual(shown_pages, 5)
        self.assertEqual(len(previews), 5)


class GetPdfPagePreviewsSizingTests(unittest.TestCase):
    @staticmethod
    def _make_fake_doc(width=600.0, height=800.0):
        class _Rect:
            def __init__(self, w, h):
                self.width = w
                self.height = h

        class _Page:
            def __init__(self, w, h):
                self.rect = _Rect(w, h)

            def get_pixmap(self, matrix, alpha=False):
                sx, sy = matrix
                pix_width = max(1, int(round(self.rect.width * sx)))
                pix_height = max(1, int(round(self.rect.height * sy)))
                return type(
                    "Pix",
                    (),
                    {
                        "width": pix_width,
                        "height": pix_height,
                        "n": 3,
                        "alpha": False,
                        "samples": b"\x00" * (pix_width * pix_height * 3),
                    },
                )()

        class _Doc:
            def __init__(self, pages):
                self._pages = pages

            def __len__(self):
                return len(self._pages)

            def __getitem__(self, index):
                return self._pages[index]

            def close(self):
                return None

        return _Doc([_Page(width, height)])

    @staticmethod
    def _fake_bitmap_from_buffer(width, height, _samples):
        return type("Bitmap", (), {"width": width, "height": height})()

    def test_target_box_keeps_original_aspect_ratio(self):
        doc = self._make_fake_doc(600.0, 800.0)

        with mock.patch("file_operations.pdf_utils._open_pdf_document", return_value=doc), \
             mock.patch("file_operations.pdf_utils.fitz.Matrix", side_effect=lambda sx, sy: (sx, sy)), \
             mock.patch("file_operations.pdf_utils.wx.Bitmap.FromBuffer", side_effect=self._fake_bitmap_from_buffer):
            page_count, shown_pages, previews = pdf_utils.get_pdf_page_previews(
                "dummy.pdf",
                target_width=600,
                target_height=600,
            )

        self.assertEqual(page_count, 1)
        self.assertEqual(shown_pages, 1)
        self.assertEqual(len(previews), 1)

        _page_no, bitmap = previews[0]
        self.assertEqual(bitmap.width, 450)
        self.assertEqual(bitmap.height, 600)

    def test_wide_mode_signal_prefers_scale_x(self):
        doc = self._make_fake_doc(600.0, 800.0)

        with mock.patch("file_operations.pdf_utils._open_pdf_document", return_value=doc), \
             mock.patch("file_operations.pdf_utils.fitz.Matrix", side_effect=lambda sx, sy: (sx, sy)), \
             mock.patch("file_operations.pdf_utils.wx.Bitmap.FromBuffer", side_effect=self._fake_bitmap_from_buffer):
            _page_count, _shown_pages, previews = pdf_utils.get_pdf_page_previews(
                "dummy.pdf",
                target_width=600,
                target_height=600,
                avg_width=600.0,
                avg_height=None,
            )

        _page_no, bitmap = previews[0]
        self.assertEqual(bitmap.width, 600)
        self.assertEqual(bitmap.height, 800)

    def test_tall_mode_signal_prefers_scale_y(self):
        doc = self._make_fake_doc(600.0, 800.0)

        with mock.patch("file_operations.pdf_utils._open_pdf_document", return_value=doc), \
             mock.patch("file_operations.pdf_utils.fitz.Matrix", side_effect=lambda sx, sy: (sx, sy)), \
             mock.patch("file_operations.pdf_utils.wx.Bitmap.FromBuffer", side_effect=self._fake_bitmap_from_buffer):
            _page_count, _shown_pages, previews = pdf_utils.get_pdf_page_previews(
                "dummy.pdf",
                target_width=600,
                target_height=600,
                avg_width=None,
                avg_height=800.0,
            )

        _page_no, bitmap = previews[0]
        self.assertEqual(bitmap.width, 450)
        self.assertEqual(bitmap.height, 600)


if __name__ == "__main__":
    unittest.main()
