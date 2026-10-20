"""Native wx smoke test with a fake Word worker (no Office needed)."""
from pathlib import Path
from copy import deepcopy
from contextlib import contextmanager
import sys
import csv
import io
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wx
import wx.grid as gridlib
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

    def add_selection(self, shared_index=None):
        name = 'bookmark' + str(len(self.rows) + 1)
        if shared_index is None:
            self.rows.append({'name': name, 'value': 'New field'})
        else:
            row = self.rows[shared_index]
            group = row.setdefault('group', 'shared-' + row['name'])
            self.rows.insert(shared_index + 1, {'name': name, 'value': row['value'], 'group': group})

    def delete_row(self, index):
        removed = self.rows.pop(index)
        if removed.get('uid') and removed.get('group'):
            for row in self.rows:
                if row.get('group') == removed['group']:
                    row['uid'] = True
                    break


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


def click(button):
    button.GetEventHandler().ProcessEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, button.GetId()))


def check_table_clipboard(frame):
    frame.worker.session.tables = [{'name': 'Clipboard', 'widths': [100] * 3,
        'rows': [['a', 'b', 'outside'], ['line\nbreak', 'tab\tvalue', 'keep'],
                 ['tail', '', 'last']], 'applied_rows': 1}]
    frame._render_tables(frame.worker.session.state()['tables'])
    pump()
    grid = frame.table_fields[0][1]
    clipboard = MagicMock()
    clipboard.text = ''
    def write(data):
        clipboard.text = data.GetText()
        return True
    def read(data):
        data.SetText(clipboard.text)
        return True
    clipboard.Open.return_value = True
    clipboard.SetData.side_effect = write
    clipboard.GetData.side_effect = read
    def shortcut(key):
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetControlDown(True)
        event.SetKeyCode(ord(key))
        grid.GetEventHandler().ProcessEvent(event)
        pump()
    with patch('wx.TheClipboard', clipboard):
        grid.SelectBlock(0, 0, 1, 1)
        shortcut('C')
        original = clipboard.text
        assert list(csv.reader(io.StringIO(original), delimiter='\t')) == [['a', 'b'], ['line\nbreak', 'tab\tvalue']]
        clipboard.Open.return_value = False
        shortcut('X')
        assert grid.GetCellValue(0, 0) == 'a', 'Failed clipboard access must not erase values'
        clipboard.Open.return_value = True
        shortcut('X')
        assert all(grid.GetCellValue(r, c) == '' for r in (0, 1) for c in (0, 1))
        assert grid.GetCellValue(0, 2) == 'outside'
        shortcut('V')
        assert grid.GetCellValue(1, 0) == 'line\nbreak' and grid.GetCellValue(1, 1) == 'tab\tvalue'
        # Right-clicking inside a selection preserves it and dispatches the menu action.
        def popup(menu):
            assert [item.GetItemLabel() for item in menu.GetMenuItems()] == [
                tr('context_copy') + '\tCtrl+C', tr('context_cut') + '\tCtrl+X',
                tr('context_paste') + '\tCtrl+V', tr('generator_clear_cells') + '\tCtrl+D']
            menu.ProcessEvent(wx.CommandEvent(wx.EVT_MENU.typeId, menu.GetMenuItems()[3].GetId()))
        with patch.object(grid, 'PopupMenu', side_effect=popup):
            grid.GetEventHandler().ProcessEvent(gridlib.GridEvent(
                grid.GetId(), gridlib.EVT_GRID_CELL_RIGHT_CLICK.typeId, grid, 1, 1))
        pump()
        assert len(frame._selected_table_cells(grid)) == 4
        assert grid.GetCellValue(1, 1) == '' and grid.GetCellValue(1, 2) == 'keep'
        grid.ClearSelection()
        grid.SelectBlock(0, 0, 0, 0)
        grid.SelectBlock(2, 2, 2, 2, addToSelected=True)
        clipboard.text = 'filled'
        shortcut('V')
        assert grid.GetCellValue(0, 0) == grid.GetCellValue(2, 2) == 'filled'
        assert grid.GetCellValue(1, 2) == 'keep'
        shortcut('D')
        assert grid.GetCellValue(0, 0) == grid.GetCellValue(2, 2) == ''
        assert grid.GetNumberRows() == 3
        grid.ClearSelection()
        grid.SetGridCursor(1, 1)
        clipboard.text = '1\t2\tclipped\r\n3\t4\r\nclipped'
        shortcut('V')
        assert [grid.GetCellValue(r, c) for r in (1, 2) for c in (1, 2)] == ['1', '2', '3', '4']
        assert frame.worker.session.tables[0]['rows'][2][2] == '4'
        # Copy includes an active editor's pending text; ordinary editor shortcuts stay native.
        grid.SetGridCursor(0, 0)
        grid.EnableCellEditControl()
        pump()
        editor = grid.GetCellEditor(0, 0)
        editor.GetControl().SetValue('pending text')
        editor.DecRef()
        event = wx.KeyEvent(wx.wxEVT_CHAR_HOOK)
        event.SetControlDown(True)
        event.SetKeyCode(ord('C'))
        frame._on_table_key(event, grid)
        assert event.GetSkipped()
        frame._table_clipboard_action(grid, 'copy')
        assert clipboard.text == 'pending text\r\n'


