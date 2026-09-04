import ctypes
import contextlib
import os
import wx


class IconManager:
    """Load preview toolbar icons from BMP files and cache scaled bitmaps."""

    DEFAULT_ICON_FILES = {
        "save": "save.bmp",
        "delete": "delete.bmp",
        "ok": "ok.bmp",
        "up": "up.bmp",
        "rotation": "rotation.bmp",
        "scan": "scan.bmp",
        "cancel": "cancel.bmp",
        "copy": "copy.bmp",
        "file_view": "file_view.bmp",
        "load_all": "load_all.bmp",
        "add_to_archive": "add_to_archive.bmp",
        "extract_from_archive": "extract_from_archive.bmp",
        "setup": "setup.bmp",
        "recycle_bin": "recycle_bin.bmp",
        "favorite": "favorite.bmp",
        "standard_shortcuts": "standard_shortcuts.bmp",
        "standard_shortcuts_pressed": "standard_shortcuts_pressed.bmp",
        "add_to_favorites": "add_to_favorite.bmp",
        "remove_from_favorites": "remove_from_favorite.bmp",
        "remove_from_favorite": "remove_from_favorite.bmp",
        "double_up": "double_up.bmp",
        "double_down": "double_down.bmp",
    }

    def __init__(self, images_dir=None, icon_files=None):
        project_root = os.path.dirname(os.path.dirname(__file__))
        self.images_dir = images_dir or os.path.join(project_root, "images")

        self._bitmap_cache = {}
        mapping = dict(self.DEFAULT_ICON_FILES)
        if icon_files:
            mapping.update(icon_files)
        self.icon_files = self._build_index(mapping)

    def _build_index(self, mapping):
        result = {}
        for name, file_ref in mapping.items():
            normalized_name = str(name).strip().lower()
            icon_path = file_ref if os.path.isabs(file_ref) else os.path.join(self.images_dir, file_ref)
            if not os.path.isfile(icon_path):
                raise FileNotFoundError(icon_path)
            result[normalized_name] = icon_path
        return result

    def set_menu_icon(self, item, art_id=None, bitmap=None):
        if bitmap is None:
            bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
        if bitmap.IsOk():
            item.SetBitmap(bitmap)

    def set_menu_icon2(self, item, icon_name, bitmap=None):
        try:
            if bitmap is None:
                bitmap = self.get_bitmap(icon_name, size=(16, 16))
            if bitmap is not None and bitmap.IsOk():
                item.SetBitmap(bitmap)
        except (KeyError, AttributeError, RuntimeError, TypeError, OSError):
            pass

    @staticmethod
    def _normalize_size(size):
        if not (isinstance(size, tuple) and len(size) == 2):
            raise TypeError("size must be a tuple(width, height)")
        return max(1, int(size[0])), max(1, int(size[1]))

    @staticmethod
    def _load_bitmap(icon_path, size):
        image = wx.Image(icon_path, wx.BITMAP_TYPE_BMP)
        if image is None or not image.IsOk():
            raise RuntimeError(f"Unable to load bitmap: {icon_path}")

        if image.GetWidth() != size[0] or image.GetHeight() != size[1]:
            image = image.Scale(size[0], size[1], wx.IMAGE_QUALITY_HIGH)
            if not image.IsOk():
                raise RuntimeError(f"Unable to scale bitmap: {icon_path}")

        bitmap = image.ConvertToBitmap()
        if bitmap is None or not bitmap.IsOk():
            raise RuntimeError(f"Unable to create bitmap: {icon_path}")
        return bitmap

    def get_bitmap(self, icon_name, size=(16, 16)):
        if icon_name not in self.icon_files:
            raise KeyError(f"Unknown icon name: {icon_name}")

        normalized_size = self._normalize_size(size)
        cache_key = (icon_name, normalized_size)
        cached = self._bitmap_cache.get(cache_key)
        if cached is not None and cached.IsOk():
            return cached

        icon_path = self.icon_files[icon_name]
        bitmap = self._load_bitmap(icon_path, normalized_size)
        self._bitmap_cache[cache_key] = bitmap
        return bitmap


