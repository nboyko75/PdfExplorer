"""Real Windows file locks and the generator's foreground Retry/Cancel dialog."""
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from file_operations.document_generator import check_document_available, GeneratorError


def check_access():
    import win32con
    import win32file

    with tempfile.TemporaryDirectory(prefix='generator-access-') as folder:
        path = Path(folder) / 'available.docx'
        path.write_bytes(b'unchanged content')
        check_document_available(str(path))
        handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | win32con.GENERIC_WRITE,
                                      win32con.FILE_SHARE_READ, None, win32con.OPEN_EXISTING, 0, None)
        try:
            for attempt in range(2):
                try:
                    check_document_available(str(path))
                except GeneratorError:
                    pass
                else:
                    raise AssertionError('Locked file was accepted')
        finally:
            handle.Close()
        check_document_available(str(path))
        win32file.SetFileAttributes(str(path), win32con.FILE_ATTRIBUTE_READONLY)
        try:
            try:
                check_document_available(str(path))
            except GeneratorError:
                pass
            else:
                raise AssertionError('Read-only file was accepted')
        finally:
            win32file.SetFileAttributes(str(path), win32con.FILE_ATTRIBUTE_NORMAL)
        assert path.read_bytes() == b'unchanged content'
        path.unlink()
        try:
            check_document_available(str(path))
        except GeneratorError:
            pass
        else:
            raise AssertionError('Missing file was accepted')
    print('PASS: locked/read-only/missing files rejected, retry succeeds after release, content unchanged', flush=True)


def check_dialog():
    import wx
    import win32con
    import win32gui
    from controls.document_generator_frame import show_generator_message
    from localization import tr

    app = wx.App(False)
    owner = wx.Frame(None, title='Generator availability probe')
    workspace = wx.Panel(wx.Panel(owner))
    owner.Show()
    failures = []

    def run():
        try:
            for parent, choice in ((owner, wx.ID_OK), (owner, wx.ID_CANCEL),
                                   (workspace, wx.ID_OK), (workspace, wx.ID_CANCEL)):
                owner.Iconize(True)
                observed = {}

                def inspect():
                    dialogs = [window for window in wx.GetTopLevelWindows()
                               if isinstance(window, wx.Dialog) and window.IsModal()]
                    if not dialogs:
                        failures.append('Retry dialog missing')
                        app.ExitMainLoop()
                        return
                    dialog = dialogs[0]
                    try:
                        observed['topmost'] = bool(win32gui.GetWindowLong(
                            dialog.GetHandle(), win32con.GWL_EXSTYLE) & win32con.WS_EX_TOPMOST)
                        observed['restored'] = not owner.IsIconized()
                        observed['parent'] = dialog.GetParent() is owner
                        observed['retry'] = dialog.FindWindow(wx.ID_OK).GetLabel() == tr('generator_retry')
                    finally:
                        dialog.EndModal(choice)

                wx.CallLater(150, inspect)
                result = show_generator_message(parent, tr('generator_open_unavailable',
                    path='example.docx', error='The file is in use.'), retry=True)
                assert result == choice, result
                assert observed and all(observed.values()), observed
            print('PASS: topmost Retry/Cancel dialog with frame and nested workspace parents, restored owner and both choices', flush=True)
        except Exception as error:
            failures.append(str(error))
        finally:
            owner.Destroy()
            app.ExitMainLoop()

    wx.CallAfter(run)
    app.MainLoop()
    assert not failures, failures


def check_word_access():
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx('Word.Application')
        app.Visible = False
        app.DisplayAlerts = 0
        app.AutomationSecurity = 3
        with tempfile.TemporaryDirectory(prefix='generator-word-access-') as folder:
            for extension, format_code in (('.docx', 12), ('.doc', 0), ('.docm', 13)):
                document = app.Documents.Add(Visible=False)
                path = str(Path(folder) / ('locked' + extension))
                try:
                    document.Content.Text = 'Availability probe'
                    document.SaveAs2(FileName=path, FileFormat=format_code, AddToRecentFiles=False)
                    try:
                        check_document_available(path)
                    except GeneratorError:
                        pass
                    else:
                        raise AssertionError(f'Open Word document accepted: {extension}')
                finally:
                    document.Close(False)
                check_document_available(path)
                print(f'PASS {extension}: Word lock detected before launch; available after Word closes it', flush=True)
    finally:
        if app is not None:
            app.Quit(0)
        pythoncom.CoUninitialize()


if __name__ == '__main__':
    check_access()
    check_dialog()
    if '--word' in sys.argv:
        check_word_access()
