"""Native, modeless editor for Word document generator fields."""
import os
import logging

import wx
import wx.grid as gridlib

from file_operations.document_generator import GeneratorWorker, WordDisconnected
from common.window_tools import load_settings, restore_control_geometry, update_settings
from localization import tr


def show_generator_message(owner, message, retry=False):
    """Use a real wx dialog so its topmost native window can be raised."""
    # Menu commands pass an ExplorerWorkspace panel, not necessarily a frame.
    owner = wx.GetTopLevelParent(owner) if owner else None
    if owner:
        if owner.IsIconized():
            owner.Restore()
        owner.Show()
        owner.Raise()
    style = wx.OK | wx.ICON_ERROR | wx.STAY_ON_TOP
    if retry:
        style |= wx.CANCEL
    with wx.GenericMessageDialog(owner, message, tr('generator_title'), style) as dialog:
        if retry:
            dialog.SetOKLabel(tr('generator_retry'))

        def foreground(event):
            event.Skip()
            if not event.IsShown():
                return
            dialog.Raise()
            if wx.Platform == '__WXMSW__':
                try:
                    import win32con
                    import win32gui
                    win32gui.SetWindowPos(dialog.GetHandle(), win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                          win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_SHOWWINDOW)
                    win32gui.SetForegroundWindow(dialog.GetHandle())
                except Exception:
                    logging.getLogger(__name__).debug('Windows declined generator dialog focus', exc_info=True)

        dialog.Bind(wx.EVT_SHOW, foreground)
        return dialog.ShowModal()


