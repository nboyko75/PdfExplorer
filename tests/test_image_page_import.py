import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from types import SimpleNamespace
from unittest import mock

import fitz
from PIL import Image, ImageDraw

from file_operations import pdf_utils


class ImagePageImportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.getcwd())
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.target = str(self.directory / "target.pdf")
        self.addCleanup(pdf_utils.discard_pdf_changes, self.target)
        with fitz.open() as document:
            for text in ("Before", "After"):
                page = document.new_page()
                page.insert_text((72, 72), text)
            document.save(self.target)

    def make_image(self):
        image = Image.new("RGB", (1200, 1800), "white")
        draw = ImageDraw.Draw(image)
        draw.text((30, 30), "Small text: 0123456789 ABC abc", fill="black")
        for x in range(30, 120, 3):
            draw.line((x, 60, x, 130), fill="black", width=1)
        return image

    def test_lossless_images_keep_every_pixel_at_scan_resolutions(self):
        for extension, dpi in (("png", 300), ("tiff", 600), ("bmp", 96)):
            with self.subTest(extension=extension, dpi=dpi):
                pdf_utils.discard_pdf_changes(self.target)
                source = self.directory / ("scan." + extension)
                with self.make_image() as image:
                    image.save(source, dpi=(dpi, dpi))
                    expected_pixels = image.tobytes()
                pdf_utils.import_pdf_pages(self.target, str(source), 1)
                with pdf_utils._open_pdf_document(self.target) as document:
                    page = document[1]
                    self.assertEqual(len(document), 3)
                    image_info = page.get_images()[0]
                    self.assertEqual(image_info[2:4], (1200, 1800))
                    pixmap = fitz.Pixmap(document, image_info[0])
                    self.assertEqual(pixmap.samples, expected_pixels)
                    self.assertAlmostEqual(page.rect.width, 1200 * 72 / dpi, delta=1)
                    self.assertAlmostEqual(page.rect.height, 1800 * 72 / dpi, delta=1)

    def test_jpeg_is_embedded_without_recompression_and_survives_save(self):
        source = self.directory / "scan.jpg"
        with self.make_image() as image:
            image.save(source, quality=90, dpi=(300, 300))
        original_pdf = Path(self.target).read_bytes()
        pdf_utils.import_pdf_pages(self.target, str(source), 1)
        self.assertEqual(Path(self.target).read_bytes(), original_pdf)
        self.assertTrue(pdf_utils.has_unsaved_pdf_changes(self.target))
        pdf_utils.save_pdf(self.target)
        with fitz.open(self.target) as document:
            image_info = document[1].get_images()[0]
            self.assertEqual(image_info[2:4], (1200, 1800))
            extracted = document.extract_image(image_info[0])
            self.assertEqual(extracted["image"], source.read_bytes())
            self.assertEqual(document[0].get_text().strip(), "Before")
            self.assertEqual(document[2].get_text().strip(), "After")

    def test_multipage_tiff_keeps_resolution_and_insertion_order(self):
        source = self.directory / "scan.tiff"
        with Image.new("L", (600, 900), 32) as first, Image.new("L", (900, 600), 224) as second:
            first.save(source, save_all=True, append_images=[second], dpi=(300, 300))
        pdf_utils.import_pdf_pages(self.target, str(source), 1)
        with pdf_utils._open_pdf_document(self.target) as document:
            self.assertEqual(len(document), 4)
            self.assertEqual(document[0].get_text().strip(), "Before")
            self.assertEqual(document[3].get_text().strip(), "After")
            for index, size, shade in ((1, (600, 900), 32), (2, (900, 600), 224)):
                image_info = document[index].get_images()[0]
                self.assertEqual(image_info[2:4], size)
                extracted = document.extract_image(image_info[0])
                with Image.open(io.BytesIO(extracted["image"])) as image:
                    with image.convert("RGB") as pixels:
                        self.assertEqual(pixels.getpixel((0, 0)), (shade, shade, shade))

    def test_multiple_files_keep_order_at_each_destination(self):
        from controls import file_preview

        first = self.directory / "z-first.pdf"
        last = self.directory / "a-last.pdf"
        for path, labels in ((first, ("First 1", "First 2")), (last, ("Last",))):
            with fitz.open() as document:
                for label in labels:
                    document.new_page().insert_text((72, 72), label)
                document.save(path)
        image_path = self.directory / "middle.tiff"
        with Image.new("RGB", (80, 90), "red") as one, Image.new("RGB", (100, 120), "blue") as two:
            one.save(image_path, save_all=True, append_images=[two])

        owner = SimpleNamespace(current_preview_path=self.target, busy_cursor=nullcontext)
        for insert_at in (0, 1, 2):
            with self.subTest(insert_at=insert_at):
                pdf_utils.discard_pdf_changes(self.target)
                with mock.patch.object(file_preview, "_get_preview_owner_from_event", return_value=owner), \
                     mock.patch.object(file_preview, "_show_import_pdf_dialog", return_value={
                         "source_paths": [str(first), str(image_path), str(last)],
                         "insert_at_index": insert_at,
                     }), \
                     mock.patch.object(file_preview, "show_pdf_feed"), \
                     mock.patch.object(file_preview, "update_pdf_save_button_state"), \
                     mock.patch.object(file_preview.wx, "MessageBox") as error:
                    file_preview.on_preview_import_from_file(SimpleNamespace())
                error.assert_not_called()
                with pdf_utils._open_pdf_document(self.target) as document:
                    expected = ["Before", "After"]
                    expected[insert_at:insert_at] = ["First 1", "First 2", "", "", "Last"]
                    self.assertEqual([page.get_text().strip() for page in document], expected)
                    self.assertEqual(document[insert_at + 2].get_images()[0][2:4], (80, 90))
                    self.assertEqual(document[insert_at + 3].get_images()[0][2:4], (100, 120))


if __name__ == "__main__":
    unittest.main()
