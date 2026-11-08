"""Explorer's New-menu UI, with built-in creation as a fallback."""

import io
import logging
import os
from pathlib import Path
import re
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

import wx

from localization import tr
from file_operations import shell_new

log = logging.getLogger(__name__)


# Fallback only, for systems where the Windows New-menu handler is unavailable.
ITEM_TYPES = (
    ("folder", "file_type_folder", ""),
    ("shortcut", "create_shortcut", ".lnk"),
    ("word", "create_word", ".docx"),
    ("excel", "create_excel", ".xlsx"),
    ("text", "create_text", ".txt"),
    ("rich_text", "create_rich_text", ".rtf"),
)
_TYPES = {kind: (label, extension) for kind, label, extension in ITEM_TYPES}
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def target_directory(context):
    path = context.new_folder_target if context.source == "tree" else context.current_folder
    return path if isinstance(path, str) and os.path.isdir(path) else None


def item_name(name, kind=None, *, extension=None):
    """Accept one Windows filename, never a path or an alternate data stream."""
    if (not name or name in (".", "..") or name.endswith((".", " "))
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³]",
                            name.split(".")[0].rstrip(), re.IGNORECASE)):
        raise ValueError(tr("rename_invalid_name"))
    if extension is None:
        extension = _TYPES[kind][1]
    if extension and not name.lower().endswith(extension):
        name += extension
    if len(name.encode("utf-16-le")) // 2 > 255:
        raise ValueError(tr("rename_invalid_name"))
    return name


def default_name(directory, kind):
    label, extension = _TYPES[kind]
    base = tr("context_new_folder" if kind == "folder" else label)
    name = base + extension
    index = 2
    while os.path.lexists(os.path.join(directory, name)):
        name = f"{base} ({index}){extension}"
        index += 1
    return name


def _office_document(kind):
    """Minimal OOXML packages with real document/workbook parts, not empty files."""
    if kind == "word":
        main_part = "word/document.xml"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
        parts = {main_part: '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p/><w:sectPr/></w:body></w:document>'}
        overrides = ""
    else:
        main_part = "xl/workbook.xml"
        content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
        spreadsheet_ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        parts = {
            main_part: f'<workbook xmlns="{spreadsheet_ns}" xmlns:r="{_OFFICE_REL_NS}"><sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": f'<Relationships xmlns="{_REL_NS}"><Relationship Id="rId1" Type="{_OFFICE_REL_NS}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{spreadsheet_ns}"><sheetData/></worksheet>',
        }
        overrides = '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    parts["[Content_Types].xml"] = (
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f'<Override PartName="/{main_part}" ContentType="{content_type}"/>{overrides}</Types>'
    )
    parts["_rels/.rels"] = f'<Relationships xmlns="{_REL_NS}"><Relationship Id="rId1" Type="{_OFFICE_REL_NS}/officeDocument" Target="{main_part}"/></Relationships>'
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, xml in parts.items():
            archive.writestr(name, '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' + xml)
    return output.getvalue()


