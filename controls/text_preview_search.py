"""Inline literal search for the read-only rich text preview."""
from bisect import bisect_left
import re

import wx

from localization import tr


class TextPreviewSearch(wx.Panel):
    def __init__(self, parent, text):
        super().__init__(parent)
        self.text = text
        self.active = False
        self.matches = []
        self.current = -1
        self._formatting = False
        self.normal_style = wx.TextAttr(text.GetForegroundColour(), text.GetBackgroundColour())
        self.match_style = wx.TextAttr(wx.BLACK, wx.Colour(255, 235, 120))
        self.current_style = wx.TextAttr(wx.BLACK, wx.Colour(255, 175, 70))

        self.query = wx.SearchCtrl(self, style=wx.TE_PROCESS_ENTER)
        self.query.SetDescriptiveText(tr("preview_find_hint"))
        self.query.SetMinSize((100, -1))
        self.query.ShowCancelButton(True)
        self.previous = wx.Button(self, label="↑", style=wx.BU_EXACTFIT)
        self.previous.SetSize(100, -1)
        self.previous.SetToolTip(tr("preview_find_previous"))
        self.next = wx.Button(self, label="↓", style=wx.BU_EXACTFIT)
        self.next.SetSize(100, -1)
        self.next.SetToolTip(tr("preview_find_next"))
        self.status = wx.StaticText(self)
        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(self.query, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        for control in (self.previous, self.next, self.status):
            row.Add(control, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.SetSizer(row)
        self.query.Bind(wx.EVT_TEXT, self._on_query)
        self.query.Bind(wx.EVT_SEARCHCTRL_CANCEL_BTN, self._on_clear)
        self.previous.Bind(wx.EVT_BUTTON, lambda event: self.navigate(-1))
        self.next.Bind(wx.EVT_BUTTON, lambda event: self.navigate(1))
        text.Bind(wx.EVT_TEXT, self._on_content)
        self._update_status()
        self.Hide()

    def set_active(self, active):
        self.active = active
        if not active:
            self.clear()
        self.Show(active)

    def clear(self):
        self.query.ChangeValue("")
        self._set_style(0, self.text.GetLastPosition(), self.normal_style)
        self.matches = []
        self.current = -1
        self._update_status()

    def _on_content(self, event):
        # SetValue can inherit the previous document's last character style.
        if not self._formatting:
            self.clear()
        event.Skip()

    def _set_style(self, start, end, style):
        # RichEdit sends EVT_TEXT for formatting changes as well as content.
        self._formatting = True
        try:
            self.text.SetStyle(start, end, style)
        finally:
            self._formatting = False

    def _on_clear(self, event):
        self.clear()
        self.query.SetFocus()

    def _on_query(self, event):
        self.text.Freeze()
        try:
            self._set_style(0, self.text.GetLastPosition(), self.normal_style)
            self.matches = []
            self.current = -1
            query = self.query.GetValue()
            if query and self.active:
                value = self.text.GetValue()
                # Windows RichEdit positions count UTF-16 units, including
                # two units for emoji; each normalized newline counts as one.
                extra_units = []
                if wx.Platform == "__WXMSW__":
                    extra_units = [i for i, char in enumerate(value) if ord(char) > 0xFFFF]
                for match in re.finditer(re.escape(query), value, re.IGNORECASE):
                    start, end = match.span()
                    span = (start + bisect_left(extra_units, start),
                            end + bisect_left(extra_units, end))
                    self.matches.append(span)
                    self._set_style(*span, self.match_style)
            self.navigate(1)
        finally:
            self.text.Thaw()

    def navigate(self, direction):
        if self.matches:
            if self.current >= 0:
                self._set_style(*self.matches[self.current], self.match_style)
                self.current = (self.current + direction) % len(self.matches)
            else:
                self.current = 0 if direction > 0 else len(self.matches) - 1
            start, end = self.matches[self.current]
            self._set_style(start, end, self.current_style)
            self.text.SetSelection(start, start)
            self.text.ShowPosition(start)
        self._update_status()

    def _update_status(self):
        count = len(self.matches)
        self.previous.Enable(bool(count))
        self.next.Enable(bool(count))
        label = ""
        if self.query.GetValue():
            label = (tr("preview_find_count", current=self.current + 1, total=count)
                     if count else tr("preview_find_none"))
        self.status.SetLabel(label)
        self.Layout()

    def handle_key(self, event):
        """Called before the frame's global shortcuts; confined to this preview."""
        focus = wx.Window.FindFocus()
        if not self.active or focus is None or not self.GetParent().IsDescendant(focus):
            return False
        key = event.GetKeyCode()
        if event.ControlDown() and key == ord("F"):
            self.query.SetFocus()
            self.query.SelectAll()
            return True
        if key == wx.WXK_F3 or (key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER)
                               and (focus is self.query or self.query.IsDescendant(focus))):
            self.navigate(-1 if event.ShiftDown() else 1)
            return True
        if key == wx.WXK_ESCAPE:
            self.clear()
            self.text.SetFocus()
            return True
        return False
