import os
import wx
from controls.window_tools import load_settings, update_settings

try:
    import fitz
except ImportError:
    fitz = None


DEFAULT_OPTIMIZE_IMAGE_WIDTH = 1400
DEFAULT_OPTIMIZE_IMAGE_QUALITY = 150
DEFAULT_COLOR_TARGET_DPI = 120
DEFAULT_COLOR_THRESHOLD_DPI = 180
DEFAULT_COLOR_COMPRESSION = "jpeg"
DEFAULT_COLOR_QUALITY = "low"
DEFAULT_MONO_TARGET_DPI = 120
DEFAULT_MONO_THRESHOLD_DPI = 180
DEFAULT_MONO_COMPRESSION = "ccitt_group3"
DEFAULT_COMPRESS_ONLY_IF_RESIZED = True
_PDF_SESSION_BYTES = {}


def _get_optimize_pdf_settings():
    settings = load_settings()

    width = settings.get("optimize_pdf_image_width", DEFAULT_OPTIMIZE_IMAGE_WIDTH)
    quality = settings.get("optimize_pdf_image_quality", DEFAULT_OPTIMIZE_IMAGE_QUALITY)

    try:
        width = int(width)
    except (TypeError, ValueError):
        width = DEFAULT_OPTIMIZE_IMAGE_WIDTH

    try:
        quality = int(quality)
    except (TypeError, ValueError):
        quality = DEFAULT_OPTIMIZE_IMAGE_QUALITY

    width = max(1, width)
    quality = min(100, max(1, quality))

    update_settings(
        {
            "optimize_pdf_image_width": width,
            "optimize_pdf_image_quality": quality,
        }
    )
    return width, quality


