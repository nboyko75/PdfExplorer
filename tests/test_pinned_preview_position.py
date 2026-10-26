"""Pinned previews return to the visible page, independently of selection."""
import importlib
import json
import os
import tempfile
import types
import unittest
from contextlib import ExitStack, nullcontext
from unittest import mock

import fitz
import wx


class PinnedPreviewPositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.preview = importlib.import_module("controls.file_preview")
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(mock.patch.object(self.preview, "wx", wx))
        self.frame = wx.Frame(None, size=(300, 300))
        self.addCleanup(self.frame.Destroy)
        panel = wx.ScrolledWindow(self.frame, size=(240, 240))
        panel.SetScrollRate(10, 10)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(sizer)
        self.frame.Layout()
        self.directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.paths = [os.path.join(self.directory, name) for name in ("first.pdf", "second.pdf")]
        for path in self.paths:
            with fitz.open() as document:
                for _ in range(5):
                    document.new_page(width=200, height=300)
                document.save(path)
        self.owner = types.SimpleNamespace(
            filePreview=self.frame, pdf_pages_panel=panel, pdf_pages_sizer=sizer,
            pdf_page_panels={}, pdf_page_gaps=[], busy_cursor=nullcontext,
            preview_tabs=[{"path": path, "pinned": True} for path in self.paths],
            preview_active_tab_index=0, current_preview_path=None,
        )
        for name in ("update_preview_toolbar_visibility", "sync_pdf_page_view_mode_controls",
                     "update_page_buttons_state", "update_pdf_save_button_state", "_render_preview_tab_bar"):
            self.stack.enter_context(mock.patch.object(self.preview, name))

    def scroll_to_page(self, index):
        panel = self.owner.pdf_page_panels[index]
        scroller = self.owner.pdf_pages_panel
        point = scroller.CalcUnscrolledPosition(panel.GetPosition())
        scroller.Scroll(point.x // 10, point.y // 10)

    def test_file_switch_keeps_tabs_and_content_frozen_until_ready(self):
        self.owner.preview_content_panel = self.frame
        render = self.preview.get_pdf_page_previews
        stages = []

        def check_tabs(owner):
            self.assertTrue(owner.preview_content_panel.IsFrozen())
            stages.append("tabs")

        def check_render(*args, **kwargs):
            self.assertTrue(self.frame.IsFrozen())
            stages.append("pages")
            return render(*args, **kwargs)

        with mock.patch.object(self.preview, "_render_preview_tab_bar", side_effect=check_tabs), \
             mock.patch.object(self.preview, "get_pdf_page_previews", side_effect=check_render):
            for path in self.paths:
                self.preview.show_file_preview(self.owner, path)
                self.assertFalse(self.frame.IsFrozen())
                self.assertFalse(self.owner.pdf_pages_panel.IsFrozen())
                self.assertEqual(self.owner.current_preview_mode, "pages")
                self.assertEqual(len(self.owner.pdf_page_panels), 5)
        self.assertIn("tabs", stages)
        self.assertEqual(stages.count("pages"), 2)

    def test_round_trip_restores_each_documents_visible_page_in_both_orientations(self):
        for vertical in (False, True):
            with self.subTest(vertical=vertical):
                self.preview.show_file_preview(self.owner, None)
                self.owner.preview_vertical_view = vertical
                self.preview.show_file_preview(self.owner, self.paths[0])
                self.scroll_to_page(2)
                first_scroll = tuple(self.owner.pdf_pages_panel.GetViewStart())
                self.assertNotEqual(first_scroll, (0, 0))
                # Selecting the destination tab updates the index before saving.
                self.preview._select_preview_tab(self.owner, 1)
                self.scroll_to_page(3)
                second_scroll = tuple(self.owner.pdf_pages_panel.GetViewStart())
                self.preview._select_preview_tab(self.owner, 0)
                axis = int(vertical)
                # Fit-to-window rendering can resize pages when scrollbars
                # appear; the same page must remain at the viewport edge.
                self.assertLessEqual(abs(self.owner.pdf_page_panels[2].GetPosition()[axis]), 10)
                self.preview._select_preview_tab(self.owner, 1)
                self.assertNotEqual(second_scroll, (0, 0))
                self.assertLessEqual(abs(self.owner.pdf_page_panels[3].GetPosition()[axis]), 10)

    def test_folder_selection_preserves_position_and_unpin_discards_it(self):
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(2)
        self.preview.show_file_preview(self.owner, self.directory)
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.assertLessEqual(abs(self.owner.pdf_page_panels[2].GetPosition().x), 10)
        self.preview._toggle_preview_tab_pin(self.owner, 0)
        self.assertTrue(all("preview_position" not in tab for tab in self.owner.preview_tabs))

    def test_return_to_page_beyond_preview_limit_loads_that_page(self):
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(3)
        self.preview.show_file_preview(self.owner, self.paths[1])
        with mock.patch.object(self.preview.pdf_utils, "_get_show_pages_limit_for_path", return_value=2):
            self.preview.show_file_preview(self.owner, self.paths[0])
        self.assertEqual(len(self.owner.pdf_page_panels), 5)
        self.assertLessEqual(abs(self.owner.pdf_page_panels[3].GetPosition().x), 10)

    def test_changed_orientation_restores_saved_page(self):
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(2)
        self.preview.show_file_preview(self.owner, self.paths[1])
        self.owner.preview_vertical_view = True
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.assertLessEqual(abs(self.owner.pdf_page_panels[2].GetPosition().y), 10)

    def test_refresh_saves_latest_position_instead_of_reusing_previous_visit(self):
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(1)
        self.preview.show_file_preview(self.owner, self.paths[1])
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(3)
        self.preview.show_pdf_feed(self.owner, self.paths[0])
        self.assertLessEqual(abs(self.owner.pdf_page_panels[3].GetPosition().x), 10)

    def test_unpinned_preview_does_not_save_position(self):
        self.owner.preview_tabs[0]["pinned"] = False
        self.preview.show_file_preview(self.owner, self.paths[0])
        self.scroll_to_page(2)
        self.preview._save_pinned_preview_position(self.owner)
        self.assertNotIn("preview_position", self.owner.preview_tabs[0])

    def test_text_preview_restores_scroll_without_moving_caret(self):
        owner = self.owner
        owner.current_preview_path = self.paths[0]
        owner.current_preview_mode = "text"
        owner.preview_text = mock.Mock()
        owner.preview_text.GetScrollPos.return_value = 42
        self.preview._save_pinned_preview_position(owner)
        owner.preview_text.GetScrollPos.return_value = 0
        self.preview._restore_pinned_preview_position(owner)
        owner.preview_text.ScrollLines.assert_called_once_with(42)
        owner.preview_text.SetInsertionPoint.assert_not_called()

    def test_html_position_restored_after_load_and_stale_callback_ignored(self):
        browser = mock.Mock()
        browser.RunScript.return_value = (True, json.dumps([0, 1350]))
        owner = self.owner
        owner.html_preview = browser
        owner.current_preview_path = self.paths[0]
        owner.current_preview_mode = "office"
        owner._html_preview_request = {"url": "file:///preview.html", "loaded": True}
        self.preview._save_pinned_preview_position(owner)
        request = {"url": "file:///preview.html"}
        owner._html_preview_request = request
        # Navigating away before loading must not overwrite the saved scroll.
        self.preview._save_pinned_preview_position(owner)
        event = mock.Mock()
        event.GetEventObject.return_value = browser
        event.GetURL.return_value = request["url"]
        with mock.patch.object(self.preview.wx, "CallAfter") as later:
            self.preview._on_html_preview_loaded(owner, event)
        browser.RunScriptAsync.assert_not_called()
        callback, *args = later.call_args.args
        callback(*args)
        self.assertIn("window.scrollTo(0, 1350)", browser.RunScriptAsync.call_args.args[0])
        browser.reset_mock()
        owner._html_preview_request = {"url": "file:///another.html"}
        callback(*args)
        browser.RunScriptAsync.assert_not_called()


if __name__ == "__main__":
    unittest.main()