def ensure_owner_icon_manager(owner):
    """Return the owner's icon manager, creating and caching it when missing."""
    if owner is None:
        return None

    icon_manager = getattr(owner, "icon_manager", None)
    if icon_manager is None or not hasattr(icon_manager, "set_menu_icon2"):
        try:
            icon_manager = IconManager()
        except (AttributeError, FileNotFoundError, OSError, RuntimeError, TypeError):
            return None
        owner.icon_manager = icon_manager

    return icon_manager


def can_preview_image(path):
    if not path or not os.path.isfile(path):
        return False

    # Some libpng builds print profile/chromaticity warnings to native stderr
    # for otherwise readable PNG files.
    try:
        with _suppress_image_decode_warnings():
            if bool(wx.Image.CanRead(path)):
                return True
    except Exception:
        pass

    return _can_read_with_pillow(path)


@contextlib.contextmanager
def _suppress_native_stderr():
    original_stderr_fd = None
    try:
        original_stderr_fd = os.dup(2)
    except OSError:
        yield
        return

    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), 2)
            yield
    finally:
        try:
            os.dup2(original_stderr_fd, 2)
        finally:
            os.close(original_stderr_fd)


@contextlib.contextmanager
def _suppress_wx_logs():
    log_guard = None
    try:
        log_null_type = getattr(wx, "LogNull", None)
        if log_null_type is not None:
            log_guard = log_null_type()
        yield
    finally:
        # Keep the guard alive for the full context and release explicitly.
        log_guard = None


@contextlib.contextmanager
def _suppress_image_decode_warnings():
    with _suppress_native_stderr():
        with _suppress_wx_logs():
            yield


def _can_read_with_pillow(path):
    try:
        from PIL import Image
    except ImportError:
        return False

    try:
        with Image.open(path) as pil_image:
            pil_image.verify()
        return True
    except Exception:
        return False


def _load_image_with_wx(path):
    with _suppress_image_decode_warnings():
        return wx.Image(path, wx.BITMAP_TYPE_ANY)


def _convert_pillow_to_wx_image(pil_image):
    rgba_image = pil_image.convert("RGBA")
    width, height = rgba_image.size
    rgb_image = rgba_image.convert("RGB")
    alpha = rgba_image.getchannel("A")

    wx_image = wx.Image(width, height)
    wx_image.SetData(rgb_image.tobytes())
    wx_image.SetAlpha(alpha.tobytes())
    return wx_image


def _load_image_for_preview(path):
    image = _load_image_with_wx(path)
    if image is not None and image.IsOk():
        return image

    try:
        from PIL import Image, ImageOps
    except ImportError:
        return image

    try:
        with Image.open(path) as pil_image:
            sanitized = ImageOps.exif_transpose(pil_image)
            converted = _convert_pillow_to_wx_image(sanitized)
            if converted is not None and converted.IsOk():
                return converted
    except Exception:
        return image

    return image


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

    page_mode = getattr(owner, "pdf_page_view_mode", "1_page_tall")
    if page_mode == "1_page_tall":
        fit_scale = min(target_w / src_w, target_h / src_h, 1.0)
    elif page_mode == "2_pages_wide":
        fit_scale = min(target_w / src_w, (target_h * 0.85) / src_h, 1.0)
    else:
        fit_scale = min((target_w * 0.95) / src_w, target_h / src_h, 1.0)

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
        image = _load_image_for_preview(path)
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

    image = _load_image_for_preview(path)
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


