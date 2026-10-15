"""Native wx smoke test with a fake Word worker (no Office needed)."""
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
from controls.document_generator import DocumentGeneratorFrame
from localization import available_locales, load_locale


class FakeSession:
    def __init__(self):
        self.rows = [{'name': 'Customer', 'value': 'Example customer'},
                     {'name': 'Address', 'value': 'Example street\nExample city'}]
        self.dirty = False
        self.closed = False
        self.rectangle = None
        self.export_error = None

    def arrange_window(self, rectangle):
        self.rectangle = rectangle

    def needs_save(self):
        return self.dirty

    def close_document(self):
        self.closed = True

    def export_document(self, target):
        if self.export_error:
            raise RuntimeError(self.export_error)
        self.dirty = False

    def open(self):
        return self.snapshot()

    def snapshot(self):
        return [dict(row) for row in self.rows]

    def update_rows(self, rows):
        self.dirty = self.dirty or rows != self.rows
        self.rows = rows

    def add_selection(self):
        self.rows.append({'name': 'bookmark3', 'value': 'New field'})

    def delete_row(self, index):
        del self.rows[index]


class FakeWorker:
    def __init__(self, source, dispatch):
        self.session = FakeSession()
        self.dispatch = dispatch
        self.closed = False

    def submit(self, operation, callback):
        try:
            result = operation(self.session)
        except Exception as error:
            self.dispatch(callback, None, str(error))
        else:
            self.dispatch(callback, result, None)

    def close(self):
        self.closed = True


def pump():
    wx.CallLater(25, wx.GetApp().ExitMainLoop)
    wx.GetApp().MainLoop()


