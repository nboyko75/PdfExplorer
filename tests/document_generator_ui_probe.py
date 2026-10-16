"""Native wx smoke test with a fake Word worker (no Office needed)."""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
from controls.document_generator_frame import DocumentGeneratorFrame
from file_operations.document_generator import WordDisconnected
from localization import available_locales, load_locale, tr


@contextmanager
def save_prompt(choice=wx.ID_CANCEL):
    with patch('wx.MessageDialog') as factory:
        dialog = factory.return_value.__enter__.return_value
        dialog.ShowModal.return_value = choice
        yield factory
        if factory.called:
            dialog.SetYesNoCancelLabels.assert_called_once_with(
                tr('confirm_yes'), tr('confirm_no'), tr('cancel_button'))


class FakeSession:
    def __init__(self):
        self.rows = [{'name': 'Customer', 'value': 'Example customer'},
                     {'name': 'Address', 'value': 'Example street\nExample city'}]
        self.dirty = False
        self.closed = False
        self.rectangle = None
        self.export_error = None
        self.save_error = None
        self.save_calls = 0
        self.exports = []
        self.tables = []

    def arrange_window(self, rectangle):
        self.rectangle = rectangle

    def needs_save(self):
        return self.dirty

    def close_document(self):
        self.closed = True

    def export_document(self, target):
        if self.export_error:
            raise RuntimeError(self.export_error)
        self.exports.append(target)
        self.dirty = False

    def save_document(self):
        if self.save_error:
            raise RuntimeError(self.save_error)
        self.save_calls += 1
        self.dirty = False

    def open(self):
        return self.snapshot()

    def snapshot(self):
        return [dict(row) for row in self.rows]

    def state(self):
        return {'rows': self.snapshot(), 'tables': deepcopy(self.tables)}

    def update_fields(self, rows, tables):
        self.update_rows(rows)
        for old, new in zip(self.tables, tables):
            self.dirty = self.dirty or old['name'] != new['name'] or old['rows'] != new['rows']
            old.update(deepcopy(new))

    def add_table_selection(self):
        self.tables.append({'name': 'table' + str(len(self.tables) + 1),
                            'rows': [['Example item', '2', '10.00']],
                            'widths': [180, 60, 60], 'applied_rows': 1})
        self.dirty = True

    def delete_table(self, index):
        del self.tables[index]
        self.dirty = True

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
             patch('controls.document_generator.show_generator_message', return_value=wx.ID_CANCEL), \
             patch('common.window_tools.load_settings', return_value=settings), \
             patch('controls.document_generator.load_settings', return_value=settings), \
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
                    minimum = frame.splitter.GetMinimumPaneSize()
                    expected = max(minimum, min(settings['document_generator_sash_position'],
                                               frame.splitter.GetClientSize().height - minimum))
                    assert frame.splitter.GetSashPosition() == expected
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
                    assert abs(frame.bookmark_panel.GetClientSize().width - frame.add.GetRect().right - 8) <= 2
                    assert frame.save.GetRect().right < frame.export.GetRect().left
                    assert frame.export.GetRect().right < frame.exit.GetRect().left
                    assert frame.status.GetRect().bottom <= frame.save.GetRect().top
                assert frame.info.GetParent() is frame.bookmark_panel
                assert frame.table_info.GetParent() is frame.table_panel
                assert not frame.add_row.IsEnabled()
                frame.on_add_table(None)
                pump()
                assert frame.add_row.IsEnabled() and len(frame.table_fields) == 1
                table_name, grid = frame.table_fields[0]
                assert grid.GetNumberRows() == 1 and grid.GetNumberCols() == 3
                table_name.SetValue('Products')
                grid.SetCellValue(0, 0, 'Edited item')
                frame.on_add_row(None)
                pump()
                grid.SetCellValue(1, 0, 'Second item')
                assert grid.GetNumberRows() == 2
                frame._perform(lambda session: None)
                pump()
                assert worker.session.tables[0]['name'] == 'Products'
                assert worker.session.tables[0]['rows'][1][0] == 'Second item'
                if locale == 'en':
                    grid = frame.table_fields[0][1]
                    grid.SetGridCursor(0, 0)
                    grid.EnableCellEditControl()
                    pump()
                    editor = grid.GetCellEditor(0, 0)
                    editor.GetControl().SetValue('Pending editor text')
                    editor.DecRef()
                    editor = None
                    frame._perform(lambda session: None)
                    pump()
                    assert worker.session.tables[0]['rows'][0][0] == 'Pending editor text'
                frame.on_add_table(None)
                pump()
                frame.on_add_row(None)
                pump()
                assert frame.table_fields[0][1].GetNumberRows() == 2
                assert frame.table_fields[1][1].GetNumberRows() == 2
                frame._perform(lambda session: session.delete_table(1))
                pump()
                assert len(frame.table_fields) == 1
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
                with save_prompt(wx.ID_CANCEL) as prompt:
                    frame.Close()
                    pump()
                    prompt.assert_called_once()
                    assert frame and not worker.session.closed
                with save_prompt(wx.ID_NO):
                    frame.SetPosition((frame.GetPosition().x + 12, frame.GetPosition().y + 15))
                    pump()
                    expected_position = list(frame.GetPosition())
                    expected_size = list(frame.GetSize())
                    frame.splitter.SetSashPosition(frame.splitter.GetMinimumPaneSize() + 15)
                    expected_sash = frame.splitter.GetSashPosition()
                    frame.Close()
                    pump()
                assert worker.closed, locale
                assert worker.session.closed
                assert settings['document_generator_position'] == expected_position
                assert settings['document_generator_size'] == expected_size
                assert settings['document_generator_sash_position'] == expected_sash
            load_locale('en')
            # Use a real native window as Word's HWND to exercise geometry
            # capture and persistence without requiring Office.
            word = wx.Frame(None, title='Generator Word geometry probe')
            word.Show()
            def arrange_word(session, rectangle):
                session.rectangle = rectangle
                word.SetSize(wx.Rect(*rectangle))
                return word.GetHandle()
            try:
                with patch.object(FakeSession, 'arrange_window', arrange_word):
                    frame = DocumentGeneratorFrame(owner, 'example.docx')
                    frame.Show()
                    pump()
                    area = wx.Display(max(0, wx.Display.GetFromWindow(word))).GetClientArea()
                    word.SetSize(wx.Rect(area.x + 30, area.y + 45,
                                        min(700, area.width - 60), min(500, area.height - 90)))
                    pump()
                    frame._remember_word_geometry()
                    position = list(word.GetPosition())
                    size = list(word.GetSize())
                    assert frame._geometry['document_generator_word_position'] == position
                    assert frame._geometry['document_generator_word_size'] == size
                    word.Maximize()
                    pump()
                    frame._remember_word_geometry()
                    assert frame._geometry['document_generator_word_size'] == size
                    word.Iconize(True)
                    pump()
                    frame._remember_word_geometry()
                    assert frame._geometry['document_generator_word_position'] == position
                    with save_prompt(wx.ID_NO):
                        frame.Close()
                        pump()
                    assert settings['document_generator_word_position'] == position
                    assert settings['document_generator_word_size'] == size
                    word.Restore()
                    pump()
                    frame = DocumentGeneratorFrame(owner, 'example.docx')
                    frame.Show()
                    pump()
                    assert frame.worker.session.rectangle == tuple(position + size)
                    # Bad settings and disconnected monitors fall back safely.
                    fallback = (area.x, area.y, 640, 480)
                    for bad_position, bad_size in (([100000, 100000], size),
                                                    (['bad', 10], size), (position, [0, 0])):
                        frame._layout_settings = dict(settings, document_generator_word_position=bad_position,
                                                      document_generator_word_size=bad_size)
                        assert frame._restore_word_geometry(fallback) == fallback
                    with save_prompt(wx.ID_NO):
                        frame.Close()
                        pump()
            finally:
                word.Destroy()
                pump()
            for scenario in ('save', 'commit', 'opening', 'close_check', 'close_document'):
                frame = DocumentGeneratorFrame(owner, 'example.docx')
                frame.Show()
                pump()
                worker = frame.worker
                frame.fields[0][1].SetValue('Keep this entered value')
                expected_values = frame._values()
                message = WordDisconnected(tr('generator_word_disconnected'))
                worker.submit = lambda operation, callback: wx.CallAfter(callback, None, message)
                with patch('controls.document_generator.show_generator_message') as error_prompt, \
                     save_prompt() as close_prompt:
                    if scenario == 'save':
                        frame.on_save(None)
                    elif scenario == 'commit':
                        frame._commit_fields()
                    elif scenario == 'opening':
                        frame.ready = False
                        frame._opened(None, message)
                    elif scenario == 'close_check':
                        frame.Close()
                    else:
                        frame.saved_rows = frame._values()
                        frame.saved_tables = frame._table_values()
                        frame._confirm_close(False, None)
                    pump()
                    if scenario not in ('close_check', 'close_document'):
                        assert frame._values() == expected_values
                        assert frame.status.GetStatusText() == message
                        assert not frame.save.IsEnabled() and not frame.export.IsEnabled()
                        assert frame.exit.IsEnabled() and frame.scroller.IsEnabled()
                        assert frame.saved_rows is None
                        frame.Close()
                        pump()
                    error_prompt.assert_not_called()
                    close_prompt.assert_not_called()
                    assert worker.closed
            for choices, errors, succeeds in (
                    ([wx.ID_OK], [RuntimeError('File locked'), None], True),
                    ([wx.ID_OK, wx.ID_OK], [RuntimeError('File locked'), RuntimeError('Still locked'), None], True),
                    ([wx.ID_CANCEL], [RuntimeError('File locked')], False)):
                with patch.object(FakeSession, 'open', side_effect=errors) as opening, \
                     patch('controls.document_generator.show_generator_message', side_effect=choices) as prompt:
                    frame = DocumentGeneratorFrame(owner, 'example.docx')
                    worker = frame.worker
                    frame.Show()
                    pump()
                    pump()
                    assert opening.call_count == len(errors)
                    assert prompt.call_count == len(choices)
                    assert all(call.kwargs['retry'] for call in prompt.call_args_list)
                    if succeeds:
                        assert frame.ready and not frame.busy
                        with save_prompt(wx.ID_NO):
                            frame.Close()
                            pump()
                    assert worker.closed
            for scenario in ('saved', 'changed_after_save', 'yes', 'save_error',
                             'exported', 'cancel_file', 'export_error'):
                frame = DocumentGeneratorFrame(owner, 'example.docx')
                frame.Show()
                pump()
                worker = frame.worker
                dialog = MagicMock()
                dialog.__enter__.return_value = dialog
                dialog.ShowModal.return_value = wx.ID_CANCEL if scenario == 'cancel_file' else wx.ID_OK
                dialog.GetPath.return_value = 'example_result.docx'
                with patch('wx.FileDialog', return_value=dialog) as file_dialog:
                    if scenario in ('saved', 'changed_after_save'):
                        frame.on_save(None)
                        pump()
                        file_dialog.assert_not_called()
                        assert worker.session.save_calls == 1
                        assert worker.session.exports == []
                        if scenario == 'changed_after_save':
                            worker.session.dirty = True
                            with save_prompt(wx.ID_NO) as prompt:
                                frame.Close()
                                pump()
                                prompt.assert_called_once()
                        else:
                            with save_prompt() as prompt:
                                frame.Close()
                                pump()
                                prompt.assert_not_called()
                        assert worker.closed and worker.session.closed
                    elif scenario in ('yes', 'save_error'):
                        if scenario == 'save_error':
                            worker.session.save_error = 'Test save failure'
                        with save_prompt(wx.ID_YES):
                            frame.Close()
                            pump()
                        file_dialog.assert_not_called()
                        assert worker.session.exports == []
                        if scenario == 'yes':
                            assert worker.closed and worker.session.closed
                            assert worker.session.save_calls == 1
                        else:
                            assert frame and not worker.session.closed
                            with save_prompt(wx.ID_NO):
                                frame.Close()
                                pump()
                            assert worker.closed and worker.session.closed
                    else:
                        if scenario == 'export_error':
                            worker.session.export_error = 'Test export failure'
                        with patch('wx.MessageBox', return_value=wx.OK):
                            frame.on_export(None)
                            pump()
                        file_dialog.assert_called_once()
                        assert frame and not worker.session.closed
                        if scenario == 'exported':
                            assert worker.session.exports == ['example_result.docx']
                            assert frame.saved_rows == frame._values()
                            with save_prompt() as prompt:
                                frame.Close()
                                pump()
                                prompt.assert_not_called()
                        else:
                            assert worker.session.exports == []
                            assert frame.saved_rows is None
                            with save_prompt(wx.ID_NO):
                                frame.Close()
                                pump()
                        assert worker.closed and worker.session.closed
        print('PASS: both panels, table grids and active editors, Add value/table/row, splitter persistence and Save/Export/Exit in all 11 locales')
    finally:
        load_locale('en')
        owner.Destroy()
        pump()


if __name__ == '__main__':
    run()
