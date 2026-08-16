import hashlib
import os
import subprocess
import sys
import tempfile

from file_operations.pdf_utils import DEFAULT_SHOW_PAGES_LIMIT, _get_show_pages_limit_for_path

try:
    import pythoncom
    import win32com.client as win32_client
except ImportError:  # pragma: no cover - optional runtime dependency
    pythoncom = None
    win32_client = None


_OFFICE_EXTENSIONS = {
    ".doc",
    ".docx",
    ".docm",
    ".xls",
    ".xlsx",
    ".xlsm",
    ".ppt",
    ".pptx",
    ".pptm",
}


def _run_powershell_office_export(script_body, source_path, output_pdf):
    script_fd, script_path = tempfile.mkstemp(prefix="docexplorer_office_", suffix=".ps1")
    os.close(script_fd)
    try:
        with open(script_path, "w", encoding="utf-8-sig", newline="\n") as handle:
            handle.write("param([string]$src, [string]$dst)\n")
            handle.write("$ErrorActionPreference = 'Stop'\n")
            handle.write(script_body)

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
            source_path,
            output_pdf,
        ]
        result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "PowerShell Office export failed.").strip()
            raise RuntimeError(details)
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass


def can_preview_office(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in _OFFICE_EXTENSIONS


def _build_cached_preview_pdf_path(path):
    normalized_path = os.path.abspath(path)
    mtime_ns = os.path.getmtime(path)
    digest = hashlib.sha1(f"{normalized_path}|{mtime_ns}".encode("utf-8")).hexdigest()
    cache_dir = os.path.join(tempfile.gettempdir(), "docexplorer_office_preview")
    os.makedirs(cache_dir, exist_ok=True)
    return os.path.join(cache_dir, f"{digest}.pdf")


def _safe_remove_file(path):
    if not isinstance(path, str) or not path:
        return False
    try:
        os.remove(path)
        return True
    except (FileNotFoundError, OSError):
        return False


def _limit_preview_pdf_pages(path, max_pages=None):
    if not isinstance(path, str) or not os.path.isfile(path):
        return path

    try:
        import fitz
    except ImportError:
        return path

    if max_pages is None:
        max_pages = _get_show_pages_limit_for_path(path)
    try:
        limit = int(max_pages)
    except (TypeError, ValueError):
        limit = DEFAULT_SHOW_PAGES_LIMIT
    if limit <= 0:
        return path

    doc = fitz.open(path)
    try:
        if len(doc) <= limit:
            return path

        limited_doc = fitz.open()
        try:
            for page_index in range(limit):
                limited_doc.insert_pdf(doc, from_page=page_index, to_page=page_index)
            limited_doc.save(path, garbage=4, deflate=True, clean=True)
            return path
        finally:
            if not limited_doc.is_closed:
                limited_doc.close()
    finally:
        doc.close()

    return path


def _resolve_export_page_limit(path, max_pages=None):
    if max_pages is None:
        max_pages = _get_show_pages_limit_for_path(path)
    try:
        limit = int(max_pages)
    except (TypeError, ValueError):
        limit = DEFAULT_SHOW_PAGES_LIMIT
    return max(1, limit)


def _build_office_ps_script(path, output_pdf=None, max_pages=None):
    if not can_preview_office(path):
        raise RuntimeError("Unsupported Office file type for preview.")

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext in {".doc", ".docx", ".docm"}:
        limit = _resolve_export_page_limit(path, max_pages) if output_pdf else 0
        return f"""
$word = $null
$doc = $null
try {{
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($src, $false)
    $count = $doc.ComputeStatistics(2)
    if ($dst -and $dst.Length -gt 0) {{
        $doc.ExportAsFixedFormat($dst, 17, $false, 0, 3, 1, {limit})
    }}
    [int]$count
}}
finally {{
    if ($doc -ne $null) {{ $doc.Close($false) }}
    if ($word -ne $null) {{ $word.Quit() }}
}}
"""

    if ext in {".xls", ".xlsx", ".xlsm"}:
        limit = _resolve_export_page_limit(path, max_pages) if output_pdf else 0
        return f"""
$excel = $null
$book = $null
try {{
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $book = $excel.Workbooks.Open($src)
    $count = $book.Worksheets.Count
    if ($dst -and $dst.Length -gt 0) {{
        $book.ExportAsFixedFormat(0, $dst, 0, $false, $false, 1, {limit}, $false)
    }}
    [int]$count
}}
finally {{
    if ($book -ne $null) {{ $book.Close($false) }}
    if ($excel -ne $null) {{ $excel.Quit() }}
}}
"""

    if ext in {".ppt", ".pptx", ".pptm"}:
        return """
$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Open($src)
    $count = $presentation.Slides.Count
    if ($dst -and $dst.Length -gt 0) {
        $presentation.SaveAs($dst, 32)
    }
    [int]$count
}
finally {
    if ($presentation -ne $null) { $presentation.Close() }
    if ($ppt -ne $null) { $ppt.Quit() }
}
"""

    raise RuntimeError("Unsupported Office file type for preview.")


def _run_office_ps_script(path, output_pdf=None, max_pages=None):
    script = _build_office_ps_script(path, output_pdf=output_pdf, max_pages=max_pages)
    script_fd, script_path = tempfile.mkstemp(prefix="docexplorer_office_", suffix=".ps1")
    os.close(script_fd)
    try:
        with open(script_path, "w", encoding="utf-8-sig", newline="\n") as handle:
            handle.write("param([string]$src, [string]$dst)\n")
            handle.write("$ErrorActionPreference = 'Stop'\n")
            handle.write(script)

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script_path,
            path,
            output_pdf or "",
        ]
        result = subprocess.run(command, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode != 0:
            details = (result.stderr or result.stdout or "PowerShell Office script failed.").strip()
            raise RuntimeError(details)

        raw = (result.stdout or "").strip()
        if not raw:
            return 0
        try:
            return max(0, int(float(raw)))
        except ValueError:
            return 0
    finally:
        try:
            os.remove(script_path)
        except OSError:
            pass


def get_office_document_page_count(path):
    if not can_preview_office(path):
        return 0
    return _run_office_ps_script(path)


def _export_word_to_pdf(source_path, output_pdf, max_pages=None):
    page_limit = _resolve_export_page_limit(source_path, max_pages)
    if win32_client is None:
        _run_office_ps_script(source_path, output_pdf=output_pdf, max_pages=page_limit)
        return

    app = win32_client.DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    doc = None
    try:
        doc = app.Documents.Open(source_path, ReadOnly=True)
        doc.ExportAsFixedFormat(output_pdf, 17, False, 0, 3, 1, page_limit)
    finally:
        if doc is not None:
            doc.Close(False)
        app.Quit()


def _export_excel_to_pdf(source_path, output_pdf, max_pages=None):
    page_limit = _resolve_export_page_limit(source_path, max_pages)
    if win32_client is None:
        _run_office_ps_script(source_path, output_pdf=output_pdf, max_pages=page_limit)
        return

    app = win32_client.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    workbook = None
    try:
        workbook = app.Workbooks.Open(source_path, ReadOnly=True)
        workbook.ExportAsFixedFormat(0, output_pdf, 0, False, False, 1, page_limit, False)
    finally:
        if workbook is not None:
            workbook.Close(False)
        app.Quit()


def _export_powerpoint_to_pdf(source_path, output_pdf):
    if win32_client is None:
        _run_office_ps_script(source_path, output_pdf=output_pdf, max_pages=None)
        return

    app = win32_client.DispatchEx("PowerPoint.Application")
    app.Visible = 1
    presentation = None
    try:
        presentation = app.Presentations.Open(source_path, WithWindow=False)
        presentation.SaveAs(output_pdf, 32)
    finally:
        if presentation is not None:
            presentation.Close()
        app.Quit()


def convert_office_to_preview_pdf(path, max_pages=None):
    if sys.platform != "win32":
        raise RuntimeError("Office preview is supported on Windows only.")

    if not can_preview_office(path):
        raise RuntimeError("Unsupported Office file type for preview.")

    if max_pages is None:
        page_limit = _get_show_pages_limit_for_path(path)
    else:
        try:
            page_limit = max(1, int(max_pages))
        except (TypeError, ValueError):
            page_limit = _get_show_pages_limit_for_path(path)

    output_pdf = _build_cached_preview_pdf_path(path)
    if os.path.isfile(output_pdf) and max_pages is None:
        _limit_preview_pdf_pages(output_pdf, page_limit)
        return output_pdf
    if os.path.isfile(output_pdf) and max_pages is not None:
        _safe_remove_file(output_pdf)

    temp_output_pdf = os.path.join(
        os.path.dirname(output_pdf),
        f".{os.path.basename(output_pdf)}.{os.getpid()}.pdf",
    )
    if os.path.exists(temp_output_pdf):
        _safe_remove_file(temp_output_pdf)

    keep_temp_preview = False
    try:
        if pythoncom is not None:
            pythoncom.CoInitialize()
        try:
            _, ext = os.path.splitext(path)
            ext = ext.lower()
            if ext in {".doc", ".docx", ".docm"}:
                _export_word_to_pdf(path, temp_output_pdf, page_limit)
            elif ext in {".xls", ".xlsx", ".xlsm"}:
                _export_excel_to_pdf(path, temp_output_pdf, page_limit)
            elif ext in {".ppt", ".pptx", ".pptm"}:
                _export_powerpoint_to_pdf(path, temp_output_pdf)
            else:
                raise RuntimeError("Unsupported Office file type for preview.")
        finally:
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        if not os.path.isfile(temp_output_pdf):
            raise RuntimeError("Unable to generate preview PDF from Office document.")

        try:
            if os.path.exists(output_pdf):
                _safe_remove_file(output_pdf)
            os.replace(temp_output_pdf, output_pdf)
            _limit_preview_pdf_pages(output_pdf, page_limit)
            return output_pdf
        except (PermissionError, FileNotFoundError, OSError):
            keep_temp_preview = True
            _limit_preview_pdf_pages(temp_output_pdf, page_limit)
            return temp_output_pdf
    finally:
        if os.path.exists(temp_output_pdf) and not keep_temp_preview:
            try:
                _safe_remove_file(temp_output_pdf)
            except Exception:
                pass