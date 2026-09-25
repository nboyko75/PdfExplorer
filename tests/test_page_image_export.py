import io
import tempfile
import unittest
from pathlib import Path
import fitz
from PIL import Image
from file_operations.page_image_export import FORMATS, export_images, detect_page_dpi


class PageImageExportTests(unittest.TestCase):
    def test_all_image_formats(self):
        with tempfile.TemporaryDirectory() as folder, fitz.open() as doc:
            doc.new_page(width=144, height=72)
            for extension in FORMATS:
                with self.subTest(extension=extension):
                    target = str(Path(folder, 'page' + extension))
                    self.assertEqual(export_images(doc, [0], target), [target])
                    with Image.open(target) as image:
                        self.assertEqual(image.format, FORMATS[extension])
                        self.assertEqual(image.size, (300, 150))
                        image.load()

    def test_automatic_resolution_per_page(self):
        def png(width, height):
            stream = io.BytesIO()
            with Image.new('RGB', (width, height), 'white') as image:
                image.save(stream, format='PNG')
            return stream.getvalue()
        with tempfile.TemporaryDirectory() as folder, fitz.open() as doc:
            page = doc.new_page(width=144, height=144)
            page.insert_image(page.rect, stream=png(600, 600))
            # A small high-density logo must not override the main scan.
            page.insert_image(fitz.Rect(0, 0, 12, 12), stream=png(200, 200))
            self.assertEqual(detect_page_dpi(page), 300)
            page = doc.new_page(width=144, height=144)
            page.insert_image(page.rect, stream=png(400, 400), rotate=90)
            page.set_rotation(90)
            self.assertEqual(detect_page_dpi(page), 200)
            page = doc.new_page(width=144, height=144)
            page.insert_text((20, 20), 'Text only')
            self.assertEqual(detect_page_dpi(page), 150)
            paths = export_images(doc, [0, 1, 2], str(Path(folder, 'auto.png')), dpi=None)
            for path, dpi in zip(paths, (300, 200, 150)):
                with Image.open(path) as image:
                    self.assertEqual(image.size, (dpi * 2, dpi * 2))
                    self.assertAlmostEqual(image.info['dpi'][0], dpi, delta=0.1)

    def test_selected_resolution(self):
        with tempfile.TemporaryDirectory() as folder, fitz.open() as doc:
            doc.new_page(width=72, height=72)
            for dpi in (72, 96, 150, 300, 600, 1200, 2400):
                target = str(Path(folder, 'resolution.png'))
                export_images(doc, [0], target, dpi=dpi)
                with Image.open(target) as image:
                    self.assertEqual(image.size, (dpi, dpi))
                    self.assertAlmostEqual(image.info['dpi'][0], dpi, delta=0.1)

    def test_selected_pages_and_order(self):
        with tempfile.TemporaryDirectory() as folder, fitz.open() as doc:
            for width in (72, 144, 216):
                doc.new_page(width=width, height=72)
            target = str(Path(folder, 'pages.png'))
            paths = export_images(doc, [2, 0], target)
            self.assertEqual([Path(p).name for p in paths], ['pages_3.png', 'pages_1.png'])
            for path, width in zip(paths, (450, 150)):
                with Image.open(path) as image:
                    self.assertEqual(image.width, width)
            self.assertFalse(Path(target).exists())
            with self.assertRaises(ValueError):
                export_images(doc, [5], target)


if __name__ == '__main__':
    unittest.main()
