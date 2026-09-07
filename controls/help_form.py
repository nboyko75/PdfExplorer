import os
import sys
import webbrowser

import wx

try:
    import wx.html2 as html2
except ImportError:  # pragma: no cover
    html2 = None

from localization import tr


HELP_RELATIVE_PATH = os.path.join("docs", "help", "index.html")
MANUAL_RELATIVE_PATH = os.path.join("docs", "DocExplorer_User_Manual.pdf")


def _resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)


def _open_local_file(path):
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:  # pragma: no cover
        webbrowser.open("file:///" + os.path.abspath(path).replace(os.sep, "/"))


def show_app_manual_form(owner):
    """Show the menu-structured, animated offline help."""
    help_path = _resource_path(HELP_RELATIVE_PATH)
    manual_path = _resource_path(MANUAL_RELATIVE_PATH)
    if not os.path.isfile(help_path):
        wx.MessageBox(
            f"Help file was not found:\n{help_path}",
            tr("menu_app_manual"),
            style=wx.OK | wx.ICON_ERROR,
        )
        return

    dialog = wx.Dialog(
        owner,
        title=tr("menu_app_manual"),
        size=(1120, 820),
        style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER,
    )
    panel = wx.Panel(dialog)
    toolbar = wx.BoxSizer(wx.HORIZONTAL)
    open_browser_btn = wx.Button(panel, label="Open in browser")
    open_pdf_btn = wx.Button(panel, label="Open PDF")
    close_btn = wx.Button(panel, wx.ID_CLOSE, tr("exit_button"))
    toolbar.Add(open_browser_btn, 0, wx.RIGHT, 8)
    if os.path.isfile(manual_path):
        toolbar.Add(open_pdf_btn, 0, wx.RIGHT, 8)
    else:
        open_pdf_btn.Hide()
    toolbar.AddStretchSpacer(1)
    toolbar.Add(close_btn, 0)

    if html2 is not None:
        viewer = html2.WebView.New(panel)
        viewer.LoadURL("file:///" + os.path.abspath(help_path).replace(os.sep, "/"))
    else:
        viewer = wx.Panel(panel)
        message = wx.StaticText(
            viewer,
            label="The embedded HTML viewer is unavailable. Select Open in browser to view Help.",
        )
        fallback_sizer = wx.BoxSizer(wx.VERTICAL)
        fallback_sizer.Add(message, 0, wx.ALL, 18)
        viewer.SetSizer(fallback_sizer)

    main_sizer = wx.BoxSizer(wx.VERTICAL)
    main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 10)
    main_sizer.Add(viewer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    panel.SetSizer(main_sizer)

    open_browser_btn.Bind(wx.EVT_BUTTON, lambda _event: _open_local_file(help_path))
    open_pdf_btn.Bind(wx.EVT_BUTTON, lambda _event: _open_local_file(manual_path))
    close_btn.Bind(wx.EVT_BUTTON, lambda _event: dialog.EndModal(wx.ID_CLOSE))
    dialog.CenterOnParent()
    try:
        dialog.ShowModal()
    finally:
        dialog.Destroy()
