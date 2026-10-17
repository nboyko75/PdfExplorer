"""Live Word checks on synthetic files; no VBA access or macros required.

Run: python tests/document_generator_probe.py
"""
from pathlib import Path
import sys
import tempfile
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations.document_generator import DocumentGenerator, STATE_VARIABLE


def run(folder):
    import pythoncom
    import win32com.client
    import win32con
    import win32gui
    pythoncom.CoInitialize()
    app = session = output = document = None
    try:
        for extension, file_format in (('.docx', 12), ('.doc', 0), ('.docm', 13)):
            app = win32com.client.DispatchEx('Word.Application')
            app.Visible = False
            app.DisplayAlerts = 0
            app.AutomationSecurity = 3
            source = folder / ('source' + extension)
            document = app.Documents.Add(Visible=False)
            document.Content.Text = 'AlphaBeta again'
            document.Range(0, 5).Font.Bold = True
            document.Sections(1).Headers(1).Range.Text = 'Preserved header'
            document.SaveAs2(FileName=str(source), FileFormat=file_format, AddToRecentFiles=False)
            document.Close(False)
            document = None
            app.Quit(0)
            app = None
            original = source.read_bytes()
            session = DocumentGenerator(str(source))
            assert session.open() == []
            assert session.document.FullName == str(source)
            assert session.document.SaveFormat == file_format
            assert source.read_bytes() == original, 'Opening changed the source'
            hwnd = session.document.Windows(1).Hwnd
            # Exercise restoration of both normal and maximized placements.
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetWindowPos(hwnd, 0, 90, 80, 850, 650, win32con.SWP_NOZORDER)
            if extension == '.doc':
                win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            placement = win32gui.GetWindowPlacement(hwnd)
            import win32api
            monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
            left, top, right, bottom = win32api.GetMonitorInfo(monitor)['Work']
            middle = left + (right - left) // 2
            session.arrange_window((middle, top, right - middle, bottom - top))
            assert win32gui.GetWindowRect(hwnd) == (middle, top, right, bottom)
            # Windows can deny OS foreground focus to a console/background test.
            # The app also requests it on its foreground GUI thread.
            assert session.app.ActiveWindow.Hwnd == hwnd
            session.restore_window()
            restored = win32gui.GetWindowPlacement(hwnd)
            assert restored[1:] == placement[1:], (placement, restored)
            session.arrange_window((middle, top, right - middle, bottom - top))
            session.document.Range(0, 5).Select()
            session.add_selection()
            session.document.Range(5, 9).Select()
            session.add_selection()
            session.document.Range(10, 15).Select()
            session.add_selection()
            session.delete_row(2)
            assert session.document.Content.Text == 'AlphaBeta again\r'
            session.update_rows([{'name': 'First', 'value': 'Replacement'},
                                 {'name': 'Second', 'value': ''}])
            session.save_document()
            assert session.document.Saved
            assert session.document.Content.Text == 'AlphaBeta again\r'
            assert session._load_rows() == session.rows
            result = folder / ('result' + extension)
            session.export_document(str(result))
            assert session.document.Content.Text == 'AlphaBeta again\r'
            output = session.app.Documents.Open(FileName=str(result), ReadOnly=True, Visible=False)
            assert output.Content.Text == 'Replacement again\r', repr(output.Content.Text)
            assert output.SaveFormat == file_format
            assert output.Bookmarks('First').Range.Text == 'Replacement'
            assert output.Bookmarks('Second').Range.Text == ''
            assert output.Bookmarks('First').Range.Font.Bold == -1
            assert output.Sections(1).Headers(1).Range.Text == 'Preserved header\r'
            assert all(output.Variables.Item(i).Name != STATE_VARIABLE
                       for i in range(1, output.Variables.Count + 1))
            output.Close(False)
            output = None
            # An unrelated document in the owned instance must stay open.
            other = session.app.Documents.Add(Visible=True)
            session.close_document()
            assert other.Application.Documents.Count == 1
            other.Application.Quit(0)
            other = None
            session = DocumentGenerator(str(source))
            assert session.open() == [{'name': 'First', 'value': 'Replacement'},
                                      {'name': 'Second', 'value': ''}]
            session.update_rows([{'name': 'First', 'value': 'Україна\n日本'},
                                 {'name': 'Second', 'value': 'Result'}])
            second = folder / ('second' + extension)
            session.export_document(str(second))
            output = session.app.Documents.Open(FileName=str(second), ReadOnly=True, Visible=False)
            assert output.Content.Text == 'Україна\r日本Result again\r', repr(output.Content.Text)
            output.Close(False)
            output = None
            if extension == '.docx':
                for path in (source, result, second):
                    with zipfile.ZipFile(path) as package:
                        assert 'word/vbaProject.bin' not in package.namelist()
            # A second bookmark shares the first field's value, persists as a
            # link after reopening, and receives the same text on export.
            session.document.Range(10, 15).Select()
            session.add_selection(0)
            linked = session.snapshot()
            linked[1]['name'] = 'Linked'
            session.update_rows(linked)
            assert linked[0]['group'] == linked[1]['group']
            assert linked[0]['value'] == linked[1]['value']
            session.save_document()
            session.close_document()
            session = DocumentGenerator(str(source))
            assert session.open() == linked
            shared_result = folder / ('shared-result' + extension)
            session.export_document(str(shared_result))
            output = session.app.Documents.Open(FileName=str(shared_result), ReadOnly=True, Visible=False)
            assert output.Bookmarks('First').Range.Text == output.Bookmarks('Linked').Range.Text
            assert output.Bookmarks('Second').Range.Text == 'Result'
            output.Close(False)
            output = None
            session.delete_row(0)
            remaining = session.snapshot()
            remaining[0]['name'] = 'RemainingLink'
            remaining[0]['value'] = 'After removal'
            session.update_rows(remaining)
            session.export_document(str(shared_result))
            output = session.app.Documents.Open(FileName=str(shared_result), ReadOnly=True, Visible=False)
            assert output.Bookmarks('RemainingLink').Range.Text == 'After removal'
            assert output.Content.Text.startswith('AlphaResult ')
            output.Close(False)
            output = None
            session.close_document()
            session = None
            print(f'PASS {extension}: original format, Add/Rename/Delete, adjacent and empty fields, '
                  'shared values, formatting, persistence, Unicode, tiling/restoration and document close', flush=True)
    finally:
        if session is not None and session.app is not None:
            session.app.Quit(0)
            session.detach()
        if app is not None:
            app.Quit(0)
        output = document = app = session = None
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='document-generator-probe-') as directory:
        run(Path(directory))
