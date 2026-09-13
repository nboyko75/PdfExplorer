"""Render Word and Excel documents to cached HTML using Microsoft Office COM."""

import gc
import hashlib
import os
import shutil
import sys
import tempfile
import time

try:
    import pythoncom
    import win32com.client as win32_client
except ImportError:  # pragma: no cover - optional outside Windows
    pythoncom = None
    win32_client = None


WORD_EXTENSIONS = {".doc", ".docx", ".docm"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
HTML_OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS

_CACHE_ROOT = os.path.join(tempfile.gettempdir(), "docexplorer_office_html")


def is_html_office_document(path):
    return bool(path) and os.path.splitext(path)[1].lower() in HTML_OFFICE_EXTENSIONS


def _cache_directory(path):
    stat = os.stat(path)
    identity = "|".join(
        (
            os.path.normcase(os.path.abspath(path)),
            str(stat.st_size),
            str(stat.st_mtime_ns),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8", errors="surrogatepass")).hexdigest()
    return os.path.join(_CACHE_ROOT, digest)


def _require_office_com():
    if sys.platform != "win32":
        raise RuntimeError("Microsoft Office HTML preview is supported on Windows only.")
    if pythoncom is None or win32_client is None:
        raise RuntimeError("Microsoft Office automation requires the pywin32 package.")


def _export_word_to_html(source_path, html_path):
    application = None
    document = None
    try:
        application = win32_client.DispatchEx("Word.Application")
        application.Visible = False
        application.DisplayAlerts = 0
        application.ScreenUpdating = False
        document = application.Documents.Open(
            FileName=os.path.abspath(source_path),
            ConfirmConversions=False,
            ReadOnly=True,
            AddToRecentFiles=False,
            Visible=False,
            OpenAndRepair=False,
        )
        document.SaveAs2(
            FileName=os.path.abspath(html_path),
            FileFormat=10,  # wdFormatFilteredHTML
            AddToRecentFiles=False,
            Encoding=65001,  # UTF-8
        )
    finally:
        if document is not None:
            try:
                document.Close(False)
            except Exception:
                pass
        if application is not None:
            try:
                application.Quit(False)
            except Exception:
                pass
        document = None
        application = None
        gc.collect()


def _export_excel_to_html(source_path, html_path):
    application = None
    workbook = None
    try:
        application = win32_client.DispatchEx("Excel.Application")
        application.Visible = False
        application.DisplayAlerts = False
        application.ScreenUpdating = False
        application.EnableEvents = False
        application.AskToUpdateLinks = False
        workbook = application.Workbooks.Open(
            Filename=os.path.abspath(source_path),
            UpdateLinks=0,
            ReadOnly=True,
            IgnoreReadOnlyRecommended=True,
            AddToMru=False,
            Notify=False,
        )
        workbook.SaveAs(
            Filename=os.path.abspath(html_path),
            FileFormat=44,  # xlHtml
            ReadOnlyRecommended=False,
            CreateBackup=False,
            AddToMru=False,
        )
    finally:
        if workbook is not None:
            try:
                workbook.Close(False)
            except Exception:
                pass
        if application is not None:
            try:
                application.Quit()
            except Exception:
                pass
        workbook = None
        application = None
        gc.collect()


def render_to_html(path):
    """Return a cached HTML rendering of a Word or Excel document."""
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    if not is_html_office_document(path):
        raise RuntimeError("Only Word and Excel documents can be rendered to HTML.")
    _require_office_com()

    cache_dir = _cache_directory(path)
    html_path = os.path.join(cache_dir, "document.html")
    if os.path.isfile(html_path) and os.path.getsize(html_path) > 0:
        return html_path

    os.makedirs(_CACHE_ROOT, exist_ok=True)
    work_dir = cache_dir + ".rendering"
    shutil.rmtree(work_dir, ignore_errors=True)
    os.makedirs(work_dir, exist_ok=True)
    work_html = os.path.join(work_dir, "document.html")

    pythoncom.CoInitialize()
    try:
        extension = os.path.splitext(path)[1].lower()
        if extension in WORD_EXTENSIONS:
            _export_word_to_html(path, work_html)
        else:
            _export_excel_to_html(path, work_html)

        if not os.path.isfile(work_html) or os.path.getsize(work_html) <= 0:
            raise RuntimeError("Microsoft Office did not create the HTML preview.")

        shutil.rmtree(cache_dir, ignore_errors=True)
        os.replace(work_dir, cache_dir)
        return html_path
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    finally:
        pythoncom.CoUninitialize()


def remove_stale_cache(max_age_days=14):
    """Best-effort cleanup of old HTML previews and their resource folders."""
    if not os.path.isdir(_CACHE_ROOT):
        return
    cutoff = time.time() - max(1, int(max_age_days)) * 86400
    for name in os.listdir(_CACHE_ROOT):
        path = os.path.join(_CACHE_ROOT, name)
        try:
            if os.path.getmtime(path) < cutoff:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass
