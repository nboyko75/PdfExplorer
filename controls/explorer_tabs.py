"""Compact tab headings; each heading selects a persistent explorer workspace."""
import ntpath
import wx
from file_operations.recycle_bin import RECYCLE_BIN_PATH
from localization import tr


class TabHeading(wx.Panel):
    def __init__(self, parent, host, workspace):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.active = False
        self.host = host
        self.workspace = workspace
        self.SetMinSize(self.FromDIP((180, 28)))
        self.SetMaxSize((-1, self.FromDIP(28)))
        row = wx.BoxSizer(wx.HORIZONTAL)
        self.label = wx.StaticText(self, label='', style=wx.ALIGN_CENTER | wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE)
        self.label.SetMinSize((1, -1))
        row.Add(self.label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, self.FromDIP(6))
        # The close button is inside the heading with no gap or sizer border.
        self.close_button = wx.Button(self, label='×', style=wx.BU_EXACTFIT | wx.BORDER_NONE,
                                      size=self.FromDIP((18, 18)))
        self.close_button.SetMinSize(self.FromDIP((18, 18)))
        self.close_button.Show(len(host.workspaces) > 1)
        self.close_button.SetToolTip(tr('explorer_close_tab') + ' (Ctrl+W)')
        row.Add(self.close_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, self.FromDIP(1))
        self.SetSizer(row)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_LEFT_DOWN, self._select)
        self.label.Bind(wx.EVT_LEFT_DOWN, self._select)
        self.Bind(wx.EVT_MIDDLE_UP, self._close)
        self.label.Bind(wx.EVT_MIDDLE_UP, self._close)
        self.close_button.Bind(wx.EVT_BUTTON, self._close)
        self.update_title()
        self.set_active(False)

    def _select(self, event):
        self.host.activate_tab(self.workspace)

    def _close(self, event):
        wx.CallAfter(self.host.close_tab, self.workspace)

    def update_title(self):
        path = getattr(self.workspace, '_list_folder_path', '')
        if path.lower() == RECYCLE_BIN_PATH.lower():
            title = tr('favorite_shortcut_recycle_bin')
        else:
            title = ntpath.basename(path.rstrip('\\/')) or path or tr('explorer_new_tab')
        self.label.SetLabel(title.replace('&', '&&'))
        self.SetName(title)
        self.SetToolTip(path)
        self.label.SetToolTip(path)
        self.Layout()
        self.Refresh()

    def set_active(self, active):
        self.active = active
        colour = wx.Colour(207, 228, 247) if active else wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE)
        for control in (self, self.label, self.close_button):
            control.SetBackgroundColour(colour)
            control.Refresh()


    def _on_size(self, event):
        self.Refresh()
        event.Skip()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        width, height = self.GetClientSize()
        if width < 2 or height < 2:
            return
        fill = self.GetBackgroundColour()
        border = wx.SystemSettings.GetColour(
            wx.SYS_COLOUR_HIGHLIGHT if self.active else wx.SYS_COLOUR_BTNSHADOW)
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            dc.SetBrush(wx.Brush(fill))
            dc.SetPen(wx.Pen(border))
            dc.DrawRectangle(0, 0, width, height)
            return
        # Only the upper corners are rounded; the bottom meets the toolbar.
        left, top, right, bottom = 0.5, 0.5, width - 0.5, height - 0.5
        radius = min(float(self.FromDIP(6)), (right - left) / 2, (bottom - top) / 2)
        tangent = radius * 0.55228475
        path = gc.CreatePath()
        path.MoveToPoint(left, bottom)
        path.AddLineToPoint(left, top + radius)
        path.AddCurveToPoint(left, top + radius - tangent,
                             left + radius - tangent, top, left + radius, top)
        path.AddLineToPoint(right - radius, top)
        path.AddCurveToPoint(right - radius + tangent, top,
                             right, top + radius - tangent, right, top + radius)
        path.AddLineToPoint(right, bottom)
        path.CloseSubpath()
        gc.SetBrush(wx.Brush(fill))
        gc.SetPen(wx.Pen(border))
        gc.DrawPath(path)


class ExplorerTabs(wx.ScrolledWindow):
    def __init__(self, parent, host):
        super().__init__(parent, style=wx.HSCROLL | wx.BORDER_NONE)
        self.host = host
        self.headings = {}
        self.row = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self.row)
        self.SetScrollRate(20, 0)
        self.ShowScrollbars(wx.SHOW_SB_NEVER, wx.SHOW_SB_NEVER)
        self.SetMinSize((-1, self.FromDIP(28)))
        self.SetMaxSize((-1, self.FromDIP(28)))
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)

    def rebuild(self):
        self.row.Clear(True)
        self.headings = {}
        for workspace in self.host.workspaces:
            heading = TabHeading(self, self.host, workspace)
            self.headings[workspace] = heading
            self.row.Add(heading, 0, wx.EXPAND)
        self.add_button = wx.Button(self, label='+', style=wx.BU_EXACTFIT,
                                    size=self.FromDIP((24, 28)))
        self.add_button.SetMinSize(self.FromDIP((24, 28)))
        self.add_button.SetToolTip(tr('explorer_new_tab') + ' (Ctrl+T)')
        self.add_button.Bind(wx.EVT_BUTTON, lambda event: wx.CallAfter(self.host.add_tab))
        # No expanding spacer: + immediately follows the last heading.
        self.row.Add(self.add_button, 0, wx.EXPAND)
        self.Layout()
        self.FitInside()
        self.mark_active(self.host.active_workspace)

    def mark_active(self, workspace):
        for page, heading in self.headings.items():
            heading.set_active(page is workspace)
        heading = self.headings.get(workspace)
        if heading is not None:
            # wx.ScrolledWindow has no ScrollChildIntoView (it is a
            # wx.lib.scrolledpanel helper), so scroll using logical coordinates.
            left = self.CalcUnscrolledPosition(heading.GetPosition()).x
            width = heading.GetSize().width
            view_start = self.GetViewStart()[0] * 20
            client_width = self.GetClientSize().width
            if left < view_start:
                self.Scroll(max(0, left // 20), 0)
            elif left + width > view_start + client_width:
                self.Scroll(max(0, (left + width - client_width + 19) // 20), 0)

    def location_changed(self, workspace, path):
        heading = self.headings.get(workspace)
        if heading is not None:
            heading.update_title()

    def _on_wheel(self, event):
        x, _ = self.GetViewStart()
        delta = event.GetWheelDelta() or 120
        self.Scroll(max(0, x - int(event.GetWheelRotation() / delta) * 3), 0)
