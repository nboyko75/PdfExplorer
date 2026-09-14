"""Exercise actual HTTP streaming, seeking and cleanup without a GUI runtime."""
import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def load_module():
    wx = Mock()
    wx.Panel = object
    spec = importlib.util.spec_from_file_location(
        "video_preview_under_test", Path(__file__).parents[1] / "controls/video_preview.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"wx": wx, "wx.html2": Mock(),
                                 "localization": SimpleNamespace(tr=lambda key, **kw: key)}):
        spec.loader.exec_module(module)
    return module


class VideoPreviewTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'відео #1.mp4'
        self.data = bytes(range(256)) * 1000
        self.path.write_bytes(self.data)
        self.stream = self.module.VideoStream(str(self.path), 'Unsupported <codec>')
        self.addCleanup(self.stream.close)

    def test_full_stream_matches_original_and_head_has_no_body(self):
        with urlopen(self.stream.url + 'video') as response:
            self.assertEqual(response.read(), self.data)
            self.assertEqual(response.headers['Content-Type'], 'video/mp4')
        with urlopen(Request(self.stream.url + 'video', method='HEAD')) as response:
            self.assertEqual(int(response.headers['Content-Length']), len(self.data))
            self.assertEqual(response.read(), b'')

    def test_seek_ranges_and_suffix(self):
        for header, expected in [('bytes=123-456', self.data[123:457]),
                                 ('bytes=-100', self.data[-100:]),
                                 ('bytes=250000-', self.data[250000:])]:
            with urlopen(Request(self.stream.url + 'video', headers={'Range': header})) as r:
                self.assertEqual(r.status, 206)
                self.assertEqual(r.read(), expected)
                self.assertIn('Content-Range', r.headers)

    def test_invalid_range_and_unselected_paths_rejected(self):
        for url, headers, code in [
            (self.stream.url + 'video', {'Range': 'bytes=999999-'}, 416),
            (self.stream.url + '../other.mp4', {}, 404),
        ]:
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(url, headers=headers))
            self.assertEqual(caught.exception.code, code)
            caught.exception.close()

    def test_html_controls_and_escaped_error(self):
        with urlopen(self.stream.url) as response:
            page = response.read().decode()
        self.assertIn('<video controls', page)
        self.assertIn('Unsupported &lt;codec&gt;', page)
        self.assertNotIn('autoplay', page)

    def test_close_stops_server_and_is_repeatable(self):
        self.stream.close()
        self.stream.close()
        self.assertFalse(self.stream.thread.is_alive())

    def test_panel_close_releases_browser_and_stream(self):
        panel = self.module.VideoPreviewPanel.__new__(self.module.VideoPreviewPanel)
        browser, stream = Mock(), Mock()
        panel.browser, panel.stream, panel.sizer = browser, stream, Mock()
        panel.close()
        browser.LoadURL.assert_called_once_with('about:blank')
        browser.Destroy.assert_called_once()
        stream.close.assert_called_once()
        panel.close()
        stream.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
