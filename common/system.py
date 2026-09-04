import ctypes
import os

FILE_ATTRIBUTE_HIDDEN = 0x02


def move_to_recycle_bin(paths):
    if os.name != "nt":
        return False

    normalized_paths = []
    for path in paths or []:
        if isinstance(path, str) and os.path.exists(path):
            normalized_paths.append(path)

    if not normalized_paths:
        return False

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", ctypes.c_void_p),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", ctypes.c_int),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    file_buffer = "\0".join(normalized_paths) + "\0\0"
    shell32 = ctypes.windll.shell32
    operation = SHFILEOPSTRUCTW()
    operation.hwnd = None
    operation.wFunc = 0x0003
    operation.pFrom = file_buffer
    operation.pTo = None
    operation.fFlags = 0x0004 | 0x0010 | 0x0040
    result = shell32.SHFileOperationW(ctypes.byref(operation))
    if result == 1223:
        return False
    if result != 0:
        raise OSError(f"SHFileOperationW failed with code {result}")
    return not bool(operation.fAnyOperationsAborted)


def is_hidden(path):
    if not path:
        return False

    try:
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    except Exception:
        return False

    if attrs == -1:
        return False

    return bool(attrs & FILE_ATTRIBUTE_HIDDEN)