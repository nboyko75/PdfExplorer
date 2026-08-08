import hashlib
import os
import subprocess
import sys
import tempfile

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
        result = subprocess.run(command, capture_output=True, text=True)
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


def _export_word_to_pdf(source_path, output_pdf):
    if win32_client is None:
        script = """
$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $doc = $word.Documents.Open($src)
    $doc.ExportAsFixedFormat($dst, 17)
}
finally {
    if ($doc -ne $null) { $doc.Close($false) }
    if ($word -ne $null) { $word.Quit() }
}
"""
        _run_powershell_office_export(script, source_path, output_pdf)
        return

    app = win32_client.DispatchEx("Word.Application")
    app.Visible = False
    app.DisplayAlerts = 0
    doc = None
    try:
        doc = app.Documents.Open(source_path, ReadOnly=True)
        doc.ExportAsFixedFormat(output_pdf, 17)
    finally:
        if doc is not None:
            doc.Close(False)
        app.Quit()


def _export_excel_to_pdf(source_path, output_pdf):
    if win32_client is None:
        script = """
$excel = $null
$book = $null
try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $book = $excel.Workbooks.Open($src)
    $book.ExportAsFixedFormat(0, $dst)
}
finally {
    if ($book -ne $null) { $book.Close($false) }
    if ($excel -ne $null) { $excel.Quit() }
}
"""
        _run_powershell_office_export(script, source_path, output_pdf)
        return

    app = win32_client.DispatchEx("Excel.Application")
    app.Visible = False
    app.DisplayAlerts = False
    workbook = None
    try:
        workbook = app.Workbooks.Open(source_path, ReadOnly=True)
        workbook.ExportAsFixedFormat(0, output_pdf)
    finally:
        if workbook is not None:
            workbook.Close(False)
        app.Quit()


def _export_powerpoint_to_pdf(source_path, output_pdf):
    if win32_client is None:
        script = """
$ppt = $null
$presentation = $null
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $presentation = $ppt.Presentations.Open($src)
    $presentation.SaveAs($dst, 32)
}
finally {
    if ($presentation -ne $null) { $presentation.Close() }
    if ($ppt -ne $null) { $ppt.Quit() }
}
"""
        _run_powershell_office_export(script, source_path, output_pdf)
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


def convert_office_to_preview_pdf(path):
    if sys.platform != "win32":
        raise RuntimeError("Office preview is supported on Windows only.")

    if not can_preview_office(path):
        raise RuntimeError("Unsupported Office file type for preview.")

    output_pdf = _build_cached_preview_pdf_path(path)
    if os.path.isfile(output_pdf):
        return output_pdf

    if pythoncom is not None:
        pythoncom.CoInitialize()
    try:
        _, ext = os.path.splitext(path)
        ext = ext.lower()
        if ext in {".doc", ".docx", ".docm"}:
            _export_word_to_pdf(path, output_pdf)
        elif ext in {".xls", ".xlsx", ".xlsm"}:
            _export_excel_to_pdf(path, output_pdf)
        elif ext in {".ppt", ".pptx", ".pptm"}:
            _export_powerpoint_to_pdf(path, output_pdf)
        else:
            raise RuntimeError("Unsupported Office file type for preview.")
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    if not os.path.isfile(output_pdf):
        raise RuntimeError("Unable to generate preview PDF from Office document.")

    return output_pdf