def get_shell_bitmap(path, file_attr=0, use_file_attributes=False):
    """Return a 16x16 Windows shell icon for a real or hypothetical path."""
    SHGFI_ICON = 0x00000100
    SHGFI_SMALLICON = 0x00000001
    SHGFI_USEFILEATTRIBUTES = 0x00000010

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", ctypes.c_void_p),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", ctypes.c_uint),
            ("szDisplayName", ctypes.c_wchar * 260),
            ("szTypeName", ctypes.c_wchar * 80),
        ]

    try:
        shfi = SHFILEINFOW()
        flags = SHGFI_ICON | SHGFI_SMALLICON

        if use_file_attributes:
            flags |= SHGFI_USEFILEATTRIBUTES

        result = ctypes.windll.shell32.SHGetFileInfoW(
            path,
            file_attr,
            ctypes.byref(shfi),
            ctypes.sizeof(shfi),
            flags,
        )

        if result and shfi.hIcon:
            try:
                bitmap = hicon_to_bitmap(shfi.hIcon, 16)
            finally:
                ctypes.windll.user32.DestroyIcon(
                    ctypes.c_void_p(shfi.hIcon)
                )

            if bitmap and bitmap.IsOk():
                return bitmap
    except Exception:
        pass

    return None


def get_recycle_bin_icon_bitmap():
    """Return the stock Recycle Bin icon for Windows 10/11."""
    SIID_RECYCLER = 31
    SHGSI_ICON = 0x000000100
    SHGSI_SMALLICON = 0x000000001

    class SHSTOCKICONINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint),
            ("hIcon", ctypes.c_void_p),
            ("iSysImageIndex", ctypes.c_int),
            ("iIcon", ctypes.c_int),
            ("szPath", ctypes.c_wchar * 260),
        ]

    try:
        shell32 = ctypes.windll.shell32
        if not hasattr(shell32, "SHGetStockIconInfo"):
            return None

        info = SHSTOCKICONINFO()
        info.cbSize = ctypes.sizeof(info)
        flags = SHGSI_ICON | SHGSI_SMALLICON
        result = shell32.SHGetStockIconInfo(SIID_RECYCLER, flags, ctypes.byref(info))
        if result == 0 and info.hIcon:
            try:
                bitmap = hicon_to_bitmap(info.hIcon, 16)
            finally:
                ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(info.hIcon))
            if bitmap and bitmap.IsOk():
                return bitmap
    except Exception:
        pass

    return None


