"""Mass filename renaming dialog with a preview that must be searched again after edits."""
import os
import re
import wx
from localization import tr
from file_operations import batch_rename
from common.window_tools import load_settings, update_settings, restore_control_geometry, save_control_geometry


class RenameBlockedDialog(wx.Dialog):
    def __init__(self, parent, entry, error):
        super().__init__(parent, title=tr('rename_blocked_title'),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.action = 'cancel'
        layout = wx.BoxSizer(wx.VERTICAL)
        message = wx.StaticText(self, label=tr('rename_blocked_message',
                                               source=entry.source, target=entry.target))
        message.Wrap(620)
        layout.Add(message, 0, wx.EXPAND | wx.ALL, 12)
        detail = tr(error.key) + '\n' + error.detail if isinstance(error, batch_rename.RenameError) else str(error)
        details = wx.TextCtrl(self, value=detail, size=(620, 85),
                              style=wx.TE_MULTILINE | wx.TE_READONLY)
        layout.Add(details, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer()
        for action in ('retry', 'skip', 'skip_all', 'cancel'):
            button = wx.Button(self, wx.ID_CANCEL if action == 'cancel' else wx.ID_ANY,
                               tr('rename_blocked_' + action))
            button.Bind(wx.EVT_BUTTON, lambda event, choice=action: self.choose(choice))
            buttons.Add(button, 0, wx.LEFT, 8)
            if action == 'retry':
                button.SetDefault()
        layout.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        self.SetSizerAndFit(layout)
        self.SetMinSize(self.GetSize())
        self.CentreOnParent()

    def choose(self, action):
        self.action = action
        self.EndModal(wx.ID_CANCEL if action == 'cancel' else wx.ID_OK)


class RenameFilesDialog(wx.Dialog):
    def __init__(self, owner, folder):
        super().__init__(owner, title=tr('rename_files'), size=(920, 600),
                         style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.owner = owner
        self._closing = False
        self.entries = []
        self.changed = False
        panel = wx.Panel(self)
        layout = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)
        self.folder = wx.TextCtrl(panel, value=folder)
        browse = wx.Button(panel, label=tr('search_browse_button'))
        folder_row = wx.BoxSizer(wx.HORIZONTAL)
        folder_row.Add(self.folder, 1, wx.RIGHT, 6)
        folder_row.Add(browse)
        self.mask = wx.TextCtrl(panel, value='*', size=(140, -1))
        folder_row.Add(wx.StaticText(panel, label=tr('search_file_mask_label')), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 8)
        folder_row.Add(self.mask, 0)
        grid.Add(wx.StaticText(panel, label=tr('search_folder_label')), 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(folder_row, 1, wx.EXPAND)
        self.recursive = wx.CheckBox(panel, label=tr('search_include_subfolders'))
        grid.Add((1, 1))
        grid.Add(self.recursive)
        self.pattern = wx.TextCtrl(panel)
        self.replacement = wx.TextCtrl(panel)
        layout.Add(grid, 0, wx.EXPAND | wx.ALL, 12)
        expressions = wx.BoxSizer(wx.HORIZONTAL)
        for key, field in [('rename_find_regex', self.pattern), ('rename_replace_regex', self.replacement)]:
            column = wx.BoxSizer(wx.VERTICAL)
            column.Add(wx.StaticText(panel, label=tr(key)), 0, wx.BOTTOM, 4)
            column.Add(field, 0, wx.EXPAND)
            expressions.Add(column, 1, wx.LEFT | wx.RIGHT, 6)
        layout.Add(expressions, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        self.splitter = splitter = wx.SplitterWindow(panel, style=wx.SP_LIVE_UPDATE)
        self.before = wx.ListCtrl(splitter, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.after = wx.ListCtrl(splitter, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.before.InsertColumn(0, tr('rename_found_names'), width=400)
        self.after.InsertColumn(0, tr('rename_new_names'), width=400)
        splitter.SetMinimumPaneSize(180)
        splitter.SetSashGravity(0.5)
        splitter.SplitVertically(self.before, self.after)
        layout.Add(splitter, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 12)
        self.status = wx.StaticText(panel)
        layout.Add(self.status, 0, wx.EXPAND | wx.ALL, 12)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer()
        search = wx.Button(panel, label=tr('search_button'))
        self.save = wx.Button(panel, label=tr('preview_save_button'))
        cancel = wx.Button(panel, wx.ID_CANCEL, tr('exit_button'))
        for button in (search, self.save, cancel):
            buttons.Add(button, 0, wx.LEFT, 8)
        layout.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
        panel.SetSizer(layout)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.SetMinSize((720, 420))
        self.save.Disable()
        browse.Bind(wx.EVT_BUTTON, self.on_browse)
        search.Bind(wx.EVT_BUTTON, self.on_search)
        self.save.Bind(wx.EVT_BUTTON, self.on_save)
        for field in (self.folder, self.mask, self.pattern, self.replacement):
            field.Bind(wx.EVT_TEXT, self.invalidate)
        self.recursive.Bind(wx.EVT_CHECKBOX, self.invalidate)
        self.before.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: self.show_path(e, self.after))
        self.after.Bind(wx.EVT_LIST_ITEM_SELECTED, lambda e: self.show_path(e, self.before))
        self.CentreOnParent()
        self._layout_settings = load_settings()
        restore_control_geometry(self, 'rename_files', (920, 600), (720, 420),
                                 settings=self._layout_settings)
        if wx.Display.GetFromWindow(self) == wx.NOT_FOUND:
            self.CentreOnParent()
        self.Bind(wx.EVT_SHOW, self.on_show)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.Bind(wx.EVT_BUTTON, self.on_cancel, id=wx.ID_CANCEL)
        self._splitter_restored = False

    def on_cancel(self, event):
        self.Close()

    def on_close(self, event):
        if self._closing:
            return
        self._closing = True
        self.save_layout()
        if getattr(self.owner, '_rename_files_dialog', None) is self:
            self.owner._rename_files_dialog = None
        self.Destroy()

    def refresh_owner(self):
        if not self.changed or not self.owner:
            return
        refresh = getattr(self.owner, 'refresh_current_folder_preserving_context', None)
        if callable(refresh):
            refresh()
        else:
            from controls.tree_control import refresh_tree_selection_and_filelist
            refresh_tree_selection_and_filelist(self.owner)
        self.changed = False

    def on_show(self, event):
        if event.IsShown() and not self._splitter_restored:
            self._splitter_restored = True
            wx.CallAfter(self.restore_splitter)
        event.Skip()

    def restore_splitter(self):
        if not self or self._closing:
            return
        self.Layout()
        self.splitter.GetParent().Layout()
        width = self.splitter.GetClientSize().width
        position = self._layout_settings.get('rename_files_sash_position', width // 2)
        if not isinstance(position, int):
            position = width // 2
        self.splitter.SetSashPosition(max(180, min(position, width - 180)))

    def save_layout(self):
        save_control_geometry(self, 'rename_files')
        update_settings({'rename_files_sash_position': self.splitter.GetSashPosition()})

    def show_path(self, event, other):
        index = event.GetIndex()
        if index < len(self.entries):
            self.status.SetLabel(self.entries[index].source)
            if not other.IsSelected(index):
                other.Select(index)
                other.EnsureVisible(index)

    def invalidate(self, event=None):
        self.entries = []
        self.save.Disable()
        self.before.DeleteAllItems()
        self.after.DeleteAllItems()
        self.status.SetLabel('')
        if event:
            event.Skip()

    def on_browse(self, event):
        with wx.DirDialog(self, tr('search_folder_label'), defaultPath=self.folder.GetValue(),
                          style=wx.DD_DEFAULT_STYLE | wx.DD_DIR_MUST_EXIST) as dialog:
            if dialog.ShowModal() == wx.ID_OK:
                self.folder.SetValue(dialog.GetPath())

    def error(self, exc):
        if isinstance(exc, batch_rename.RenameError):
            message = tr(exc.key)
            if exc.detail:
                message += '\n' + exc.detail
        elif isinstance(exc, re.error):
            message = tr('rename_regex_error') + '\n' + str(exc)
        else:
            message = tr('rename_io_error') + '\n' + str(exc)
        wx.MessageBox(message, tr('rename_files'), wx.OK | wx.ICON_ERROR, self)

    def on_search(self, event):
        self.invalidate()
        try:
            with wx.BusyCursor():
                self.entries = batch_rename.search(self.folder.GetValue(), self.recursive.GetValue(),
                                                   self.pattern.GetValue(), self.replacement.GetValue(),
                                                   self.mask.GetValue())
                for entry in self.entries:
                    self.before.InsertItem(self.before.GetItemCount(), os.path.basename(entry.source))
                    self.after.InsertItem(self.after.GetItemCount(), os.path.basename(entry.target))
                batch_rename.validate(self.entries)
            self.status.SetLabel(tr('rename_matches', count=len(self.entries)))
            self.save.Enable(any(e.source != e.target for e in self.entries))
        except (ValueError, OSError, IndexError) as exc:
            self.error(exc)

    def on_rename_error(self, entry, error):
        with RenameBlockedDialog(self, entry, error) as dialog:
            dialog.ShowModal()
            return dialog.action

    def on_save(self, event):
        self.save.Disable()
        try:
            # Keep the normal cursor while an error dialog is awaiting a choice.
            self.changed = True
            count = batch_rename.apply(self.entries, on_error=self.on_rename_error)
            self.invalidate()
            self.status.SetLabel(tr('rename_saved', count=count))
        except (ValueError, OSError) as exc:
            self.invalidate()
            self.error(exc)
        finally:
            self.refresh_owner()


def show_rename_files(owner, folder):
    existing = getattr(owner, '_rename_files_dialog', None)
    if existing and not existing._closing:
        existing.Show()
        existing.Raise()
        return existing
    dialog = RenameFilesDialog(owner, folder)
    owner._rename_files_dialog = dialog
    dialog.Show()
    return dialog
