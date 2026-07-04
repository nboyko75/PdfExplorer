import os
import wx
from window_tools import load_settings, update_settings

try:
    import fitz
except ImportError:
    fitz = None


DEFAULT_OPTIMIZE_IMAGE_WIDTH = 1200
DEFAULT_OPTIMIZE_IMAGE_QUALITY = 70
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


def optimize_pdf(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    target_width, target_quality = _get_optimize_pdf_settings()

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

                target_height = max(1, int(round(source_pix.height * (target_width / source_pix.width))))

                scaled_pix = source_pix
                if source_pix.width != target_width:
                    scaled_pix = fitz.Pixmap(source_pix, target_width, target_height)

                try:
                    jpeg_bytes = scaled_pix.tobytes("jpg", jpg_quality=target_quality)
                except TypeError:
                    jpeg_bytes = scaled_pix.tobytes("jpg")

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
