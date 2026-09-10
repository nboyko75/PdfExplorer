"""Embed the installed Microsoft Office editor in a wxPython panel.

This module deliberately uses a separate Office application instance.  That
keeps documents opened by the user outside DocExplorer untouched and lets the
embedded instance be closed predictably when the preview changes.
"""

import os
import shutil
import sys
import tempfile
import time


try:
    import pythoncom
    import win32api
    import win32com.client as win32_client
    import win32con
    import win32gui
    import win32process
except ImportError:  # pragma: no cover - Windows-only optional dependency
    pythoncom = None
    win32api = None
    win32_client = None
    win32con = None
    win32gui = None
    win32process = None


WORD_EXTENSIONS = {".doc", ".docx", ".docm"}
EXCEL_EXTENSIONS = {".xls", ".xlsx", ".xlsm"}
POWERPOINT_EXTENSIONS = {".ppt", ".pptx", ".pptm"}
OFFICE_EXTENSIONS = WORD_EXTENSIONS | EXCEL_EXTENSIONS | POWERPOINT_EXTENSIONS
OFFICE_CHROME_FALLBACK_HEIGHT_DIP = 150
OFFICE_ZOOM_MIN = 10
OFFICE_ZOOM_MAX = 400
OFFICE_ZOOM_STEP = 10