def _normalize_dpi(value, default_value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default_value
    return max(1, value)


def _normalize_bool(value, default_value):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default_value


def _normalize_choice(value, default_value, allowed_values):
    if not isinstance(value, str):
        return default_value
    normalized = value.strip().lower()
    if normalized in allowed_values:
        return normalized
    return default_value


def _normalize_color_quality(value):
    if isinstance(value, int):
        return min(100, max(1, value))

    if isinstance(value, str):
        normalized = value.strip().lower()
        quality_map = {
            "low": 45,
            "medium": 65,
            "high": 85,
        }
        if normalized in quality_map:
            return quality_map[normalized]
        try:
            return min(100, max(1, int(normalized)))
        except (TypeError, ValueError):
            return _normalize_color_quality(DEFAULT_COLOR_QUALITY)

    return _normalize_color_quality(DEFAULT_COLOR_QUALITY)


def _get_optimize_pdf_advanced_settings():
    settings = load_settings()

    color_target_dpi = _normalize_dpi(
        settings.get("optimize_pdf_color_target_dpi", DEFAULT_COLOR_TARGET_DPI),
        DEFAULT_COLOR_TARGET_DPI,
    )
    color_threshold_dpi = _normalize_dpi(
        settings.get("optimize_pdf_color_threshold_dpi", DEFAULT_COLOR_THRESHOLD_DPI),
        DEFAULT_COLOR_THRESHOLD_DPI,
    )
    color_compression = _normalize_choice(
        settings.get("optimize_pdf_color_compression", DEFAULT_COLOR_COMPRESSION),
        DEFAULT_COLOR_COMPRESSION,
        {"jpeg", "png"},
    )
    color_quality = _normalize_color_quality(
        settings.get("optimize_pdf_color_quality", DEFAULT_COLOR_QUALITY)
    )

    mono_target_dpi = _normalize_dpi(
        settings.get("optimize_pdf_mono_target_dpi", DEFAULT_MONO_TARGET_DPI),
        DEFAULT_MONO_TARGET_DPI,
    )
    mono_threshold_dpi = _normalize_dpi(
        settings.get("optimize_pdf_mono_threshold_dpi", DEFAULT_MONO_THRESHOLD_DPI),
        DEFAULT_MONO_THRESHOLD_DPI,
    )
    mono_compression = _normalize_choice(
        settings.get("optimize_pdf_mono_compression", DEFAULT_MONO_COMPRESSION),
        DEFAULT_MONO_COMPRESSION,
        {"ccitt_group3", "ccitt_group4", "png"},
    )
    compress_only_if_resized = _normalize_bool(
        settings.get(
            "optimize_pdf_compress_only_if_resized",
            DEFAULT_COMPRESS_ONLY_IF_RESIZED,
        ),
        DEFAULT_COMPRESS_ONLY_IF_RESIZED,
    )

    update_settings(
        {
            "optimize_pdf_color_target_dpi": color_target_dpi,
            "optimize_pdf_color_threshold_dpi": color_threshold_dpi,
            "optimize_pdf_color_compression": color_compression,
            "optimize_pdf_color_quality": color_quality,
            "optimize_pdf_mono_target_dpi": mono_target_dpi,
            "optimize_pdf_mono_threshold_dpi": mono_threshold_dpi,
            "optimize_pdf_mono_compression": mono_compression,
            "optimize_pdf_compress_only_if_resized": compress_only_if_resized,
        }
    )

    return {
        "color_target_dpi": color_target_dpi,
        "color_threshold_dpi": color_threshold_dpi,
        "color_compression": color_compression,
        "color_quality": color_quality,
        "mono_target_dpi": mono_target_dpi,
        "mono_threshold_dpi": mono_threshold_dpi,
        "mono_compression": mono_compression,
        "compress_only_if_resized": compress_only_if_resized,
    }


def _get_max_image_dpi(page, xref, pixel_width, pixel_height):
    max_dpi = 0.0
    try:
        rects = page.get_image_rects(xref)
    except Exception:
        rects = []

    for rect in rects:
        if rect.width <= 0 or rect.height <= 0:
            continue
        dpi_x = (float(pixel_width) * 72.0) / float(rect.width)
        dpi_y = (float(pixel_height) * 72.0) / float(rect.height)
        max_dpi = max(max_dpi, dpi_x, dpi_y)

    return max_dpi


def _get_target_size_from_dpi(source_pix, target_dpi, source_dpi):
    if source_dpi <= 0:
        return source_pix.width, source_pix.height

    scale = float(target_dpi) / float(source_dpi)
    if scale >= 1.0:
        return source_pix.width, source_pix.height

    target_width = max(1, int(round(source_pix.width * scale)))
    target_height = max(1, int(round(source_pix.height * scale)))
    return target_width, target_height


def _encode_pixmap_bytes(scaled_pix, is_monochrome, advanced_settings, fallback_quality):
    if is_monochrome:
        mono_compression = advanced_settings["mono_compression"]

        # PyMuPDF does not expose direct CCITT encoding for replace_image streams.
        # PNG keeps monochrome scans lossless and compact.
        if mono_compression in {"ccitt_group3", "ccitt_group4", "png"}:
            return scaled_pix.tobytes("png")

    color_compression = advanced_settings["color_compression"]
    if color_compression == "png":
        return scaled_pix.tobytes("png")

    color_quality = advanced_settings["color_quality"]
    try:
        return scaled_pix.tobytes("jpg", jpg_quality=color_quality)
    except TypeError:
        try:
            return scaled_pix.tobytes("jpg", jpg_quality=fallback_quality)
        except TypeError:
            return scaled_pix.tobytes("jpg")


def is_pdf_file(path):
    return isinstance(path, str) and path.lower().endswith(".pdf")


def _normalize_pdf_session_path(path):
    return os.path.normpath(path)


def _get_pdf_session_bytes(path):
    return _PDF_SESSION_BYTES.get(_normalize_pdf_session_path(path))


def _set_pdf_session_bytes(path, pdf_bytes):
    _PDF_SESSION_BYTES[_normalize_pdf_session_path(path)] = pdf_bytes


def has_unsaved_pdf_changes(path):
    return isinstance(path, str) and _normalize_pdf_session_path(path) in _PDF_SESSION_BYTES


def discard_pdf_changes(path):
    if isinstance(path, str):
        _PDF_SESSION_BYTES.pop(_normalize_pdf_session_path(path), None)


def _read_pdf_bytes(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    session_bytes = _get_pdf_session_bytes(path)
    if session_bytes is not None:
        return session_bytes

    with open(path, "rb") as handle:
        return handle.read()


def _open_pdf_document(path):
    return fitz.open(stream=_read_pdf_bytes(path), filetype="pdf")


def _store_pdf_document(path, doc, **save_kwargs):
    _set_pdf_session_bytes(path, doc.tobytes(**save_kwargs))
    return path


def save_pdf(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    session_bytes = _get_pdf_session_bytes(path)
    if session_bytes is None:
        return path

    with open(path, "wb") as handle:
        handle.write(session_bytes)

    discard_pdf_changes(path)
    return path


def get_pdf_page_count(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        return len(doc)
    finally:
        doc.close()


def move_pdf_page(path, from_index, to_index):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        page_count = len(doc)
        if not 0 <= from_index < page_count:
            raise ValueError(f"Page index {from_index} is out of range")
        if not 0 <= to_index < page_count:
            raise ValueError(f"Target index {to_index} is out of range")
        if from_index == to_index:
            return path

        order = list(range(page_count))
        page = order.pop(from_index)
        insert_at = to_index - 1 if from_index < to_index else to_index
        order.insert(insert_at, page)

        new_doc = fitz.open()
        try:
            for index in order:
                new_doc.insert_pdf(doc, from_page=index, to_page=index)

            return _store_pdf_document(path, new_doc, garbage=4, deflate=True, clean=True)
        finally:
            if not new_doc.is_closed:
                new_doc.close()
    finally:
        doc.close()


def rotate_pdf(path, angle=90):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        for page in doc:
            page.set_rotation((page.rotation + angle) % 360)

        return _store_pdf_document(path, doc, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def rotate_pdf_page(path, page_index, angle=90):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        if not 0 <= page_index < len(doc):
            raise ValueError(f"Page index {page_index} is out of range")
        page = doc[page_index]
        page.set_rotation((page.rotation + angle) % 360)

        return _store_pdf_document(path, doc, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def remove_pdf_page(path, page_index):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        if not 0 <= page_index < len(doc):
            raise ValueError(f"Page index {page_index} is out of range")

        doc.delete_page(page_index)
        return _store_pdf_document(path, doc, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def optimize_pdf(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    target_width, target_quality = _get_optimize_pdf_settings()
    advanced_settings = _get_optimize_pdf_advanced_settings()

    doc = _open_pdf_document(path)
    try:
        processed_xrefs = set()
        for page in doc:
            page_images = page.get_images(full=True)
            for image_info in page_images:
                xref = image_info[0]
                if xref in processed_xrefs:
                    continue
                processed_xrefs.add(xref)

                try:
                    pix = fitz.Pixmap(doc, xref)
                except Exception:
                    continue

                source_pix = pix
                if pix.alpha:
                    source_pix = fitz.Pixmap(fitz.csRGB, pix)

                if source_pix.width <= 0 or source_pix.height <= 0:
                    if source_pix is not pix:
                        source_pix = None
                    pix = None
                    continue

                max_dpi = _get_max_image_dpi(page, xref, source_pix.width, source_pix.height)
                bpc = image_info[4] if len(image_info) > 4 else None
                is_monochrome = bpc == 1

                if max_dpi > 0:
                    if is_monochrome:
                        target_dpi = advanced_settings["mono_target_dpi"]
                        threshold_dpi = advanced_settings["mono_threshold_dpi"]
                    else:
                        target_dpi = advanced_settings["color_target_dpi"]
                        threshold_dpi = advanced_settings["color_threshold_dpi"]

                    should_resize = max_dpi > threshold_dpi
                    if should_resize:
                        target_w, target_h = _get_target_size_from_dpi(source_pix, target_dpi, max_dpi)
                    else:
                        target_w, target_h = source_pix.width, source_pix.height
                else:
                    # Fallback for images where display rectangles are unavailable.
                    target_w = target_width
                    target_h = max(1, int(round(source_pix.height * (target_w / source_pix.width))))

                scaled_pix = source_pix
                resized = source_pix.width != target_w or source_pix.height != target_h
                if resized:
                    scaled_pix = fitz.Pixmap(source_pix, target_w, target_h)

                if advanced_settings["compress_only_if_resized"] and not resized:
                    if scaled_pix is not source_pix:
                        scaled_pix = None
                    if source_pix is not pix:
                        source_pix = None
                    pix = None
                    continue

                jpeg_bytes = _encode_pixmap_bytes(
                    scaled_pix,
                    is_monochrome,
                    advanced_settings,
                    target_quality,
                )

                try:
                    page.replace_image(xref, stream=jpeg_bytes)
                except Exception:
                    pass

                if scaled_pix is not source_pix:
                    scaled_pix = None
                if source_pix is not pix:
                    source_pix = None
                pix = None

        return _store_pdf_document(path, doc, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()


def ajust_page_width(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    new_doc = fitz.open()
    try:
        if len(doc) == 0:
            return path

        widths = []
        for page in doc:
            page_width = int(round(page.rect.width))
            if page_width > 0:
                widths.append(page_width)

        if not widths:
            return path

        width_counts = {}
        for width in widths:
            width_counts[width] = width_counts.get(width, 0) + 1

        target_width = max(width_counts.items(), key=lambda item: (item[1], item[0]))[0]

        for page_index in range(len(doc)):
            page = doc[page_index]
            src_width = float(page.rect.width)
            src_height = float(page.rect.height)
            if src_width <= 0 or src_height <= 0:
                continue

            scale = target_width / src_width
            target_height = max(1.0, src_height * scale)

            new_page = new_doc.new_page(width=float(target_width), height=target_height)
            new_page.show_pdf_page(new_page.rect, doc, page_index)

        return _store_pdf_document(path, new_doc, garbage=4, deflate=True, clean=True)
    finally:
        doc.close()
        if not new_doc.is_closed:
            new_doc.close()


def get_pdf_page_previews(path, max_height=300, max_pages=None):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = _open_pdf_document(path)
    try:
        page_count = len(doc)
        shown_pages = page_count if max_pages is None else min(page_count, max_pages)
        previews = []

        for index in range(shown_pages):
            page = doc[index]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            rgb_pix = pix if pix.n == 3 and not pix.alpha else fitz.Pixmap(fitz.csRGB, pix)
            bitmap = wx.Bitmap.FromBuffer(rgb_pix.width, rgb_pix.height, rgb_pix.samples)
            image = bitmap.ConvertToImage()
            if image.GetHeight() > max_height:
                target_width = max(1, int(round(image.GetWidth() * (max_height / image.GetHeight()))))
                image = image.Rescale(target_width, max_height)

            previews.append((index + 1, image.ConvertToBitmap()))

        return page_count, shown_pages, previews
    finally:
        doc.close()