def run():
    app = wx.App(False)
    owner = wx.Frame(None, title='Generator UI probe')
    owner.refresh_current_folder_preserving_context = lambda: None
    owner.Show()
    settings = {}
    try:
        with patch('controls.document_generator.GeneratorWorker', FakeWorker), \
             patch('common.window_tools.load_settings', return_value=settings), \
             patch('controls.document_generator.update_settings', side_effect=settings.update):
            for locale in available_locales():
                load_locale(locale)
                frame = DocumentGeneratorFrame(owner, 'example.docx')
                worker = frame.worker
                frame.Show()
                pump()
                assert frame.IsShown() and owner.IsEnabled(), 'Form must be modeless'
                assert frame.ready and len(frame.fields) == 2
                assert worker.session.rectangle == frame.word_rectangle
                if settings:
                    assert list(frame.GetPosition()) == settings['document_generator_position']
                    assert list(frame.GetSize()) == settings['document_generator_size']
                else:
                    assert abs(frame.GetRect().right - frame.word_rectangle[0]) <= 1
                assert all(not value.IsMultiLine() for name, value in frame.fields)
                assert all(name.GetSize().height == value.GetSize().height for name, value in frame.fields)
                assert all(name.GetSize().width < 190 for name, value in frame.fields)
                for index in range(len(frame.fields)):
                    button = frame.grid.GetItem(5 + index * 5).GetWindow()
                    assert button.GetSize().width == button.GetSize().height
                    assert button.GetSize().width < frame.FromDIP(32)
                original = frame._values()[1]['value']
                assert original == 'Example street\nExample city'
                frame.expand_checks[1].SetValue(True)
                frame.on_expand(1)
                pump()
                name, value = frame.fields[1]
                assert value.IsMultiLine() and value.GetValue() == original
                assert value.GetSize().height > name.GetSize().height
                value.SetValue('Updated street\nUpdated city\nУкраїна / 日本')
                expanded_text = value.GetValue()
                frame.expand_checks[1].SetValue(False)
                frame.on_expand(1)
                pump()
                assert not frame.fields[1][1].IsMultiLine()
                assert frame._values()[1]['value'] == expanded_text
                frame.expand_checks[1].SetValue(True)
                frame.on_expand(1)
                pump()
                assert frame.fields[1][1].GetValue() == expanded_text
                for width in (800, 1000, 640):
                    frame.SetSize((width, 480))
                    pump()
                    assert abs(frame.panel.GetClientSize().width - frame.exit.GetRect().right - 10) <= 2
                    assert frame.add.GetRect().right < frame.save.GetRect().left
                    assert frame.save.GetRect().right < frame.exit.GetRect().left
                    assert frame.status.GetRect().bottom <= frame.add.GetRect().top
                frame.fields[0][1].SetValue('Updated value')
                frame._perform(lambda session: session.add_selection())
                pump()
                assert len(frame.fields) == 3
                assert worker.session.rows[0]['value'] == 'Updated value'
                assert worker.session.rows[1]['value'] == expanded_text
                assert frame.expand_checks[1].IsChecked()
                frame._perform(lambda session: session.delete_row(1))
                pump()
                assert len(frame.fields) == 2
                if locale == 'en':
                    frame.SetSize((800, 480))
                    pump()
                    size = frame.GetClientSize()
                    bitmap = wx.Bitmap(size.width, size.height)
                    dc = wx.MemoryDC(bitmap)
                    dc.Blit(0, 0, size.width, size.height, wx.ClientDC(frame), 0, 0)
                    dc.SelectObject(wx.NullBitmap)
                    if len(sys.argv) > 1:
                        bitmap.SaveFile(sys.argv[1], wx.BITMAP_TYPE_PNG)
                with patch('wx.MessageBox', return_value=wx.CANCEL) as prompt:
                    frame.Close()
                    pump()
                    prompt.assert_called_once()
                    assert frame and not worker.session.closed
                with patch('wx.MessageBox', return_value=wx.NO):
                    frame.SetPosition((frame.GetPosition().x + 12, frame.GetPosition().y + 15))
                    pump()
                    expected_position = list(frame.GetPosition())
                    expected_size = list(frame.GetSize())
                    frame.Close()
                    pump()
                assert worker.closed, locale
                assert worker.session.closed
                assert settings['document_generator_position'] == expected_position
                assert settings['document_generator_size'] == expected_size
            load_locale('en')
            for scenario in ('saved', 'changed_after_save', 'yes', 'cancel_file', 'save_error'):
                frame = DocumentGeneratorFrame(owner, 'example.docx')
                frame.Show()
                pump()
                worker = frame.worker
                dialog = MagicMock()
                dialog.__enter__.return_value = dialog
                dialog.ShowModal.return_value = wx.ID_CANCEL if scenario == 'cancel_file' else wx.ID_OK
                dialog.GetPath.return_value = 'example_result.docx'
                with patch('wx.FileDialog', return_value=dialog):
                    if scenario in ('saved', 'changed_after_save'):
                        frame.on_save(None)
                        pump()
                        if scenario == 'changed_after_save':
                            worker.session.dirty = True
                            with patch('wx.MessageBox', return_value=wx.NO) as prompt:
                                frame.Close()
                                pump()
                                prompt.assert_called_once()
                        else:
                            with patch('wx.MessageBox') as prompt:
                                frame.Close()
                                pump()
                                prompt.assert_not_called()
                        assert worker.closed and worker.session.closed
                    else:
                        if scenario == 'save_error':
                            worker.session.export_error = 'Test save failure'
                        with patch('wx.MessageBox', return_value=wx.YES):
                            frame.Close()
                            pump()
                        if scenario == 'yes':
                            assert worker.closed and worker.session.closed
                        else:
                            assert frame and not worker.session.closed
                            with patch('wx.MessageBox', return_value=wx.NO):
                                frame.Close()
                                pump()
                            assert worker.closed and worker.session.closed
        print('PASS: saved geometry, compact rows, Expand/collapse with Unicode/newline preservation, toolbar and close/save flows in all 11 locales')
    finally:
        load_locale('en')
        owner.Destroy()
        pump()


if __name__ == '__main__':
    run()
