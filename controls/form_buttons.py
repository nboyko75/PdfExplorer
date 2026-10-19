"""Shared rounded blue text buttons, with native controls for short labels."""
import wx
from wx.lib.buttons import GenButton


class RoundedButton(GenButton):
    """Paint the text actions consistently instead of using themed MSW borders."""

    def __init__(self, parent, **kwargs):
        self._hovered = False
        super().__init__(parent, **kwargs)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour('#0067C0'))
        self.SetForegroundColour(wx.WHITE)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_hover)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_hover)

    def _on_hover(self, event):
        self._hovered = event.GetEventType() == wx.wxEVT_ENTER_WINDOW
        self.Refresh()
        event.Skip()

    def OnPaint(self, event):
        self._draw(wx.AutoBufferedPaintDC(self))

    def _draw(self, dc):
        width, height = self.GetClientSize()
        dc.SetBackground(wx.Brush(self.GetParent().GetBackgroundColour()))
        dc.Clear()
        colour = ('#9EB9D0' if not self.IsEnabled() else '#005AA8' if not self.up
                  else '#1975C5' if self._hovered else '#0067C0')
        graphics = wx.GraphicsContext.Create(dc)
        graphics.SetBrush(wx.Brush(colour))
        graphics.SetPen(wx.Pen(colour))
        graphics.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, self.FromDIP(4))
        if self.hasFocus and self.IsEnabled():
            inset = self.FromDIP(3)
            graphics.SetBrush(wx.TRANSPARENT_BRUSH)
            graphics.SetPen(wx.Pen('#003B70'))
            graphics.DrawRoundedRectangle(inset + 0.5, inset + 0.5,
                                          width - inset * 2 - 1, height - inset * 2 - 1,
                                          self.FromDIP(2))
        graphics.Flush()
        dc.SetFont(self.GetFont())
        dc.SetTextForeground(wx.WHITE)
        dc.DrawLabel(self.GetLabelText(), wx.Rect(0, 0, width, height), wx.ALIGN_CENTER)

    def OnKeyDown(self, event):
        if self.hasFocus and self.IsEnabled() and event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.up = False
            self.Refresh()
        else:
            event.Skip()

    def OnKeyUp(self, event):
        if self.hasFocus and self.IsEnabled() and event.GetKeyCode() in (wx.WXK_SPACE, wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            pressed = not self.up
            self.up = True
            if pressed:
                self.Notify()
            if self:
                self.Refresh()
        else:
            event.Skip()

    def OnLoseFocus(self, event):
        self.up = True
        super().OnLoseFocus(event)


def form_button(parent, id=wx.ID_ANY, label='', **kwargs):
    """Keep native buttons for short labels and symbols."""
    button_class = RoundedButton if len(label.replace('&', '')) > 2 else wx.Button
    return button_class(parent, id=id, label=label, **kwargs)