def resize_value(value, height):
    container = value._generator_container
    assert container.GetSashVisible(wx.adv.SASH_BOTTOM)
    x = container.GetSize().width // 2
    for kind, y, down in ((wx.wxEVT_LEFT_DOWN, container.GetSize().height - 2, True),
                          (wx.wxEVT_MOTION, height, True), (wx.wxEVT_LEFT_UP, height, False)):
        event = wx.MouseEvent(kind)
        event.SetEventObject(container)
        event.SetPosition((x, y))
        event.SetLeftDown(down)
        container.GetEventHandler().ProcessEvent(event)
    pump()


def check_bookmark_layout_persistence(owner, settings):
    key = 'document_generator_bookmark_editor_layout'
    frame = DocumentGeneratorFrame(owner, 'bookmark-layout.docx')
    frame.Show()
    pump()
    heights = []
    for index in range(2):
        frame.expand_checks[index].SetValue(True)
        frame.on_expand(index)
        pump()
        value = frame.fields[index][1]
        height = value._generator_container.GetSize().height + frame.FromDIP(40 + 20 * index)
        resize_value(value, height)
        heights.append(height)
    frame.expand_checks[1].SetValue(False)
    frame.on_expand(1)
    document = frame._layout_document
    expected = {
        'Customer': {'expanded': True, 'height': frame.ToDIP(heights[0])},
        'Address': {'expanded': False, 'height': frame.ToDIP(heights[1])},
    }
    assert settings[key][document] == expected
    with save_prompt(wx.ID_NO):
        frame.Close()
        pump()

    # The same bookmark names in another document have independent settings.
    other = DocumentGeneratorFrame(owner, 'other-bookmark-layout.docx')
    other.Show()
    pump()
    assert all(not check.IsChecked() for check in other.expand_checks)
    with save_prompt(wx.ID_NO):
        other.Close()
        pump()
    assert settings[key][document] == expected

    frame = DocumentGeneratorFrame(owner, 'bookmark-layout.docx')
    frame.Show()
    pump()
    assert frame.expand_checks[0].IsChecked()
    assert frame.fields[0][1].IsMultiLine()
    assert frame.fields[0][1]._generator_container.GetSize().height == heights[0]
    assert not frame.expand_checks[1].IsChecked()
    assert not frame.fields[1][1].IsMultiLine()
    frame.expand_checks[1].SetValue(True)
    frame.on_expand(1)
    pump()
    assert frame.fields[1][1]._generator_container.GetSize().height == heights[1]
    with save_prompt(wx.ID_NO):
        frame.Close()
        pump()


