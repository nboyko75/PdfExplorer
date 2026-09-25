"""Render selected PDF pages into individual image files."""
import math
import os
import tempfile
from PIL import Image

FORMATS = {'.png': 'PNG', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.jfif': 'JPEG',
           '.bmp': 'BMP', '.gif': 'GIF', '.tif': 'TIFF', '.tiff': 'TIFF', '.webp': 'WEBP'}


def output_paths(output_path, page_indices):
    stem, extension = os.path.splitext(output_path)
    if extension.lower() not in FORMATS:
        raise ValueError('Unsupported image format: ' + extension)
    return ([output_path] if len(page_indices) == 1 else
            [f'{stem}_{index + 1}{extension}' for index in page_indices])


def detect_page_dpi(page):
    """Use the largest visible image's pixel density at its placed PDF size."""
    candidates = []
    # Image transforms are in unrotated page coordinates and include scaling,
    # rotation and skew. Their axis lengths give the placed size in points.
    import fitz
    visible_page = page.rect * page.derotation_matrix
    for info in page.get_image_info():
        width, height = info['width'], info['height']
        a, b, c, d, _, _ = info['transform']
        placed_width, placed_height = math.hypot(a, b), math.hypot(c, d)
        visible = fitz.Rect(info['bbox']) & visible_page
        if width <= 0 or height <= 0 or placed_width <= 0 or placed_height <= 0 or visible.is_empty:
            continue
        density = max(width * 72 / placed_width, height * 72 / placed_height)
        if math.isfinite(density) and density > 0:
            candidates.append((visible.get_area(), density))
    if not candidates:
        return 150
    return max(1, int(math.floor(max(candidates)[1] + 0.5)))


def export_images(document, page_indices, output_path, dpi=150):
    if dpi is not None and (not isinstance(dpi, int) or isinstance(dpi, bool) or dpi <= 0):
        raise ValueError("DPI must be a positive integer.")
    indices = [int(index) for index in page_indices]
    if not indices or any(index < 0 or index >= len(document) for index in indices):
        raise ValueError('Select valid page numbers.')
    paths = output_paths(output_path, indices)
    staged = []
    try:
        for index, target in zip(indices, paths):
            import fitz
            page = document[index]
            page_dpi = detect_page_dpi(page) if dpi is None else dpi
            pixmap = page.get_pixmap(dpi=page_dpi, colorspace=fitz.csRGB, alpha=False)
            with Image.frombytes('RGB', (pixmap.width, pixmap.height), pixmap.samples) as image:
                extension = os.path.splitext(target)[1].lower()
                fd, temporary = tempfile.mkstemp(prefix='.docexplorer-export-',
                                                 dir=os.path.dirname(os.path.abspath(target)))
                os.close(fd)
                staged.append((temporary, target))
                options = {'quality': 95} if FORMATS[extension] in ('JPEG', 'WEBP') else {}
                image.save(temporary, format=FORMATS[extension], dpi=(page_dpi, page_dpi), **options)
        # Complete encoding before replacing any existing output.
        for temporary, target in staged:
            os.replace(temporary, target)
        return paths
    finally:
        for temporary, _ in staged:
            if os.path.exists(temporary):
                os.unlink(temporary)
