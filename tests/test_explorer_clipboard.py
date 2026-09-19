"""Clipboard regression tests, runnable without Windows or wxPython."""
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock


def load_module():
    spec = importlib.util.spec_from_file_location(
        'clipboard_under_test', Path(__file__).resolve().parents[1] / 'file_operations/copy_and_paste.py')
    module = importlib.util.module_from_spec(spec)
    constants = types.SimpleNamespace(CLIPBOARD_MODE_COPY='copy', CLIPBOARD_MODE_CUT='cut', _OVERWRITE_DECISION=None)
    with mock.patch.dict(sys.modules, {'wx': mock.MagicMock(),
                                      'localization': types.SimpleNamespace(tr=lambda x: x),
                                      'common.consts': constants}):
        spec.loader.exec_module(module)
    return module


class ExplorerClipboardTests(unittest.TestCase):
    def setUp(self):
        self.module = load_module()
        self.owner = types.SimpleNamespace(file_clipboard_paths=['old'], file_clipboard_mode='cut')

    def test_external_copy_replaces_cached_cut(self):
        with mock.patch.object(self.module, '_read_native_clipboard', return_value=(['new'], 'copy')):
            self.assertEqual(self.module._sync_clipboard(self.owner), (['new'], 'copy'))

    def test_non_file_clipboard_clears_old_paths(self):
        with mock.patch.object(self.module, '_read_native_clipboard', return_value=([], None)):
            self.assertEqual(self.module._sync_clipboard(self.owner), ([], None))
            self.assertEqual(self.owner.file_clipboard_paths, [])

    def test_busy_clipboard_does_not_paste_cached_files(self):
        with mock.patch.object(self.module, '_read_native_clipboard', return_value=None):
            self.assertEqual(self.module._sync_clipboard(self.owner), ([], None))

    def test_internal_cut_preserved_until_clipboard_replaced(self):
        self.owner._file_clipboard_written_paths = ['old']
        self.owner._file_clipboard_written_mode = 'cut'
        self.owner._file_clipboard_sequence = 10
        with mock.patch.object(self.module, '_read_native_clipboard', return_value=(['old'], 'copy')), \
             mock.patch.object(self.module, '_clipboard_sequence_number', return_value=10):
            self.assertEqual(self.module._sync_clipboard(self.owner)[1], 'cut')
        with mock.patch.object(self.module, '_read_native_clipboard', return_value=(['old'], 'copy')), \
             mock.patch.object(self.module, '_clipboard_sequence_number', return_value=11):
            self.assertEqual(self.module._sync_clipboard(self.owner)[1], 'copy')

    def test_explorer_copy_pastes_files_and_folders_without_moving_source(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            source = root / 'source'; source.mkdir()
            file = source / 'файл.txt'; file.write_text('data')
            folder = source / 'folder'; folder.mkdir()
            (folder / 'nested.txt').write_text('nested')
            target = root / 'target'; target.mkdir()
            with mock.patch.object(self.module, '_read_native_clipboard', return_value=([str(file), str(folder)], 'copy')):
                self.module.paste_into_path(self.owner, str(target), refresh_callback=mock.Mock(), update_toolbar_callback=mock.Mock())
            self.assertEqual((target / file.name).read_text(), 'data')
            self.assertEqual((target / 'folder/nested.txt').read_text(), 'nested')
            self.assertTrue(file.exists())
            self.assertTrue(folder.exists())

    def test_windows_hdrop_and_drop_effect(self):
        native = mock.Mock()
        native.IsClipboardFormatAvailable.return_value = True
        native.RegisterClipboardFormat.return_value = 123
        native.GetClipboardData.side_effect = lambda fmt: ('C:/file.txt',) if fmt == 15 else b'\x02\x00\x00\x00'
        with mock.patch.dict(sys.modules, {'win32clipboard': native}), mock.patch.object(self.module.os, 'name', 'nt'):
            paths, mode = self.module._read_native_clipboard()
        self.assertEqual(len(paths), 1)
        self.assertEqual(mode, 'cut')
        native.CloseClipboard.assert_called_once()


if __name__ == '__main__':
    unittest.main()
