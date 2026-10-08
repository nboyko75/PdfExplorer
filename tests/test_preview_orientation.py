"""Exercise page orientation with native wx sizers and scroll extents."""
import importlib
import os
import tempfile
import types
import unittest
from contextlib import nullcontext
from unittest import mock

import fitz
import wx


class PreviewOrientationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.preview = importlib.import_module("controls.file_preview")
        self.wx_patch = mock.patch.object(self.preview, "wx", wx)
        self.wx_patch.start()
        self.addCleanup(self.wx_patch.stop)
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        panel = wx.ScrolledWindow(self.frame, size=(240, 240))
        panel.SetScrollRate(10, 10)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel.SetSizer(sizer)
        pages, gaps = {}, []
        for index in range(3):
            gap = wx.Panel(panel)
            gaps.append(gap)
            sizer.Add(gap)
            page = wx.Panel(panel)
            page.SetMinSize((100 + index * 10, 150 + index * 10))
            pages[index] = page
            sizer.Add(page, 0, wx.ALL, 3)
        self.owner = types.SimpleNamespace(
            pdf_pages_panel=panel, pdf_pages_sizer=sizer,
            pdf_page_panels=pages, pdf_page_gaps=gaps,
            preview_horizontal_view_btn=self.preview._create_preview_orientation_button(self.frame),
            preview_vertical_view_btn=self.preview._create_preview_orientation_button(self.frame, True),
            selected_pdf_page_indices={1, 2}, selected_pdf_page_panel=pages[1],
            pdf_preview_zoom=1.25,
        )

    def test_default_is_horizontal_and_icons_are_distinct(self):
        self.preview._layout_pdf_pages(self.owner)
        first, second = (self.owner.pdf_page_panels[i] for i in (0, 1))
        self.assertEqual(first.GetPosition().y, second.GetPosition().y)
        self.assertGreater(second.GetPosition().x, first.GetPosition().x)
        self.assertGreater(self.owner.pdf_pages_panel.GetVirtualSize().x, 240)
        self.assertTrue(self.owner.preview_horizontal_view_btn.GetValue())
        self.assertFalse(self.owner.preview_vertical_view_btn.GetValue())
        self.assertNotEqual(
            self.owner.preview_horizontal_view_btn.GetBitmap().ConvertToImage().GetData(),
            self.owner.preview_vertical_view_btn.GetBitmap().ConvertToImage().GetData(),
        )

    def test_switch_reflows_pages_and_gaps_without_losing_selection_or_zoom(self):
        for vertical in (True, True, False):
            with self.subTest(vertical=vertical):
                self.preview._set_preview_orientation(self.owner, vertical)
                first, second = (self.owner.pdf_page_panels[i] for i in (0, 1))
                if vertical:
                    self.assertEqual(first.GetPosition().x, second.GetPosition().x)
                    self.assertGreater(second.GetPosition().y, first.GetPosition().y)
                    self.assertGreater(self.owner.pdf_pages_panel.GetVirtualSize().y, 240)
                    self.assertEqual(tuple(self.owner.pdf_page_gaps[0].GetMinSize()), (120, 22))
                else:
                    self.assertEqual(first.GetPosition().y, second.GetPosition().y)
                    self.assertGreater(second.GetPosition().x, first.GetPosition().x)
                    self.assertEqual(tuple(self.owner.pdf_page_gaps[0].GetMinSize()), (22, 170))
                self.assertEqual(self.owner.preview_horizontal_view_btn.GetValue(), not vertical)
                self.assertEqual(self.owner.preview_vertical_view_btn.GetValue(), vertical)
                self.assertEqual(self.owner.selected_pdf_page_indices, {1, 2})
                self.assertIs(self.owner.selected_pdf_page_panel, self.owner.pdf_page_panels[1])
                self.assertEqual(self.owner.pdf_preview_zoom, 1.25)

    def test_relayout_keeps_vertical_orientation_after_page_size_changes(self):
        self.preview._set_preview_orientation(self.owner, True)
        self.owner.pdf_page_panels[0].SetMinSize((200, 300))
        self.preview._layout_pdf_pages(self.owner)
        self.assertEqual(self.owner.pdf_pages_sizer.GetOrientation(), wx.VERTICAL)
        self.assertEqual(tuple(self.owner.pdf_page_gaps[0].GetMinSize()), (200, 22))

    def test_pdf_rendering_and_reload_use_selected_orientation(self):
        self.owner.filePreview = self.frame
        self.owner.busy_cursor = nullcontext
        self.owner.current_preview_path = None
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "pages.pdf")
            with fitz.open() as document:
                for _ in range(3):
                    document.new_page(width=200, height=300)
                document.save(path)
            with mock.patch.object(self.preview, "update_preview_toolbar_visibility"), \
                 mock.patch.object(self.preview, "sync_pdf_page_view_mode_controls"), \
                 mock.patch.object(self.preview, "update_page_buttons_state"):
                for vertical in (False, True):
                    self.preview._set_preview_orientation(self.owner, vertical)
                    self.preview.show_pdf_feed(self.owner, path, force_all_pages=True)
                    self.assertEqual(len(self.owner.pdf_page_panels), 3)
                    self.assertEqual(self.owner.current_preview_mode, "pages")
                    first, second = (self.owner.pdf_page_panels[i] for i in (0, 1))
                    if vertical:
                        self.assertGreater(second.GetPosition().y, first.GetPosition().y)
                        self.assertEqual(first.GetPosition().x, second.GetPosition().x)
                    else:
                        self.assertGreater(second.GetPosition().x, first.GetPosition().x)
                        self.assertEqual(first.GetPosition().y, second.GetPosition().y)
                    self.assertTrue(self.owner.preview_horizontal_view_btn.IsEnabled())
                    self.assertTrue(self.owner.preview_vertical_view_btn.IsEnabled())


if __name__ == "__main__":
    unittest.main()
