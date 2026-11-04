"""Open Explorer's file-type-specific property sheets without blocking wx."""
import os

import wx

from localization import tr


def selected_path(context):
    """Use the clicked tree item or the single selected list item."""
    paths = ([context.target_path] if context.source == "tree" and context.target_path
             else context.selected_paths)
    if len(paths) != 1 or not isinstance(paths[0], str):
        return None
    return paths[0] if os.path.lexists(paths[0]) else None


def open_properties(path):
    """Invoke the Shell verb on the wx UI thread, which keeps pumping messages.

    Windows supplies the tabs, metadata editors and installed property-page
    extensions. No owner HWND is passed, so the sheet cannot disable the app.
    Keep shortcuts as shortcuts instead of resolving their targets.
    """
    import pythoncom
    from win32com.shell import shell, shellcon

    pythoncom.CoInitialize()
    try:
        shell.ShellExecuteEx(
            fMask=shellcon.SEE_MASK_INVOKEIDLIST | shellcon.SEE_MASK_FLAG_NO_UI,
            hwnd=0,
            lpVerb="properties",
            lpFile=os.path.abspath(path),
            nShow=1,
        )
    finally:
        pythoncom.CoUninitialize()


def show_properties(context, event=None):
    path = selected_path(context)
    if path is None:
        return
    try:
        open_properties(path)
    except Exception as exc:
        wx.MessageBox(
            tr("properties_failed", path=path, error=str(exc)),
            tr("context_properties"), wx.OK | wx.ICON_ERROR, context.owner,
        )
