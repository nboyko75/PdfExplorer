"""Word HTML export must preserve the original document view."""
from itertools import product
import os
from types import SimpleNamespace
import unittest
from unittest import mock

from file_operations import office_html_preview


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
                self.assertLogs(office_html_preview.__name__, level='WARNING'), \
                self.assertRaisesRegex(RuntimeError, 'export failed'):
            office_html_preview._export_word_to_html('source.docx', 'preview.html')
        document.Close.assert_called_once_with(False)
        app.Quit.assert_called_once_with(0)
        com.CoUninitialize.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
