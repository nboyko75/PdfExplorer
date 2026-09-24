import json
import os
import sys
import ctypes
import uuid
from ctypes import wintypes

import wx

from common.consts import KNOWN_FOLDER_IDS, OPTION_FIELDS, OPTION_GROUP_ORDER, OPTION_GROUP_TRANSLATION_KEYS, PERSISTED_LAYOUT_KEYS
from common.settings_utils import (
    get_option_group_label,
    quality_label_to_value,
    quality_value_to_label,
    get_locale_value_label,
    normalize_setting_value,
)
from localization import tr


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value):
        guid = uuid.UUID(value)
        return cls.from_buffer_copy(guid.bytes_le)



def get_windows_known_folder(folder_key):
    guid_text = KNOWN_FOLDER_IDS.get(str(folder_key).lower())
    if not guid_text:
        return ""

    folder_id = GUID.from_string(guid_text)
    path_pointer = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32

    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        wintypes.HANDLE,
        ctypes.POINTER(ctypes.c_wchar_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.HRESULT

    result = shell32.SHGetKnownFolderPath(
        ctypes.byref(folder_id),
        0,
        None,
        ctypes.byref(path_pointer),
    )

    if result != 0:
        return ""

    try:
        path = path_pointer.value or ""
        return os.path.normpath(path) if path else ""
    finally:
        ole32.CoTaskMemFree(path_pointer)


def get_windows_special_folder(name):
    normalized_name = str(name).lower()
    if normalized_name in KNOWN_FOLDER_IDS:
        return get_windows_known_folder(normalized_name)

    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        path = shell.SpecialFolders(name)

        if path and os.path.isdir(path):
            return os.path.normpath(path)
    except Exception:
        pass

    return ""


def get_windows_display_name(path):
    if not path:
        return ""

    try:
        from win32comext.shell import shell, shellcon

        display_name = ""
        try:
            info = shell.SHGetFileInfo(str(path), 0, shellcon.SHGFI_DISPLAYNAME)
            if info and len(info) > 1 and info[1] and len(info[1]) > 3:
                display_name = info[1][3] or ""
        except Exception:
            display_name = ""

        if display_name:
            return display_name
    except Exception:
        pass

    try:
        basename = os.path.basename(os.path.normpath(str(path)))
        if basename:
            return basename
    except Exception:
        pass

    return str(path)


def get_special_folder_display_name(csidl, fallback=""):
    try:
        from win32comext.shell import shell, shellcon

        pidl = None
        try:
            pidl = shell.SHGetSpecialFolderLocation(0, csidl)
        except Exception:
            pidl = None

        if pidl is not None:
            try:
                info = shell.SHGetFileInfo(pidl, 0, shellcon.SHGFI_PIDL | shellcon.SHGFI_DISPLAYNAME)
                if info and len(info) > 1 and info[1] and len(info[1]) > 3:
                    display_name = info[1][3] or ""
                if display_name:
                    return display_name
            except Exception:
                pass
    except Exception:
        pass

    return fallback


def _get_project_root_dir():
    # In frozen builds (e.g. PyInstaller), persist settings next to the executable.
    if getattr(sys, "frozen", False):
        executable_path = os.path.abspath(getattr(sys, "executable", ""))
        executable_dir = os.path.dirname(executable_path)
        if executable_dir:
            return executable_dir

    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    if os.path.basename(current_dir) == "controls":
        return os.path.dirname(current_dir)
    return current_dir


def _get_settings_file_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "DocExplorer", ".pdf_explorer_settings.json")


def _legacy_settings_paths():
    # Keep existing preferences when upgrading from source or portable builds.
    roots = [_get_project_root_dir()]
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        roots.extend([os.path.join(exe_dir, "common")])
        if os.path.basename(exe_dir).lower() == "docexplorer":
            dist_dir = os.path.dirname(exe_dir)
        else:
            dist_dir = exe_dir
        if os.path.basename(dist_dir).lower() == "dist":
            project_dir = os.path.dirname(dist_dir)
            roots.extend([dist_dir, os.path.join(project_dir, "common"), project_dir])
    else:
        roots.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return [os.path.join(root, ".pdf_explorer_settings.json") for root in roots]


def load_settings():
    settings_file = _get_settings_file_path()
    candidates = [settings_file]
    if not os.path.isfile(settings_file):
        candidates.extend(_legacy_settings_paths())
    for candidate in candidates:
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                settings = json.load(handle)
            if not isinstance(settings, dict):
                continue
            if candidate != settings_file:
                save_settings(settings)
            return settings
        except (OSError, ValueError):
            continue
    return {}


def save_settings(settings):
    settings_file = _get_settings_file_path()
    try:
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=4)
    except Exception:
        pass


def update_settings(new_values):
    settings = load_settings()
    settings.update(new_values)
    save_settings(settings)


