import wx

from localization import tr


def show_about_form(owner):
    dialog = wx.Dialog(owner, title=tr("menu_about"), size=(420, 220))
    panel = wx.Panel(dialog)

    title = wx.StaticText(panel, label=tr("app_title"), style=wx.ALIGN_CENTRE)
    title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

    version = wx.StaticText(panel, label="Version 1.0")
    description = wx.StaticText(panel, label="Document Explorer")
    copyright = wx.StaticText(panel, label="(c) Nick Boyko")

    close_btn = wx.Button(panel, wx.ID_OK, tr("exit_button"))

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(title, 0, wx.ALIGN_CENTRE | wx.TOP | wx.BOTTOM, 12)
    sizer.Add(version, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 6)
    sizer.Add(description, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 6)
    sizer.Add(copyright, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 16)
    sizer.Add(close_btn, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 12)
    panel.SetSizer(sizer)
    dialog.CenterOnParent()
    dialog.ShowModal()
    dialog.Destroy()