class DocumentGeneratorFrame(wx.Frame):
    def __init__(self, owner, path):
        super().__init__(owner, title=tr('generator_title') + ' — ' + os.path.basename(path),
                         size=(800, 480))
        self.owner = owner
        self._window_id = self.GetId()
        self.path = path
        self.rows = []
        self.fields = []
        self.expand_checks = []
        self.tables = []
        self.table_fields = []
        self.active_table = None
        self.busy = False
        self.closing = False
        self.ready = False
        self._disconnected = False
        self.saved_rows = None
        self.saved_tables = None
        self._prompting = False
        panel = self.panel = wx.Panel(self)
        layout = wx.BoxSizer(wx.VERTICAL)
        self.toolbar = wx.BoxSizer(wx.HORIZONTAL)
        self.toolbar.AddStretchSpacer()
        self.save = wx.Button(panel, label=tr('preview_save_button'))
        self.export = wx.Button(panel, label=tr('generator_export'))
        self.exit = wx.Button(panel, label=tr('exit_button'))
        for button in (self.save, self.export, self.exit):
            self.toolbar.Add(button, 0, wx.LEFT, 8)
        self.splitter = wx.SplitterWindow(
            panel, style=wx.SP_LIVE_UPDATE | wx.SP_3D | wx.SP_NO_XP_THEME)
        self.splitter.SetMinimumPaneSize(self.FromDIP(130))
        self.splitter.SetSashGravity(0.5)
        self.bookmark_panel = wx.Panel(self.splitter)
        self.table_panel = wx.Panel(self.splitter)
        self.bookmark_panel.SetBackgroundColour(panel.GetBackgroundColour())
        self.table_panel.SetBackgroundColour(panel.GetBackgroundColour())
        bookmarks_layout = wx.BoxSizer(wx.VERTICAL)
        bookmark_header, self.info = self._section_header(
            self.bookmark_panel, 'generator_bookmark_values', 'generator_instructions')
        bookmarks_layout.Add(bookmark_header, 0, wx.EXPAND | wx.ALL, 8)
        self.scroller = wx.ScrolledWindow(self.bookmark_panel, style=wx.VSCROLL)
        self.scroller.SetScrollRate(0, 16)
        self.grid = wx.FlexGridSizer(cols=5, vgap=8, hgap=8)
        self.grid.AddGrowableCol(3, 1)
        self.scroller.SetSizer(self.grid)
        bookmarks_layout.Add(self.scroller, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        bookmark_buttons = wx.BoxSizer(wx.HORIZONTAL)
        bookmark_buttons.AddStretchSpacer()
        self.add = wx.Button(self.bookmark_panel, label=tr('generator_add'))
        bookmark_buttons.Add(self.add)
        bookmarks_layout.Add(bookmark_buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.bookmark_panel.SetSizer(bookmarks_layout)

        tables_layout = wx.BoxSizer(wx.VERTICAL)
        table_header, self.table_info = self._section_header(
            self.table_panel, 'generator_table_values', 'generator_table_instructions')
        tables_layout.Add(table_header, 0, wx.EXPAND | wx.ALL, 8)
        self.table_scroller = wx.ScrolledWindow(self.table_panel, style=wx.VSCROLL)
        self.table_scroller.SetScrollRate(0, 16)
        self.table_list = wx.BoxSizer(wx.VERTICAL)
        self.table_scroller.SetSizer(self.table_list)
        tables_layout.Add(self.table_scroller, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        table_buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.add_row = wx.Button(self.table_panel, label=tr('generator_add_row'))
        self.add_table = wx.Button(self.table_panel, label=tr('generator_add_table'))
        table_buttons.Add(self.add_row)
        table_buttons.AddStretchSpacer()
        table_buttons.Add(self.add_table)
        tables_layout.Add(table_buttons, 0, wx.EXPAND | wx.ALL, 8)
        self.table_panel.SetSizer(tables_layout)
        self.splitter.SplitHorizontally(self.bookmark_panel, self.table_panel)
        layout.Add(self.splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
        self.status = wx.StatusBar(panel, style=wx.STB_DEFAULT_STYLE & ~wx.STB_SIZEGRIP)
        self.status.SetFieldsCount(1)
        self.status.SetStatusStyles([wx.SB_SUNKEN])
        self.status.SetMinSize((-1, self.FromDIP(24)))
        self.status.SetStatusText(tr('generator_opening'))
        layout.Add(self.status, 0, wx.EXPAND | wx.ALL, 10)
        layout.Add(self.toolbar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        panel.SetSizer(layout)
        display_index = wx.Display.GetFromWindow(owner)
        area = wx.Display(max(0, display_index)).GetClientArea()
        half = area.width // 2
        self.SetPosition((area.x, area.y))
        self._layout_settings = load_settings()
        restore_control_geometry(self, 'document_generator', (half, area.height),
                                 (min(620, half), min(420, area.height)), settings=self._layout_settings)
        if wx.Display.GetFromWindow(self) == wx.NOT_FOUND:
            self.SetPosition((area.x, area.y))
        area = wx.Display(max(0, wx.Display.GetFromWindow(self))).GetClientArea()
        half = area.width // 2
        self.word_rectangle = self._restore_word_geometry(
            (area.x + half, area.y, area.width - half, area.height))
        self._geometry = {}
        self._word_hwnd = None
        self._word_geometry_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda event: self._remember_word_geometry(), self._word_geometry_timer)
        self._splitter_restored = False
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.splitter.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGED, self.on_sash_changed)
        self._remember_geometry()
        self.Bind(wx.EVT_MOVE, self.on_geometry)
        self.Bind(wx.EVT_SIZE, self.on_geometry)
        self.add.Bind(wx.EVT_BUTTON, lambda event: self._perform(lambda session: session.add_selection()))
        self.add_table.Bind(wx.EVT_BUTTON, self.on_add_table)
        self.add_row.Bind(wx.EVT_BUTTON, self.on_add_row)
        self.save.Bind(wx.EVT_BUTTON, self.on_save)
        self.export.Bind(wx.EVT_BUTTON, self.on_export)
        self.exit.Bind(wx.EVT_BUTTON, lambda event: self.Close())
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        self.worker = GeneratorWorker(path, wx.CallAfter)
        self._open_document()

    def _open_document(self):
        self._set_busy(True)
        self.status.SetStatusText(tr('generator_opening'))
        def open_session(session):
            session.open()
            return session.state()
        self.worker.submit(open_session, self._opened)

    def _section_header(self, panel, title_key, instructions_key):
        header = wx.BoxSizer(wx.HORIZONTAL)
        title = wx.StaticText(panel, label=tr(title_key))
        title.SetFont(title.GetFont().Bold())
        header.Add(title, 0, wx.ALIGN_CENTER_VERTICAL)
        header.AddStretchSpacer()
        info = wx.BitmapButton(panel, bitmap=wx.ArtProvider.GetBitmap(
            wx.ART_INFORMATION, wx.ART_BUTTON, (20, 20)))
        info.SetToolTip(tr(instructions_key))
        info.SetName(tr(title_key))
        info.Bind(wx.EVT_BUTTON, lambda event: self.show_instructions(event, instructions_key))
        header.Add(info, 0, wx.ALIGN_CENTER_VERTICAL)
        return header, info

    def on_show(self, event):
        if event.IsShown() and not self._splitter_restored:
            wx.CallAfter(self.restore_splitter)
        event.Skip()

    def restore_splitter(self):
        if not self or self.closing or self._splitter_restored:
            return
        height = self.splitter.GetClientSize().height
        minimum = self.splitter.GetMinimumPaneSize()
        position = self._layout_settings.get('document_generator_sash_position', height // 2)
        if not isinstance(position, int):
            position = height // 2
        self.splitter.SetSashPosition(max(minimum, min(position, height - minimum)))
        self._splitter_restored = True
        self._geometry['document_generator_sash_position'] = self.splitter.GetSashPosition()

    def on_sash_changed(self, event):
        if self._splitter_restored:
            self._geometry['document_generator_sash_position'] = self.splitter.GetSashPosition()
        event.Skip()

    def _remember_geometry(self):
        if not self.IsIconized() and not self.IsMaximized():
            position, size = self.GetPosition(), self.GetSize()
            self._geometry.update({
                'document_generator_position': [position.x, position.y],
                'document_generator_size': [size.width, size.height],
            })

    def _restore_word_geometry(self, default):
        position = self._layout_settings.get('document_generator_word_position')
        size = self._layout_settings.get('document_generator_word_size')
        if any(not isinstance(value, (list, tuple)) or len(value) != 2 or
               any(type(number) is not int for number in value) for value in (position, size)):
            return default
        x, y = position
        width, height = size
        if width < 240 or height < 160:
            return default
        # Require a visible title bar, then fit the saved bounds to that screen.
        screen = wx.Display.GetFromPoint((x + min(width // 2, 100), y + 10))
        if screen == wx.NOT_FOUND:
            return default
        area = wx.Display(screen).GetClientArea()
        width, height = min(width, area.width), min(height, area.height)
        return (max(area.x, min(x, area.x + area.width - width)),
                max(area.y, min(y, area.y + area.height - height)), width, height)

    def _remember_word_geometry(self):
        # Read the native handle without COM, so this also works while Word is
        # busy. Skip generator operations: closing restores Word's old bounds.
        if not self._word_hwnd or self.busy or self.closing:
            return
        try:
            import win32con
            import win32gui
            if (not win32gui.IsWindow(self._word_hwnd) or
                    win32gui.IsIconic(self._word_hwnd) or
                    win32gui.GetWindowPlacement(self._word_hwnd)[1] == win32con.SW_SHOWMAXIMIZED):
                return
            left, top, right, bottom = win32gui.GetWindowRect(self._word_hwnd)
            if right - left >= 240 and bottom - top >= 160:
                self._geometry.update({
                    'document_generator_word_position': [left, top],
                    'document_generator_word_size': [right - left, bottom - top],
                })
        except Exception:
            # Word may have closed between the native window queries.
            logging.getLogger(__name__).debug('Cannot read Word window geometry', exc_info=True)

    def on_geometry(self, event):
        self._remember_geometry()
        event.Skip()

    def _set_busy(self, busy):
        self.busy = busy
        connected = not busy and not self._disconnected
        self.add.Enable(connected)
        self.add_table.Enable(connected)
        self.add_row.Enable(connected and bool(self.table_fields))
        self.save.Enable(connected)
        self.export.Enable(connected)
        self.exit.Enable(not busy)
        self.scroller.Enable(not busy)
        self.table_scroller.Enable(not busy)

    def _opened(self, state, error):
        if not self or self.closing:
            return
        if error:
            if self._handle_disconnect(error):
                return
            self._set_busy(False)
            self._prompting = True
            try:
                choice = show_generator_message(
                    self, tr('generator_open_unavailable', path=self.path, error=error), retry=True)
            finally:
                self._prompting = False
            if choice == wx.ID_OK:
                self._open_document()
            else:
                self.Destroy()
            return
        self.ready = True
        self.status.SetStatusText('')
        self._render(state['rows'])
        self._render_tables(state['tables'])
        # The frame has now been shown and populated, so its creation will no
        # longer steal focus back from Word after arranging the two windows.
        def arranged(result, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error:
                self._error(error)
            elif result:
                self._word_hwnd = result
                self._remember_word_geometry()
                self._word_geometry_timer.Start(500)
                # This GUI thread owns the newly activated form. Request focus
                # here as well, since Windows can deny a background COM thread.
                try:
                    import win32gui
                    win32gui.SetForegroundWindow(result)
                except Exception:
                    logging.getLogger(__name__).debug('Windows declined Word focus', exc_info=True)
        self.worker.submit(lambda session: session.arrange_window(self.word_rectangle), arranged)

    def _error(self, error):
        if not self._handle_disconnect(error):
            show_generator_message(self, tr('generator_failed', error=error))

    def _handle_disconnect(self, error):
        if not isinstance(error, WordDisconnected):
            return False
        self._disconnected = True
        self._set_busy(False)
        self.status.SetStatusText(str(error))
        return True

    def show_instructions(self, event, instructions_key='generator_instructions'):
        popup = wx.PopupTransientWindow(self, wx.BORDER_SIMPLE)
        panel = wx.Panel(popup)
        label = wx.StaticText(panel, label=tr(instructions_key))
        label.Wrap(480)
        content = wx.BoxSizer(wx.VERTICAL)
        content.Add(label, 0, wx.ALL, 12)
        panel.SetSizerAndFit(content)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel)
        popup.SetSizerAndFit(outer)
        button = event.GetEventObject()
        popup.Position(button.ClientToScreen((0, 0)), button.GetSize())
        popup.Popup()

    def _render(self, rows):
        expanded = {name.GetValue() for (name, value), check in zip(self.fields, self.expand_checks)
                    if check.IsChecked()}
        self.rows = rows
        self.fields = []
        self.expand_checks = []
        self.grid.Clear(delete_windows=True)
        name_width = self.scroller.GetTextExtent('bookmark' + str(max(1, len(rows))))[0] + self.FromDIP(24)
        for column, label in enumerate(('', '№', tr('generator_bookmark'), tr('generator_value'), '')):
            header = wx.StaticText(self.scroller, label=label)
            if column == 2:
                header.Wrap(name_width)
                header.SetMinSize((name_width, -1))
            self.grid.Add(header, 0, wx.ALIGN_CENTER_VERTICAL)
        for index, row in enumerate(rows):
            delete = wx.Button(self.scroller, label='×', style=wx.BU_EXACTFIT)
            delete.SetToolTip(tr('generator_delete_row'))
            delete.Bind(wx.EVT_BUTTON, lambda event, i=index: self._perform(
                lambda session: session.delete_row(i)))
            name = wx.TextCtrl(self.scroller, value=row['name'], size=(name_width, -1))
            name.SetMaxLength(40)
            check = wx.CheckBox(self.scroller, label=tr('generator_expand'))
            check.SetValue(row['name'] in expanded)
            check.Bind(wx.EVT_CHECKBOX, lambda event, i=index: self.on_expand(i))
            row_height = max(name.GetBestSize().height, delete.GetBestSize().height,
                             check.GetBestSize().height)
            name.SetMinSize((name_width, row_height))
            delete.SetMinSize((row_height, row_height))
            delete.SetSize((row_height, row_height))
            value = self._create_value(row['value'], check.IsChecked(), row_height)
            name.Bind(wx.EVT_KILL_FOCUS, self.on_field_blur)
            self.fields.append((name, value))
            self.expand_checks.append(check)
            self.grid.Add(delete, 0)
            self.grid.Add(wx.StaticText(self.scroller, label=str(index + 1)), 0,
                          wx.ALIGN_CENTER_VERTICAL)
            self.grid.Add(name, 0, wx.ALIGN_TOP)
            self.grid.Add(value, 1, wx.EXPAND)
            self.grid.Add(check, 0, wx.ALIGN_TOP)
        self.scroller.Layout()
        self.scroller.FitInside()

    def _create_value(self, text, expanded, row_height):
        # A single-line native control can strip newlines. Keep the original
        # text behind its compact preview until the user actually edits it.
        display = text if expanded else text.replace('\r\n', '\n').replace('\r', '\n').replace('\n', ' ↵ ')
        value = wx.TextCtrl(self.scroller, value=display,
                            size=(-1, row_height * (3 if expanded else 1)),
                            style=wx.TE_MULTILINE if expanded else 0)
        value._generator_original = text
        value._generator_display = value.GetValue()
        value.Bind(wx.EVT_KILL_FOCUS, self.on_field_blur)
        return value

    @staticmethod
    def _value_text(value):
        text = value.GetValue()
        if not value.IsMultiLine() and text == value._generator_display:
            return value._generator_original
        return text

    def on_expand(self, index):
        name, old = self.fields[index]
        value = self._create_value(self._value_text(old), self.expand_checks[index].IsChecked(),
                                   name.GetMinSize().height)
        self.grid.Replace(old, value)
        self.fields[index] = (name, value)
        old.Destroy()
        self.scroller.Layout()
        self.scroller.FitInside()

    def _values(self):
        return [{'name': name.GetValue(), 'value': self._value_text(value)} for name, value in self.fields]

    def _table_values(self):
        values = []
        for name, grid in self.table_fields:
            if grid.IsCellEditControlShown():
                grid.SaveEditControlValue()
            values.append({'name': name.GetValue(), 'rows': [
                [grid.GetCellValue(row, col) for col in range(grid.GetNumberCols())]
                for row in range(grid.GetNumberRows())]})
        return values

    def _finish_table_editing(self):
        for name, grid in self.table_fields:
            if grid.IsCellEditControlEnabled():
                grid.SaveEditControlValue()
                grid.HideCellEditControl()
                grid.DisableCellEditControl()

    def _render_tables(self, tables):
        self._finish_table_editing()
        self.tables = tables
        self.table_fields = []
        self.table_list.Clear(delete_windows=True)
        for index, item in enumerate(tables):
            card = wx.Panel(self.table_scroller)
            layout = wx.BoxSizer(wx.VERTICAL)
            heading = wx.BoxSizer(wx.HORIZONTAL)
            heading.Add(wx.StaticText(card, label=tr('generator_table_bookmark')), 0,
                        wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
            name = wx.TextCtrl(card, value=item['name'], size=(160, -1))
            name.SetMaxLength(40)
            name.Bind(wx.EVT_KILL_FOCUS, self.on_field_blur)
            name.Bind(wx.EVT_SET_FOCUS, lambda event, i=index: self._select_table(event, i))
            heading.Add(name, 1)
            remove = wx.Button(card, label='×', style=wx.BU_EXACTFIT)
            remove.SetToolTip(tr('generator_delete_table'))
            remove.Bind(wx.EVT_BUTTON, lambda event, i=index: self._perform(
                lambda session: session.delete_table(i)))
            heading.Add(remove, 0, wx.LEFT, 8)
            layout.Add(heading, 0, wx.EXPAND | wx.BOTTOM, 6)
            grid = gridlib.Grid(card)
            grid.CreateGrid(len(item['rows']), len(item['widths']))
            grid.SetRowLabelSize(self.FromDIP(36))
            grid.SetColLabelSize(0)
            grid.SetDefaultEditor(gridlib.GridCellAutoWrapStringEditor())
            grid.SetDefaultRenderer(gridlib.GridCellAutoWrapStringRenderer())
            for row, cells in enumerate(item['rows']):
                for column, text in enumerate(cells):
                    grid.SetCellValue(row, column, text)
            self._size_table_height(grid)
            grid.Bind(gridlib.EVT_GRID_SELECT_CELL, lambda event, i=index: self._select_table(event, i))
            grid.Bind(gridlib.EVT_GRID_CELL_CHANGED, self.on_field_blur)
            grid.Bind(wx.EVT_SIZE, lambda event, g=grid, widths=item['widths']: self._size_table_columns(event, g, widths))
            layout.Add(grid, 0, wx.EXPAND)
            card.SetSizer(layout)
            self.table_list.Add(card, 0, wx.EXPAND | wx.BOTTOM, 12)
            self.table_fields.append((name, grid))
        self.active_table = min(self.active_table or 0, len(tables) - 1) if tables else None
        self.add_row.Enable(not self.busy and bool(tables))
        self.table_scroller.Layout()
        self.table_scroller.FitInside()

    def _size_table_height(self, grid):
        # Reserve scrollbar space even before layout determines horizontal
        # overflow, so a new one-row table always shows the whole row.
        scrollbar_height = wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y, grid)
        if scrollbar_height < 0:
            scrollbar_height = self.FromDIP(17)
        rows_height = sum(grid.GetRowSize(row) for row in range(grid.GetNumberRows()))
        height = min(self.FromDIP(230), rows_height + grid.GetColLabelSize() +
                     scrollbar_height + self.FromDIP(6))
        grid.SetMinSize((1, height))

    def _size_table_columns(self, event, grid, widths):
        available = max(1, grid.GetClientSize().width - grid.GetRowLabelSize() - self.FromDIP(20))
        for column, width in enumerate(widths):
            target = max(self.FromDIP(50), round(available * width / sum(widths)))
            if grid.GetColSize(column) != target:
                grid.SetColSize(column, target)
        event.Skip()

    def _select_table(self, event, index):
        self.active_table = index
        event.Skip()

    def on_add_table(self, event):
        self.active_table = len(self.table_fields)
        self._perform(lambda session: session.add_table_selection())

    def on_add_row(self, event):
        if self.busy or not self.table_fields:
            return
        index = min(self.active_table if self.active_table is not None else len(self.table_fields) - 1,
                    len(self.table_fields) - 1)
        self.active_table = index
        grid = self.table_fields[index][1]
        self._finish_table_editing()
        grid.AppendRows(1)
        self._size_table_height(grid)
        self.table_scroller.Layout()
        self.table_scroller.FitInside()
        grid.SetGridCursor(grid.GetNumberRows() - 1, 0)
        grid.MakeCellVisible(grid.GetNumberRows() - 1, 0)
        grid.SetFocus()
        self._commit_fields()

    def on_field_blur(self, event):
        event.Skip()
        wx.CallAfter(self._commit_fields)

    def _commit_fields(self):
        if not self or self.closing or self.busy or self._prompting or not self.ready or self._disconnected:
            return
        values = self._values()
        tables = self._table_values()
        current_tables = [{'name': table['name'], 'rows': table['rows']} for table in self.tables]
        if values == self.rows and tables == current_tables:
            return

        def finished(result, error):
            if not self or self.closing:
                return
            if error:
                if self._handle_disconnect(error):
                    return
                # Keep invalid input available to correct; toolbar operations
                # validate it again before changing the document.
                self.status.SetStatusText(error)
            else:
                self.rows = values
                for table, value in zip(self.tables, tables):
                    table.update(value)
                self.status.SetStatusText('')
        self.worker.submit(lambda session: session.update_fields(values, tables), finished)

    def _perform(self, action, message='', close=False, saved=False):
        if self.busy or self.closing or self._disconnected:
            return
        if close:
            self._remember_word_geometry()
        values = self._values()
        tables = self._table_values()
        self._finish_table_editing()
        self._set_busy(True)

        def work(session):
            session.update_fields(values, tables)
            action(session)
            if close:
                session.close_document()
            return session.state()

        def finished(state, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error:
                self._error(error)
            else:
                if saved:
                    self.saved_rows = state['rows']
                    self.saved_tables = [{'name': table['name'], 'rows': table['rows']} for table in state['tables']]
                if close:
                    self.Destroy()
                    return
                self._render(state['rows'])
                self._render_tables(state['tables'])
                self.status.SetStatusText(message)
                if message and self.owner and not getattr(self.owner, '_closing_workspace', False):
                    self.owner.refresh_current_folder_preserving_context()
        self.worker.submit(work, finished)

    def on_save(self, event):
        self._save_document()

    def _save_document(self, close=False):
        self._perform(lambda session: session.save_document(),
                      tr('generator_saved', path=self.path), close=close, saved=True)

    def on_export(self, event):
        extension = os.path.splitext(self.path)[1].lower()
        with wx.FileDialog(self, tr('generator_save_title'),
                           defaultDir=os.path.dirname(self.path),
                           defaultFile=os.path.splitext(os.path.basename(self.path))[0] + '_result' + extension,
                           wildcard=f'Word (*{extension})|*{extension}',
                           style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as dialog:
            if dialog.ShowModal() != wx.ID_OK:
                return
            target = dialog.GetPath()
        self._perform(lambda session: session.export_document(target),
                      tr('generator_saved', path=target), saved=True)

    def on_close(self, event):
        self._remember_word_geometry()
        self._finish_table_editing()
        if not event.CanVeto():
            event.Skip()
        elif self.busy or self._prompting:
            event.Veto()
        elif not self.ready or self._disconnected:
            self.Destroy()
        else:
            event.Veto()
            self._set_busy(True)
            self.worker.submit(lambda session: session.needs_save(), self._confirm_close)

    def _confirm_close(self, word_dirty, error):
        if not self or self.closing:
            return
        self._set_busy(False)
        if error:
            if self._handle_disconnect(error):
                self.Destroy()
            else:
                self._error(error)
            return
        if self.saved_rows != self._values() or self.saved_tables != self._table_values() or word_dirty:
            self._prompting = True
            try:
                with wx.MessageDialog(self, tr('generator_confirm_save'), tr('generator_title'),
                                      wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION) as dialog:
                    dialog.SetYesNoCancelLabels(tr('confirm_yes'), tr('confirm_no'), tr('cancel_button'))
                    choice = dialog.ShowModal()
                if choice == wx.ID_CANCEL:
                    return
                if choice == wx.ID_YES:
                    self._save_document(close=True)
                    return
            finally:
                self._prompting = False
        # No means discard unsaved changes, including invalid field edits. Do
        # not validate/commit those fields on the way out.
        self._remember_word_geometry()
        self._set_busy(True)

        def finished(result, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error and not self._handle_disconnect(error):
                self._error(error)
            else:
                self.Destroy()
        self.worker.submit(lambda session: session.close_document(), finished)

    def on_destroy(self, event):
        if event.GetId() == self._window_id and not self.closing:
            self._word_geometry_timer.Stop()
            self.closing = True
            if self._splitter_restored:
                self._geometry['document_generator_sash_position'] = self.splitter.GetSashPosition()
            update_settings(self._geometry)
            self.worker.close()
            if self.owner:
                windows = getattr(self.owner, '_document_generators', {})
                windows.pop(os.path.normcase(os.path.abspath(self.path)), None)
        event.Skip()