def get_configurable_settings_rows(settings):
    if not isinstance(settings, dict):
        return []

    rows = []
    for key, value in sorted(settings.items()):
        if key in PERSISTED_LAYOUT_KEYS:
            continue
        if key.endswith("_position") or key.endswith("_size"):
            continue
        if key.startswith("search_form_date_") or key.startswith("search_form_size_"):
            continue
        if key in {"search_form_folder", "search_form_file_mask"}:
            continue
        rows.append({"key": key, "value": value})
    return rows


def _format_setting_value(value):
    if isinstance(value, bool):
        return tr("options_value_true") if value else tr("options_value_false")
    if value is None:
        return tr("options_value_empty")
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _get_setting_label(key):
    translated = tr(f"settings_{key}")
    if translated.startswith("settings_"):
        return key.replace("_", " ").strip().title()
    return translated


_get_option_group_label = get_option_group_label
_quality_label_to_value = quality_label_to_value
_quality_value_to_label = quality_value_to_label
_get_locale_value_label = get_locale_value_label
_normalize_setting_value = normalize_setting_value


def show_options_form(owner):
    from controls.options_form import show_options_form as _show_options_form
    return _show_options_form(owner)


def save_window_geometry(frame):
    if frame.IsIconized():
        return

    maximized = bool(frame.IsMaximized())
    geometry = {"window_maximized": maximized}
    # Keep the normal bounds when maximized, so Restore returns to that size.
    if not maximized:
        position = frame.GetPosition()
        size = frame.GetSize()
        geometry.update({
            "window_position": [int(position.x), int(position.y)],
            "window_size": [int(size.x), int(size.y)],
        })
    update_settings(geometry)


def save_control_geometry(control, settings_prefix):
    position = control.GetPosition()
    size = control.GetSize()

    update_settings({
        f"{settings_prefix}_position": [int(position.x), int(position.y)],
        f"{settings_prefix}_size": [int(size.x), int(size.y)],
    })


def restore_control_geometry(
    control,
    settings_prefix,
    default_size,
    min_size,
    settings=None,
):
    if settings is None:
        settings = load_settings()

    control.SetMinSize(min_size)
    control.SetSize(default_size)

    saved_size = settings.get(f"{settings_prefix}_size")
    if isinstance(saved_size, list) and len(saved_size) == 2:
        width, height = map(int, saved_size)
        if width >= min_size[0] and height >= min_size[1]:
            control.SetSize((width, height))

    saved_position = settings.get(f"{settings_prefix}_position")
    if isinstance(saved_position, list) and len(saved_position) == 2:
        control.SetPosition(tuple(map(int, saved_position)))

    return control


def restore_window_geometry(frame, settings=None):
    if settings is None:
        settings = load_settings()

    position = settings.get("window_position")
    size = settings.get("window_size")

    if isinstance(size, list) and len(size) == 2:
        width, height = int(size[0]), int(size[1])
        if width > 100 and height > 100:
            frame.SetSize((width, height))

    if isinstance(position, list) and len(position) == 2:
        x, y = int(position[0]), int(position[1])
        frame.SetPosition((x, y))

    if settings.get("window_maximized", False):
        frame.Maximize(True)


def set_column_image_on_left(list_ctrl, column_index):
    """Force a wx.ListCtrl header image to appear before its text on Windows."""
    if wx.Platform != "__WXMSW__":
        return

    LVM_GETHEADER = 0x101F
    HDM_FIRST = 0x1200
    HDM_GETITEMW = HDM_FIRST + 11
    HDM_SETITEMW = HDM_FIRST + 12

    HDI_FORMAT = 0x0004
    HDF_BITMAP_ON_RIGHT = 0x1000

    class HDITEMW(ctypes.Structure):
        _fields_ = [
            ("mask", wintypes.UINT),
            ("cxy", ctypes.c_int),
            ("pszText", wintypes.LPWSTR),
            ("hbm", wintypes.HBITMAP),
            ("cchTextMax", ctypes.c_int),
            ("fmt", ctypes.c_int),
            ("lParam", wintypes.LPARAM),
            ("iImage", ctypes.c_int),
            ("iOrder", ctypes.c_int),
            ("type", wintypes.UINT),
            ("pvFilter", ctypes.c_void_p),
            ("state", wintypes.UINT),
        ]

    send_message = ctypes.windll.user32.SendMessageW
    send_message.restype = wintypes.LPARAM

    list_hwnd = list_ctrl.GetHandle()
    header_hwnd = send_message(list_hwnd, LVM_GETHEADER, 0, 0)

    if not header_hwnd:
        return

    item = HDITEMW()
    item.mask = HDI_FORMAT

    if send_message(header_hwnd, HDM_GETITEMW, column_index, ctypes.byref(item)):
        item.fmt &= ~HDF_BITMAP_ON_RIGHT
        send_message(header_hwnd, HDM_SETITEMW, column_index, ctypes.byref(item))