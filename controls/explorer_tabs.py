"""Folder tabs; the expensive preview controls are shared by all tabs."""
import ntpath
import os
from dataclasses import dataclass, field

import wx
from file_operations.recycle_bin import RECYCLE_BIN_PATH, is_virtual_shell_path
from localization import tr


@dataclass
class FolderTab:
    path: str = ''
    history: list = field(default_factory=list)
    history_index: int = -1
    query: str = ''
    sort_column: object = None
    sort_direction: int = 0
    selection: list = field(default_factory=list)
    top_item: int = 0


class ExplorerTabs(wx.Panel):
    def __init__(self, parent, owner):
        super().__init__(parent)
        self.owner = owner
        self.tabs = [FolderTab()]
        self.active = 0
        self.switching = False
        self.buttons = []
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.strip = wx.ScrolledWindow(self, style=wx.HSCROLL)
        self.strip.SetScrollRate(20, 0)
        self.strip.SetMinSize((-1, self.FromDIP(30)))
        self.strip.ShowScrollbars(wx.SHOW_SB_NEVER, wx.SHOW_SB_NEVER)
        self.strip.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.tab_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.strip.SetSizer(self.tab_sizer)
        row.Add(self.strip, 1, wx.EXPAND)
        self.add_button = wx.Button(self, label='+', size=self.FromDIP((34, 30)))
        self.add_button.SetToolTip(tr('explorer_new_tab') + ' (Ctrl+T)')
        self.add_button.Bind(wx.EVT_BUTTON, lambda event: self.add())
        row.Add(self.add_button, 0, wx.EXPAND)
        self.SetSizer(row)
        self.rebuild()

    def title(self, tab):
        if tab.path.lower() == RECYCLE_BIN_PATH.lower():
            return tr('favorite_shortcut_recycle_bin')
        return ntpath.basename(tab.path.rstrip('\\/')) or tab.path or tr('explorer_new_tab')

    def rebuild(self):
        self.tab_sizer.Clear(True)
        self.buttons = []
        for index, tab in enumerate(self.tabs):
            button = wx.ToggleButton(self.strip, label=self.title(tab).replace('&', '&&'),
                                     size=self.FromDIP((180, 30)))
            button.SetValue(index == self.active)
            button.SetToolTip(tab.path)
            button.Bind(wx.EVT_TOGGLEBUTTON, lambda event, i=index: self.select(i))
            button.Bind(wx.EVT_MIDDLE_UP, lambda event, i=index: self.close(i))
            self.tab_sizer.Add(button, 0, wx.EXPAND)
            self.buttons.append(button)
        self.close_button = wx.Button(self.strip, label='×', size=self.FromDIP((28, 30)))
        self.close_button.SetToolTip(tr('explorer_close_tab') + ' (Ctrl+W)')
        self.close_button.Enable(len(self.tabs) > 1)
        self.close_button.Bind(wx.EVT_BUTTON, lambda event: self.close())
        self.tab_sizer.Add(self.close_button, 0, wx.EXPAND)
        self.strip.FitInside()
        self.Layout()
        self.strip.Scroll(self.active * self.FromDIP(180) // 20, 0)

    def _on_wheel(self, event):
        x, _ = self.strip.GetViewStart()
        delta = event.GetWheelDelta() or 120
        self.strip.Scroll(max(0, x - int(event.GetWheelRotation() / delta) * 3), 0)

    def location_changed(self, path):
        if self.switching:
            return
        tab = self.tabs[self.active]
        tab.path = path
        button = self.buttons[self.active]
        button.SetLabel(self.title(tab).replace('&', '&&'))
        button.SetToolTip(path)

    def capture(self):
        owner = self.owner
        tab = self.tabs[self.active]
        tab.path = getattr(owner, '_list_folder_path', '') or owner.path_box.GetValue()
        tab.history = list(owner.history)
        tab.history_index = owner.history_index
        tab.query = owner.search_box.GetValue()
        tab.sort_column = owner.list_sort_column
        tab.sort_direction = owner.list_sort_direction
        tab.selection = []
        item = owner.list.GetFirstSelected()
        while item != -1:
            path = owner._list_item_paths.get(item)
            if path:
                tab.selection.append(path)
            item = owner.list.GetNextSelected(item)
        tab.top_item = owner.list.GetTopItem()

    def select(self, index):
        if index == self.active:
            self.buttons[index].SetValue(True)
            return True
        owner = self.owner
        target = self.tabs[index]
        path = target.path
        if not path or (not is_virtual_shell_path(path) and not os.path.isdir(path)):
            wx.MessageBox(tr('explorer_folder_unavailable', path=path), tr('app_title'), wx.OK | wx.ICON_WARNING)
            self.rebuild()
            return False
        if not owner.confirm_preview_change(path):
            self.rebuild()
            return False
        self.capture()
        previous = self.active
        self.switching = True
        owner.Freeze()
        try:
            owner.search_box.ChangeValue(target.query)
            owner.list_sort_column = target.sort_column
            owner.list_sort_direction = target.sort_direction
            if not owner.open_path(path, add_history=False):
                self.restore_state(self.tabs[previous])
                return False
            self.active = index
            owner.history = list(target.history) or [path]
            owner.history_index = target.history_index if target.history else 0
            owner.show_file_preview(path)
            owner._restoring_list_selection = True
            try:
                for row, item_path in owner._list_item_paths.items():
                    if item_path in target.selection:
                        owner.list.SetItemState(row, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
            finally:
                owner._restoring_list_selection = False
            if owner.list.GetItemCount():
                owner.list.EnsureVisible(min(target.top_item, owner.list.GetItemCount() - 1))
            owner._update_main_menu_state()
            return True
        except OSError as exc:
            self.active = previous
            self.restore_state(self.tabs[previous])
            wx.MessageBox(str(exc), tr('app_title'), wx.OK | wx.ICON_WARNING)
            return False
        finally:
            self.switching = False
            owner.Thaw()
            self.rebuild()

    def restore_state(self, tab):
        owner = self.owner
        owner.search_box.ChangeValue(tab.query)
        owner.list_sort_column = tab.sort_column
        owner.list_sort_direction = tab.sort_direction
        owner.history = list(tab.history)
        owner.history_index = tab.history_index
        try:
            owner.open_path(tab.path, add_history=False)
        except OSError:
            pass

    def add(self):
        path = getattr(self.owner, '_list_folder_path', '') or os.path.expanduser('~')
        self.tabs.append(FolderTab(path=path))
        if not self.select(len(self.tabs) - 1):
            self.tabs.pop()
            self.rebuild()

    def close(self, index=None):
        index = self.active if index is None else index
        if len(self.tabs) == 1:
            return
        if index == self.active:
            if not self.select(index - 1 if index else 1):
                return
        del self.tabs[index]
        if index < self.active:
            self.active -= 1
        self.rebuild()

    def cycle(self, backwards=False):
        self.select((self.active + (-1 if backwards else 1)) % len(self.tabs))
