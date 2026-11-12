"""Exercise inline search with native Windows text positions and formatting."""
import importlib
import os
import tempfile
import types
import unittest
from unittest import mock

import wx

from controls.text_preview_search import TextPreviewSearch
from localization import tr


class TextPreviewSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        self.panel = wx.Panel(self.frame)
        self.text = wx.TextCtrl(self.panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2)
        self.search = TextPreviewSearch(self.panel, self.text)
        self.search.set_active(True)

    def background_at(self, position):
        style = wx.TextAttr()
        selection = self.text.GetSelection()
        # At the caret RichEdit reports insertion formatting; select the
        # character to inspect its actual highlight instead.
        self.text.SetSelection(position, position + 1)
        try:
            self.assertTrue(self.text.GetStyle(position, style))
        finally:
            self.text.SetSelection(*selection)
        return style.GetBackgroundColour()

    def test_highlights_all_literal_case_insensitive_matches_and_wraps(self):
        self.text.SetValue("One [a.] two [A.] three ax")
        self.search.query.SetValue("[a.]")
        self.assertEqual([self.text.GetRange(*span) for span in self.search.matches], ["[a.]", "[A.]"])
        self.assertEqual(self.search.status.GetLabel(), tr("preview_find_count", current=1, total=2))
        first, second = [span[0] for span in self.search.matches]
        self.assertEqual(self.background_at(first), self.search.current_style.GetBackgroundColour())
        self.assertEqual(self.background_at(second), self.search.match_style.GetBackgroundColour())
        self.search.navigate(-1)
        self.assertEqual(self.search.current, 1)
        self.assertEqual(self.background_at(first), self.search.match_style.GetBackgroundColour())
        self.assertEqual(self.background_at(second), self.search.current_style.GetBackgroundColour())
        self.search.navigate(1)
        self.assertEqual(self.search.current, 0)
        self.assertFalse(self.text.IsEditable())
        self.assertEqual(self.text.GetValue(), "One [a.] two [A.] three ax")

    def test_unicode_offsets_after_newlines_and_surrogate_pairs(self):
        self.text.SetValue("😀\r\nЗбіг\nİ another 😀 збіг\nЗБІГ")
        self.search.query.SetValue("збіг")
        self.assertEqual([self.text.GetRange(*span) for span in self.search.matches], ["Збіг", "збіг", "ЗБІГ"])
        for start, end in self.search.matches:
            self.assertIn(self.background_at(start), (self.search.match_style.GetBackgroundColour(),
                                                     self.search.current_style.GetBackgroundColour()))
        self.search.query.SetValue("😀")
        self.assertEqual([self.text.GetRange(*span) for span in self.search.matches], ["😀", "😀"])

    def test_edit_clear_and_no_results_remove_old_highlights(self):
        self.text.SetValue("alpha beta alpha")
        self.search.query.SetValue("alpha")
        self.search.query.SetValue("beta")
        self.assertEqual(self.background_at(0), self.search.normal_style.GetBackgroundColour())
        self.search.query.SetValue("missing")
        self.assertEqual(self.search.status.GetLabel(), tr("preview_find_none"))
        self.assertFalse(self.search.next.IsEnabled())
        self.assertFalse(self.search.previous.IsEnabled())
        self.assertEqual(self.background_at(6), self.search.normal_style.GetBackgroundColour())
        self.search.navigate(1)
        self.search.clear()
        self.assertEqual(self.search.status.GetLabel(), "")
        self.assertEqual(self.search.matches, [])

    def test_replacing_content_and_leaving_preview_reset_search(self):
        self.text.SetValue("match")
        self.search.query.SetValue("match")
        self.text.SetValue("new file")
        self.assertEqual(self.search.query.GetValue(), "")
        self.assertEqual(self.search.matches, [])
        self.assertEqual(self.background_at(0), self.search.normal_style.GetBackgroundColour())
        self.search.query.SetValue("file")
        self.search.set_active(False)
        self.assertFalse(self.search.IsShown())
        self.assertEqual(self.search.matches, [])
        self.search.set_active(True)
        self.text.SetValue("")
        self.search.query.SetValue("file")
        self.assertEqual(self.search.status.GetLabel(), tr("preview_find_none"))

    def test_keyboard_navigation_is_confined_to_preview(self):
        self.text.SetValue("one one")
        self.search.query.SetValue("one")
        event = mock.Mock()
        event.ControlDown.return_value = False
        event.ShiftDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_F3
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.text):
            self.assertTrue(self.search.handle_key(event))
            self.assertEqual(self.search.current, 1)
            event.ShiftDown.return_value = True
            self.assertTrue(self.search.handle_key(event))
            self.assertEqual(self.search.current, 0)
            event.ControlDown.return_value = True
            event.GetKeyCode.return_value = ord("F")
            with mock.patch.object(self.search.query, "SetFocus") as focus:
                self.assertTrue(self.search.handle_key(event))
                focus.assert_called_once()
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.frame):
            self.assertFalse(self.search.handle_key(event))
        event.ControlDown.return_value = False
        event.GetKeyCode.return_value = wx.WXK_RETURN
        with mock.patch.object(wx.Window, "FindFocus", return_value=self.search.query):
            self.assertTrue(self.search.handle_key(event))
            self.assertEqual(self.search.current, 1)
            event.GetKeyCode.return_value = wx.WXK_ESCAPE
            self.assertTrue(self.search.handle_key(event))
            self.assertEqual(self.search.query.GetValue(), "")

    def test_only_successful_text_previews_enable_search(self):
        preview = importlib.import_module("controls.file_preview")
        owner = types.SimpleNamespace(preview_text=self.text, preview_text_search=self.search,
                                      filePreview=self.panel)
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(preview, "wx", wx), \
                mock.patch.object(preview, "update_preview_toolbar_visibility"):
            path = os.path.join(directory, "sample.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("hello hello")
            preview.show_text_preview(owner, path)
            self.assertTrue(self.search.active)
            self.search.query.SetValue("hello")
            self.assertEqual(len(self.search.matches), 2)
            preview.set_preview_mode(owner, "pages")
            self.assertFalse(self.search.active)
            self.assertFalse(self.search.IsShown())
            preview.show_text_preview(owner, path)
            self.assertTrue(self.search.active)
            self.assertEqual(self.search.query.GetValue(), "")
            preview.show_text_preview(owner, os.path.join(directory, "missing.txt"))
            self.assertFalse(self.search.active)
            self.assertFalse(self.search.IsShown())

    def test_preview_pane_builds_search_above_read_only_rich_text(self):
        preview = importlib.import_module("controls.file_preview")
        splitter = wx.SplitterWindow(self.frame)
        owner = types.SimpleNamespace(list=wx.Panel(splitter), icon_manager=object())

        def button(parent, *args, **kwargs):
            return wx.Button(parent)

        with mock.patch.object(preview, "wx", wx), \
                mock.patch.object(preview.image_utils, "create_bitmap_button", side_effect=button), \
                mock.patch.object(preview.image_utils, "create_bitmap_button2", side_effect=button):
            preview.build_file_preview_pane(owner, splitter)
        self.assertIs(owner.filePreview.GetSizer().GetItem(1).GetWindow(), owner.preview_text_search)
        self.assertIs(owner.filePreview.GetSizer().GetItem(2).GetWindow(), owner.preview_text)
        self.assertTrue(owner.preview_text.HasFlag(wx.TE_RICH2))
        self.assertFalse(owner.preview_text.IsEditable())
        self.assertFalse(owner.preview_text_search.IsShown())


if __name__ == "__main__":
    unittest.main()
