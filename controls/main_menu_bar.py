"""Client-area menu row so folder tabs can sit above the main menu."""
import wx


class MainMenuBar(wx.Panel):
    def __init__(self, parent, owner):
        super().__init__(parent)
        self.owner = owner
        self.entries = []
        self.row = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.row)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

    def Append(self, menu, title):
        button = wx.Button(self, label=title, style=wx.BU_EXACTFIT | wx.BORDER_NONE)
        button.Bind(wx.EVT_BUTTON, lambda event: self.open_menu(menu, button))
        button.Bind(wx.EVT_KEY_DOWN, self._on_key)
        self.entries.append((menu, button))
        self.row.Add(button, 0, wx.EXPAND)
        self.Layout()
        return True

    def SetMenuLabel(self, index, title):
        self.entries[index][1].SetLabel(title)
        self.Layout()

    def open_menu(self, menu, button):
        self.owner._update_main_menu_state()
        # Show on the frame: existing EVT_MENU handlers are bound there.
        position = self.owner.ScreenToClient(button.ClientToScreen((0, button.GetSize().height)))
        self.owner.PopupMenu(menu, position)

    def focus_first(self):
        if self.entries:
            self.entries[0][1].SetFocus()

    def _on_key(self, event):
        buttons = [button for _, button in self.entries]
        focused = wx.Window.FindFocus()
        key = event.GetKeyCode()
        if focused in buttons and key in (wx.WXK_LEFT, wx.WXK_RIGHT):
            delta = -1 if key == wx.WXK_LEFT else 1
            buttons[(buttons.index(focused) + delta) % len(buttons)].SetFocus()
        elif focused in buttons and key == wx.WXK_DOWN:
            index = buttons.index(focused)
            self.open_menu(*self.entries[index])
        else:
            event.Skip()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            for menu, _ in self.entries:
                menu.Destroy()
            self.entries.clear()
        event.Skip()
