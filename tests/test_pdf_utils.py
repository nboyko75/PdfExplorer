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

        self.assertEqual(settings["color_target_dpi"], 50)
        self.assertEqual(settings["color_threshold_dpi"], 70)
        self.assertEqual(settings["color_quality"], 20)
        self.assertEqual(settings["mono_target_dpi"], 50)
        self.assertEqual(settings["mono_threshold_dpi"], 70)


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


if __name__ == "__main__":
    unittest.main()
