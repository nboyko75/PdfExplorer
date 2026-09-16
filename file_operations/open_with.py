"""Windows association handlers and shared Open With menus (no registry edits)."""
import contextlib
import ctypes as ct
import logging
import os
import uuid

import wx
from localization import tr

log = logging.getLogger(__name__)
P = ct.c_void_p
HRESULT = ct.c_int32


def _check(hr):
    if hr < 0:
        raise OSError(f"Windows Shell HRESULT 0x{hr & 0xffffffff:08X}")


def _method(pointer, slot, *types):
    table = ct.cast(pointer, ct.POINTER(ct.POINTER(P))).contents
    return ct.WINFUNCTYPE(HRESULT, P, *types)(table[slot])


def _release(pointer):
    if pointer:
        _method(pointer, 2)(pointer)


def _guid(value):
    return (ct.c_ubyte * 16).from_buffer_copy(uuid.UUID(value).bytes_le)


@contextlib.contextmanager
def _shell():
    # WinDLL preserves HRESULTs for explicit handling (including cancellation).
    ole = ct.WinDLL('ole32')
    ole.CoInitializeEx.argtypes = [P, ct.c_uint32]
    ole.CoInitializeEx.restype = HRESULT
    ole.CoTaskMemFree.argtypes = [P]
    ole.CoTaskMemFree.restype = None
    ole.CoUninitialize.argtypes = []
    ole.CoUninitialize.restype = None
    hr = ole.CoInitializeEx(None, 2)
    if hr < 0 and (hr & 0xffffffff) != 0x80010106:  # already initialized MTA
        _check(hr)
    try:
        yield ct.WinDLL('shell32'), ole
    finally:
        if hr >= 0:
            ole.CoUninitialize()


def _string(handler, slot, ole):
    value = P()
    try:
        _check(_method(handler, slot, ct.POINTER(P))(handler, ct.byref(value)))
        return ct.wstring_at(value) if value else ''
    finally:
        if value:
            ole.CoTaskMemFree(value)


@contextlib.contextmanager
def _handlers(shell, path):
    enum = P()
    handlers = []
    shell.SHAssocEnumHandlers.argtypes = [ct.c_wchar_p, ct.c_uint32, ct.POINTER(P)]
    shell.SHAssocEnumHandlers.restype = HRESULT
    try:
        extension = os.path.splitext(path)[1]
        if extension:
            _check(shell.SHAssocEnumHandlers(extension, 1, ct.byref(enum)))
            while enum:
                handler, count = P(), ct.c_uint32()
                hr = _method(enum, 3, ct.c_uint32, ct.POINTER(P), ct.POINTER(ct.c_uint32))(
                    enum, 1, ct.byref(handler), ct.byref(count))
                if handler:
                    handlers.append(handler)
                _check(hr)
                if hr != 0 or not count.value:
                    break
        yield handlers
    finally:
        for handler in handlers:
            _release(handler)
        _release(enum)


def applications(path):
    result, seen = [], set()
    with _shell() as (shell, ole), _handlers(shell, path) as handlers:
        for handler in handlers:
            try:
                identity = _string(handler, 3, ole)
                title = _string(handler, 4, ole) or identity
                if not identity or identity.casefold() in seen:
                    continue
                icon_path, icon_index = P(), ct.c_int()
                try:
                    hr = _method(handler, 5, ct.POINTER(P), ct.POINTER(ct.c_int))(
                        handler, ct.byref(icon_path), ct.byref(icon_index))
                    location = ct.wstring_at(icon_path) if hr >= 0 and icon_path else identity
                finally:
                    if icon_path:
                        ole.CoTaskMemFree(icon_path)
                result.append((identity, title, location, icon_index.value))
                seen.add(identity.casefold())
            except OSError:
                log.debug('Unable to read association handler', exc_info=True)
    return result


def invoke(path, identity):
    with _shell() as (shell, ole), _handlers(shell, path) as handlers:
        for handler in handlers:
            if _string(handler, 3, ole) != identity:
                continue
            item, data = P(), P()
            try:
                shell.SHCreateItemFromParsingName.argtypes = [ct.c_wchar_p, P, P, ct.POINTER(P)]
                shell.SHCreateItemFromParsingName.restype = HRESULT
                iid_item = _guid('43826d1e-e718-42ee-bc55-a1e261c37bfe')
                _check(shell.SHCreateItemFromParsingName(path, None, iid_item, ct.byref(item)))
                bhid_data = _guid('b8c0bd9f-ed24-455c-83e6-d5390c4fe8c4')
                iid_data = _guid('0000010e-0000-0000-c000-000000000046')
                _check(_method(item, 3, P, P, P, ct.POINTER(P))(
                    item, None, bhid_data, iid_data, ct.byref(data)))
                _check(_method(handler, 8, P)(handler, data))
                return
            finally:
                _release(data)
                _release(item)
    raise OSError(tr('open_with_unavailable'))