def is_available():
    return sys.platform == "win32" and all(
        dependency is not None
        for dependency in (
            pythoncom,
            win32api,
            win32_client,
            win32con,
            win32gui,
            win32process,
        )
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
        self._opening_path = None
        self._preview_temp_dir = None
        self._com_initialized = False
        self._original_style = None
        self._original_ex_style = None
        wx = __import__("wx")
        panel.Bind(wx.EVT_SIZE, self._on_panel_size)
        panel.Bind(wx.EVT_SET_FOCUS, self._on_panel_focus)

    def open(self, path):
        if not is_available():
            raise RuntimeError("Microsoft Office embedding requires Windows and pywin32.")
        if not os.path.isfile(path):
            raise FileNotFoundError(path)

        normalized = os.path.normcase(os.path.abspath(path))
        if self.path == normalized and self.document is not None:
            self.resize()
            return

        # Office COM calls can pump the Windows message queue.  A second list
        # selection event may therefore re-enter this method before self.path
        # is assigned.  Ignore only that duplicate in-progress request.
        if self._opening_path == normalized:
            return

        self.close(save_changes=False)
        self._opening_path = normalized
        extension = os.path.splitext(path)[1].lower()
        try:
            # Open an isolated copy in the embedded Office process.  Even a
            # read-only Word document can create an owner file beside the
            # original and prevent an external editable open.
            self._preview_temp_dir = tempfile.mkdtemp(
                prefix="docexplorer_office_preview_"
            )
            preview_path = os.path.join(
                self._preview_temp_dir,
                os.path.basename(path),
            )
            shutil.copy2(os.path.abspath(path), preview_path)

            pythoncom.CoInitialize()
            self._com_initialized = True

            if extension in WORD_EXTENSIONS:
                self._open_word(preview_path)
            elif extension in EXCEL_EXTENSIONS:
                self._open_excel(preview_path)
            elif extension in POWERPOINT_EXTENSIONS:
                self._open_powerpoint(preview_path)
            else:
                raise RuntimeError("Unsupported Microsoft Office document type.")

            self.path = normalized
            self._embed_window()
        except Exception:
            self.close(save_changes=False)
            raise
        finally:
            if self._opening_path == normalized:
                self._opening_path = None

    def _open_word(self, path):
        self.kind = "word"
        self.application = win32_client.DispatchEx("Word.Application")
        self.application.DisplayAlerts = 0
        self.document = self.application.Documents.Open(
            os.path.abspath(path), ReadOnly=True, AddToRecentFiles=False
        )
        self.application.Visible = True
        self.application.DisplayAlerts = -1
        self.hwnd = self._resolve_office_hwnd("OpusApp", path)

    def _open_excel(self, path):
        self.kind = "excel"
        self.application = win32_client.DispatchEx("Excel.Application")
        self.application.DisplayAlerts = False
        self.document = self.application.Workbooks.Open(
            os.path.abspath(path), ReadOnly=True, AddToMru=False
        )
        self.application.Visible = True
        self.application.DisplayAlerts = True
        self.hwnd = self._resolve_office_hwnd("XLMAIN", path)

    def _open_powerpoint(self, path):
        self.kind = "powerpoint"
        self.application = win32_client.DispatchEx("PowerPoint.Application")
        self.document = self.application.Presentations.Open(
            os.path.abspath(path), ReadOnly=True, Untitled=False, WithWindow=True
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

        # Remove/disable the Office frame's Close command before making it a
        # child window.  Without the explicit frame refresh below, Windows can
        # leave the old top-level caption (including its X button) visible and
        # clickable even though WS_CAPTION/WS_SYSMENU were already cleared.
        try:
            system_menu = win32gui.GetSystemMenu(self.hwnd, False)
            if system_menu:
                win32gui.EnableMenuItem(
                    system_menu,
                    win32con.SC_CLOSE,
                    win32con.MF_BYCOMMAND | win32con.MF_GRAYED,
                )
        except Exception:
            pass

        win32gui.SetParent(self.hwnd, int(self.panel.GetHandle()))
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

        ex_style = self._original_ex_style
        ex_style &= ~(
            win32con.WS_EX_APPWINDOW
            | win32con.WS_EX_DLGMODALFRAME
            | win32con.WS_EX_WINDOWEDGE
            | getattr(win32con, "WS_EX_NOACTIVATE", 0)
        )
        win32gui.SetWindowLong(self.hwnd, win32con.GWL_EXSTYLE, ex_style)

        frame_flags = (
            win32con.SWP_FRAMECHANGED
            | win32con.SWP_NOMOVE
            | win32con.SWP_NOSIZE
            | win32con.SWP_NOZORDER
            | win32con.SWP_NOACTIVATE
        )
        win32gui.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0, frame_flags)
        self.resize()
        win32gui.ShowWindow(self.hwnd, win32con.SW_SHOW)
        self.activate()

    def activate(self):
        """Reactivate the Office document view after Win32 reparenting."""
        if not self.hwnd or win32gui is None or not win32gui.IsWindow(self.hwnd):
            return False

        try:
            win32gui.EnableWindow(self.hwnd, True)
        except Exception:
            pass

        # Read-only documents must still be interactive: selection, copying,
        # scrolling and zooming are valid operations.
        try:
            self.application.Interactive = True
        except Exception:
            pass
        try:
            self.document.Activate()
        except Exception:
            pass
        try:
            self.application.ActiveWindow.Activate()
        except Exception:
            pass

        preferred_classes = {
            "word": {"_wwg"},
            "excel": {"excel7"},
            "powerpoint": {"paneclassdc", "mdiclient"},
        }.get(self.kind, set())
        focus_targets = []

        def collect(child_hwnd, _):
            try:
                class_name = win32gui.GetClassName(child_hwnd).casefold()
                if (
                    class_name in preferred_classes
                    and win32gui.IsWindowVisible(child_hwnd)
                    and win32gui.IsWindowEnabled(child_hwnd)
                ):
                    focus_targets.append(child_hwnd)
            except Exception:
                pass

        try:
            win32gui.EnumChildWindows(self.hwnd, collect, None)
        except Exception:
            pass

        current_thread = None
        office_thread = None
        input_attached = False
        try:
            current_thread = win32api.GetCurrentThreadId()
            office_thread, _ = win32process.GetWindowThreadProcessId(self.hwnd)
            if office_thread and office_thread != current_thread:
                win32process.AttachThreadInput(current_thread, office_thread, True)
                input_attached = True
            win32gui.SetActiveWindow(self.hwnd)
            win32gui.SetFocus(focus_targets[-1] if focus_targets else self.hwnd)
            return True
        except Exception:
            return False
        finally:
            if input_attached:
                try:
                    win32process.AttachThreadInput(current_thread, office_thread, False)
                except Exception:
                    pass

    def resize(self):
        if not self.hwnd or win32gui is None or not win32gui.IsWindow(self.hwnd):
            return
        size = self.panel.GetClientSize()
        width = max(1, int(size.GetWidth()))
        height = max(1, int(size.GetHeight()))

        chrome_height = self._get_office_chrome_height()
        win32gui.MoveWindow(
            self.hwnd,
            0,
            -chrome_height,
            width,
            height + chrome_height,
            True,
        )

    def _get_office_chrome_height(self):
        """Measure and hide the complete Office title bar and Ribbon."""
        try:
            fallback = int(self.panel.FromDIP(OFFICE_CHROME_FALLBACK_HEIGHT_DIP))
        except Exception:
            fallback = OFFICE_CHROME_FALLBACK_HEIGHT_DIP
        fallback = max(0, fallback)

        if not self.hwnd or win32gui is None or not win32gui.IsWindow(self.hwnd):
            return fallback

        detected_bottoms = []
        try:
            _, frame_top, _, frame_bottom = win32gui.GetWindowRect(self.hwnd)
            frame_height = max(1, frame_bottom - frame_top)

            def collect(child_hwnd, _):
                try:
                    class_name = win32gui.GetClassName(child_hwnd).casefold()
                    if "netuihwnd" not in class_name and "msocommandbar" not in class_name:
                        return
                    _, child_top, _, child_bottom = win32gui.GetWindowRect(child_hwnd)
                    relative_top = child_top - frame_top
                    relative_bottom = child_bottom - frame_top
                    if relative_top < frame_height * 0.45 and 20 < relative_bottom < frame_height * 0.60:
                        detected_bottoms.append(relative_bottom)
                except Exception:
                    pass

            win32gui.EnumChildWindows(self.hwnd, collect, None)
        except Exception:
            pass

        # The fallback also covers Office builds whose modern Ribbon is drawn
        # directly by the frame and therefore has no separate child HWND.
        return max([fallback] + detected_bottoms)

    def _on_panel_size(self, event):
        self.resize()
        event.Skip()

    def _on_panel_focus(self, event):
        self.activate()
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

    def handle_shortcut(self, key_code):
        if key_code == ord("C"):
            return self._execute_selection_action("Copy")
        if key_code == ord("X"):
            return self._execute_selection_action("Cut")
        if key_code == ord("V"):
            return self._execute_selection_action("Paste")
        return False

    def _execute_selection_action(self, action_name):
        if self.application is None:
            return False

        attempted_targets = []
        try:
            attempted_targets.append(self.application.Selection)
        except Exception:
            pass
        try:
            attempted_targets.append(self.application.ActiveWindow.Selection)
        except Exception:
            pass

        for target in attempted_targets:
            if target is None:
                continue
            method = getattr(target, action_name, None)
            if callable(method):
                method()
                return True

        try:
            view = self.application.ActiveWindow.View
        except Exception:
            view = None
        if view is not None:
            method = getattr(view, action_name, None)
            if callable(method):
                method()
                return True
        return False
    
    def get_zoom(self):
        """Return the active Office document zoom percentage."""
        if self.application is None or self.document is None:
            return None

        try:
            window = self.application.ActiveWindow
            if self.kind == "word":
                return int(window.View.Zoom.Percentage)
            if self.kind == "excel":
                return int(window.Zoom)
            if self.kind == "powerpoint":
                return int(window.View.Zoom)
        except Exception:
            return None
        return None

    def set_zoom(self, percentage):
        """Set zoom through Office COM, independently of the hidden Ribbon."""
        if self.application is None or self.document is None:
            return False

        percentage = max(OFFICE_ZOOM_MIN, min(OFFICE_ZOOM_MAX, int(percentage)))
        try:
            window = self.application.ActiveWindow
            if self.kind == "word":
                window.View.Zoom.Percentage = percentage
            elif self.kind == "excel":
                window.Zoom = percentage
            elif self.kind == "powerpoint":
                window.View.Zoom = percentage
            else:
                return False
            return True
        except Exception:
            return False

    def zoom_in(self):
        zoom = self.get_zoom()
        return zoom is not None and self.set_zoom(zoom + OFFICE_ZOOM_STEP)

    def zoom_out(self):
        zoom = self.get_zoom()
        return zoom is not None and self.set_zoom(zoom - OFFICE_ZOOM_STEP)

    def close(self, save_changes=False):
        document = self.document
        application = self.application
        kind = self.kind
        hwnd = self.hwnd
        preview_temp_dir = self._preview_temp_dir

        self.path = None
        self.kind = None
        self.document = None
        self.application = None
        self.hwnd = None
        self._preview_temp_dir = None

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

        try:
            if application is not None:
                application.Quit()
        except Exception:
            pass

        if self._com_initialized and pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        self._com_initialized = False

        if preview_temp_dir:
            shutil.rmtree(preview_temp_dir, ignore_errors=True)
