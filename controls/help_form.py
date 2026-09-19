import os
import sys
import webbrowser
from pathlib import Path

import wx

from common.consts import HELP_RELATIVE_PATH, MANUAL_RELATIVE_PATH

try:
    import wx.html2 as html2
except ImportError:  # pragma: no cover
    html2 = None

from localization import tr




def _resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)


SUPPORTED_HELP_LOCALES = frozenset(("en", "uk", "de", "fr", "es", "it", "pt_br", "ja", "ko", "zh_cn", "ru"))


def _localized_resource_path(relative_path, locale_code):
    """Resolve a bundled manual without letting a locale escape the docs folder."""
    code = str(locale_code or "en").lower().replace("-", "_")
    if code not in SUPPORTED_HELP_LOCALES:
        code = code.split("_", 1)[0]
    if code not in SUPPORTED_HELP_LOCALES:
        code = "en"
    stem, extension = os.path.splitext(relative_path)
    for candidate in (f"{stem}_{code}{extension}", f"{stem}_en{extension}", relative_path):
        path = _resource_path(candidate)
        if os.path.isfile(path):
            return path
    return _resource_path(relative_path)


def _open_local_file(path):
    if hasattr(os, "startfile"):
        os.startfile(path)
    else:  # pragma: no cover
        webbrowser.open(Path(path).resolve().as_uri())


def show_app_manual_form(owner):
    """Show the menu-structured, animated offline help."""
    locale_code = getattr(owner, "current_locale", "en")
    help_path = _localized_resource_path(HELP_RELATIVE_PATH, locale_code)
    manual_path = _localized_resource_path(MANUAL_RELATIVE_PATH, locale_code)
    if not os.path.isfile(help_path):
        wx.MessageBox(
            tr("help_manual_missing", path=help_path),
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
    open_browser_btn = wx.Button(panel, label=tr("help_manual_open_in_browser_button"))
    open_pdf_btn = wx.Button(panel, label=tr("help_manual_open_pdf_button"))
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
        viewer.LoadURL(Path(help_path).resolve().as_uri())
    else:
        viewer = wx.Panel(panel)
        message = wx.StaticText(
            viewer,
            label=tr("help_manual_viewer_unavailable"),
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
