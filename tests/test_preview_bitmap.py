"""Check transparent preview repaints using the native wx rasterizer."""
import importlib
import unittest
from unittest import mock

import wx


class PreviewBitmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.preview = importlib.import_module("controls.file_preview")
        patch = mock.patch.object(self.preview, "wx", wx)
        patch.start()
        self.addCleanup(patch.stop)
        self.frame = wx.Frame(None)
        self.addCleanup(self.frame.Destroy)
        self.control = self.preview._PreviewBitmap(self.frame, wx.ID_ANY, wx.Bitmap(3, 1))
        self.control.SetBackgroundColour(wx.Colour(240, 240, 240))
        self.surface = wx.Bitmap(3, 1, 24)
        self.dc = wx.MemoryDC(self.surface)
        self.addCleanup(self.dc.SelectObject, wx.NullBitmap)
        # Stand in for strokes left by a previously displayed image.
        self.dc.SetBackground(wx.Brush(wx.BLACK))
        self.dc.Clear()

    def paint(self):
        # Exercise production painting into a deterministic offscreen target.
        with mock.patch.object(wx, "AutoBufferedPaintDC", return_value=self.dc):
            self.control.OnPaint(None)
        return bytes(self.surface.ConvertToImage().GetData())

    def test_transparent_pixels_clear_previous_strokes(self):
        image = wx.Image(3, 1)
        image.SetData(bytes([0, 0, 0] * 3))
        image.SetAlpha(bytes([0, 128, 255]))
        self.control.SetBitmap(wx.Bitmap(image))

        pixels = self.paint()

        self.assertEqual(pixels[:3], bytes([240] * 3))
        self.assertTrue(all(119 <= value <= 120 for value in pixels[3:6]))
        self.assertEqual(pixels[6:], bytes([0] * 3))
        # Repainting must not darken the antialiased edge.
        self.assertEqual(self.paint(), pixels)
        self.assertEqual(self.control.GetBackgroundStyle(), wx.BG_STYLE_PAINT)

    def test_smaller_masked_bitmap_clears_previous_image_and_uncovered_area(self):
        image = wx.Image(2, 1)
        image.SetData(bytes([255, 0, 255, 20, 40, 60]))
        image.SetMaskColour(255, 0, 255)
        self.control.SetBitmap(wx.Bitmap(image))

        self.assertEqual(self.paint(), bytes([240, 240, 240, 20, 40, 60, 240, 240, 240]))

    def test_empty_bitmap_clears_previous_image(self):
        self.control.SetBitmap(wx.NullBitmap)

        self.assertEqual(self.paint(), bytes([240] * 9))


if __name__ == "__main__":
    unittest.main()