def Hidden_Image(image):
    if image is None or not image.IsOk():
        return image

    dimmed = image.Copy()
    if not dimmed.HasAlpha():
        dimmed.InitAlpha()

    width = dimmed.GetWidth()
    height = dimmed.GetHeight()

    for y in range(height):
        for x in range(width):
            red = dimmed.GetRed(x, y)
            green = dimmed.GetGreen(x, y)
            blue = dimmed.GetBlue(x, y)
            alpha = dimmed.GetAlpha(x, y)
            dimmed.SetRGB(
                x,
                y,
                max(0, red * 3 // 4),
                max(0, green * 3 // 4),
                max(0, blue * 3 // 4),
            )
            if dimmed.HasAlpha():
                dimmed.SetAlpha(x, y, alpha)

    return dimmed


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
    try:
        size = 16
        SHGFI_ICON = 0x000000100
        SHGFI_SMALLICON = 0x000000001
        SHGFI_USEFILEATTRIBUTES = 0x000000010
        FILE_ATTRIBUTE_NORMAL = 0x00000080

        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon", ctypes.c_void_p),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", ctypes.c_uint),
                ("szDisplayName", ctypes.c_wchar * 260),
                ("szTypeName", ctypes.c_wchar * 80),
            ]

        try:
            shfi = SHFILEINFOW()
            fake_path = "file" + ext  # e.g. "file.pdf"
            flags = SHGFI_ICON | SHGFI_SMALLICON | SHGFI_USEFILEATTRIBUTES
            ret = ctypes.windll.shell32.SHGetFileInfoW(
                fake_path,
                FILE_ATTRIBUTE_NORMAL,
                ctypes.byref(shfi),
                ctypes.sizeof(shfi),
                flags,
            )
            if ret and shfi.hIcon:
                bmp = hicon_to_bitmap(shfi.hIcon, size)
                ctypes.windll.user32.DestroyIcon(ctypes.c_void_p(shfi.hIcon))
                if bmp and bmp.IsOk():
                    return bmp
        except Exception:
            pass

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
    except Exception:
        return None


def init_list_images(owner):
    owner.list_images = wx.ImageList(16, 16)
    owner.list_icon_cache = {}

    FILE_ATTRIBUTE_DIRECTORY = 0x00000010
    FILE_ATTRIBUTE_NORMAL    = 0x00000080

    folder_bmp = get_shell_bitmap("folder", FILE_ATTRIBUTE_DIRECTORY, use_file_attributes=True)
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


def _ensure_list_image_cache(owner):
    if not hasattr(owner, "list_icon_cache") or owner.list_icon_cache is None:
        owner.list_icon_cache = {}
    if not hasattr(owner, "list_images") or owner.list_images is None:
        try:
            owner.list_images = wx.ImageList(16, 16)
            if hasattr(owner, "list") and owner.list is not None:
                owner.list.SetImageList(owner.list_images, wx.IMAGE_LIST_SMALL)
        except Exception:
            owner.list_images = None


def get_list_icon_index(owner, path, is_dir, is_hidden_item=False):
    _ensure_list_image_cache(owner)

    def _add_bitmap_to_cache(cache_key, bmp):
        if owner.list_images is None:
            owner.list_icon_cache[cache_key] = 0
            return 0
        owner.list_icon_cache[cache_key] = owner.list_images.Add(bmp)
        return owner.list_icon_cache[cache_key]

    if is_dir:
        cache_key = "__folder__|hidden" if is_hidden_item else "__folder__"
        cached = owner.list_icon_cache.get(cache_key)
        if cached is not None:
            return cached

        folder_bmp = get_shell_bitmap("folder", 0x00000010, use_file_attributes=True)
        if not folder_bmp:
            folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        if not folder_bmp.IsOk():
            folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, (16, 16))
        if is_hidden_item and folder_bmp is not None:
            folder_bmp = Hidden_Image(folder_bmp.ConvertToImage()).ConvertToBitmap()
        if folder_bmp is None:
            return 0
        return _add_bitmap_to_cache(cache_key, folder_bmp)

    ext = os.path.splitext(path)[1].lower()
    if not ext:
        cache_key = "__file__|hidden" if is_hidden_item else "__file__"
        cached = owner.list_icon_cache.get(cache_key)
        if cached is not None:
            return cached

        file_bmp = get_shell_bitmap("file", 0x00000080)
        if not file_bmp:
            file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
        if not file_bmp.IsOk():
            file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (16, 16))
        if is_hidden_item and file_bmp is not None:
            file_bmp = Hidden_Image(file_bmp.ConvertToImage()).ConvertToBitmap()
        if file_bmp is None:
            return 0
        return _add_bitmap_to_cache(cache_key, file_bmp)

    if ext == ".lnk":
        cache_key = f"{ext}|hidden" if is_hidden_item else ext
        cached = owner.list_icon_cache.get(cache_key)
        if cached is not None:
            return cached

        shortcut_bmp = get_shell_bitmap(path)
        if shortcut_bmp is None or not shortcut_bmp.IsOk():
            shortcut_bmp = create_extension_icon_bitmap(ext)
        if shortcut_bmp is None:
            return 0
        if is_hidden_item:
            shortcut_bmp = Hidden_Image(shortcut_bmp.ConvertToImage()).ConvertToBitmap()
        return _add_bitmap_to_cache(cache_key, shortcut_bmp)

    cache_key = f"{ext}|hidden" if is_hidden_item else ext
    cached = owner.list_icon_cache.get(cache_key)
    if cached is not None:
        return cached

    bmp = create_extension_icon_bitmap(ext)
    if bmp is None:
        return 0
    if is_hidden_item:
        bmp = Hidden_Image(bmp.ConvertToImage()).ConvertToBitmap()
    return _add_bitmap_to_cache(cache_key, bmp)
