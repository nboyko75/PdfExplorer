import ctypes
import os
import tempfile
import xml.etree.ElementTree as ET

import wx


class IconManager:
    """Load an SVG sprite once and render named symbols as wx.Bitmap."""

    DEFAULT_ICON_INDEX = {
        "save": 0,
        "open": 1,
        "delete": 2,
        "ok": 3,
    }

    def __init__(self, sprite_path=None, icon_index=None):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.sprite_path = sprite_path or os.path.join(project_root, "images", "icons01.svg")

        if not os.path.isfile(self.sprite_path):
            raise FileNotFoundError(self.sprite_path)

        self._tree = ET.parse(self.sprite_path)
        self._root = self._tree.getroot()
        self._view_box = self._root.attrib.get("viewBox", "0 0 64 64")
        self._groups = [child for child in list(self._root) if self._local_name(child.tag) == "g"]
        if not self._groups:
            raise RuntimeError("No top-level <g> symbols found in sprite")

        self._bitmap_cache = {}
        mapping = dict(self.DEFAULT_ICON_INDEX)
        if icon_index:
            mapping.update(icon_index)
        self.icon_index = self._build_index(mapping)

    @staticmethod
    def _local_name(tag):
        if not isinstance(tag, str):
            return ""
        return tag.split("}", 1)[-1]

    def _build_index(self, mapping):
        result = {}
        for name, symbol_ref in mapping.items():
            normalized_name = str(name).strip().lower()
            if isinstance(symbol_ref, int):
                if symbol_ref < 0 or symbol_ref >= len(self._groups):
                    raise IndexError(f"Icon index {symbol_ref} for '{name}' is out of range")
                symbol = self._groups[symbol_ref]
            elif isinstance(symbol_ref, str):
                symbol = None
                for group in self._groups:
                    if group.attrib.get("id") == symbol_ref:
                        symbol = group
                        break
                if symbol is None:
                    raise KeyError(f"Symbol id '{symbol_ref}' not found for '{name}'")
            else:
                raise TypeError("Icon mapping values must be int index or str symbol id")

            result[normalized_name] = symbol
        return result

    def _build_symbol_svg(self, symbol):
        group_markup = ET.tostring(symbol, encoding="unicode")
        return (
            "<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            f"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"{self._view_box}\">"
            f"{group_markup}"
            "</svg>"
        )

    @staticmethod
    def _normalize_size(size):
        if not (isinstance(size, tuple) and len(size) == 2):
            raise TypeError("size must be a tuple(width, height)")
        return max(1, int(size[0])), max(1, int(size[1]))

    @staticmethod
    def _render_svg_to_bitmap(svg_markup, size):
        try:
            import wx.svg as wxsvg
        except Exception as exc:
            raise RuntimeError("wx.svg module is unavailable") from exc

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False, encoding="utf-8") as handle:
                handle.write(svg_markup)
                temp_path = handle.name

            svg_image = wxsvg.SVGimage.CreateFromFile(temp_path)
            if svg_image is None:
                raise RuntimeError("Unable to load generated SVG")

            bitmap = svg_image.ConvertToScaledBitmap(wx.Size(size[0], size[1]))
            if bitmap is None or not bitmap.IsOk():
                raise RuntimeError("Unable to render generated SVG")
            return bitmap
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def get_bitmap(self, icon_name, size=(16, 16)):
        if icon_name not in self.icon_index:
            raise KeyError(f"Unknown icon name: {icon_name}")

        normalized_size = self._normalize_size(size)
        cache_key = (icon_name, normalized_size)
        cached = self._bitmap_cache.get(cache_key)
        if cached is not None and cached.IsOk():
            return cached

        symbol = self.icon_index[icon_name]
        symbol_svg = self._build_symbol_svg(symbol)
        bitmap = self._render_svg_to_bitmap(symbol_svg, normalized_size)
        self._bitmap_cache[cache_key] = bitmap
        return bitmap


def can_preview_image(path):
    if not path or not os.path.isfile(path):
        return False
    try:
        return bool(wx.Image.CanRead(path))
    except Exception:
        return False