def choose_application(owner, path):
    class OpenAsInfo(ct.Structure):
        _fields_ = [('file', ct.c_wchar_p), ('class_name', ct.c_wchar_p), ('flags', ct.c_uint32)]
    with _shell() as (shell, _):
        shell.SHOpenWithDialog.argtypes = [P, ct.POINTER(OpenAsInfo)]
        shell.SHOpenWithDialog.restype = HRESULT
        info = OpenAsInfo(path, None, 4)  # OAIF_EXEC: open once, do not set defaults.
        hr = shell.SHOpenWithDialog(owner.GetHandle(), ct.byref(info))
        if (hr & 0xffffffff) != 0x800704c7:  # user cancelled
            _check(hr)


def _resolve_icon_location(location):
    """Resolve Shell indirect resources before passing a filename to wx."""
    location = os.path.expandvars(location)
    if location.startswith('@'):
        shlwapi = ct.WinDLL('shlwapi')
        shlwapi.SHLoadIndirectString.argtypes = [ct.c_wchar_p, ct.c_wchar_p, ct.c_uint32, P]
        shlwapi.SHLoadIndirectString.restype = HRESULT
        buffer = ct.create_unicode_buffer(32768)
        hr = shlwapi.SHLoadIndirectString(location, buffer, len(buffer), None)
        if hr < 0:
            return None
        location = os.path.expandvars(buffer.value)
    # Unresolved ms-resource URIs and missing files must never reach wx loaders.
    return location if location and os.path.isfile(location) else None


def icon_bitmap(location=None, index=0):
    location = location or os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'OpenWith.exe')
    try:
        location = _resolve_icon_location(location)
        if location:
            # wx logs load failures separately from Python exceptions. Suppress
            # only optional icon loading; use the fallback below if it fails.
            quiet = wx.LogNull()
            try:
                if os.path.splitext(location)[1].lower() in ('.png', '.bmp', '.jpg', '.jpeg'):
                    image = wx.Image(location)
                    if image.IsOk():
                        return image.Scale(16, 16, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
                else:
                    icon = wx.Icon(wx.IconLocation(location, index))
                    if icon.IsOk():
                        bitmap = wx.Bitmap()
                        bitmap.CopyFromIcon(icon)
                        if bitmap.IsOk():
                            return bitmap.ConvertToImage().Scale(16, 16, wx.IMAGE_QUALITY_HIGH).ConvertToBitmap()
            finally:
                del quiet
    except (OSError, RuntimeError, AttributeError, TypeError, ValueError):
        pass
    return wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE, wx.ART_MENU, (16, 16))


def selected_file(context):
    if context.source == 'tree':
        path = context.target_path or (context.selected_paths[0] if len(context.selected_paths) == 1 else None)
    else:
        path = context.selected_paths[0] if len(context.selected_paths) == 1 else None
    return path if isinstance(path, str) and os.path.isfile(path) else None


def _run(owner, path, identity=None):
    try:
        if not os.path.isfile(path):
            raise OSError(tr('open_with_unavailable'))
        if identity is None:
            choose_application(owner, path)
        else:
            invoke(path, identity)
    except Exception as exc:
        wx.MessageBox(str(exc), tr('context_open_with'), wx.OK | wx.ICON_ERROR, owner)


def populate_menu(menu, owner, path):
    # Bind handlers to the menu, not the frame; rebuilding leaves no stale bindings.
    for item in list(menu.GetMenuItems()):
        menu.Unbind(wx.EVT_MENU, id=item.GetId())
        menu.DestroyItem(item)
    if path:
        try:
            apps = applications(path)
        except Exception:
            log.debug('Unable to enumerate Open With applications', exc_info=True)
            apps = []
        for identity, title, location, index in apps:
            item = menu.Append(wx.ID_ANY, title.replace('&', '&&'))
            item.SetBitmap(icon_bitmap(location, index))
            menu.Bind(wx.EVT_MENU, lambda event, app=identity: _run(owner, path, app), item)
        if apps:
            menu.AppendSeparator()
    item = menu.Append(wx.ID_ANY, tr('open_with_choose_app'))
    from file_operations.image_utils import ensure_owner_icon_manager
    ensure_owner_icon_manager(owner).set_menu_icon2(item, "open_with")
    item.Enable(bool(path))
    menu.Bind(wx.EVT_MENU, lambda event: _run(owner, path), item)


def append_menu(menu, owner, context):
    submenu = wx.Menu()
    path = selected_file(context)
    populate_menu(submenu, owner, path)
    item = menu.AppendSubMenu(submenu, tr('context_open_with'))
    from file_operations.image_utils import ensure_owner_icon_manager
    ensure_owner_icon_manager(owner).set_menu_icon2(item, "open_with")
    item.Enable(bool(path))
    return item


def popup(context, event=None):
    path = selected_file(context)
    if not path:
        return
    owner = context.owner
    button = owner.list_open_with_btn
    menu = wx.Menu()
    try:
        populate_menu(menu, owner, path)
        button.PopupMenu(menu, (0, button.GetSize().height))
    finally:
        menu.Destroy()
