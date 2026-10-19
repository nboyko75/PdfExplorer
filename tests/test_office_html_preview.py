"""Word HTML export must preserve the original document view."""
from contextlib import contextmanager
from itertools import product
import hashlib
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from file_operations import office_html_preview, office_session, word_merge


class WordHtmlPreviewTests(unittest.TestCase):
    def test_restores_view_before_close_on_success_and_export_failure(self):
        for original_view, fails in product((1, 3, 6), (False, True)):
            with self.subTest(original_view=original_view, export_fails=fails):
                client, com = mock.MagicMock(), mock.MagicMock()
                app = client.DispatchEx.return_value
                document = app.Documents.Open.return_value
                view = SimpleNamespace(Type=original_view)
                document.ActiveWindow.View = view

                def save_html(**kwargs):
                    view.Type = 6  # Word switches to wdWebView during SaveAs2.
                    if fails:
                        raise RuntimeError("export failed")

                document.SaveAs2.side_effect = save_html
                views_at_close = []
                document.Close.side_effect = lambda *args: views_at_close.append(view.Type)
                with mock.patch.object(office_html_preview, 'win32_client', client), \
                        mock.patch.object(office_html_preview, 'pythoncom', com):
                    if fails:
                        with self.assertRaisesRegex(RuntimeError, 'export failed'):
                            office_html_preview._export_word_to_html('source.docx', 'preview.html')
                    else:
                        office_html_preview._export_word_to_html('source.docx', 'preview.html')

                self.assertEqual(view.Type, original_view)
                self.assertEqual(views_at_close, [original_view])
                document.SaveAs2.assert_called_once_with(
                    FileName=os.path.abspath('preview.html'), FileFormat=10,
                    AddToRecentFiles=False, Encoding=65001,
                )
                self.assertTrue(app.Documents.Open.call_args.kwargs['ReadOnly'])
                client.GetActiveObject.assert_not_called()
                document.Save.assert_not_called()
                document.Close.assert_called_once_with(False)
                app.Quit.assert_called_once_with(0)
                com.CoUninitialize.assert_called_once_with()

    def test_view_restore_failure_does_not_mask_export_error_or_skip_cleanup(self):
        client, com = mock.MagicMock(), mock.MagicMock()
        app = client.DispatchEx.return_value
        document = app.Documents.Open.return_value
        document.SaveAs2.side_effect = RuntimeError('export failed')
        type(document).ActiveWindow = mock.PropertyMock(side_effect=[
            SimpleNamespace(View=SimpleNamespace(Type=1)), RuntimeError('no window'),
        ])
        with mock.patch.object(office_html_preview, 'win32_client', client), \
                mock.patch.object(office_html_preview, 'pythoncom', com), \
                self.assertLogs(office_session.__name__, level='WARNING'), \
                self.assertRaisesRegex(RuntimeError, 'export failed'):
            office_html_preview._export_word_to_html('source.docx', 'preview.html')
        document.Close.assert_called_once_with(False)
        app.Quit.assert_called_once_with(0)
        com.CoUninitialize.assert_called_once_with()


    def test_merge_preview_restores_view_before_close_on_success_and_failure(self):
        for original_view, fails in product((1, 3, 6), (False, True)):
            with self.subTest(original_view=original_view, export_fails=fails), \
                    tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'source.docx'
                source.write_bytes(b'original document')
                base = word_merge.Document(str(source), word_merge.fingerprint(source), '')
                document = mock.MagicMock()
                view = SimpleNamespace(Type=original_view)
                document.ActiveWindow.View = view
                events = []

                def save_html(**kwargs):
                    view.Type = 6
                    if fails:
                        raise RuntimeError('export failed')
                    Path(kwargs['FileName']).write_text('<html>preview</html>')

                document.SaveAs2.side_effect = save_html
                document.Close.side_effect = lambda *args: events.append(('close', view.Type))

                @contextmanager
                def app():
                    try:
                        yield mock.Mock()
                    finally:
                        events.append(('quit', view.Type))

                with mock.patch.object(word_merge, 'word_app', app), \
                        mock.patch.object(word_merge, 'open_document', return_value=document):
                    if fails:
                        with self.assertRaisesRegex(RuntimeError, 'export failed'):
                            word_merge.render_preview(base, str(Path(folder) / 'preview'))
                    else:
                        output = word_merge.render_preview(base, str(Path(folder) / 'preview'))
                        self.assertEqual(Path(output).read_text(), '<html>preview</html>')

                self.assertEqual(events, [('close', original_view), ('quit', original_view)])
                self.assertEqual(source.read_bytes(), b'original document')
                document.Save.assert_not_called()
                document.Close.assert_called_once_with(False)