def refresh_image_preview_bitmap(owner):
    if owner.current_image_preview is None or not owner.current_image_preview.IsOk():
        return

    target_widget = getattr(owner, "pdf_preview_container", owner.pdf_preview)
    target_w, target_h = target_widget.GetClientSize()
    if target_w <= 1 or target_h <= 1:
        return

    src_w, src_h = owner.current_image_preview.GetSize()
    if src_w <= 0 or src_h <= 0:
        return

    fit_scale = min(target_w / src_w, target_h / src_h, 1.0)
    image_zoom = max(0.1, float(getattr(owner, "current_image_zoom", 1.0)))
    scale = fit_scale * image_zoom
    render_w = max(1, int(src_w * scale))
    render_h = max(1, int(src_h * scale))

    if render_w == src_w and render_h == src_h:
        render_image = owner.current_image_preview
    else:
        render_image = owner.current_image_preview.Scale(render_w, render_h, wx.IMAGE_QUALITY_HIGH)

    owner.pdf_preview.SetMinSize((render_w, render_h))
    owner.pdf_preview.SetBitmap(wx.Bitmap(render_image))
    _update_image_preview_viewport(owner, render_w, render_h)


def _update_image_preview_viewport(owner, image_w, image_h):
    container = getattr(owner, "pdf_preview_container", None)
    if container is None:
        return

    client_w, client_h = container.GetClientSize()
    if client_w <= 1 or client_h <= 1:
        return

    virtual_w = max(client_w, image_w)
    virtual_h = max(client_h, image_h)
    container.SetVirtualSize((virtual_w, virtual_h))

    pos_x = max((client_w - image_w) // 2, 0)
    pos_y = max((client_h - image_h) // 2, 0)
    owner.pdf_preview.SetPosition((pos_x, pos_y))
    owner.pdf_preview.SetSize((image_w, image_h))

    container.Layout()


def show_image_preview(owner, path, tr_func):
    try:
        image = wx.Image(path, wx.BITMAP_TYPE_ANY)
        if not image.IsOk():
            raise RuntimeError(tr_func("no_preview_available"))
        owner.current_image_preview = image
    except Exception as exc:
        owner.current_image_preview = None
        owner.preview_text.SetValue(tr_func("unable_preview_file", exc=exc))
        owner.preview_text.Show(True)
        owner.pdf_pages_panel.Hide()
        owner.pdf_preview_container.Hide()
        owner.filePreview.Layout()
        return

    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Hide()
    owner.pdf_preview_container.Show(True)
    owner.filePreview.Layout()
    refresh_image_preview_bitmap(owner)


def rotate_image_file(path, clockwise=True):
    if not can_preview_image(path):
        raise RuntimeError("No preview available for this item.")

    image = wx.Image(path, wx.BITMAP_TYPE_ANY)
    if not image.IsOk():
        raise RuntimeError(f"Unable to load image: {path}")

    rotated = image.Rotate90(clockwise=clockwise)
    if not rotated.IsOk():
        raise RuntimeError(f"Unable to rotate image: {path}")

    if not rotated.SaveFile(path):
        raise RuntimeError(f"Unable to save rotated image: {path}")


# ---------------------------------------------------------------------------
# Bitmap / icon helpers
# ---------------------------------------------------------------------------

def create_bitmap_button(parent, art_id, tooltip=None, icon_size=(24, 24), button_size=(32, 32)):
    bmp = wx.ArtProvider.GetBitmap(art_id, wx.ART_TOOLBAR, icon_size)
    button = wx.BitmapButton(parent, bitmap=bmp, size=button_size)
    if tooltip:
        button.SetToolTip(tooltip)
    return button


def create_bitmap_button2(parent, icon_manager, icon_name, tooltip=None, icon_size=(24, 24), button_size=(32, 32)):
    bmp = icon_manager.get_bitmap(icon_name, size=icon_size)
    button = wx.BitmapButton(parent, bitmap=bmp, size=button_size)
    if tooltip:
        button.SetToolTip(tooltip)
    return button


def create_joined_art_bitmap(art_id, client=wx.ART_TOOLBAR, size=(24, 24)):
    first = wx.ArtProvider.GetBitmap(art_id, client, size)
    second = wx.ArtProvider.GetBitmap(art_id, client, size)
    if not first.IsOk():
        return first
    if not second.IsOk():
        return first

    width, height = size
    joined = wx.Bitmap(width, height, depth=32)
    joined.UseAlpha()
    dc = wx.MemoryDC(joined)
    dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
    dc.Clear()

    offset_x = max(3, width // 3)
    dc.DrawBitmap(first, 0, 0, True)
    dc.DrawBitmap(second, offset_x, 0, True)
    dc.SelectObject(wx.NullBitmap)
    return joined


def hicon_to_bitmap(hicon, size=16):
    """Render a Windows HICON handle into a wx.Bitmap (drawn on white BG)."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ('biSize', ctypes.c_uint32),
            ('biWidth', ctypes.c_int32),
            ('biHeight', ctypes.c_int32),
            ('biPlanes', ctypes.c_uint16),
            ('biBitCount', ctypes.c_uint16),
            ('biCompression', ctypes.c_uint32),
            ('biSizeImage', ctypes.c_uint32),
            ('biXPelsPerMeter', ctypes.c_int32),
            ('biYPelsPerMeter', ctypes.c_int32),
            ('biClrUsed', ctypes.c_uint32),
            ('biClrImportant', ctypes.c_uint32),
        ]

    hdc = user32.GetDC(None)
    hdc_mem = gdi32.CreateCompatibleDC(hdc)

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(bmi)
    bmi.biWidth = size
    bmi.biHeight = -size  # top-down DIB
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0

    pbits = ctypes.c_void_p()
    hbm = gdi32.CreateDIBSection(hdc_mem, ctypes.byref(bmi), 0,
                                 ctypes.byref(pbits), None, 0)
    old_obj = gdi32.SelectObject(hdc_mem, hbm)

    gdi32.PatBlt(hdc_mem, 0, 0, size, size, 0x00F00021)  # WHITENESS
    user32.DrawIconEx(hdc_mem, 0, 0, ctypes.c_void_p(hicon),
                      size, size, 0, None, 3)  # DI_NORMAL = 3

    buf = (ctypes.c_ubyte * (size * size * 4))()
    ctypes.memmove(buf, pbits, size * size * 4)

    gdi32.SelectObject(hdc_mem, old_obj)
    gdi32.DeleteObject(hbm)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(None, hdc)

    # GDI gives BGRA; wx.Image wants RGB bytes
    rgb = bytearray(size * size * 3)
    for i in range(size * size):
        rgb[i * 3]     = buf[i * 4 + 2]  # R
        rgb[i * 3 + 1] = buf[i * 4 + 1]  # G
        rgb[i * 3 + 2] = buf[i * 4]      # B

    img = wx.Image(size, size)
    img.SetData(bytes(rgb))
    return img.ConvertToBitmap()


def get_shell_bitmap(fake_path, file_attr):
    """Return a 16x16 wx.Bitmap for *fake_path* using SHGetFileInfo, or None."""
    SHGFI_ICON              = 0x000000100
    SHGFI_SMALLICON         = 0x000000001
    SHGFI_USEFILEATTRIBUTES = 0x000000010

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon",         ctypes.c_void_p),
            ("iIcon",         ctypes.c_int),
            ("dwAttributes",  ctypes.c_uint),
            ("szDisplayName", ctypes.c_wchar * 260),
            ("szTypeName",    ctypes.c_wchar * 80),
        ]

    try:
        shfi = SHFILEINFOW()
        flags = SHGFI_ICON | SHGFI_SMALLICON | SHGFI_USEFILEATTRIBUTES
        ret = ctypes.windll.shell32.SHGetFileInfoW(
            fake_path, file_attr, ctypes.byref(shfi), ctypes.sizeof(shfi), flags
        )
        if ret and shfi.hIcon:
            bmp = hicon_to_bitmap(shfi.hIcon, 16)
            ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(shfi.hIcon))
            if bmp and bmp.IsOk():
                return bmp
    except Exception:
        pass
    return None


def get_extension_color(ext):
    value = 0
    for index, ch in enumerate(ext):
        value += (index + 17) * ord(ch)
    red = 80 + (value % 120)
    green = 70 + ((value // 7) % 130)
    blue = 80 + ((value // 13) % 120)
    return wx.Colour(red, green, blue)


def create_extension_icon_bitmap(ext):
    """Return a 16x16 wx.Bitmap for the given file extension.

    Tries to fetch the real Windows shell icon first; falls back to
    a coloured square with a two-letter abbreviation.
    """
    size = 16
    SHGFI_ICON              = 0x000000100
    SHGFI_SMALLICON         = 0x000000001
    SHGFI_USEFILEATTRIBUTES = 0x000000010
    FILE_ATTRIBUTE_NORMAL   = 0x00000080

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon",         ctypes.c_void_p),
            ("iIcon",         ctypes.c_int),
            ("dwAttributes",  ctypes.c_uint),
            ("szDisplayName", ctypes.c_wchar * 260),
            ("szTypeName",    ctypes.c_wchar * 80),
        ]

    try:
        shfi = SHFILEINFOW()
        fake_path = "file" + ext  # e.g. "file.pdf"
        flags = SHGFI_ICON | SHGFI_SMALLICON | SHGFI_USEFILEATTRIBUTES
        ret = ctypes.windll.shell32.SHGetFileInfoW(
            fake_path, FILE_ATTRIBUTE_NORMAL,
            ctypes.byref(shfi), ctypes.sizeof(shfi), flags
        )
        if ret and shfi.hIcon:
            bmp = hicon_to_bitmap(shfi.hIcon, size)
            ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(shfi.hIcon))
            if bmp and bmp.IsOk():
                return bmp
    except Exception:
        pass

    # --- fallback: coloured square with two-letter abbreviation ---
    bmp = wx.Bitmap(size, size, depth=32)
    bmp.UseAlpha()

    dc = wx.MemoryDC(bmp)
    dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
    dc.Clear()

    color = get_extension_color(ext)
    dc.SetBrush(wx.Brush(color))
    dc.SetPen(wx.Pen(color))
    dc.DrawRoundedRectangle(0, 0, size, size, 3)

    text = (ext[1:3] if ext.startswith(".") else ext[:2]).upper() or "?"
    font = wx.Font(7, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
    dc.SetFont(font)
    dc.SetTextForeground(wx.Colour(255, 255, 255))
    tw, th = dc.GetTextExtent(text)
    dc.DrawText(text, max(0, (size - tw) // 2), max(0, (size - th) // 2))

    dc.SelectObject(wx.NullBitmap)
    return bmp


def init_list_images(owner):
    owner.list_images = wx.ImageList(16, 16)
    owner.list_icon_cache = {}

    FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    FILE_ATTRIBUTE_NORMAL    = 0x00000080

    folder_bmp = get_shell_bitmap("folder", FILE_ATTRIBUTE_DIRECTORY)
    if not folder_bmp:
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
    if not folder_bmp.IsOk():
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, (16, 16))

    file_bmp = get_shell_bitmap("file", FILE_ATTRIBUTE_NORMAL)
    if not file_bmp:
        file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
    if not file_bmp.IsOk():
        file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (16, 16))

    owner.list_icon_cache["__folder__"] = owner.list_images.Add(folder_bmp)
    owner.list_icon_cache["__file__"] = owner.list_images.Add(file_bmp)
    owner.list.SetImageList(owner.list_images, wx.IMAGE_LIST_SMALL)


def get_list_icon_index(owner, path, is_dir):
    if is_dir:
        return owner.list_icon_cache["__folder__"]

    ext = os.path.splitext(path)[1].lower()
    if not ext:
        return owner.list_icon_cache["__file__"]

    cached = owner.list_icon_cache.get(ext)
    if cached is not None:
        return cached

    bmp = create_extension_icon_bitmap(ext)
    owner.list_icon_cache[ext] = owner.list_images.Add(bmp)
    return owner.list_icon_cache[ext]
