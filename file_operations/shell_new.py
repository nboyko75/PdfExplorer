"""Read and invoke Explorer's New menu, including its own labels and bitmaps.

The Shell owns registration filtering, templates, ordering and localization.
No registry registrations or application associations are changed here.
"""

import ctypes as ct
from dataclasses import dataclass
import os

from file_operations.open_with import P, HRESULT, _check, _guid, _method, _release, _shell


class _MenuItemInfo(ct.Structure):
    _fields_ = [("cbSize", ct.c_uint32), ("fMask", ct.c_uint32),
                ("fType", ct.c_uint32), ("fState", ct.c_uint32),
                ("wID", ct.c_uint32), ("hSubMenu", P), ("hbmpChecked", P),
                ("hbmpUnchecked", P), ("dwItemData", ct.c_size_t),
                ("dwTypeData", ct.c_wchar_p), ("cch", ct.c_uint32), ("hbmpItem", P)]


class _InvokeInfo(ct.Structure):
    _fields_ = [("cbSize", ct.c_uint32), ("fMask", ct.c_uint32), ("hwnd", P),
                ("lpVerb", P), ("lpParameters", ct.c_char_p), ("lpDirectory", ct.c_char_p),
                ("nShow", ct.c_int), ("dwHotKey", ct.c_uint32), ("hIcon", P),
                ("lpTitle", ct.c_char_p), ("lpVerbW", P), ("lpParametersW", ct.c_wchar_p),
                ("lpDirectoryW", ct.c_wchar_p), ("lpTitleW", ct.c_wchar_p),
                ("ptX", ct.c_int32), ("ptY", ct.c_int32)]


@dataclass(frozen=True)
class NewItem:
    offset: int
    label: str
    verb: str = ""
    enabled: bool = True
    separator: bool = False
    # An owned RGBA copy, independent of the Shell's HBITMAP lifetime.
    icon: tuple | None = None


