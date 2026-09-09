"""Embed the installed Microsoft Office editor in a wxPython panel.

This module deliberately uses a separate Office application instance.  That
keeps documents opened by the user outside DocExplorer untouched and lets the
embedded instance be closed predictably when the preview changes.
"""

import os
import sys
import time


try:
    import pythoncom
    import win32com.client as win32_client
    import win32con
    import win32gui
except ImportError:  # pragma: no cover - Windows-only optional dependency
    pythoncom = None
    win32_client = None
    win32con = None
    win32gui = None


WORD_EXTENSIONS = {".doc", ".docx", ".docm"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx", ".pptm"}
OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS | POWERPOINT_EXTENSIONS


def is_available():
    return sys.platform == "win32" and all(
        dependency is not None
        for dependency in (pythoncom, win32_client, win32con, win32gui)
    )


class EmbeddedOfficeEditor:
    """Own and host one Word, Excel, or PowerPoint application window."""

    def __init__(self, panel):
        self.panel = panel
        self.path = None
        self.kind = None
        self.application = None
        self.document = None
        self.hwnd = None
        self._com_initialized = False
        self._original_style = None
        self._original_ex_style = None
        panel.Bind(__import__("wx").EVT_SIZE, self._on_panel_size)

    def open(self, path):
        if not is_available():
            raise RuntimeError("Microsoft Office embedding requires Windows and pywin32.")
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        normalized = os.path.normcase(os.path.abspath(path))
        if self.path == normalized and self.document is not None:
            self.resize()
            return

        self.close(save_changes=False)
        pythoncom.CoInitialize()
        self._com_initialized = True

        extension = os.path.splitext(path)[1].lower()
        try:
            if extension in WORD_EXTENSIONS:
                self._open_word(path)
            elif extension in EXCEL_EXTENSIONS:
                self._open_excel(path)
            elif extension in POWERPOINT_EXTENSIONS:
                self._open_powerpoint(path)
            else:
                raise RuntimeError("Unsupported Microsoft Office document type.")

            self.path = normalized
            self._embed_window()
        except Exception:
            self.close(save_changes=False)
            raise

    def _open_word(self, path):
        self.kind = "word"
        self.application = win32_client.DispatchEx("Word.Application")
        self.application.DisplayAlerts = 0
        self.document = self.application.Documents.Open(
            os.path.abspath(path), ReadOnly=False, AddToRecentFiles=False
        )
        self.application.Visible = True
        self.application.DisplayAlerts = -1
        self.hwnd = self._resolve_office_hwnd("OpusApp", path)

    def _open_excel(self, path):
        self.kind = "excel"
        self.application = win32_client.DispatchEx("Excel.Application")
        self.application.DisplayAlerts = False
        self.document = self.application.Workbooks.Open(
            os.path.abspath(path), ReadOnly=False, AddToMru=False
        )
        self.application.Visible = True
        self.application.DisplayAlerts = True
        self.hwnd = self._resolve_office_hwnd("XLMAIN", path)

    def _open_powerpoint(self, path):
        self.kind = "powerpoint"
        self.application = win32_client.DispatchEx("PowerPoint.Application")
        self.document = self.application.Presentations.Open(
            os.path.abspath(path), ReadOnly=False, Untitled=False, WithWindow=True
        )
        self.application.Visible = True
        self.hwnd = self._resolve_office_hwnd("PPTFrameClass", path)

    def _resolve_office_hwnd(self, window_class, path):
        """Return the Office frame handle across old and new COM versions."""
        com_objects = [self.application]
        try:
            active_window = self.application.ActiveWindow
            if active_window is not None:
                com_objects.append(active_window)
        except Exception:
            pass

        for com_object in com_objects:
            for property_name in ("Hwnd", "HWND", "hwnd"):
                try:
                    hwnd = int(getattr(com_object, property_name))
                    if hwnd and win32gui.IsWindow(hwnd):
                        return hwnd
                except Exception:
                    continue

        # Some Word releases do not expose a window handle through COM.  In
        # that case locate the top-level Office frame created for this file.
        expected_name = os.path.basename(path).casefold()
        expected_stem = os.path.splitext(expected_name)[0]
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            matching = []
            fallback = []

            def collect(hwnd, _):
                try:
                    if win32gui.GetClassName(hwnd) != window_class:
                        return
                    fallback.append(hwnd)
                    title = win32gui.GetWindowText(hwnd).casefold()
                    if expected_name in title or expected_stem in title:
                        matching.append(hwnd)
                except Exception:
                    pass

            win32gui.EnumWindows(collect, None)
            if matching:
                return matching[-1]
            if len(fallback) == 1:
                return fallback[0]
            time.sleep(0.05)

        raise RuntimeError(
            "Microsoft Office opened the document but its editor window could not be found."
        )

    def _embed_window(self):
        if not self.hwnd or not win32gui.IsWindow(self.hwnd):
            raise RuntimeError("Microsoft Office did not create an editor window.")

        self._original_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_STYLE)
        self._original_ex_style = win32gui.GetWindowLong(self.hwnd, win32con.GWL_EXSTYLE)
        style = self._original_style
        style &= ~(
            win32con.WS_CAPTION
            | win32con.WS_THICKFRAME
            | win32con.WS_MINIMIZEBOX
            | win32con.WS_MAXIMIZEBOX
            | win32con.WS_SYSMENU
            | win32con.WS_POPUP
        )
        style |= win32con.WS_CHILD | win32con.WS_VISIBLE
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_STYLE, style)

        ex_style = self._original_ex_style & ~win32con.WS_EX_APPWINDOW
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, ex_style)
        win32gui.SetParent(self.hwnd, int(self.panel.GetHandle()))
        self.resize()
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)

    def resize(self):
        if not self.hwnd or win32gui is None or not win32gui.IsWindow(self.hwnd):
            return
        size = self.panel.GetClientSize()
        width = max(1, int(size.GetWidth()))
        height = max(1, int(size.GetHeight()))
        win32gui.MoveWindow(self.hwnd, 0, 0, width, height, True)

    def _on_panel_size(self, event):
        self.resize()
        event.Skip()

    def is_dirty(self):
        if self.document is None:
            return False
        try:
            return not bool(self.document.Saved)
        except Exception:
            return False

    def save(self):
        if self.document is None:
            return
        self.document.Save()

    def close(self, save_changes=False):
        document = self.document
        kind = self.kind
        hwnd = self.hwnd

        self.path = None
        self.kind = None
        self.document = None
        self.application = None
        self.hwnd = None

        if hwnd is not None and win32gui is not None and win32gui.IsWindow(hwnd):
            try:
                win32gui.SetParent(hwnd, 0)
            except Exception:
                pass
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            except Exception:
                pass

        try:
            if document is not None:
                if kind == "word":
                    document.Close(SaveChanges=-1 if save_changes else 0)
                elif kind == "powerpoint":
                    if save_changes:
                        document.Save()
                    else:
                        document.Saved = True
                    document.Close()
                else:
                    document.Close(SaveChanges=bool(save_changes))
        except Exception:
            pass

        if self._com_initialized and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        self._com_initialized = False
