"""Scanner import must match Scan output and retain cancellation/cleanup behavior."""
from contextlib import ExitStack
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import Image
import pythoncom
import win32com.client
import wx

from controls import scan_form
from file_operations import pdf_utils, scanner_import


class ScannerImportTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.scanner = Mock()
        self.stack.enter_context(patch.object(win32com.client, "Dispatch", return_value=self.scanner))
        self.stack.enter_context(patch.object(pythoncom, "CoInitialize"))
        self.uninitialize = self.stack.enter_context(patch.object(pythoncom, "CoUninitialize"))
        self.saved_images = []

    def scanner_image(self, source):
        def save(path):
            shutil.copyfile(source, path)
            self.saved_images.append(Path(path))
        return SimpleNamespace(SaveFile=save)

    def assert_cleaned(self):
        self.assertTrue(self.saved_images)
        self.assertTrue(all(not path.exists() for path in self.saved_images))
        self.uninitialize.assert_called()

    def test_import_matches_scan_dimensions_and_embedded_image(self):
        for mode, dpi, orientation in (("RGB", 144, 1), ("L", 300, 1), ("RGB", 600, 6)):
            with self.subTest(mode=mode, dpi=dpi, orientation=orientation):
                source = self.folder / "source.jpg"
                with Image.new(mode, (240, 360), 128) as image:
                    exif = image.getexif()
                    exif[274] = orientation
                    image.save(source, dpi=(dpi, dpi), exif=exif)
                self.scanner.ShowAcquireImage.return_value = self.scanner_image(source)
                paths = scan_form._acquire_scanned_image_files({"multiple_pages": False})
                for path in paths:
                    self.addCleanup(Path(path).unlink, missing_ok=True)
                scan_call = self.scanner.ShowAcquireImage.call_args
                expected = scan_form._save_scanned_pages(paths, str(self.folder / "scan.pdf"), 0)
                with scanner_import.scanned_pdf(None) as imported:
                    self.assertEqual(self.scanner.ShowAcquireImage.call_args, scan_call)
                    with fitz.open(expected) as standalone, fitz.open(imported) as preview:
                        self.assertEqual(len(preview), 1)
                        self.assertEqual(preview[0].rect, standalone[0].rect)
                        expected_size = (360, 240) if orientation == 6 else (240, 360)
                        self.assertEqual(tuple(preview[0].rect)[2:], expected_size)
                        scan_image = standalone.extract_image(standalone[0].get_images()[0][0])
                        imported_image = preview.extract_image(preview[0].get_images()[0][0])
                        self.assertEqual(imported_image["image"], scan_image["image"])
                    output_path = Path(imported)
                self.assertFalse(output_path.exists())

    def test_multiple_pages_keep_order_and_size_when_inserted(self):
        images = []
        sizes = [(240, 360), (480, 300)]
        for index, size in enumerate(sizes):
            path = self.folder / f"source_{index}.png"
            with Image.new("RGB", size, "white") as image:
                image.save(path, dpi=(144, 144))
            images.append(self.scanner_image(path))
        self.scanner.ShowAcquireImage.side_effect = images
        prompt = Mock()
        prompt.ShowModal.side_effect = [wx.ID_YES, wx.ID_NO]
        target = str(self.folder / "target.pdf")
        self.addCleanup(pdf_utils.discard_pdf_changes, target)
        with fitz.open() as document:
            document.new_page()
            document.save(target)
        with patch.object(wx, "MessageDialog", return_value=prompt):
            with scanner_import.scanned_pdf(None, multiple_pages=True) as imported:
                pdf_utils.import_pdf_pages(target, imported, 1)
        with pdf_utils._open_pdf_document(target) as document:
            self.assertEqual(len(document), 3)
            for index, size in enumerate(sizes, 1):
                self.assertEqual(tuple(document[index].rect)[2:], size)
        calls = self.scanner.ShowAcquireImage.call_args_list
        self.assertEqual([call.args[4] for call in calls], [True, False])
        self.assert_cleaned()

    def test_cancel_after_first_page_aborts_import_and_cleans_files(self):
        source = self.folder / "source.png"
        with Image.new("RGB", (24, 36), "white") as image:
            image.save(source)
        self.scanner.ShowAcquireImage.side_effect = [self.scanner_image(source), None]
        prompt = Mock()
        prompt.ShowModal.return_value = wx.ID_YES
        with patch.object(wx, "MessageDialog", return_value=prompt):
            with scanner_import.scanned_pdf(None, multiple_pages=True) as imported:
                self.assertIsNone(imported)
        self.assert_cleaned()

    def test_conversion_failure_cleans_files(self):
        source = self.folder / "invalid.img"
        source.write_bytes(b"invalid scanner image")
        self.scanner.ShowAcquireImage.return_value = self.scanner_image(source)
        with self.assertRaises(OSError):
            with scanner_import.scanned_pdf(None):
                self.fail("Invalid scan must not be imported")
        self.assert_cleaned()


if __name__ == "__main__":
    unittest.main()