def _bitmap_rgba(handle):
    if not handle or handle <= 12 or handle == ct.c_void_p(-1).value:
        return None  # HBMMENU_CALLBACK / predefined menu glyphs are not bitmaps.

    class Bitmap(ct.Structure):
        _fields_ = [("type", ct.c_int32), ("width", ct.c_int32), ("height", ct.c_int32),
                    ("widthBytes", ct.c_int32), ("planes", ct.c_uint16),
                    ("bitsPixel", ct.c_uint16), ("bits", P)]

    class BitmapInfo(ct.Structure):
        _fields_ = [("size", ct.c_uint32), ("width", ct.c_int32), ("height", ct.c_int32),
                    ("planes", ct.c_uint16), ("bits", ct.c_uint16), ("compression", ct.c_uint32),
                    ("imageSize", ct.c_uint32), ("xppm", ct.c_int32), ("yppm", ct.c_int32),
                    ("colorsUsed", ct.c_uint32), ("colorsImportant", ct.c_uint32)]

    gdi = ct.WinDLL("gdi32")
    gdi.GetObjectW.argtypes = [P, ct.c_int, P]
    gdi.GetObjectW.restype = ct.c_int
    gdi.CreateCompatibleDC.argtypes = [P]
    gdi.CreateCompatibleDC.restype = P
    gdi.DeleteDC.argtypes = [P]
    gdi.DeleteDC.restype = ct.c_int
    gdi.GetDIBits.argtypes = [P, P, ct.c_uint, ct.c_uint, P, P, ct.c_uint]
    gdi.GetDIBits.restype = ct.c_int
    bitmap = Bitmap()
    if not gdi.GetObjectW(handle, ct.sizeof(bitmap), ct.byref(bitmap)):
        return None
    width, height = bitmap.width, abs(bitmap.height)
    if not (0 < width <= 256 and 0 < height <= 256):
        return None
    info = BitmapInfo(ct.sizeof(BitmapInfo), width, -height, 1, 32)
    pixels = (ct.c_ubyte * (width * height * 4))()
    dc = gdi.CreateCompatibleDC(None)
    if not dc:
        return None
    try:
        if gdi.GetDIBits(dc, handle, 0, height, pixels, ct.byref(info), 0) != height:
            return None
    finally:
        gdi.DeleteDC(dc)
    rgba = bytearray(pixels)
    has_alpha = any(rgba[3::4])
    for index in range(0, len(rgba), 4):
        blue, green, red, alpha = rgba[index:index + 4]
        if not has_alpha:
            alpha = 255
        # Shell menu DIBs use premultiplied alpha; wx expects straight RGBA.
        elif 0 < alpha < 255:
            red, green, blue = (min(255, channel * 255 // alpha) for channel in (red, green, blue))
        rgba[index:index + 4] = bytes((red, green, blue, alpha))
    return width, height, bytes(rgba)


class NativeNewMenu:
    """Short-lived, UI-thread COM scope; all native resources are released together."""

    def __init__(self, directory):
        self.directory = os.path.abspath(directory)
        self.initializer, self.context_menu, self.pidl = P(), P(), P()
        self.menu = None

    def __enter__(self):
        self.scope = _shell()
        self.shell, self.ole = self.scope.__enter__()
        try:
            self.user = ct.WinDLL("user32")
            self.user.CreatePopupMenu.argtypes = []
            self.user.CreatePopupMenu.restype = P
            self.user.DestroyMenu.argtypes = [P]
            self.user.DestroyMenu.restype = ct.c_int
            self.user.GetSubMenu.argtypes = [P, ct.c_int]
            self.user.GetSubMenu.restype = P
            self.user.GetMenuItemCount.argtypes = [P]
            self.user.GetMenuItemCount.restype = ct.c_int
            self.user.GetMenuItemInfoW.argtypes = [P, ct.c_uint, ct.c_int, ct.POINTER(_MenuItemInfo)]
            self.user.GetMenuItemInfoW.restype = ct.c_int
            self.ole.CoCreateInstance.argtypes = [P, P, ct.c_uint32, P, ct.POINTER(P)]
            self.ole.CoCreateInstance.restype = HRESULT
            self.shell.SHParseDisplayName.argtypes = [ct.c_wchar_p, P, ct.POINTER(P), ct.c_uint32, P]
            self.shell.SHParseDisplayName.restype = HRESULT
            # CLSID_NewMenu, IID_IShellExtInit, IID_IContextMenu2.
            _check(self.ole.CoCreateInstance(_guid("D969A300-E7FF-11d0-A93B-00A0C90F2719"), None, 1,
                                            _guid("000214E8-0000-0000-C000-000000000046"), ct.byref(self.initializer)))
            _check(self.shell.SHParseDisplayName(self.directory, None, ct.byref(self.pidl), 0, None))
            _check(_method(self.initializer, 3, P, P, P)(self.initializer, self.pidl, None, None))
            _check(_method(self.initializer, 0, P, ct.POINTER(P))(
                self.initializer, _guid("000214F4-0000-0000-C000-000000000046"), ct.byref(self.context_menu)))
            self.menu = self.user.CreatePopupMenu()
            if not self.menu:
                raise OSError("CreatePopupMenu failed")
            _check(_method(self.context_menu, 3, P, ct.c_uint32, ct.c_uint32, ct.c_uint32, ct.c_uint32)(
                self.context_menu, self.menu, 0, 1, 0x7fff, 0))
            self.submenu = self.user.GetSubMenu(self.menu, 0)
            if not self.submenu:
                raise OSError("Windows did not supply a New submenu")
            # New populates its types lazily, just as it does in Explorer.
            _check(_method(self.context_menu, 6, ct.c_uint32, ct.c_size_t, ct.c_ssize_t)(
                self.context_menu, 0x0117, self.submenu, 0))  # WM_INITMENUPOPUP
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_exc):
        if self.menu:
            self.user.DestroyMenu(self.menu)
            self.menu = None
        _release(self.context_menu)
        _release(self.initializer)
        self.context_menu, self.initializer = P(), P()
        if self.pidl:
            self.ole.CoTaskMemFree(self.pidl)
            self.pidl = P()
        self.scope.__exit__(None, None, None)

    def items(self, include_icons=True):
        result = []
        for index in range(self.user.GetMenuItemCount(self.submenu)):
            label = ct.create_unicode_buffer(1024)
            info = _MenuItemInfo()
            info.cbSize, info.fMask = ct.sizeof(info), 0x1C7  # type/state/id/string/bitmap
            info.dwTypeData, info.cch = ct.cast(label, ct.c_wchar_p), len(label)
            if not self.user.GetMenuItemInfoW(self.submenu, index, True, ct.byref(info)):
                raise OSError("GetMenuItemInfoW failed")
            separator = bool(info.fType & 0x800)
            verb = ct.create_unicode_buffer(512)
            if not separator:
                _method(self.context_menu, 5, ct.c_size_t, ct.c_uint, P, P, ct.c_uint)(
                    self.context_menu, info.wID - 1, 4, None, verb, len(verb))  # GCS_VERBW
            result.append(NewItem(info.wID - 1, label.value, verb.value,
                                  not bool(info.fState & 3), separator,
                                  _bitmap_rgba(info.hbmpItem) if include_icons else None))
        return result

    def invoke(self, item, hwnd=0):
        # Recheck the identity in this fresh menu; never invoke a shifted command ID.
        if not any(candidate.offset == item.offset and candidate.label == item.label
                   and candidate.verb == item.verb and candidate.enabled
                   for candidate in self.items(include_icons=False)):
            raise OSError("The Windows New menu changed. Reopen Create and try again.")
        info = _InvokeInfo()
        info.cbSize, info.fMask = ct.sizeof(info), 0x4000  # CMIC_MASK_UNICODE
        info.hwnd, info.lpVerb, info.lpVerbW = hwnd, item.offset, item.offset
        info.lpDirectoryW, info.nShow = self.directory, 1
        _check(_method(self.context_menu, 4, P)(self.context_menu, ct.byref(info)))


def items(directory):
    with NativeNewMenu(directory) as menu:
        return menu.items()


def invoke(directory, item, hwnd=0):
    with NativeNewMenu(directory) as menu:
        menu.invoke(item, hwnd)
