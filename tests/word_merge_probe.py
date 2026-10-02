"""Manual integration probe: requires Microsoft Word and pywin32 on Windows.

Run with python tests/word_merge_probe.py. Uses only synthetic temporary files
and a hidden, owned Word instance; never opens the user's documents.
Add --ui to also open the merge form and test its browser dropdowns.
"""
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations import word_merge as m


def run(folder, ui=False):
    formats = (('.docx', 12),) if ui else (('.docx', 12), ('.docm', 13), ('.doc', 0))
    for extension, file_format in formats:
        print(extension, 'creating fixtures', flush=True)
        original = folder / ('original' + extension)
        changed = folder / ('changed' + extension)
        with m.word_app() as app:
            doc = app.Documents.Add(Visible=False)
            try:
                doc.Content.Text = 'Invoice \U0001f600\rAmount: 100 USD\rDescription: red car\r'
                doc.Paragraphs(1).Range.Font.Bold = True
                doc.Fields.Add(doc.Range(0, 0), 33)  # PAGE field before the edited text
                table = doc.Tables.Add(doc.Range(doc.Content.End-1, doc.Content.End-1), 2, 2)
                table.Cell(1, 1).Range.Text = 'Item'
                table.Cell(1, 2).Range.Text = 'Color'
                table.Cell(2, 1).Range.Text = 'Car'
                table.Cell(2, 2).Range.Text = 'Red'
                table.Cell(2, 2).Shading.BackgroundPatternColor = 0xCCEEFF
                doc.Sections(1).Headers(1).Range.Text = 'Original header'
                doc.SaveAs2(FileName=str(original), FileFormat=file_format, AddToRecentFiles=False)
                area = doc.Paragraphs(2).Range
                area = doc.Range(area.Start + len('Amount: '), area.Start + len('Amount: 100'))
                assert area.Text == '100'
                area.Text = '200'
                table.Cell(2, 2).Range.Text = 'Blue'
                doc.SaveAs2(FileName=str(changed), FileFormat=file_format, AddToRecentFiles=False)
            finally:
                table = area = None
                doc.Close(False)
                doc = None
            base = m.read_document(app, str(original))
            other = m.read_document(app, str(changed))
            app = None
        original_bytes = original.read_bytes()
        print(extension, 'comparing and rendering', flush=True)
        conflicts, skipped = m.conflicts_for(base, [other])
        assert not skipped, skipped
        assert [c.values for c in conflicts] == [['100', '200'], ['Red', 'Blue']], conflicts
        preview = m.render_preview(base, str(folder / extension[1:]), conflicts, {},
                                   {'choose': 'Choose', 'empty': 'Empty', 'keep': 'Keep original'}, 'probe')
        html = Path(preview).read_text(encoding='utf-8')
        assert html.count('<select ') == 2
        assert '<table' in html
        assert original.read_bytes() == original_bytes
        if ui:
            check_ui(original)
        print(extension, 'saving and verifying', flush=True)
        m.save_merge(base, conflicts, change_color=(18, 52, 86))
        assert Path(str(original) + '.merge-backup').read_bytes() == original_bytes
        with m.word_app() as app:
            doc = m.open_document(app, str(original))
            try:
                assert 'Amount: 200 USD' in doc.Content.Text
                assert doc.Tables.Count == 1
                assert doc.Tables(1).Cell(2, 2).Range.Text == 'Blue\r\x07'
                assert doc.Tables(1).Cell(2, 2).Shading.BackgroundPatternColor == 0xCCEEFF
                assert doc.Paragraphs(1).Range.Font.Bold == -1
                assert 'Original header' in doc.Sections(1).Headers(1).Range.Text
                assert doc.Fields.Count == 1
                for text in ('200', 'Blue'):
                    marked = doc.Content.Duplicate
                    assert marked.Find.Execute(FindText=text)
                    assert marked.Font.Color == 0x563412
                    marked = None
            finally:
                doc.Close(False)
                doc = None
            app = None
        print(extension, 'preview, Unicode/field offsets, save, backup, formatting and tables passed', flush=True)


def check_ui(original):
    import wx
    from controls.merge_documents import WordMergeDialog
    from localization import load_locale
    load_locale('en')
    app = wx.App(False)
    dialog = WordMergeDialog(None, str(original))
    dialog.Show()
    def wait_for(condition):
        deadline = time.monotonic() + 60
        result = []
        def poll():
            try:
                ready = condition()
            except Exception as exc:
                result.append(exc)
                app.ExitMainLoop()
                return
            if ready or time.monotonic() >= deadline:
                result.append(ready)
                app.ExitMainLoop()
            else:
                wx.CallLater(25, poll)
        wx.CallLater(25, poll)
        app.MainLoop()
        if result and isinstance(result[0], Exception):
            raise result[0]
        if result and result[0]:
            return
        if hasattr(dialog, 'word_view'):
            print('Browser URL:', dialog.word_view.GetCurrentURL(), flush=True)
            print('Expected URL:', getattr(dialog, 'word_preview_url', ''), flush=True)
        raise AssertionError('UI timeout: ' + dialog.status.GetLabel())
    def choices():
        success, result = dialog.word_view.RunScript("document.querySelectorAll('.word-merge-choice').length")
        return int(result) if success else -1
    try:
        wait_for(lambda: dialog.base is not None and not dialog.busy)
        dialog.on_search(None)
        wait_for(lambda: not dialog.busy and bool(dialog.matches))
        dialog.on_compare(None)
        wait_for(lambda: not dialog.busy and dialog.compared)
        wait_for(lambda: choices() == 2)
        wx.CallAfter(dialog.word_view.RunScript,
                     "var s = document.querySelector('.word-merge-choice'); s.value='0'; s.dispatchEvent(new Event('change'));")
        wait_for(lambda: dialog.conflicts[0].selected == 0)
        assert dialog.save_button.IsEnabled()
        dialog.set_all_checks(False)
        wait_for(lambda: choices() == 0)
        assert not dialog.compared and not dialog.save_button.IsEnabled()
        print('Native Word dialog: search, compare, dropdown bridge and invalidation passed', flush=True)
    finally:
        dialog.dispose()
        wx.Yield()
        app.Destroy()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='docexplorer_word_probe_') as temporary:
        run(Path(temporary), ui='--ui' in sys.argv)
