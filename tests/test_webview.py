"""WebView2 must never need to write beside the packaged executable."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from common.webview import create_webview
from common import webview


class WebViewStorageTests(unittest.TestCase):
    def test_frozen_loader_is_loaded_before_backend_detection_and_only_once(self):
        with tempfile.TemporaryDirectory() as directory:
            loader = Path(directory) / 'WebView2Loader.dll'
            loader.touch()
            calls = []
            html2 = mock.Mock()
            html2.WebView.IsBackendAvailable.side_effect = lambda backend: calls.append('available') or True
            html2.WebView.New.side_effect = lambda *args, **kwargs: calls.append('create')
            with mock.patch.object(webview.sys, 'platform', 'win32'), \
                 mock.patch.object(webview.sys, 'frozen', True, create=True), \
                 mock.patch.object(webview.sys, '_MEIPASS', directory, create=True), \
                 mock.patch.object(webview, '_webview_loader', None), \
                 mock.patch.object(webview.ctypes, 'WinDLL', side_effect=lambda path: calls.append(path) or object(), create=True) as load, \
                 mock.patch.dict(os.environ, {'LOCALAPPDATA': directory}, clear=True):
                create_webview(html2, object())
                create_webview(html2, object())
                load.assert_called_once_with(str(loader))
            self.assertEqual(calls, [str(loader), 'available', 'create', 'available', 'create'])

    def test_incomplete_frozen_package_fails_before_creating_blank_view(self):
        with tempfile.TemporaryDirectory() as directory:
            html2 = mock.Mock()
            with mock.patch.object(webview.sys, 'platform', 'win32'), \
                 mock.patch.object(webview.sys, 'frozen', True, create=True), \
                 mock.patch.object(webview.sys, '_MEIPASS', directory, create=True), \
                 mock.patch.object(webview, '_webview_loader', None):
                with self.assertRaisesRegex(RuntimeError, 'missing WebView2Loader.dll'):
                    create_webview(html2, object())
            html2.WebView.New.assert_not_called()

    def test_missing_runtime_fails_before_creating_blank_view(self):
        html2 = mock.Mock()
        html2.WebView.IsBackendAvailable.return_value = False
        with mock.patch.object(webview.sys, 'platform', 'win32'):
            with self.assertRaisesRegex(RuntimeError, 'WebView2 Runtime'):
                create_webview(html2, object())
        html2.WebView.New.assert_not_called()

    def test_packaged_views_use_shared_writable_profile_before_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / "DocExplorer" / "WebView2"
            browser = mock.Mock()
            parent = object()

            def native_create(actual_parent, **kwargs):
                self.assertIs(actual_parent, parent)
                self.assertEqual(kwargs, {"backend": "edge"})
                self.assertEqual(os.environ["WEBVIEW2_USER_DATA_FOLDER"], str(profile))
                self.assertTrue(profile.is_dir())
                (profile / "browser-data").write_text("writable", encoding="utf-8")
                return browser

            html2 = mock.Mock()
            html2.WebView.New.side_effect = native_create
            with mock.patch("common.webview.sys.platform", "win32"), \
                 mock.patch("common.webview.sys.executable", r"C:\Program Files\WindowsApps\DocExplorer\DocExplorer.exe"), \
                 mock.patch.dict(os.environ, {"LOCALAPPDATA": directory}, clear=True):
                self.assertIs(create_webview(html2, parent, backend="edge"), browser)
                self.assertIs(create_webview(html2, parent, backend="edge"), browser)
            self.assertEqual(html2.WebView.New.call_count, 2)

    def test_explicit_profile_override_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = str(Path(directory) / "custom")
            with mock.patch("common.webview.sys.platform", "win32"), \
                 mock.patch.dict(os.environ, {"WEBVIEW2_USER_DATA_FOLDER": profile}, clear=True):
                create_webview(mock.Mock(), object())
                self.assertEqual(os.environ["WEBVIEW2_USER_DATA_FOLDER"], profile)
                self.assertTrue(Path(profile).is_dir())

    def test_missing_localappdata_uses_user_home(self):
        with tempfile.TemporaryDirectory() as directory:
            with mock.patch("common.webview.sys.platform", "win32"), \
                 mock.patch("common.webview.os.path.expanduser", return_value=directory), \
                 mock.patch.dict(os.environ, {}, clear=True):
                create_webview(mock.Mock(), object())
                self.assertEqual(Path(os.environ["WEBVIEW2_USER_DATA_FOLDER"]),
                                 Path(directory) / "AppData" / "Local" / "DocExplorer" / "WebView2")

    def test_non_windows_keeps_native_defaults(self):
        html2 = mock.Mock()
        with mock.patch("common.webview.sys.platform", "linux"), \
             mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch("common.webview.os.makedirs") as mkdir:
            create_webview(html2, "parent", backend="webkit")
            mkdir.assert_not_called()
            self.assertNotIn("WEBVIEW2_USER_DATA_FOLDER", os.environ)
        html2.WebView.New.assert_called_once_with("parent", backend="webkit")


if __name__ == "__main__":
    unittest.main()
