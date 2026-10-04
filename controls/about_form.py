import sys
from pathlib import Path
from xml.etree import ElementTree

import wx

from localization import tr


def _app_version():
    resource_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    manifests = [resource_dir / "store" / "AppxManifest.xml"]
    if getattr(sys, "frozen", False):
        # MSIX packaging can override the version after the executable is built.
        manifests.insert(0, Path(sys.executable).parent / "AppxManifest.xml")
    for manifest in manifests:
        try:
            identity = ElementTree.parse(manifest).find(
                "{http://schemas.microsoft.com/appx/manifest/foundation/windows10}Identity"
            )
        except (OSError, ElementTree.ParseError):
            continue
        if identity is not None and identity.get("Version"):
            return identity.get("Version")
    return "\u2014"


def show_about_form(owner):
    dialog = wx.Dialog(owner, title=tr("menu_about"), size=(420, 220))
    panel = wx.Panel(dialog)

    title = wx.StaticText(panel, label=tr("app_title"), style=wx.ALIGN_CENTRE)
    title.SetFont(wx.Font(16, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

    version = wx.StaticText(panel, label=tr("about_version", version=_app_version()))
    description = wx.StaticText(panel, label="Document Explorer")
    copyright = wx.StaticText(panel, label="(c) Nick Boiko")
    email = wx.StaticText(panel, label="nboyko75@gmail.com")

    close_btn = wx.Button(panel, wx.ID_OK, tr("exit_button"))

    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(title, 0, wx.ALIGN_CENTRE | wx.TOP | wx.BOTTOM, 12)
    sizer.Add(version, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 6)
    sizer.Add(description, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 6)
    sizer.Add(copyright, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 6)
    sizer.Add(email, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 16)
    sizer.Add(close_btn, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 12)
    panel.SetSizer(sizer)
    dialog.CenterOnParent()
    dialog.ShowModal()
    dialog.Destroy()