def run():
    app = wx.App(False)
    owner = wx.Frame(None, title='Generator UI probe')
    owner.refresh_current_folder_preserving_context = lambda: None
    owner.Show()
    settings = {}
    try:
        with patch('controls.document_generator_frame.GeneratorWorker', FakeWorker), \
             patch('controls.document_generator_frame.show_generator_message', return_value=wx.ID_CANCEL), \
             patch('common.window_tools.load_settings', return_value=settings), \
             patch('controls.document_generator_frame.load_settings', return_value=settings), \
             patch('controls.document_generator_frame.update_settings', side_effect=settings.update):
            for locale in available_locales():
                load_locale(locale)
                frame = DocumentGeneratorFrame(owner, 'example.docx')
                worker = frame.worker
                frame.Show()
                pump()
                assert frame.IsShown() and owner.IsEnabled(), 'Form must be modeless'
                assert frame.ready and len(frame.fields) == 2
                assert worker.session.rectangle == frame.word_rectangle
                if 'document_generator_position' in settings:
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
                    button = frame.grid.FindItemAtPosition((index + 1, 0)).GetWindow()
                    assert button.GetSize().width == button.GetSize().height
                    assert button.GetSize().width < frame.FromDIP(32)
                    number = frame.grid.FindItemAtPosition((index + 1, 2)).GetWindow()
                    label = number.GetChildren()[0]
                    assert number.GetSize().height == frame.fields[index][0].GetSize().height
                    assert abs(label.GetPosition().y * 2 + label.GetSize().height - number.GetSize().height) <= 1
                original = frame._values()[1]['value']
                assert original == 'Example street\nExample city'
                frame.expand_checks[1].SetValue(True)
                frame.on_expand(1)
                pump()
                name, value = frame.fields[1]
                assert value.IsMultiLine() and value.GetValue() == original
                assert value.GetSize().height > name.GetSize().height
                resized_height = value._generator_container.GetSize().height + frame.FromDIP(60)
                resize_value(value, resized_height)
                assert value._generator_container.GetSize().height == resized_height
                assert value.GetValue() == original
                assert value.GetRect().bottom <= value._generator_container.GetClientSize().height - frame.FromDIP(5)
                resize_value(value, 1)
                assert value.GetSize().height >= name.GetSize().height * 2
                resize_value(value, resized_height)
                value.SetValue('Updated street\nUpdated city\nУкраїна / 日本')
                expanded_text = value.GetValue()
                frame.expand_checks[1].SetValue(False)
                frame.on_expand(1)
                pump()
                assert not frame.fields[1][1].IsMultiLine()
                assert frame.fields[1][1]._generator_container is frame.fields[1][1]
                assert frame._values()[1]['value'] == expanded_text
                frame.expand_checks[1].SetValue(True)
                frame.on_expand(1)
                pump()
                assert frame.fields[1][1].GetValue() == expanded_text
                assert frame.fields[1][1]._generator_container.GetSize().height == resized_height
                for width in (800, 1000, 640):
                    frame.SetSize((width, 480))
                    pump()
                    assert abs(frame.panel.GetClientSize().width - frame.exit.GetRect().right - 10) <= 2
                    assert abs(frame.add.GetRect().left - 8) <= 2
                    assert abs(frame.add_table.GetRect().left - 8) <= 2
                    assert frame.save.GetRect().right < frame.export.GetRect().left
                    assert frame.export.GetRect().right < frame.exit.GetRect().left
                    assert frame.status.GetRect().bottom <= frame.save.GetRect().top
                assert frame.info.GetParent() is frame.bookmark_panel
                assert frame.table_info.GetParent() is frame.table_panel
                assert not frame.table_add_buttons
                frame.on_add_table(None)
                pump()
                assert frame.table_add_buttons[0].IsEnabled() and len(frame.table_fields) == 1
                assert frame.table_add_buttons[0].GetToolTipText() == tr('generator_add_row')
                table_name, grid = frame.table_fields[0]
                assert grid.GetNumberRows() == 1 and grid.GetNumberCols() == 3
                bookmark_width = frame.grid.FindItemAtPosition((1, 0)).GetWindow().GetSize().width
                table_remove = next(child for child in grid.GetParent().GetChildren()
                                    if isinstance(child, wx.Button) and child.GetToolTipText() == tr('generator_delete_table'))
                assert table_remove.GetSize().width == bookmark_width
                assert frame.table_add_buttons[0].GetSize().width == bookmark_width
                assert grid._generator_row_buttons[0].GetSize().width == bookmark_width
                table_name.SetValue('Products')
                grid.SetCellValue(0, 0, 'Edited item')
                assert not grid._generator_row_buttons[0].IsEnabled()
                click(frame.table_add_buttons[0])
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
                frame.active_table = 0  # Each + must target its own table.
                click(frame.table_add_buttons[1])
                pump()
                assert frame.table_fields[0][1].GetNumberRows() == 2
                assert frame.table_fields[1][1].GetNumberRows() == 2
                second = frame.table_fields[1][1]
                assert second._generator_row_buttons[1].GetToolTipText() == tr('generator_remove_row')
                click(second._generator_row_buttons[1])
                pump()
                assert second.GetNumberRows() == 1
                assert len(worker.session.tables[1]['rows']) == 1
                assert frame.table_fields[0][1].GetNumberRows() == 2
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
                assert frame.fields[1][1]._generator_container.GetSize().height == resized_height
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
            check_bookmark_layout_persistence(owner, settings)
            frame = DocumentGeneratorFrame(owner, 'uid.docx')
            frame.Show()
            pump()
            frame.uid_checks[0].SetValue(True)
            frame.on_uid_changed(frame.uid_checks[0])
            pump()
            assert frame.worker.session.rows[0]['uid'] is True
            frame.uid_checks[1].SetValue(True)
            frame.on_uid_changed(frame.uid_checks[1])
            pump()
            assert not frame.uid_checks[0].IsChecked()
            assert sum(row.get('uid', False) for row in frame._values()) == 1
            frame.fields[1][1].SetValue('ID/42')
            with patch('wx.FileDialog') as factory:
                factory.return_value.__enter__.return_value.ShowModal.return_value = wx.ID_CANCEL
                frame.on_export(None)
                assert factory.call_args.kwargs['defaultFile'] == 'uid_result_ID_42.docx'
            frame.uid_checks[1].SetValue(False)
            frame.on_uid_changed(frame.uid_checks[1])
            pump()
            with patch('wx.FileDialog') as factory:
                factory.return_value.__enter__.return_value.ShowModal.return_value = wx.ID_CANCEL
                frame.on_export(None)
                assert factory.call_args.kwargs['defaultFile'] == 'uid_result.docx'
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
            frame = DocumentGeneratorFrame(owner, 'shared.docx')
            frame.Show()
            pump()
            frame.fields[0][1].SetValue('Shared replacement')
            frame.uid_checks[0].SetValue(True)
            frame.on_uid_changed(frame.uid_checks[0])
            pump()
            assert frame.bookmark_add_buttons[0].GetToolTipText() == tr('generator_add_shared_bookmark')
            click(frame.bookmark_add_buttons[0])
            pump()
            assert len(frame.fields) == 3
            assert frame.fields[0][1] is frame.fields[1][1]
            assert frame.uid_checks[0] is frame.uid_checks[1]
            assert frame.uid_checks[0].IsChecked()
            assert sum(row.get('uid', False) for row in frame._values()) == 1
            assert frame.fields[1][1] is not frame.fields[2][1]
            assert frame._values()[0]['value'] == frame._values()[1]['value'] == 'Shared replacement'
            assert frame.grid.FindItemAtPosition((1, 4)).GetSpan() == (2, 1)
            frame.expand_checks[0].SetValue(True)
            frame.on_expand(0)
            pump()
            assert frame.fields[0][1] is frame.fields[1][1] and frame.fields[0][1].IsMultiLine()
            shared_value = frame.fields[0][1]
            next_row_y = frame.fields[2][0].GetPosition().y
            shared_height = shared_value._generator_container.GetSize().height + frame.FromDIP(70)
            resize_value(shared_value, shared_height)
            assert shared_value._generator_container.GetSize().height == shared_height
            assert frame.fields[2][0].GetPosition().y > next_row_y
            frame.fields[1][1].SetValue('Shared\nmultiline')
            click(frame.bookmark_add_buttons[1])
            pump()
            assert len(frame.fields) == 4
            assert all(frame.fields[i][1] is frame.fields[0][1] for i in range(3))
            assert frame.fields[0][1]._generator_expanded_height == shared_height
            assert all(row['value'] == 'Shared\nmultiline' for row in frame._values()[:3])
            # Renaming and deleting the first bookmark retain the shared value.
            frame.fields[0][0].SetValue('Renamed')
            frame._perform(lambda session: session.delete_row(0))
            pump()
            assert frame.fields[0][1] is frame.fields[1][1]
            assert frame.fields[0][1].IsMultiLine()
            saved_shared = deepcopy(frame.worker.session.rows)
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
            with patch.object(FakeSession, 'state', return_value={'rows': deepcopy(saved_shared), 'tables': []}):
                frame = DocumentGeneratorFrame(owner, 'shared.docx')
            frame.worker.session.rows = saved_shared
            frame.Show()
            pump()
            assert frame.fields[0][1] is frame.fields[1][1]
            assert frame.expand_checks[0].IsChecked()
            assert frame.fields[0][1]._generator_expanded_height == shared_height
            assert frame._values() == saved_shared
            frame._perform(lambda session: session.delete_row(1))
            pump()
            assert frame._values()[0]['value'] == 'Shared\nmultiline'
            assert frame.fields[0][1] is not frame.fields[1][1]
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
            frame = DocumentGeneratorFrame(owner, 'clipboard.docx')
            frame.Show()
            pump()
            check_table_clipboard(frame)
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
            # Exercise actual text-editor events, manual width events and
            # persistence separately from the locale/layout smoke checks.
            frame = DocumentGeneratorFrame(owner, 'widths.docx')
            frame.Show()
            pump()
            frame.worker.session.tables = [{'name': 'Widths',
                'rows': [['', '', 'W' * 100]], 'widths': [100, 100, 100], 'applied_rows': 1}]
            frame._render_tables(frame.worker.session.state()['tables'])
            pump()
            name, grid = frame.table_fields[0]
            assert grid.GetColSize(0) == frame.FromDIP(32)
            assert grid.GetColSize(2) == frame.FromDIP(300)
            grid.SetGridCursor(0, 0)
            grid.EnableCellEditControl()
            pump()
            editor = grid.GetCellEditor(0, 0)
            control = editor.GetControl()
            control.SetValue('A medium length value')
            pump()
            assert frame.FromDIP(32) < grid.GetColSize(0) < frame.FromDIP(300)
            control.SetValue('W' * 100)
            pump()
            assert grid.GetColSize(0) == frame.FromDIP(300)
            control.SetValue('')
            pump()
            assert grid.GetColSize(0) == frame.FromDIP(32)
            editor.DecRef()
            frame._finish_table_editing()
            grid.SetColSize(0, frame.FromDIP(420))
            event = gridlib.GridSizeEvent(grid.GetId(), gridlib.EVT_GRID_COL_SIZE.typeId, grid, 0)
            grid.GetEventHandler().ProcessEvent(event)
            pump()
            assert settings['document_generator_table_column_widths'][frame._layout_document]['Widths']['0'] == 420
            frame.SetSize((900, 600))
            pump()
            assert grid.GetColSize(0) == frame.FromDIP(420)
            name.SetValue('RenamedWidths')
            frame._perform(lambda session: None)
            pump()
            grid = frame.table_fields[0][1]
            assert grid.GetColSize(0) == frame.FromDIP(420)
            stored = settings['document_generator_table_column_widths'][frame._layout_document]
            assert 'Widths' not in stored and stored['RenamedWidths']['0'] == 420
            saved_tables = deepcopy(frame.worker.session.tables)
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
            for path, expected_width in (('widths.docx', 420), ('other.docx', 32)):
                frame = DocumentGeneratorFrame(owner, path)
                frame.Show()
                pump()
                frame.worker.session.tables = deepcopy(saved_tables)
                frame._render_tables(frame.worker.session.state()['tables'])
                pump()
                grid = frame.table_fields[0][1]
                assert grid.GetColSize(0) == frame.FromDIP(expected_width)
                with save_prompt(wx.ID_NO):
                    frame.Close()
                    pump()
            frame = DocumentGeneratorFrame(owner, 'scrolling.docx')
            frame.Show()
            pump()
            frame.worker.session.tables = [{'name': 'Scrolling',
                'rows': [[str(row)] for row in range(25)], 'widths': [100], 'applied_rows': 1}]
            frame._render_tables(frame.worker.session.state()['tables'])
            pump()
            grid = frame.table_fields[0][1]
            grid.MakeCellVisible(24, 0)
            pump()
            pump()
            last = grid._generator_row_buttons[24]
            assert last.IsShown() and not grid._generator_row_buttons[0].IsShown()
            assert last.GetPosition().y == grid.CalcScrolledPosition(0, grid.CellToRect(24, 0).y)[1] + 1
            click(grid._generator_row_buttons[23])
            pump()
            assert [row[0] for row in frame.worker.session.tables[0]['rows']] == [str(row) for row in range(25) if row != 23]
            with save_prompt(wx.ID_NO):
                frame.Close()
                pump()
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
                with patch('controls.document_generator_frame.show_generator_message') as error_prompt, \
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
                     patch('controls.document_generator_frame.show_generator_message', side_effect=choices) as prompt:
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
        print('PASS: panels, shared bookmark values, matching row buttons, multi-cell clipboard/menu/shortcuts, column widths, geometry and Save/Export/Exit in all 11 locales')
    finally:
        load_locale('en')
        owner.Destroy()
        pump()


if __name__ == '__main__':
    run()
