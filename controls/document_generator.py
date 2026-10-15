"""Native, modeless editor for Word document generator fields."""
import os
import logging

import wx

from file_operations.document_generator import GeneratorWorker
from common.window_tools import restore_control_geometry, update_settings
from localization import tr


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
        self.busy = False
        self.closing = False
        self.ready = False
        self.saved_rows = None
        self._prompting = False
        panel = self.panel = wx.Panel(self)
        layout = wx.BoxSizer(wx.VERTICAL)
        self.toolbar = wx.BoxSizer(wx.HORIZONTAL)
        self.toolbar.AddStretchSpacer()
        self.add = wx.Button(panel, label=tr('generator_add'))
        self.save = wx.Button(panel, label=tr('preview_save_button'))
        self.exit = wx.Button(panel, label=tr('exit_button'))
        for button in (self.add, self.save, self.exit):
            self.toolbar.Add(button, 0, wx.LEFT, 8)
        self.scroller = wx.ScrolledWindow(panel, style=wx.VSCROLL)
        self.scroller.SetScrollRate(0, 16)
        self.grid = wx.FlexGridSizer(cols=5, vgap=8, hgap=8)
        self.grid.AddGrowableCol(3, 1)
        self.scroller.SetSizer(self.grid)
        layout.Add(self.scroller, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)
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
        restore_control_geometry(self, 'document_generator', (half, area.height),
                                 (min(620, half), min(300, area.height)))
        if wx.Display.GetFromWindow(self) == wx.NOT_FOUND:
            self.SetPosition((area.x, area.y))
        area = wx.Display(max(0, wx.Display.GetFromWindow(self))).GetClientArea()
        half = area.width // 2
        self.word_rectangle = (area.x + half, area.y, area.width - half, area.height)
        self._geometry = {}
        self._remember_geometry()
        self.Bind(wx.EVT_MOVE, self.on_geometry)
        self.Bind(wx.EVT_SIZE, self.on_geometry)
        self.add.Bind(wx.EVT_BUTTON, lambda event: self._perform(lambda session: session.add_selection()))
        self.save.Bind(wx.EVT_BUTTON, self.on_save)
        self.exit.Bind(wx.EVT_BUTTON, lambda event: self.Close())
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        self.worker = GeneratorWorker(path, wx.CallAfter)
        self._set_busy(True)
        self.worker.submit(lambda session: session.open(), self._opened)

    def _remember_geometry(self):
        if not self.IsIconized() and not self.IsMaximized():
            position, size = self.GetPosition(), self.GetSize()
            self._geometry = {
                'document_generator_position': [position.x, position.y],
                'document_generator_size': [size.width, size.height],
            }

    def on_geometry(self, event):
        self._remember_geometry()
        event.Skip()

    def _set_busy(self, busy):
        self.busy = busy
        self.add.Enable(not busy)
        self.save.Enable(not busy)
        self.exit.Enable(not busy)
        self.scroller.Enable(not busy)

    def _opened(self, rows, error):
        if not self or self.closing:
            return
        if error:
            self._set_busy(False)
            self._error(error)
            self.Destroy()
            return
        self.ready = True
        self.status.SetStatusText('')
        self._render(rows)
        # The frame has now been shown and populated, so its creation will no
        # longer steal focus back from Word after arranging the two windows.
        def arranged(result, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error:
                self._error(error)
            elif result:
                # This GUI thread owns the newly activated form. Request focus
                # here as well, since Windows can deny a background COM thread.
                try:
                    import win32gui
                    win32gui.SetForegroundWindow(result)
                except Exception:
                    logging.getLogger(__name__).debug('Windows declined Word focus', exc_info=True)
        self.worker.submit(lambda session: session.arrange_window(self.word_rectangle), arranged)

    def _error(self, error):
        wx.MessageBox(tr('generator_failed', error=error), tr('generator_title'),
                      wx.OK | wx.ICON_ERROR, self)

    def show_instructions(self, event):
        popup = wx.PopupTransientWindow(self, wx.BORDER_SIMPLE)
        panel = wx.Panel(popup)
        label = wx.StaticText(panel, label=tr('generator_instructions'))
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
            if column == 4:
                self.info = wx.BitmapButton(self.scroller, bitmap=wx.ArtProvider.GetBitmap(
                    wx.ART_INFORMATION, wx.ART_BUTTON, (20, 20)))
                self.info.SetToolTip(tr('generator_instructions'))
                self.info.SetName(tr('menu_help'))
                self.info.Bind(wx.EVT_BUTTON, self.show_instructions)
                self.grid.Add(self.info, 0, wx.ALIGN_RIGHT | wx.ALIGN_CENTER_VERTICAL)
                continue
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

    def on_field_blur(self, event):
        event.Skip()
        wx.CallAfter(self._commit_fields)

    def _commit_fields(self):
        if not self or self.closing or self.busy or self._prompting or not self.ready:
            return
        values = self._values()
        if values == self.rows:
            return

        def finished(result, error):
            if not self or self.closing:
                return
            if error:
                # Keep invalid input available to correct; toolbar operations
                # validate it again before changing the document.
                self.status.SetStatusText(error)
            else:
                self.rows = values
                self.status.SetStatusText('')
        self.worker.submit(lambda session: session.update_rows(values), finished)

    def _perform(self, action, message='', close=False, saved=False):
        if self.busy or self.closing:
            return
        values = self._values()
        self._set_busy(True)

        def work(session):
            session.update_rows(values)
            action(session)
            if close:
                session.close_document()
            return session.snapshot()

        def finished(rows, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error:
                self._error(error)
            else:
                if saved:
                    self.saved_rows = [dict(row) for row in rows]
                if close:
                    self.Destroy()
                    return
                self._render(rows)
                self.status.SetStatusText(message)
                if message and self.owner and not getattr(self.owner, '_closing_workspace', False):
                    self.owner.refresh_current_folder_preserving_context()
        self.worker.submit(work, finished)

    def on_save(self, event):
        self._save_document()

    def _save_document(self, close=False):
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
                      tr('generator_saved', path=target), close=close, saved=True)

    def on_close(self, event):
        if not event.CanVeto():
            event.Skip()
        elif self.busy or self._prompting:
            event.Veto()
        elif not self.ready:
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
            self._error(error)
            return
        if self.saved_rows != self._values() or word_dirty:
            self._prompting = True
            try:
                choice = wx.MessageBox(tr('generator_confirm_save'), tr('generator_title'),
                                       wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION, self)
                if choice == wx.CANCEL:
                    return
                if choice == wx.YES:
                    self._save_document(close=True)
                    return
            finally:
                self._prompting = False
        # No means discard unsaved changes, including invalid field edits. Do
        # not validate/commit those fields on the way out.
        self._set_busy(True)

        def finished(result, error):
            if not self or self.closing:
                return
            self._set_busy(False)
            if error:
                self._error(error)
            else:
                self.Destroy()
        self.worker.submit(lambda session: session.close_document(), finished)

    def on_destroy(self, event):
        if event.GetId() == self._window_id and not self.closing:
            self.closing = True
            update_settings(self._geometry)
            self.worker.close()
            if self.owner:
                windows = getattr(self.owner, '_document_generators', {})
                windows.pop(os.path.normcase(os.path.abspath(self.path)), None)
        event.Skip()
