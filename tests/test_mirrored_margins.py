"""Check mirrored print geometry with real PDFs and simulated printer handoff."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fitz
from PIL import Image, ImageChops, ImageDraw
import wx

from controls import print_form


def ink_bounds(page):
    pix = page.get_pixmap(colorspace=fitz.csRGB, alpha=False)
    with Image.frombytes("RGB", (pix.width, pix.height), pix.samples) as bitmap:
        with Image.new("RGB", bitmap.size, "white") as white:
            with ImageChops.difference(bitmap, white) as difference:
                return difference.getbbox()


class MirroredMarginsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.pdf"
        with fitz.open() as document:
            for number in range(1, 6):
                page = document.new_page(width=300, height=450)
                page.draw_rect((60, 80, 280, 180), color=None, fill=(1, 0, 0))
                page.insert_text((70, 110), f"Page {number}")
            document.save(self.path)
        self.original = self.path.read_bytes()
        self.addCleanup(patch.stopall)
        patch.object(print_form, "_get_print_temp_directory", return_value=self.temp.name).start()

    def prepare(self, pages=None, path=None):
        return print_form._create_mirrored_print_document(str(path or self.path), pages)

    def test_alternating_margins_keep_text_orientation_size_and_source(self):
        output = self.prepare()
        with fitz.open(output) as document:
            for index, page in enumerate(document):
                self.assertEqual(tuple(page.rect), (0, 0, 300, 450))
                self.assertEqual(ink_bounds(page), (20 if index % 2 else 60, 80,
                                                    240 if index % 2 else 280, 180))
                self.assertEqual(page.get_text().strip(), f"Page {index + 1}")
                lines = [line for block in page.get_text("dict")["blocks"]
                         if "lines" in block for line in block["lines"]]
                self.assertEqual(lines[0]["dir"], (1, 0))
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(len(list(Path(self.temp.name).glob("pdfexplorer_print_*.pdf"))), 1)

    def test_selected_order_sets_parity_before_duplex_and_copies(self):
        output = self.prepare([4, 0, 3])
        front, back = print_form._create_manual_duplex_passes(output, copies=2)
        with fitz.open(front) as document:
            self.assertEqual([p.get_text().strip() for p in document],
                             ["Page 5", "Page 4", "Page 5", "Page 4"])
            self.assertTrue(all(ink_bounds(p)[0] == 60 for p in document))
        with fitz.open(back) as document:
            self.assertEqual([p.get_text().strip() for p in document], ["Page 1", "", "Page 1", ""])
            self.assertEqual([ink_bounds(p) for p in document],
                             [(20, 80, 240, 180), None, (20, 80, 240, 180), None])

    def test_short_lines_use_common_margins_and_blank_pages_keep_parity(self):
        path = Path(self.temp.name) / "short.pdf"
        with fitz.open() as document:
            for right in (280, 200, None, 180):
                page = document.new_page(width=300, height=450)
                if right:
                    page.draw_rect((60, 80, right, 180), color=None, fill=(0, 0, 0))
            document.save(path)
        with fitz.open(self.prepare(path=path)) as document:
            self.assertEqual([ink_bounds(p) for p in document],
                             [(60, 80, 280, 180), (20, 80, 160, 180), None, (20, 80, 140, 180)])

    def test_rotated_and_cropped_pages_preserve_visible_content(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                path = Path(self.temp.name) / f"rotated_{rotation}.pdf"
                with fitz.open() as document:
                    for _ in range(2):
                        page = document.new_page(width=400, height=550)
                        page.draw_rect((110, 130, 330, 230), color=None, fill=(1, 0, 0))
                        page.set_cropbox(fitz.Rect(50, 50, 350, 500))
                        page.set_rotation(rotation)
                    document.save(path)
                with fitz.open(path) as source, fitz.open(self.prepare(path=path)) as output:
                    bounds = ink_bounds(source[0])
                    width = int(source[0].rect.width)
                    self.assertEqual(ink_bounds(output[0]), bounds)
                    self.assertEqual(ink_bounds(output[1]),
                                     (width - bounds[2], bounds[1], width - bounds[0], bounds[3]))

    def test_scanned_images_keep_resolution_and_swap_white_margins(self):
        path = Path(self.temp.name) / "scan.tiff"
        with Image.new("RGB", (600, 900), "white") as bitmap:
            ImageDraw.Draw(bitmap).rectangle((120, 160, 559, 359), fill="black")
            bitmap.save(path, save_all=True, append_images=[bitmap], dpi=(144, 144))
        with fitz.open(self.prepare(path=path)) as document:
            # Image interpolation at 72 dpi adds a one-pixel antialiased edge.
            self.assertEqual(ink_bounds(document[0]), (59, 79, 281, 181))
            self.assertEqual(ink_bounds(document[1]), (19, 79, 241, 181))
            self.assertEqual(document[1].get_images()[0][2:4], (600, 900))

    def test_annotation_and_form_value_survive(self):
        path = Path(self.temp.name) / "annotations.pdf"
        with fitz.open(self.path) as document:
            page = document[1]
            annot = page.add_freetext_annot((70, 200, 180, 240), "Note", fontsize=12)
            annot.update()
            widget = fitz.Widget()
            widget.field_name = "value"
            widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
            widget.field_value = "Entered value"
            widget.rect = fitz.Rect(70, 250, 200, 280)
            page.add_widget(widget)
            document.save(path)
        with fitz.open(self.prepare(path=path)) as document:
            self.assertIn("Note", document[1].get_text())
            self.assertIn("Entered value", document[1].get_text())

    def test_office_exports_every_page_before_selecting_and_mirroring(self):
        with patch.object(print_form.office_preview, "can_preview_office", return_value=True), \
                patch.object(print_form.office_preview, "get_office_document_page_count", return_value=5), \
                patch.object(print_form.office_preview, "convert_office_to_preview_pdf", return_value=str(self.path)) as convert:
            output = self.prepare([4, 0], path="document.docx")
            convert.assert_called_once_with("document.docx", max_pages=5)
        with fitz.open(output) as document:
            self.assertEqual([p.get_text().strip() for p in document], ["Page 5", "Page 1"])
            self.assertEqual(ink_bounds(document[1])[0], 20)

    def test_failed_output_removes_intermediate_and_incomplete_files(self):
        original_save = fitz.Document.save

        def fail_output(document, path, *args, **kwargs):
            if document[1].get_text().strip() == "Page 2" and ink_bounds(document[1])[0] == 20:
                raise OSError("Cannot save")
            return original_save(document, path, *args, **kwargs)

        with patch.object(fitz.Document, "save", fail_output), self.assertRaises(OSError):
            self.prepare()
        self.assertEqual(list(Path(self.temp.name).glob("pdfexplorer_print_*.pdf")), [])
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_form_applies_margins_only_for_two_sided_printing(self):
        app = wx.App.Get() or wx.App(False)
        for duplex in (1, 2, 3):
            with self.subTest(duplex=duplex):
                settings = {"print_form_printer": "Printer One",
                            "print_form_duplex_modes": {"Printer One": duplex},
                            "print_form_multiple_pages": "mirrored_margins",
                            "print_form_page_range": "selection", "print_form_page_numbers": "5,1,4"}

                def modal(dialog):
                    choices = [child for child in dialog.GetChildren()[0].GetChildren()
                               if isinstance(child, wx.Choice)]
                    self.assertEqual(choices[2].GetSelection(), 1)
                    self.assertEqual(choices[2].IsEnabled(), duplex != 1)
                    return wx.ID_OK

                with patch.object(print_form, "load_settings", return_value=settings), \
                        patch.object(print_form, "update_settings") as save, \
                        patch.object(print_form, "_get_printer_names", return_value=["Printer One"]), \
                        patch.object(print_form, "_save_print_form_geometry"), \
                        patch.object(print_form, "_print_manual_duplex", return_value="Printer One") as manual, \
                        patch.object(print_form, "_print_with_selected_printer", return_value="Printer One") as direct, \
                        patch.object(wx.Dialog, "ShowModal", modal), patch.object(wx, "MessageBox"):
                    self.assertTrue(print_form.show_print_form(None, str(self.path)))
                    handoff = direct if duplex == 1 else manual
                    unused = manual if duplex == 1 else direct
                    unused.assert_not_called()
                    handoff.assert_called_once()
                    if duplex == 1:
                        self.assertEqual(handoff.call_args.args[0], str(self.path))
                        self.assertEqual(handoff.call_args.kwargs["page_numbers"], [4, 0, 3])
                    else:
                        self.assertIsNone(handoff.call_args.kwargs["page_numbers"])
                        with fitz.open(handoff.call_args.args[0]) as document:
                            self.assertEqual([p.get_text().strip() for p in document], ["Page 5", "Page 1", "Page 4"])
                            self.assertEqual([ink_bounds(p)[0] for p in document], [60, 20, 60])
                    self.assertEqual(save.call_args.args[0]["print_form_multiple_pages"], "mirrored_margins")


if __name__ == "__main__":
    unittest.main()
