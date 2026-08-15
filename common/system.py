import ctypes

FILE_ATTRIBUTE_HIDDEN = 0x02

def is_hidden(path):
    attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    if attrs == -1:
        raise FileNotFoundError(path)

    return bool(attrs & FILE_ATTRIBUTE_HIDDEN)