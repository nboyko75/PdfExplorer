import os
import tempfile
import wx
from window_tools import load_settings, update_settings

try:
    import fitz
except ImportError:
    fitz = None


DEFAULT_OPTIMIZE_IMAGE_WIDTH = 800
DEFAULT_OPTIMIZE_IMAGE_QUALITY = 60


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


def move_pdf_page(path, from_index, to_index):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    doc = fitz.open(path)
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
        temp_path = None
        try:
            for index in order:
                new_doc.insert_pdf(doc, from_page=index, to_page=index)

            temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".pdf")
            os.close(temp_fd)
            new_doc.save(temp_path)
        finally:
            if not new_doc.is_closed:
                new_doc.close()

        # Close the original document before replacing the file on Windows.
        doc.close()
        doc = None

        os.replace(temp_path, path)
        return path
    finally:
        if doc is not None:
            doc.close()
        if temp_path is not None and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def rotate_pdf(path, angle=90):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    temp_path = None
    try:
        for page in doc:
            page.set_rotation((page.rotation + angle) % 360)

        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".pdf")
        os.close(temp_fd)
        doc.save(temp_path)
    finally:
        if doc is not None:
            doc.close()

    os.replace(temp_path, path)
    return path


def rotate_pdf_page(path, page_index, angle=90):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    temp_path = None
    try:
        if not 0 <= page_index < len(doc):
            raise ValueError(f"Page index {page_index} is out of range")
        page = doc[page_index]
        page.set_rotation((page.rotation + angle) % 360)

        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".pdf")
        os.close(temp_fd)
        doc.save(temp_path)
    finally:
        if doc is not None:
            doc.close()

    os.replace(temp_path, path)
    return path


def optimize_pdf(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    target_width, target_quality = _get_optimize_pdf_settings()

    doc = fitz.open(path)
    temp_path = None
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

        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".pdf")
        os.close(temp_fd)
        doc.save(temp_path, garbage=4, deflate=True, clean=True)
    finally:
        if doc is not None:
            doc.close()

    os.replace(temp_path, path)
    return path


def ajust_page_width(path):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    if not os.path.isfile(path):
        raise FileNotFoundError(path)

    doc = fitz.open(path)
    new_doc = fitz.open()
    temp_path = None
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

        temp_fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".pdf")
        os.close(temp_fd)
        new_doc.save(temp_path, garbage=4, deflate=True, clean=True)
    finally:
        if doc is not None:
            doc.close()
        if not new_doc.is_closed:
            new_doc.close()

    os.replace(temp_path, path)
    return path


def get_pdf_page_previews(path, max_height=300, max_pages=None):
    if fitz is None:
        raise RuntimeError("PyMuPDF is not installed. PDF preview unavailable.")

    doc = fitz.open(path)
    try:
        page_count = len(doc)
        shown_pages = page_count if max_pages is None else min(page_count, max_pages)
        previews = []

        for index in range(shown_pages):
            page = doc[index]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            safe_name = os.path.basename(path).replace(" ", "_") or "pdf_page"
            image_path = os.path.join(tempfile.gettempdir(), f"{safe_name}_{index}.png")
            pix.save(image_path)

            image = wx.Image(image_path, wx.BITMAP_TYPE_PNG)
            if image.GetHeight() > max_height:
                image = image.Rescale(max_height, int(image.GetHeight() * max_height / image.GetWidth()))

            previews.append((index + 1, image.ConvertToBitmap()))

        return page_count, shown_pages, previews
    finally:
        doc.close()