def _shortcut_bytes(target):
    import pythoncom
    from win32com.shell import shell
    from file_operations.open_with import _shell

    # Use the same balanced native COM scope as Open With. pywin32's main-thread
    # initialization shortcut can otherwise uninitialize the UI thread's COM.
    with _shell():
        link = pythoncom.CoCreateInstance(shell.CLSID_ShellLink, None,
                                         pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
        persist = None
        try:
            link.SetPath(target)
            link.SetWorkingDirectory(target if os.path.isdir(target) else os.path.dirname(target))
            with tempfile.TemporaryDirectory(prefix="docexplorer_shortcut_") as folder:
                path = os.path.join(folder, "new.lnk")
                persist = link.QueryInterface(pythoncom.IID_IPersistFile)
                persist.Save(path, 1)
                return Path(path).read_bytes()
        finally:
            del persist, link


def create(directory, kind, name, shortcut_target=None):
    """Create exclusively: collisions (including races) must never overwrite data."""
    path = os.path.join(directory, item_name(name, kind))
    if kind == "folder":
        os.mkdir(path)
        return path
    if kind == "shortcut":
        target = os.path.expanduser(os.path.expandvars((shortcut_target or "").strip().strip('"')))
        if not target or not os.path.exists(target):
            raise ValueError(tr("create_target_missing"))
        data = _shortcut_bytes(os.path.abspath(target))
    elif kind in ("word", "excel"):
        data = _office_document(kind)
    elif kind == "rich_text":
        data = b"{\\rtf1\\ansi\\deff0{\\fonttbl{\\f0 Calibri;}}\\f0\\fs22\\par}"
    else:
        data = b""
    # Open outside the cleanup block: a failed exclusive open never owns the file.
    stream = open(path, "xb")
    try:
        with stream:
            stream.write(data)
    except BaseException:
        os.unlink(path)
        raise
    return path


def _prompt(owner, message, value=""):
    dialog = wx.TextEntryDialog(owner, message, tr("context_create"), value=value)
    try:
        for identifier, label in ((wx.ID_OK, "ok_button"), (wx.ID_CANCEL, "cancel_button")):
            button = dialog.FindWindow(identifier)
            if button:
                button.SetLabel(tr(label))
        return dialog.GetValue() if dialog.ShowModal() == wx.ID_OK else None
    finally:
        dialog.Destroy()


def run(context, kind):
    directory = target_directory(context)
    if not directory:
        return
    owner = context.owner
    shortcut_target = None
    if kind == "shortcut":
        shortcut_target = _prompt(owner, tr("create_shortcut_target"))
        if shortcut_target is None:
            return
    name = _prompt(owner, tr("create_name"), default_name(directory, kind))
    if name is None:
        return
    try:
        path = create(directory, kind, name, shortcut_target)
    except Exception as exc:
        wx.MessageBox(tr("create_failed", error=str(exc)), tr("context_create"), wx.OK | wx.ICON_ERROR, owner)
        return

    _refresh_created(owner, directory, path)


def _refresh_created(owner, directory, path=None):
    from controls import filelist, tree_control
    path_box = getattr(owner, "path_box", None)
    if path_box is not None:
        path_box.ChangeValue(directory)
    filelist._refresh_after_fs_change(owner, affected_dirs=[directory], current_folder=directory)
    if path and os.path.isdir(path) and getattr(owner, "tree", None) is not None:
        tree_control.select_tree_item_by_path(owner, path, update_path_box=False)
    if path:
        filelist.select_list_item_by_path(owner, path)


def _finish_shell_creation(owner, directory, before, attempts=10, expected_folder=None):
    if not owner or getattr(owner, "_closing_workspace", False) or not os.path.isdir(directory):
        return
    try:
        if expected_folder is not None:
            current = getattr(owner, "_list_folder_path", None)
            if current is not None and current != expected_folder:
                # An asynchronous application must not navigate the user back.
                from controls import filelist
                filelist._refresh_after_fs_change(owner, affected_dirs=[directory])
                return
        added = set(os.listdir(directory)) - before
        if not added and attempts:
            # Some registered New commands create their file asynchronously.
            wx.CallLater(300, _finish_shell_creation, owner, directory, before, attempts - 1, expected_folder)
            return
        path = os.path.join(directory, next(iter(added))) if len(added) == 1 else None
        if path:
            # Explorer creates first, then offers to rename. Cancel keeps its default name.
            name = _prompt(owner, tr("create_name"), os.path.basename(path))
            if name is not None:
                extension = os.path.splitext(path)[1] if os.path.isfile(path) else ""
                destination = os.path.join(directory, item_name(name, extension=extension))
                if destination != path:
                    os.rename(path, destination)  # Windows refuses to overwrite an existing file.
                    path = destination
        _refresh_created(owner, directory, path)
    except Exception as exc:
        wx.MessageBox(tr("create_failed", error=str(exc)), tr("context_create"), wx.OK | wx.ICON_ERROR, owner)
        _refresh_created(owner, directory)


def run_shell(context, entry):
    directory = target_directory(context)
    if not directory:
        return
    # These two native commands require Explorer's IShellView for editing/wizards.
    # Keep our existing dialogs while using their exact Shell labels and icons.
    if entry.verb in ("NewFolder", "NewLink"):
        return run(context, "folder" if entry.verb == "NewFolder" else "shortcut")
    try:
        expected_folder = getattr(context.owner, "_list_folder_path", None)
        before = set(os.listdir(directory))
        shell_new.invoke(directory, entry, context.owner.GetHandle())
    except Exception as exc:
        wx.MessageBox(tr("create_failed", error=str(exc)), tr("context_create"), wx.OK | wx.ICON_ERROR, context.owner)
        return
    _finish_shell_creation(context.owner, directory, before, expected_folder=expected_folder)


def _fallback_bitmap(kind, extension):
    from file_operations.image_utils import get_shell_bitmap
    bitmap = get_shell_bitmap("folder" if kind == "folder" else "new" + extension,
                              file_attr=0x10 if kind == "folder" else 0x80,
                              use_file_attributes=True)
    if bitmap is not None and bitmap.IsOk():
        return bitmap
    return wx.ArtProvider.GetBitmap(wx.ART_FOLDER if kind == "folder" else wx.ART_NORMAL_FILE,
                                    wx.ART_MENU, (16, 16))


def populate_menu(menu, context_factory):
    for item in list(menu.GetMenuItems()):
        menu.Unbind(wx.EVT_MENU, id=item.GetId())
        menu.DestroyItem(item)
    directory = target_directory(context_factory())
    if directory:
        try:
            entries = shell_new.items(directory)
        except Exception:
            log.warning("Unable to read Windows New menu; using built-in creation types", exc_info=True)
        else:
            for entry in entries:
                if entry.separator:
                    menu.AppendSeparator()
                    continue
                item = menu.Append(wx.ID_ANY, entry.label)
                item.Enable(entry.enabled)
                if entry.icon:
                    item.SetBitmap(wx.Bitmap.FromBufferRGBA(*entry.icon))
                menu.Bind(wx.EVT_MENU, lambda event, selected=entry: run_shell(context_factory(), selected), item)
            return
    for kind, label, extension in ITEM_TYPES:
        item = menu.Append(wx.ID_ANY, tr(label))
        item.SetBitmap(_fallback_bitmap(kind, extension))
        menu.Bind(wx.EVT_MENU, lambda event, selected=kind: run(context_factory(), selected), item)


def append_menu(menu, context_factory):
    submenu = wx.Menu()
    populate_menu(submenu, context_factory)
    item = menu.AppendSubMenu(submenu, tr("context_create"), tr("create_hint"))
    item.SetBitmap(wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_MENU, (16, 16)))
    item.Enable(bool(target_directory(context_factory())))
    return item


def popup(context, event=None):
    if not target_directory(context):
        return
    button = context.owner.list_create_btn
    menu = wx.Menu()
    try:
        populate_menu(menu, lambda: context)
        button.PopupMenu(menu, (0, button.GetSize().height))
    finally:
        menu.Destroy()
