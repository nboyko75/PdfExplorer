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


@contextmanager
def scanned_pdf(owner, multiple_pages=False):
    """Yield a complete PDF or None on cancel; own and clean all scan files."""
    import wx
    from controls.scan_form import _acquire_scanned_image, _save_scanned_pages
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
            image_files = []
            scan_config = {"multiple_pages": multiple_pages}
            completed = False
            while True:
                try:
                    image = _acquire_scanned_image(common_dialog, scan_config, len(image_files))
                except Exception as exc:
                    if _is_scan_cancelled(exc):
                        image = None
                    else:
                        raise
                if image is None:
                    # Cancelling any acquisition aborts the whole import.
                    break
                image_path = os.path.join(directory, f"page_{len(image_files)}.img")
                image.SaveFile(image_path)
                image = None
                image_files.append(image_path)
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
            if completed and image_files:
                output_path = _save_scanned_pages(
                    image_files, os.path.join(directory, "scanned.pdf"), 0,
                )
            else:
                output_path = None
        finally:
            image = None
            common_dialog = None
            pythoncom.CoUninitialize()
        yield output_path
