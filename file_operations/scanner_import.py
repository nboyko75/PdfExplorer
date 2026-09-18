"""Acquire scanner pages into a temporary PDF for the PDF editing session."""
import os
import tempfile
from contextlib import contextmanager

from localization import tr


def _is_scan_cancelled(exc):
    codes = [getattr(exc, "hresult", None)]
    details = getattr(exc, "excepinfo", None)
    if details and len(details) > 5:
        codes.append(details[5])
    return any(isinstance(code, int) and (code & 0xFFFFFFFF) in
               {0x800704C7, 0x80210064} for code in codes)


def _append_scan_image(document, image_path):
    from io import BytesIO
    from PIL import Image, ImageOps, ImageSequence

    with Image.open(image_path) as image:
        for frame in ImageSequence.Iterator(image):
            dpi = frame.info.get("dpi", (300, 300))
            try:
                x_dpi, y_dpi = float(dpi[0]), float(dpi[1])
                if not (0 < x_dpi < 10000 and 0 < y_dpi < 10000):
                    raise ValueError("Invalid scan resolution")
            except (TypeError, ValueError, IndexError):
                x_dpi = y_dpi = 300
            with ImageOps.exif_transpose(frame) as oriented:
                with oriented.convert("RGB") as pixels:
                    with BytesIO() as stream:
                        pixels.save(stream, format="PNG")
                        page = document.new_page(
                            width=pixels.width * 72 / x_dpi,
                            height=pixels.height * 72 / y_dpi,
                        )
                        page.insert_image(page.rect, stream=stream.getvalue())


@contextmanager
def scanned_pdf(owner, multiple_pages=False):
    """Yield a complete PDF or None on cancel; own and clean all scan files."""
    import wx
    import fitz
    try:
        import pythoncom
        import win32com.client as win32_client
    except ImportError as exc:
        raise RuntimeError(tr("scan_wia_required")) from exc

    with tempfile.TemporaryDirectory(prefix="docexplorer_scan_") as directory:
        common_dialog = None
        image = None
        pythoncom.CoInitialize()
        try:
            common_dialog = win32_client.Dispatch("WIA.CommonDialog")
            with fitz.open() as document:
                scan_index = 0
                completed = False
                while True:
                    try:
                        # ScannerDeviceType; choose device on the first scan;
                        # native scan settings UI; cancellation returns None.
                        image = common_dialog.ShowAcquireImage(
                            1, 0, 0, "{00000000-0000-0000-0000-000000000000}",
                            scan_index == 0, True, False,
                        )
                    except Exception as exc:
                        if _is_scan_cancelled(exc):
                            image = None
                        else:
                            raise
                    if image is None:
                        # Cancelling any acquisition aborts the whole import.
                        break
                    image_path = os.path.join(directory, f"page_{scan_index}.img")
                    image.SaveFile(image_path)
                    image = None
                    _append_scan_image(document, image_path)
                    scan_index += 1
                    if not multiple_pages:
                        completed = True
                        break
                    prompt = wx.MessageDialog(
                        owner, tr("scan_next_page_prompt"), tr("scan_dialog_title"),
                        wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION,
                    )
                    prompt.SetYesNoCancelLabels(
                        tr("scan_next_page"), tr("scan_finish_import"), tr("cancel_button")
                    )
                    try:
                        answer = prompt.ShowModal()
                    finally:
                        prompt.Destroy()
                    if answer == wx.ID_YES:
                        continue
                    completed = answer == wx.ID_NO
                    break
                if completed and scan_index:
                    output_path = os.path.join(directory, "scanned.pdf")
                    document.save(output_path, garbage=4, deflate=True)
                else:
                    output_path = None
        finally:
            image = None
            common_dialog = None
            pythoncom.CoUninitialize()
        yield output_path
