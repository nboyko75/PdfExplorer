"""Scan completion must render the saved file before marking it as previewed."""
from contextlib import ExitStack
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import fitz
from PIL import Image

from controls import file_preview, filelist, scan_form


class ScanPreviewTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.folder = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.pdf = str(self.folder / "scan.pdf")
        self.jpg = str(self.folder / "scan.jpg")
        self.write_pdf(1)
        Image.new("RGB", (20, 30), "white").save(self.jpg)
        self.rendered = []
        # Keep the real preview dispatcher and tab bookkeeping; replace UI work.
        for name in (
            "_render_preview_tab_bar", "close_office_preview",
            "_clear_preview_content_state", "_reset_pdf_view_mode_for_new_file",
            "update_page_buttons_state", "update_pdf_save_button_state",
        ):
            self.stack.enter_context(patch.object(file_preview, name))
        self.stack.enter_context(patch.object(file_preview, "PREVIEW_HANDLERS", [
            (lambda owner, path: True, self.render),
        ]))
        self.stack.enter_context(patch.object(filelist, "_schedule_list_selection_state_update"))

    def write_pdf(self, pages):
        with fitz.open() as document:
            for _ in range(pages):
                document.new_page()
            document.save(self.pdf)

    def render(self, owner, path):
        with fitz.open(path) as document:
            self.rendered.append((path, document.page_count))
        owner.current_preview_mode = "pages"

    def owner(self, current=None):
        return SimpleNamespace(
            path_box=Mock(GetValue=Mock(return_value=str(self.folder))),
            load_folder=Mock(), current_preview_path=current,
            current_preview_mode="pages" if current else "empty",
            preview_tabs=[{"path": current, "pinned": False}] if current else [],
            preview_active_tab_index=0 if current else None,
            preview_enabled=True, filePreview=Mock(), list=None,
        )

    def test_new_scan_is_rendered_and_first_selection_keeps_it_visible(self):
        for path in (self.pdf, self.jpg):
            for previous in (None, self.jpg if path == self.pdf else self.pdf):
                with self.subTest(path=path, previous=previous):
                    self.rendered.clear()
                    owner = self.owner(previous)

                    scan_form._refresh_after_scan(owner, path)

                    self.assertEqual(self.rendered, [(path, 1)])
                    self.assertEqual(owner.current_preview_path, path)
                    owner.load_folder.assert_called_once_with(str(self.folder))
                    owner._list_item_paths = {0: path}
                    filelist.on_list_select(owner, Mock(GetIndex=Mock(return_value=0)))
                    self.assertEqual(owner.current_preview_mode, "pages")
                    self.assertEqual(self.rendered, [(path, 1)])

    def test_scan_over_existing_preview_reloads_saved_content(self):
        owner = self.owner(self.pdf)
        self.write_pdf(2)

        scan_form._refresh_after_scan(owner, self.pdf)

        self.assertEqual(self.rendered, [(self.pdf, 2)])

    def test_cancelled_preview_change_keeps_previous_path(self):
        owner = self.owner(self.jpg)
        with patch.object(file_preview, "confirm_preview_change", return_value=False) as confirm:
            scan_form._refresh_after_scan(owner, self.pdf)

        confirm.assert_called_once_with(owner, self.pdf)
        self.assertEqual(owner.current_preview_path, self.jpg)
        self.assertEqual(self.rendered, [])

    def test_missing_output_does_not_replace_preview(self):
        owner = self.owner(self.jpg)

        scan_form._refresh_after_scan(owner, str(self.folder / "missing.pdf"))

        self.assertEqual(owner.current_preview_path, self.jpg)
        self.assertEqual(self.rendered, [])


if __name__ == "__main__":
    unittest.main()