class ExcelHtmlPreviewTests(unittest.TestCase):
    def test_repairs_hidden_columns_in_all_sheets_without_reencoding(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'document.files'
            resources.mkdir()
            frames = root / 'document.html'
            frames.write_bytes(b'<frameset><frame src="document.files/sheet001.htm"></frameset>')
            original_frames = frames.read_bytes()
            original = (b"<table><col width=80><col span=2 width=0\r\n"
                        b" style='display:none;mso-width-source:userset'>"
                        b'<COL STYLE="width:0; DISPLAY : NONE !important;">'
                        b"<tr style='display:none'><td colspan=3>\xcf\xf0\xe8\xe2\xe5\xf2</td></tr></table>")
            sheets = [resources / 'sheet001.htm', resources / 'sheet002.HTML']
            for path in sheets:
                path.write_bytes(original)
            asset = resources / 'image.png'
            asset.write_bytes(original)

            office_html_preview._fix_excel_hidden_columns(folder)

            expected = original.replace(b'display:none;mso', b'visibility:collapse;mso').replace(
                b'DISPLAY : NONE !important', b'visibility:collapse !important')
            for path in sheets:
                self.assertEqual(path.read_bytes(), expected)
            self.assertEqual(frames.read_bytes(), original_frames)
            self.assertEqual(asset.read_bytes(), original)
            office_html_preview._fix_excel_hidden_columns(folder)
            self.assertEqual(sheets[0].read_bytes(), expected)

    def test_export_repairs_html_and_closes_source_without_saving(self):
        with tempfile.TemporaryDirectory() as folder:
            html = Path(folder) / 'document.html'
            client, com = mock.MagicMock(), mock.MagicMock()
            app = client.DispatchEx.return_value
            document = app.Workbooks.Open.return_value
            document.SaveAs.side_effect = lambda **kwargs: Path(kwargs['Filename']).write_bytes(
                b"<table><col style='display:none'><tr><td>hidden</td></tr></table>")
            with mock.patch.object(office_html_preview, 'win32_client', client), \
                    mock.patch.object(office_html_preview, 'pythoncom', com):
                office_html_preview._export_excel_to_html('source.xlsx', str(html))
            self.assertIn(b"<col style='visibility:collapse'>", html.read_bytes())
            self.assertTrue(app.Workbooks.Open.call_args.kwargs['ReadOnly'])
            document.Save.assert_not_called()
            document.Close.assert_called_once_with(False)
            app.Quit.assert_called_once_with()
            com.CoUninitialize.assert_called_once_with()

    def test_old_excel_cache_is_rebuilt_and_repaired_cache_is_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.xlsx'
            source.write_bytes(b'workbook')
            stat = source.stat()
            identity = '|'.join((os.path.normcase(os.path.abspath(source)),
                                 str(stat.st_size), str(stat.st_mtime_ns)))
            old_cache = Path(folder) / hashlib.sha256(identity.encode()).hexdigest()
            old_cache.mkdir()
            (old_cache / 'document.html').write_text('old preview')
            with mock.patch.object(office_html_preview, '_CACHE_ROOT', folder), \
                    mock.patch.object(office_html_preview, '_require_office_com'), \
                    mock.patch.object(office_html_preview, '_export_excel_to_html') as export:
                export.side_effect = lambda source, html: Path(html).write_text('new preview')
                result = office_html_preview.render_to_html(str(source))
                self.assertNotEqual(Path(result).parent, old_cache)
                self.assertEqual(Path(result).read_text(), 'new preview')
                self.assertEqual(office_html_preview.render_to_html(str(source)), result)
                export.assert_called_once()


if __name__ == '__main__':
    unittest.main()
