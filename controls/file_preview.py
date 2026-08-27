import os
from contextlib import nullcontext
import wx

try:
    import wx.html2 as wx_html2
except ImportError:  # pragma: no cover - optional runtime dependency
    wx_html2 = None

from localization import tr
import controls.drag_and_drop as drag_and_drop
from controls.drag_and_drop import PdfPageDropTarget
import controls.drag_and_drop as pdf_dragdrop
from controls.window_tools import load_settings, update_settings
from file_operations.pdf_utils import adjust_page_width, discard_pdf_changes, export_pdf_pages, get_pdf_page_count, get_pdf_page_previews, has_unsaved_pdf_changes, import_pdf_pages, is_pdf_file, move_pdf_page, optimize_pdf, remove_pdf_page, rotate_pdf, rotate_pdf_page, save_pdf, save_pdf_as
import file_operations.image_utils as image_utils
import file_operations.office_preview as office_preview
import file_operations.pdf_utils as pdf_utils


PAGE_VIEW_MODE_1_WIDE = "1_page_wide"
PAGE_VIEW_MODE_2_WIDE = "2_pages_wide"
PAGE_VIEW_MODE_1_TALL = "1_page_tall"
PAGE_VIEW_MODE_MANUAL = "manual"
FIXED_PAGE_VIEW_MODES = {PAGE_VIEW_MODE_1_WIDE, PAGE_VIEW_MODE_2_WIDE, PAGE_VIEW_MODE_1_TALL}
VALID_PAGE_VIEW_MODES = FIXED_PAGE_VIEW_MODES | {PAGE_VIEW_MODE_MANUAL}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}
HTML_EXTENSIONS = {".html", ".htm"}
TEXT_FILE_EXTENSIONS = {".txt", ".log", ".ini", ".cfg", ".conf", ".csv", ".json", ".xml", ".yaml", ".yml", ".md"}
OFFICE_EXTENSIONS = {".doc", ".docx", ".docm", ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pptm"}

def _get_preview_tab_label(path):
    if not path:
        return ""
    name = os.path.basename(path)
    return name[:20]


def _get_preview_tab_hint(path):
    if not path:
        return ""
    return os.path.basename(path)


def _ensure_preview_tab_state(owner):
    if not hasattr(owner, "preview_tabs"):
        owner.preview_tabs = []
    if not hasattr(owner, "preview_active_tab_index"):
        owner.preview_active_tab_index = None


def _normalize_preview_tabs(owner):
    _ensure_preview_tab_state(owner)
    if not owner.preview_tabs:
        owner.preview_active_tab_index = None
        return

    active_index = owner.preview_active_tab_index
    active_path = None
    if active_index is not None and 0 <= active_index < len(owner.preview_tabs):
        active_path = owner.preview_tabs[active_index].get("path")

    pinned_tabs = [tab for tab in owner.preview_tabs if tab.get("pinned", False)]
    unpinned_tabs = [tab for tab in owner.preview_tabs if not tab.get("pinned", False)]

    if active_path is not None:
        for index, tab in enumerate(unpinned_tabs):
            if tab.get("path") == active_path:
                unpinned_tabs = unpinned_tabs[:index] + unpinned_tabs[index + 1:] + [tab]
                break

    owner.preview_tabs = pinned_tabs + unpinned_tabs

    if active_path is not None:
        for index, tab in enumerate(owner.preview_tabs):
            if tab.get("path") == active_path:
                owner.preview_active_tab_index = index
                break
        else:
            owner.preview_active_tab_index = max(0, len(owner.preview_tabs) - 1)
    else:
        owner.preview_active_tab_index = max(0, len(owner.preview_tabs) - 1)


def _render_preview_tab_bar(owner):
    _ensure_preview_tab_state(owner)
    tab_pane = getattr(owner, "preview_tab_pane", None)
    tab_sizer = getattr(owner, "preview_tab_sizer", None)
    if tab_pane is None or tab_sizer is None:
        return

    try:
        tab_sizer.Clear(True)
    except Exception:
        pass

    if not owner.preview_tabs:
        tab_pane.Hide()
        tab_pane.Layout()
        return

    active_index = owner.preview_active_tab_index
    if active_index is None or active_index < 0 or active_index >= len(owner.preview_tabs):
        active_index = 0
        owner.preview_active_tab_index = 0

    for index, tab in enumerate(owner.preview_tabs):
        caption = _get_preview_tab_label(tab.get("path"))
        hint = _get_preview_tab_hint(tab.get("path"))
        tab_panel = wx.Panel(tab_pane, style=wx.BORDER_SIMPLE)
        tab_panel.SetMinSize((200, 28))
        if index == active_index:
            tab_panel.SetBackgroundColour(wx.Colour(230, 240, 255))
        else:
            tab_panel.SetBackgroundColour(wx.NullColour)

        tab_label = wx.StaticText(tab_panel, label=caption)
        tab_label.SetToolTip(hint)
        tab_label.Bind(wx.EVT_LEFT_DOWN, lambda event, tab_index=index: _select_preview_tab(owner, tab_index))

        pin_label = "📍" if tab.get("pinned") else "📌"
        pin_btn = wx.Button(tab_panel, label=pin_label, size=(28, 22))
        pin_btn.SetToolTip(tr("preview_pin_button") if not tab.get("pinned") else tr("preview_unpin_button"))
        pin_btn.Bind(wx.EVT_BUTTON, lambda event, tab_index=index: _toggle_preview_tab_pin(owner, tab_index))

        close_btn = wx.Button(tab_panel, label="✕", size=(28, 22))
        close_btn.SetToolTip(tr("preview_close_tab_button"))
        close_btn.Bind(wx.EVT_BUTTON, lambda event, tab_index=index: _close_preview_tab(owner, tab_index))
        if index == 0:
            close_btn.Hide()

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.Add(tab_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 6)
        row.Add(pin_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        if index != 0:
            row.Add(close_btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 2)
        tab_panel.SetSizer(row)
        tab_panel.Bind(wx.EVT_LEFT_DOWN, lambda event, tab_index=index: _select_preview_tab(owner, tab_index))
        tab_sizer.Add(tab_panel, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 2)

    tab_pane.Show(True)
    tab_pane.Layout()
    if hasattr(owner, "preview_content_panel"):
        owner.preview_content_panel.Layout()
        owner.preview_content_panel.Refresh()


def _select_preview_tab(owner, tab_index):
    _ensure_preview_tab_state(owner)
    if tab_index < 0 or tab_index >= len(owner.preview_tabs):
        return

    owner.preview_active_tab_index = tab_index
    path = owner.preview_tabs[tab_index].get("path")
    if path:
        show_file_preview(owner, path)
    else:
        _render_preview_tab_bar(owner)


def _toggle_preview_tab_pin(owner, tab_index):
    _ensure_preview_tab_state(owner)
    if tab_index < 0 or tab_index >= len(owner.preview_tabs):
        return

    active_path = owner.preview_tabs[tab_index].get("path")
    owner.preview_tabs[tab_index]["pinned"] = not bool(owner.preview_tabs[tab_index].get("pinned", False))
    _normalize_preview_tabs(owner)

    if active_path is not None:
        for index, tab in enumerate(owner.preview_tabs):
            if tab.get("path") == active_path:
                owner.preview_active_tab_index = index
                break
    if owner.preview_active_tab_index is None or owner.preview_active_tab_index >= len(owner.preview_tabs):
        owner.preview_active_tab_index = len(owner.preview_tabs) - 1 if owner.preview_tabs else None
    _render_preview_tab_bar(owner)


def _close_preview_tab(owner, tab_index):
    _ensure_preview_tab_state(owner)
    if tab_index < 0 or tab_index >= len(owner.preview_tabs):
        return

    active_index = owner.preview_active_tab_index
    del owner.preview_tabs[tab_index]

    if not owner.preview_tabs:
        owner.preview_active_tab_index = None
        current_preview_path = getattr(owner, "current_preview_path", None)
        if current_preview_path:
            owner.current_preview_path = None
        _render_preview_tab_bar(owner)
        return

    if active_index is None:
        active_index = 0
    elif tab_index < active_index:
        active_index -= 1
    elif tab_index == active_index and tab_index >= len(owner.preview_tabs):
        active_index = len(owner.preview_tabs) - 1
    owner.preview_active_tab_index = max(0, min(active_index, len(owner.preview_tabs) - 1))
    _render_preview_tab_bar(owner)
    show_file_preview(owner, owner.preview_tabs[owner.preview_active_tab_index].get("path"))


def _is_office_preview_path(path):
    if not isinstance(path, str):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in OFFICE_EXTENSIONS


def _is_previewable_path(owner, path):
    if not isinstance(path, str) or not path:
        return False

    if is_pdf_file(path):
        return True

    _, ext = os.path.splitext(path)
    if ext.lower() in IMAGE_EXTENSIONS:
        return True
    if ext.lower() in HTML_EXTENSIONS:
        return True
    if ext.lower() in TEXT_FILE_EXTENSIONS:
        return True
    if _is_office_preview_path(path):
        return is_office_preview_allowed(owner, path)
    return False


def _sync_preview_tab_for_path(owner, path):
    _ensure_preview_tab_state(owner)
    if not path:
        return

    if os.path.isdir(path):
        owner.preview_tabs = [
            tab for tab in owner.preview_tabs
            if not tab.get("path") or not os.path.isdir(tab["path"])
        ]
        _normalize_preview_tabs(owner)
        _render_preview_tab_bar(owner)
        return

    if not getattr(owner, "preview_enabled", True):
        return

    if not _is_previewable_path(owner, path):
        owner.preview_tabs = [tab for tab in owner.preview_tabs if tab.get("pinned", False)]
        if owner.preview_tabs:
            owner.preview_active_tab_index = max(0, len(owner.preview_tabs) - 1)
        else:
            owner.preview_active_tab_index = None
        _render_preview_tab_bar(owner)
        return

    normalized_path = os.path.normpath(path)
    active_index = owner.preview_active_tab_index
    if active_index is not None and 0 <= active_index < len(owner.preview_tabs):
        active_tab = owner.preview_tabs[active_index]
        active_path = active_tab.get("path")
        if active_path and os.path.normpath(active_path) == normalized_path:
            active_tab["caption"] = _get_preview_tab_label(path)
            active_tab["hint"] = _get_preview_tab_hint(path)
            _render_preview_tab_bar(owner)
            return

    for index, tab in enumerate(owner.preview_tabs):
        if tab.get("path") and os.path.normpath(tab["path"]) == normalized_path:
            owner.preview_active_tab_index = index
            tab["caption"] = _get_preview_tab_label(path)
            tab["hint"] = _get_preview_tab_hint(path)
            _render_preview_tab_bar(owner)
            return

    unpinned_tabs = [tab for tab in owner.preview_tabs if not tab.get("pinned", False)]
    if unpinned_tabs:
        # === COPILOT PROTECTED: BEGIN ===
        reuse_tab = unpinned_tabs[-1]
        # === COPILOT PROTECTED: END ===
        reuse_index = owner.preview_tabs.index(reuse_tab)
        owner.preview_tabs[reuse_index] = {
            "path": path,
            "pinned": False,
            "caption": _get_preview_tab_label(path),
            "hint": _get_preview_tab_hint(path),
        }
        owner.preview_active_tab_index = reuse_index
    else:
        owner.preview_tabs.append({
            "path": path,
            "pinned": False,
            "caption": _get_preview_tab_label(path),
            "hint": _get_preview_tab_hint(path),
        })
        owner.preview_active_tab_index = len(owner.preview_tabs) - 1

    _normalize_preview_tabs(owner)
    _render_preview_tab_bar(owner)


def build_file_preview_pane(owner, file_splitter):
    """Create and configure the file preview pane UI."""
    owner.preview_content_panel = wx.Panel(file_splitter)
    owner.filePreview = wx.Panel(owner.preview_content_panel, style=wx.BORDER_SUNKEN)
    owner.preview_toolbar = wx.BoxSizer(wx.HORIZONTAL)
    owner.preview_enabled = getattr(owner, "preview_enabled", True)
    owner.office_preview_enabled = getattr(owner, "office_preview_enabled", False)

    owner.preview_checkbox = wx.CheckBox(owner.filePreview, label=tr("preview_checkbox_label"))
    owner.preview_checkbox.SetValue(owner.preview_enabled)
    owner.preview_toolbar.Add(owner.preview_checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)

    owner.office_preview_checkbox = wx.CheckBox(owner.filePreview, label=tr("preview_ms_office_checkbox_label"))
    owner.office_preview_checkbox.SetValue(owner.office_preview_enabled)
    if hasattr(owner.office_preview_checkbox, "Enable"):
        owner.office_preview_checkbox.Enable(owner.preview_enabled)
    owner.preview_toolbar.Add(owner.office_preview_checkbox, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

    preview_icon_size = (16, 16)
    preview_button_size = (24, 24)
    icon_manager = owner.icon_manager
    owner.filePreview.icon_manager = icon_manager

    owner.preview_import_from_file_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_FILE_OPEN, tr("preview_import_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    export_art_id = getattr(wx, "ART_FILE_SAVE_AS", wx.ART_FILE_SAVE)
    owner.preview_export_pages_btn = image_utils.create_bitmap_button(owner.filePreview, export_art_id, tr("preview_export_pages_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_save_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "save", tr("preview_save_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_cancel_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "cancel", tr("preview_cancel_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_out_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_MINUS, tr("preview_zoom_out_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_zoom_in_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_PLUS, tr("preview_zoom_in_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_page_view_mode_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_LIST_VIEW, tr("preview_show_mode"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_rotate_menu_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "rotation", tr("preview_rotate_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_move_page_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_GO_FORWARD, tr("preview_move_page_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_remove_page_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "delete", tr("preview_remove_page_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_adjust_page_width_btn = image_utils.create_bitmap_button(owner.filePreview, wx.ART_REPORT_VIEW, tr("preview_adjust_page_width_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_optimize_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "ok", tr("preview_optimize_button"), icon_size=preview_icon_size, button_size=preview_button_size)
    owner.preview_load_all_btn = image_utils.create_bitmap_button2(owner.filePreview, icon_manager, "load_all", tr("preview_load_all_button"), icon_size=preview_icon_size, button_size=preview_button_size)

    owner.preview_toolbar.Add(owner.preview_import_from_file_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_export_pages_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_save_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_cancel_btn, 0, wx.RIGHT, 10)
    owner.preview_toolbar.Add(owner.preview_zoom_out_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_zoom_in_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_page_view_mode_btn, 0, wx.RIGHT, 10)
    owner.preview_toolbar.Add(owner.preview_rotate_menu_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_move_page_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_remove_page_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_adjust_page_width_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_optimize_btn, 0, wx.RIGHT, 3)
    owner.preview_toolbar.Add(owner.preview_load_all_btn, 0, wx.RIGHT, 3)

    owner.preview_save_btn.Enable(False)
    owner.preview_cancel_btn.Enable(False)
    owner.preview_rotate_menu_btn.Enable(False)
    owner.preview_import_from_file_btn.Enable(False)
    owner.preview_export_pages_btn.Enable(False)
    owner.preview_remove_page_btn.Enable(False)
    owner.preview_move_page_btn.Enable(False)
    owner.preview_adjust_page_width_btn.Enable(False)
    owner.preview_optimize_btn.Enable(False)
    owner.preview_load_all_btn.Enable(False)

    owner.preview_text = wx.TextCtrl(
        owner.filePreview,
        style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL,
    )
    owner.preview_text.SetValue("")
    owner.preview_text.Hide()
    owner.preview_text.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.pdf_pages_panel = wx.ScrolledWindow(owner.filePreview, style=wx.HSCROLL | wx.VSCROLL)
    owner.pdf_pages_panel.SetScrollRate(10, 10)
    owner.pdf_pages_panel.Hide()
    owner.pdf_pages_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
    owner.pdf_pages_sizer = wx.BoxSizer(wx.HORIZONTAL)
    owner.pdf_pages_panel.SetSizer(owner.pdf_pages_sizer)

    owner.pdf_preview_container = wx.ScrolledWindow(owner.filePreview, style=wx.HSCROLL | wx.VSCROLL)
    owner.pdf_preview_container.Hide()
    owner.pdf_preview_container.SetScrollRate(10, 10)
    owner.pdf_preview_container.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.pdf_preview = wx.StaticBitmap(owner.pdf_preview_container)
    owner.pdf_preview.SetMinSize((250, 250))
    owner.pdf_preview.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
    owner.filePreview.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

    owner.preview_tab_pane = wx.Panel(owner.preview_content_panel)
    owner.preview_tab_pane.Hide()
    owner.preview_tab_sizer = wx.BoxSizer(wx.HORIZONTAL)
    owner.preview_tab_pane.SetSizer(owner.preview_tab_sizer)

    preview_sizer = wx.BoxSizer(wx.VERTICAL)
    preview_sizer.Add(owner.preview_toolbar, 0, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.preview_text, 1, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.pdf_pages_panel, 1, wx.EXPAND | wx.ALL, 5)
    preview_sizer.Add(owner.pdf_preview_container, 1, wx.EXPAND | wx.ALL, 5)
    owner.filePreview.SetSizer(preview_sizer)

    content_sizer = wx.BoxSizer(wx.VERTICAL)
    content_sizer.Add(owner.filePreview, 1, wx.EXPAND)
    content_sizer.Add(owner.preview_tab_pane, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 5)
    owner.preview_content_panel.SetSizer(content_sizer)
    owner.preview_content_panel.Layout()

    _ensure_preview_tab_state(owner)
    top_pane = getattr(owner, "list_host_panel", owner.list)
    file_splitter.SplitHorizontally(top_pane, owner.preview_content_panel, 400)


def bind_preview_events(owner):
    """Bind preview pane event handlers."""
    owner.preview_checkbox.Bind(wx.EVT_CHECKBOX, on_preview_checkbox_toggle)
    owner.office_preview_checkbox.Bind(wx.EVT_CHECKBOX, on_office_preview_checkbox_toggle)
    owner.preview_import_from_file_btn.Bind(wx.EVT_BUTTON, on_preview_import_menu)
    owner.preview_export_pages_btn.Bind(wx.EVT_BUTTON, on_preview_export_pages)
    owner.preview_save_btn.Bind(wx.EVT_BUTTON, on_preview_save_menu)
    owner.preview_cancel_btn.Bind(wx.EVT_BUTTON, on_preview_cancel)
    owner.preview_zoom_in_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_in)
    owner.preview_zoom_out_btn.Bind(wx.EVT_BUTTON, on_preview_zoom_out)
    owner.preview_rotate_menu_btn.Bind(wx.EVT_BUTTON, on_preview_rotate_menu)
    owner.filePreview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_text.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_pages_panel.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview_container.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.pdf_preview.Bind(wx.EVT_MOUSEWHEEL, on_preview_rotate_buttons_wheel)
    owner.preview_page_view_mode_btn.Bind(wx.EVT_BUTTON, on_preview_page_view_mode_menu)
    owner.preview_move_page_btn.Bind(wx.EVT_BUTTON, on_preview_move_page)
    owner.preview_optimize_btn.Bind(wx.EVT_BUTTON, on_preview_optimize)
    owner.preview_adjust_page_width_btn.Bind(wx.EVT_BUTTON, on_preview_adjust_page_width)
    owner.preview_remove_page_btn.Bind(wx.EVT_BUTTON, on_preview_remove_page)
    owner.preview_load_all_btn.Bind(wx.EVT_BUTTON, on_preview_load_all_pages)


def confirm_preview_change(owner, next_path):
    current_path = getattr(owner, "current_preview_path", None)
    if not is_pdf_file(current_path) or not has_unsaved_pdf_changes(current_path):
        return True

    if next_path and os.path.normpath(next_path) == os.path.normpath(current_path):
        return True

    dialog = wx.MessageDialog(
        owner,
        tr("confirm_save_selected_file"),
        tr("app_title"),
        wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING,
    )
    result = dialog.ShowModal()
    dialog.Destroy()

    if result == wx.ID_CANCEL:
        return False

    try:
        if result == wx.ID_YES:
            save_pdf(current_path)
        else:
            discard_pdf_changes(current_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return False

    return True


def restore_list_selection(owner, path):
    owner._restoring_list_selection = True
    try:
        for index in range(owner.list.GetItemCount()):
            owner.list.SetItemState(index, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)

        if not path or os.path.dirname(path) != owner.path_box.GetValue():
            return

        target_name = os.path.basename(path)
        for index in range(owner.list.GetItemCount()):
            if owner.list.GetItemText(index) != target_name:
                continue
            owner.list.SetItemState(
                index,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            owner.list.EnsureVisible(index)
            break
    finally:
        wx.CallAfter(_clear_list_selection_restore_flag, owner)


def _clear_list_selection_restore_flag(owner):
    owner._restoring_list_selection = False


def get_pdf_page_panel_from_event(owner, event):
    obj = event.GetEventObject()
    while obj is not None and not hasattr(obj, "page_index"):
        obj = obj.GetParent()
    return obj


def get_selected_pdf_page_index(owner):
    if owner.selected_pdf_page_panel is None:
        return None
    return getattr(owner.selected_pdf_page_panel, "page_index", None)


def can_preview_html(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in {".html", ".htm"}


def can_preview_text_file(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False
    _, ext = os.path.splitext(path)
    return ext.lower() in {
        ".txt",
        ".log",
        ".ini",
        ".cfg",
        ".conf",
        ".csv",
        ".json",
        ".xml",
        ".yaml",
        ".yml",
        ".md",
    }


def _is_preview_page_limit_active(path, owner=None):
    if not path:
        return False

    try:
        if is_pdf_file(path):
            page_count = get_pdf_page_count(path)
            return page_count > pdf_utils._get_show_pages_limit_for_path(path)

        if owner is not None:
            office_allowed = is_office_preview_allowed(owner, path)
        else:
            office_allowed = office_preview.can_preview_office(path)
        if office_allowed:
            page_count = office_preview.get_office_document_page_count(path)
            return page_count > pdf_utils._get_show_pages_limit_for_path(path)
    except Exception:
        return False

    return False


def update_page_buttons_state(owner):
    current_path = getattr(owner, "current_preview_path", None)
    is_current_path = bool(current_path)
    is_pdf_preview = is_pdf_file(current_path)
    can_select_pdf_page = is_pdf_preview and get_selected_pdf_page_index(owner) is not None
    can_rotate_image = is_current_path and image_utils.can_preview_image(current_path)
    can_preview_html_file = is_current_path and can_preview_html(current_path)
    ## can_preview_text = is_current_path and can_preview_text_file(current_path)
    can_preview_office = is_current_path and is_office_preview_allowed(owner, current_path)
    can_zoom_preview = is_pdf_preview or can_rotate_image or can_preview_html_file or can_preview_office
    can_act_on_pdf = is_pdf_preview

    owner.preview_rotate_menu_btn.Enable(is_pdf_preview or can_rotate_image)
    owner.preview_import_from_file_btn.Enable(can_act_on_pdf)
    owner.preview_export_pages_btn.Enable(can_act_on_pdf)
    owner.preview_move_page_btn.Enable(can_select_pdf_page)
    owner.preview_remove_page_btn.Enable(can_select_pdf_page)
    owner.preview_adjust_page_width_btn.Enable(is_pdf_preview)
    owner.preview_optimize_btn.Enable(is_pdf_preview)
    if hasattr(owner, "preview_zoom_in_btn"):
        owner.preview_zoom_in_btn.Enable(can_zoom_preview)
    if hasattr(owner, "preview_zoom_out_btn"):
        owner.preview_zoom_out_btn.Enable(can_zoom_preview)

    load_all_btn = getattr(owner, "preview_load_all_btn", None)
    if load_all_btn is not None:
        load_all_btn.Enable(_is_preview_page_limit_active(current_path, owner=owner) and (is_pdf_preview or is_office_preview_allowed(owner, current_path) or can_preview_html(current_path)))
    # === COPILOT PROTECTED: BEGIN ===
    ## don't remove these lines, they prevent superfluous office doc calls at update_load_all_btn_state
    ## update_load_all_btn_state is called on file select only to avoid duplicate calls
    ## update_load_all_btn_state(owner)
    # === COPILOT PROTECTED: END ===


def update_load_all_btn_state(owner):
    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    is_previewable_non_pdf = bool(owner.current_preview_path) and (
        is_office_preview_allowed(owner, owner.current_preview_path)
        or can_preview_html(owner.current_preview_path)
    )
    page_limit_active = _is_preview_page_limit_active(owner.current_preview_path, owner=owner)
    load_all_btn = getattr(owner, "preview_load_all_btn", None)
    if load_all_btn is not None:
        load_all_btn_enable = page_limit_active and (is_pdf_preview or is_previewable_non_pdf)
        load_all_btn.Enable(load_all_btn_enable)


def update_pdf_save_button_state(owner):
    can_save = is_pdf_file(owner.current_preview_path)
    can_cancel = is_pdf_file(owner.current_preview_path) and has_unsaved_pdf_changes(owner.current_preview_path)
    owner.preview_save_btn.Enable(can_save)
    owner.preview_cancel_btn.Enable(can_cancel)


def update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False):
    current_path = getattr(owner, "current_preview_path", None)
    previewable_by_path = bool(
        current_path
        and os.path.isfile(current_path)
        and (
            is_pdf_file(current_path)
            or image_utils.can_preview_image(current_path)
            or is_office_preview_allowed(owner, current_path)
            or can_preview_html(current_path)
            or can_preview_text_file(current_path)
        )
    )

    show_pdf_only = is_pdf
    show_pdf_or_image = is_pdf or is_image or previewable_by_path
    show_preview_layout = is_pdf or is_image or previewable_by_path

    owner.preview_save_btn.Show(show_pdf_only)
    owner.preview_cancel_btn.Show(show_pdf_only)
    owner.preview_rotate_menu_btn.Show(show_pdf_or_image)
    owner.preview_optimize_btn.Show(show_pdf_only)
    owner.preview_adjust_page_width_btn.Show(show_pdf_only)
    owner.preview_import_from_file_btn.Show(show_pdf_only)
    owner.preview_export_pages_btn.Show(show_pdf_only)
    owner.preview_move_page_btn.Show(show_pdf_only)
    owner.preview_remove_page_btn.Show(show_pdf_only)
    owner.preview_page_view_mode_btn.Show(show_preview_layout)

    owner.preview_toolbar.Layout()
    owner.filePreview.Layout()
    update_pdf_save_button_state(owner)


def _get_preview_layout_mode(owner):
    selected_mode = getattr(owner, "pdf_page_view_selected_mode", None)
    if selected_mode in FIXED_PAGE_VIEW_MODES:
        return selected_mode

    return PAGE_VIEW_MODE_1_TALL


def refresh_preview_for_page_view_mode(owner, path=None):
    if owner is None:
        return

    current_path = path if path is not None else getattr(owner, "current_preview_path", None)
    if not current_path:
        return

    if is_pdf_file(current_path):
        show_pdf_feed(owner, current_path)
        return

    if image_utils.can_preview_image(current_path):
        if getattr(owner, "current_image_preview", None) is not None and getattr(owner.current_image_preview, "IsOk", lambda: False)():
            image_utils.refresh_image_preview_bitmap(owner)
        else:
            image_utils.show_image_preview(owner, current_path, tr)
        return

    if is_office_preview_allowed(owner, current_path):
        try:
            preview_pdf_path = _resolve_preview_pdf_path(current_path)
            if preview_pdf_path is None:
                raise RuntimeError(tr("unable_preview_file"))
            show_pdf_feed(owner, preview_pdf_path)
            return
        except Exception as exc:
            owner.preview_text.SetValue(tr("unable_preview_file", exc=exc))
            owner.preview_text.Show(True)
            owner.pdf_pages_panel.Hide()
            owner.pdf_preview_container.Hide()
            owner.filePreview.Layout()
            return

    if can_preview_html(current_path):
        show_html_preview(owner, current_path)
        return


def sync_pdf_page_view_mode_controls(owner):
    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    if current_mode in FIXED_PAGE_VIEW_MODES:
        owner.pdf_page_view_selected_mode = current_mode

    selected_mode = getattr(owner, "pdf_page_view_selected_mode", PAGE_VIEW_MODE_1_TALL)
    if selected_mode not in FIXED_PAGE_VIEW_MODES:
        selected_mode = PAGE_VIEW_MODE_1_WIDE

    if current_mode == PAGE_VIEW_MODE_MANUAL:
        tooltip_text = tr("preview_show_manual_scale")
    elif selected_mode == PAGE_VIEW_MODE_1_WIDE:
        tooltip_text = tr("preview_show_1_page_wide")
    elif selected_mode == PAGE_VIEW_MODE_2_WIDE:
        tooltip_text = tr("preview_show_2_pages_wide")
    elif selected_mode == PAGE_VIEW_MODE_1_TALL:
        tooltip_text = tr("preview_show_1_page_tall")
    else:
        tooltip_text = tr("preview_show_1_page_wide")

    owner.preview_page_view_mode_btn.SetToolTip(tooltip_text)

def _set_pdf_page_view_mode(owner, mode):
    if owner is None or not hasattr(owner, "set_pdf_page_view_mode"):
        return
    owner.pdf_page_view_selected_mode = mode
    owner.set_pdf_page_view_mode(mode, refresh_preview=True)


def on_preview_show_1_page_wide(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_1_WIDE)


def on_preview_show_2_pages_wide(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_2_WIDE)


def on_preview_show_1_page_tall(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_1_TALL)


def on_preview_show_manual_scale(event):
    owner = _get_preview_owner_from_event(event)
    _set_pdf_page_view_mode(owner, PAGE_VIEW_MODE_MANUAL)


def build_page_view_mode_menu(owner, menu):
    show_1_page_wide_item = menu.AppendRadioItem(-1, tr("preview_show_1_page_wide"))
    show_2_pages_wide_item = menu.AppendRadioItem(-1, tr("preview_show_2_pages_wide"))
    show_1_page_tall_item = menu.AppendRadioItem(-1, tr("preview_show_1_page_tall"))
    show_manual_scale_item = menu.AppendRadioItem(-1, tr("preview_show_manual_scale"))

    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    selected_mode = getattr(owner, "pdf_page_view_selected_mode", PAGE_VIEW_MODE_1_TALL)
    if selected_mode not in FIXED_PAGE_VIEW_MODES:
        selected_mode = PAGE_VIEW_MODE_1_TALL

    show_1_page_wide_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_1_WIDE)
    show_2_pages_wide_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_2_WIDE)
    show_1_page_tall_item.Check(current_mode != PAGE_VIEW_MODE_MANUAL and selected_mode == PAGE_VIEW_MODE_1_TALL)
    show_manual_scale_item.Check(current_mode == PAGE_VIEW_MODE_MANUAL)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    can_preview_layout = (
        is_pdf_preview
        or image_utils.can_preview_image(owner.current_preview_path)
        or is_office_preview_allowed(owner, owner.current_preview_path)
        or can_preview_html(owner.current_preview_path)
    )
    show_1_page_wide_item.Enable(can_preview_layout)
    show_2_pages_wide_item.Enable(can_preview_layout)
    show_1_page_tall_item.Enable(can_preview_layout)
    show_manual_scale_item.Enable(can_preview_layout)

    owner.Bind(wx.EVT_MENU, on_preview_show_1_page_wide, show_1_page_wide_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_2_pages_wide, show_2_pages_wide_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_1_page_tall, show_1_page_tall_item)
    owner.Bind(wx.EVT_MENU, on_preview_show_manual_scale, show_manual_scale_item)


def on_preview_page_view_mode_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_page_view_mode_menu(owner, menu)
    sync_pdf_page_view_mode_controls(owner)
    anchor = (0, owner.preview_page_view_mode_btn.GetSize().GetHeight())
    owner.preview_page_view_mode_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def build_save_menu(owner, menu):
    icon_manager = getattr(owner, "icon_manager", None)

    save_item = menu.Append(-1, tr("preview_save_button"))
    save_as_item = menu.Append(-1, tr("preview_save_as_button"))

    if icon_manager is not None:
        icon_manager.set_menu_icon2(save_item, "save")

    save_as_art_id = getattr(wx, "ART_FILE_SAVE_AS", wx.ART_FILE_SAVE)
    save_as_bitmap = wx.ArtProvider.GetBitmap(save_as_art_id, wx.ART_MENU, (16, 16))
    if save_as_bitmap.IsOk():
        save_as_item.SetBitmap(save_as_bitmap)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    save_item.Enable(is_pdf_preview and has_unsaved_pdf_changes(owner.current_preview_path))
    save_as_item.Enable(is_pdf_preview)

    owner.Bind(wx.EVT_MENU, on_preview_save, save_item)
    owner.Bind(wx.EVT_MENU, on_preview_save_as, save_as_item)

    return {
        "save_item": save_item,
        "save_as_item": save_as_item,
    }


def on_preview_save_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_save_menu(owner, menu)
    anchor = (0, owner.preview_save_btn.GetSize().GetHeight())
    owner.preview_save_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def build_rotation_menu(owner, menu):
    rotate_all_left_item = menu.Append(-1, tr("preview_rotate_all_left_button"))
    joined_menu_undo = image_utils.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_MENU, size=(16, 16))
    if joined_menu_undo.IsOk():
        rotate_all_left_item.SetBitmap(joined_menu_undo)

    rotate_left_item = menu.Append(-1, tr("preview_rotate_left_button"))
    left_bitmap = wx.ArtProvider.GetBitmap(wx.ART_UNDO, wx.ART_MENU, (16, 16))
    if left_bitmap.IsOk():
        rotate_left_item.SetBitmap(left_bitmap)

    rotate_right_item = menu.Append(-1, tr("preview_rotate_right_button"))
    right_bitmap = wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_MENU, (16, 16))
    if right_bitmap.IsOk():
        rotate_right_item.SetBitmap(right_bitmap)

    rotate_all_right_item = menu.Append(-1, tr("preview_rotate_all_right_button"))
    joined_menu_redo = image_utils.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_MENU, size=(16, 16))
    if joined_menu_redo.IsOk():
        rotate_all_right_item.SetBitmap(joined_menu_redo)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    can_rotate_image = image_utils.can_preview_image(owner.current_preview_path)
    can_rotate_single = (is_pdf_preview and get_selected_pdf_page_index(owner) is not None) or can_rotate_image

    rotate_all_left_item.Enable(is_pdf_preview)
    rotate_all_right_item.Enable(is_pdf_preview)
    rotate_left_item.Enable(can_rotate_single)
    rotate_right_item.Enable(can_rotate_single)

    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_left, rotate_all_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_left, rotate_left_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_right, rotate_right_item)
    owner.Bind(wx.EVT_MENU, on_preview_rotate_all_right, rotate_all_right_item)

    return {
        "rotate_all_left_item": rotate_all_left_item,
        "rotate_left_item": rotate_left_item,
        "rotate_right_item": rotate_right_item,
        "rotate_all_right_item": rotate_all_right_item,
    }


def build_import_menu(owner, menu):
    icon_manager = getattr(owner, "icon_manager", None)

    import_item = menu.Append(-1, tr("preview_import_from_file_button"))
    import_bitmap = wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_MENU, (16, 16))
    if import_bitmap.IsOk():
        import_item.SetBitmap(import_bitmap)

    import_scanner_item = menu.Append(-1, tr("preview_import_from_scanner_button"))
    if icon_manager:
        icon_manager.set_menu_icon2(import_scanner_item, "scan")

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    import_item.Enable(is_pdf_preview)
    import_scanner_item.Enable(is_pdf_preview)

    owner.Bind(wx.EVT_MENU, on_preview_import_from_file, import_item)
    owner.Bind(wx.EVT_MENU, on_preview_import_from_scanner, import_scanner_item)

    return {
        "import_item": import_item,
        "import_scanner_item": import_scanner_item,
    }


def _build_import_export_menu(owner, menu):
    build_import_menu(owner, menu)

    export_art_id = getattr(wx, "ART_FILE_SAVE_AS", wx.ART_FILE_SAVE)
    export_item = menu.Append(-1, tr("preview_export_pages_button"))
    export_bitmap = wx.ArtProvider.GetBitmap(export_art_id, wx.ART_MENU, (16, 16))
    if export_bitmap.IsOk():
        export_item.SetBitmap(export_bitmap)

    is_pdf_preview = is_pdf_file(owner.current_preview_path)
    export_item.Enable(is_pdf_preview)

    owner.Bind(wx.EVT_MENU, on_preview_export_pages, export_item)

    return {
        "export_item": export_item,
    }


def on_preview_rotate_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_rotation_menu(owner, menu)
    anchor = (0, owner.preview_rotate_menu_btn.GetSize().GetHeight())
    owner.preview_rotate_menu_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def _compute_pdf_preview_max_height(owner):
    max_bitmap_width, max_bitmap_height = _compute_pdf_page_fit_constraints(owner)
    mode = _get_preview_layout_mode(owner)
    portrait_width_ratio = 0.707
    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    zoom_scale = max(0.2, float(getattr(owner, "pdf_preview_zoom", 1.0))) if current_mode == PAGE_VIEW_MODE_MANUAL else 1.0

    if mode == PAGE_VIEW_MODE_1_TALL:
        base_height = max_bitmap_height
    else:
        page_width = max_bitmap_width
        base_height = int(page_width / portrait_width_ratio)
    max_height = int(base_height * zoom_scale)

    return max(80, min(6000, max_height))


def _get_average_pdf_page_dimensions(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return None, None

    doc = None
    try:
        doc = pdf_utils._open_pdf_document(path)
        widths = []
        heights = []
        for page in doc:
            rect = page.rect
            if rect.width <= 0 or rect.height <= 0:
                continue
            widths.append(float(rect.width))
            heights.append(float(rect.height))
        if not widths:
            return None, None
        return sum(widths) / len(widths), sum(heights) / len(heights)
    except Exception:
        return None, None
    finally:
        if doc is not None and not getattr(doc, "is_closed", False):
            doc.close()


def _get_preview_target_size_for_mode(owner, path, max_bitmap_width, max_bitmap_height):
    current_mode = getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL)
    layout_mode = _get_preview_layout_mode(owner)
    is_manual_mode = current_mode == PAGE_VIEW_MODE_MANUAL
    zoom_scale = max(0.2, float(getattr(owner, "pdf_preview_zoom", 1.0))) if is_manual_mode else 1.0
    average_width, average_height = _get_average_pdf_page_dimensions(path)
    target_zoom = 1.0

    if layout_mode == PAGE_VIEW_MODE_1_TALL and average_width and average_height:
        target_height = max(80, int(round(max_bitmap_height * zoom_scale)))
        target_width = int(round(target_height * average_width / average_height))
        target_zoom = average_height / average_width
        if not is_manual_mode and target_width > max_bitmap_width:
            target_width = max_bitmap_width
            target_height = int(round(target_width * target_zoom))
        return target_width, target_height, target_zoom, None, average_height

    if layout_mode in {PAGE_VIEW_MODE_1_WIDE, PAGE_VIEW_MODE_2_WIDE} and average_width and average_height:
        target_width = max(80, int(round(max_bitmap_width * zoom_scale)))
        target_height = int(round(target_width * average_height / average_width))
        target_zoom = average_width / average_height
        if not is_manual_mode and target_height > max_bitmap_height:
            target_height = max_bitmap_height
            target_width = int(round(target_height * target_zoom))
        return target_width, target_height, target_zoom, average_width, None

    target_width = max_bitmap_width
    target_height = max_bitmap_height
    if is_manual_mode:
        target_width = max(80, int(round(target_width * zoom_scale)))
        target_height = max(80, min(6000, int(round(target_height * zoom_scale))))

    return target_width, target_height, target_zoom, average_width, average_height


def _compute_pdf_page_fit_constraints(owner):
    panel_size = owner.pdf_pages_panel.GetClientSize()
    preview_size = owner.filePreview.GetClientSize()

    client_width = max(panel_size.x, preview_size.x - 24, 320)
    client_height = max(panel_size.y, preview_size.y - 24, 220)
    mode = _get_preview_layout_mode(owner)

    # Keep in sync with show_pdf_feed layout chrome.
    gap_width = 22
    page_panel_outer_margin = 6  # wx.ALL, 3 on page panel in parent sizer.
    page_panel_inner_margin = 6  # wx.ALL, 3 on bitmap in page panel sizer.
    page_panel_border = 4        # wx.BORDER_SIMPLE around page panel.
    label_height = max(20, int(owner.pdf_pages_panel.GetCharHeight()) + 8)
    fit_safety_margin = 24

    vscroll_width = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
    if vscroll_width < 0:
        vscroll_width = 16
    hscroll_height = wx.SystemSettings.GetMetric(wx.SYS_HSCROLL_Y)
    if hscroll_height < 0:
        hscroll_height = 16

    per_page_horizontal = page_panel_outer_margin + page_panel_inner_margin + page_panel_border
    per_page_vertical = page_panel_inner_margin + page_panel_border + label_height + hscroll_height

    if mode == PAGE_VIEW_MODE_2_WIDE:
        available_width = client_width - (gap_width * 3) - (per_page_horizontal * 2) - vscroll_width + fit_safety_margin
        max_bitmap_width = max(80, available_width // 2)
    else:
        available_width = client_width - gap_width - per_page_horizontal - vscroll_width
        max_bitmap_width = max(80, available_width)

    available_height = client_height - per_page_vertical - fit_safety_margin
    if mode == PAGE_VIEW_MODE_1_TALL:
        max_bitmap_height = max(80, available_height)
    else:
        max_bitmap_height = available_height * 10

    return max_bitmap_width, max_bitmap_height


def select_pdf_page(owner, page_panel):
    if owner.selected_pdf_page_panel is page_panel:
        return

    if owner.selected_pdf_page_panel is not None:
        owner.selected_pdf_page_panel.SetBackgroundColour(wx.NullColour)
        owner.selected_pdf_page_panel.Refresh()

    owner.selected_pdf_page_panel = page_panel
    owner.selected_pdf_page_panel.SetBackgroundColour(wx.Colour(200, 230, 255))
    owner.selected_pdf_page_panel.Refresh()
    update_page_buttons_state(owner)
    update_load_all_btn_state(owner)


def on_pdf_page_select(owner, event):
    page_panel = get_pdf_page_panel_from_event(owner, event)
    if page_panel is None:
        return

    select_pdf_page(owner, page_panel)
    owner._pdf_drag_start_panel = page_panel
    owner._pdf_drag_start_pos = event.GetPosition()
    event.Skip()


def on_pdf_page_drag_motion(owner, event):
    if not is_pdf_file(getattr(owner, "current_preview_path", None)):
        return
    drag_and_drop.on_pdf_page_drag_motion(owner, event)


def _start_pdf_page_drag(owner, page_panel):
    drag_and_drop.start_pdf_page_drag(owner, page_panel)


def handle_pdf_page_drop(owner, target_index, payload, insert_before=True):
    drag_and_drop.handle_pdf_page_drop(owner, target_index, payload, insert_before=insert_before)


def clear_pdf_feed(owner):
    """Clear the PDF feed display."""
    owner.pdf_pages_sizer.Clear(True)
    owner.selected_pdf_page_panel = None
    update_page_buttons_state(owner)


def _ensure_html_preview_widget(owner):
    if getattr(owner, "html_preview", None) is not None:
        return owner.html_preview

    if not hasattr(owner, "pdf_preview_container") or owner.pdf_preview_container is None:
        return None

    if wx_html2 is not None:
        html_preview = wx_html2.WebView.New(owner.pdf_preview_container)
        html_preview.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

        if hasattr(owner.pdf_preview_container, "GetSizer"):
            container_sizer = owner.pdf_preview_container.GetSizer()
            if container_sizer is None:
                container_sizer = wx.BoxSizer(wx.VERTICAL)
                owner.pdf_preview_container.SetSizer(container_sizer)
            try:
                container_sizer.Clear(True)
            except Exception:
                pass
            container_sizer.Add(html_preview, 1, wx.EXPAND)

        if hasattr(owner, "pdf_preview") and owner.pdf_preview is not None:
            owner.pdf_preview.Hide()

        owner.html_preview = html_preview
        return html_preview

    owner.html_preview = None
    return None


def _apply_html_zoom(owner, html_preview):
    if html_preview is None:
        return

    try:
        owner.current_html_zoom = max(0.2, min(float(getattr(owner, "current_html_zoom", 1.0)), 4.0))
        zoom_percent = max(20, int(round(owner.current_html_zoom * 100)))
        html_preview.SetZoom(zoom_percent)
    except Exception:
        pass


def show_html_preview(owner, path):
    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Hide()

    if hasattr(owner, "pdf_preview") and owner.pdf_preview is not None:
        owner.pdf_preview.Hide()

    html_preview = _ensure_html_preview_widget(owner)
    if html_preview is None:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            owner.preview_text.SetValue(handle.read())
        owner.preview_text.Show(True)
        owner.pdf_preview_container.Hide()
        owner.filePreview.Layout()
        return

    try:
        owner.current_html_zoom = max(0.2, min(float(getattr(owner, "current_html_zoom", 1.0)), 4.0))
        zoom_percent = max(20, int(round(owner.current_html_zoom * 100)))

        try:
            container_size = owner.pdf_preview_container.GetClientSize()
            if hasattr(container_size, "x") and hasattr(container_size, "y"):
                if container_size.x > 0 and container_size.y > 0:
                    html_preview.SetMinSize((container_size.x, container_size.y))
                    html_preview.SetSize((container_size.x, container_size.y))
            elif isinstance(container_size, (tuple, list)) and len(container_size) >= 2:
                width, height = container_size[:2]
                if width > 0 and height > 0:
                    html_preview.SetMinSize((width, height))
                    html_preview.SetSize((width, height))
        except Exception:
            pass

        html_preview.SetZoom(zoom_percent)
        normalized_path = os.path.abspath(path).replace("\\", "/")
        html_preview.LoadURL("file:///" + normalized_path)
        if hasattr(wx_html2, "EVT_WEBVIEW_LOADED"):
            wx.CallAfter(_apply_html_zoom, owner, html_preview)
    except Exception:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            html_preview.SetPage(handle.read(), "")
        html_preview.SetZoom(zoom_percent)

    owner.pdf_preview_container.Show(True)
    owner.pdf_preview_container.Layout()
    if hasattr(owner, "filePreview"):
        owner.filePreview.Layout()


def _resolve_preview_pdf_path(path, max_pages=None, owner=None):
    if not path:
        return None

    if is_pdf_file(path):
        return path

    if owner is not None:
        office_allowed = is_office_preview_allowed(owner, path)
    else:
        office_allowed = office_preview.can_preview_office(path)
    if office_allowed:
        try:
            if max_pages is None:
                return office_preview.convert_office_to_preview_pdf(path)
            return office_preview.convert_office_to_preview_pdf(path, max_pages=max_pages)
        except Exception:
            return None

    return None


def on_preview_load_all_pages(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None or not hasattr(owner, "current_preview_path"):
        return

    path = getattr(owner, "current_preview_path", None)
    if not path:
        return

    load_all_btn = getattr(owner, "preview_load_all_btn", None)
    if load_all_btn is not None:
        load_all_btn.Enable(False)

    cursor_context = owner.busy_cursor() if hasattr(owner, "busy_cursor") else nullcontext()
    with cursor_context:
        try:
            if not is_office_preview_allowed(owner, path) and not is_pdf_file(path):
                return

            if is_office_preview_allowed(owner, path):
                page_count = office_preview.get_office_document_page_count(path)
                preview_path = _resolve_preview_pdf_path(path, max_pages=page_count, owner=owner)
            else:
                preview_path = _resolve_preview_pdf_path(path, owner=owner)

            if not preview_path or not os.path.isfile(preview_path):
                return
            if get_pdf_page_count(preview_path) <= pdf_utils._get_show_pages_limit_for_path(path):
                return
            show_pdf_feed(owner, preview_path, force_all_pages=True)
        except Exception:
            pass
        finally:
            if load_all_btn is not None:
                load_all_btn.Enable(False)


def show_pdf_feed(owner, path, force_all_pages=False):
    update_preview_toolbar_visibility(owner, is_pdf=True, is_image=False)
    sync_pdf_page_view_mode_controls(owner)
    with owner.busy_cursor():
        try:
            owner.current_pdf_path = path
            clear_pdf_feed(owner)
            max_height = _compute_pdf_preview_max_height(owner)
            max_bitmap_width, max_bitmap_height = _compute_pdf_page_fit_constraints(owner)
            target_width, target_height, target_zoom, avg_width, avg_height = _get_preview_target_size_for_mode(
                owner,
                path,
                max_bitmap_width,
                max_bitmap_height,
            )

            page_count, shown_pages, previews = get_pdf_page_previews(
                path,
                max_height=max_height,
                target_width=target_width,
                target_height=target_height,
                target_zoom=target_zoom,
                avg_width=avg_width,
                avg_height=avg_height,
                force_all_pages=force_all_pages,
            )

            gap_width = 22
            page_height = 180
            if previews:
                tallest_preview_height = max(bitmap.GetSize().y for _, bitmap in previews if bitmap and bitmap.IsOk())
                page_height = max(160, tallest_preview_height)

            leading_gap = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
            leading_gap.SetMinSize((gap_width, page_height))
            leading_gap.page_index = 0
            leading_gap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
            leading_gap.SetDropTarget(PdfPageDropTarget(owner, 0, leading_gap, insert_before=True))
            owner.pdf_pages_sizer.Add(leading_gap, 0, wx.ALL, 0)

            for index, (page_no, bitmap) in enumerate(previews):
                page_panel = wx.Panel(owner.pdf_pages_panel, style=wx.BORDER_SIMPLE)
                page_panel.page_index = index
                page_panel.SetDropTarget(PdfPageDropTarget(owner, index, page_panel))

                def make_select_handler(owner_ref):
                    return lambda evt: on_pdf_page_select_wrapper(owner_ref, evt)

                def make_motion_handler(owner_ref):
                    return lambda evt: on_pdf_page_drag_motion(owner_ref, evt)

                page_panel.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_panel.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

                page_sizer = wx.BoxSizer(wx.VERTICAL)
                page_label = wx.StaticText(page_panel, label=tr("page_label", page_no=page_no, page_count=page_count))
                page_bitmap = wx.StaticBitmap(page_panel, bitmap=bitmap)

                page_label.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_label.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_label.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
                page_bitmap.Bind(wx.EVT_LEFT_DOWN, make_select_handler(owner))
                page_bitmap.Bind(wx.EVT_MOTION, make_motion_handler(owner))
                page_bitmap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)

                page_sizer.Add(page_label, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                page_sizer.Add(page_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                page_panel.SetSizer(page_sizer)

                owner.pdf_pages_sizer.Add(page_panel, 0, wx.ALL, 3)

                gap_panel = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
                gap_panel.SetMinSize((gap_width, page_height))
                gap_panel.page_index = index + 1
                gap_panel.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
                gap_panel.SetDropTarget(PdfPageDropTarget(owner, index + 1, gap_panel, insert_before=True))
                owner.pdf_pages_sizer.Add(gap_panel, 0, wx.ALL, 0)

            trailing_gap = wx.Panel(owner.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
            trailing_gap.SetMinSize((gap_width, page_height))
            trailing_gap.page_index = page_count
            trailing_gap.Bind(wx.EVT_CONTEXT_MENU, on_preview_right_click)
            trailing_gap.SetDropTarget(PdfPageDropTarget(owner, page_count, trailing_gap, insert_before=False))
            owner.pdf_pages_sizer.Add(trailing_gap, 0, wx.ALL, 0)

            if page_count > shown_pages:
                note = wx.StaticText(
                    owner.pdf_pages_panel,
                    label=tr("showing_first_pages", shown_pages=shown_pages, page_count=page_count),
                )
                owner.pdf_pages_sizer.Add(note, 0, wx.ALIGN_CENTER | wx.ALL, 3)
        except Exception as exc:
            _ = exc
            owner.pdf_pages_panel.Hide()
            owner.filePreview.Layout()
            return

            update_pdf_save_button_state(owner)

    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Show(True)
    owner.pdf_pages_panel.Layout()
    owner.pdf_pages_panel.FitInside()
    owner.filePreview.Layout()


def on_pdf_page_select_wrapper(owner, event):
    """Wrapper to handle PDF page selection with owner context."""
    on_pdf_page_select(owner, event)


def _reset_pdf_view_mode_for_new_file(owner, previous_path, next_path):
    if not is_pdf_file(previous_path) or not is_pdf_file(next_path):
        return

    if os.path.normpath(previous_path) == os.path.normpath(next_path):
        return

    if getattr(owner, "pdf_page_view_mode", PAGE_VIEW_MODE_1_TALL) != PAGE_VIEW_MODE_MANUAL:
        return

    selected_mode = getattr(owner, "pdf_page_view_selected_mode", PAGE_VIEW_MODE_1_WIDE)
    if selected_mode not in FIXED_PAGE_VIEW_MODES:
        selected_mode = PAGE_VIEW_MODE_1_WIDE

    owner.pdf_preview_zoom = 1.0
    owner.pdf_page_view_mode = selected_mode


def is_office_preview_allowed(owner, path):
    if not office_preview.can_preview_office(path):
        return False
    if not bool(getattr(owner, "preview_enabled", True)):
        return False

    office_preview_value = getattr(owner, "office_preview_enabled", None)
    if office_preview_value is None:
        return True
    return bool(office_preview_value)


def on_preview_checkbox_toggle(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    checkbox = event.GetEventObject()
    owner.preview_enabled = bool(getattr(checkbox, "GetValue", lambda: False)())
    if hasattr(owner, "office_preview_checkbox"):
        owner.office_preview_checkbox.Enable(owner.preview_enabled)
    update_settings({"preview_enabled": owner.preview_enabled})
    show_file_preview(owner, None)


def on_office_preview_checkbox_toggle(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    checkbox = event.GetEventObject()
    owner.office_preview_enabled = bool(getattr(checkbox, "GetValue", lambda: False)())
    update_settings({"office_preview_enabled": owner.office_preview_enabled})

    current_preview_path = getattr(owner, "current_preview_path", None)
    if not getattr(owner, "preview_enabled", True) or not current_preview_path:
        return

    if owner.office_preview_enabled:
        show_file_preview(owner, None)
    show_file_preview(owner, current_preview_path)


def show_file_preview(owner, path):
    _ensure_preview_tab_state(owner)
    if path:
        _sync_preview_tab_for_path(owner, path)

    if not getattr(owner, "preview_enabled", True):
        owner.current_preview_path = path
        owner.preview_text.Show(False)
        owner.pdf_pages_panel.Hide()
        owner.pdf_preview_container.Hide()
        if hasattr(owner, "office_preview_checkbox"):
            owner.office_preview_checkbox.Enable(False)
        owner.filePreview.Layout()
        return

    previous_path = getattr(owner, "current_preview_path", None)
    normalized_previous = os.path.normcase(os.path.normpath(previous_path)) if isinstance(previous_path, str) and previous_path else None
    normalized_path = os.path.normcase(os.path.normpath(path)) if isinstance(path, str) and path else None
    is_same_office_file = bool(normalized_path and normalized_previous and normalized_path == normalized_previous and is_office_preview_allowed(owner, path))

    owner.current_preview_path = path
    _reset_pdf_view_mode_for_new_file(owner, previous_path, path)
    owner.selected_pdf_page_panel = None
    owner.current_image_preview = None
    owner.current_image_zoom = 1.0
    owner.current_html_zoom = 1.0
    owner.preview_text.Show(False)
    owner.pdf_pages_panel.Hide()
    owner.pdf_preview_container.Hide()

    can_preview_office = is_office_preview_allowed(owner, path)
    if not can_preview_office:
        update_page_buttons_state(owner)
        update_pdf_save_button_state(owner)

    if not path:
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if is_same_office_file:
        return

    if os.path.isdir(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if not os.path.isfile(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
        owner.filePreview.Layout()
        return

    if is_pdf_file(path):
        update_preview_toolbar_visibility(owner, is_pdf=True, is_image=False)
        show_pdf_feed(owner, path)
        return

    if image_utils.can_preview_image(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=True)
        image_utils.show_image_preview(owner, path, tr)
        return

    if can_preview_html(path):
        update_preview_toolbar_visibility(owner, is_pdf=False, is_image=True)
        owner.current_html_zoom = max(0.2, min(float(getattr(owner, "current_html_zoom", 1.0)), 4.0))
        show_html_preview(owner, path)
        return

    if can_preview_text_file(path):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                text = handle.read()
            owner.preview_text.SetValue(text)
            owner.preview_text.Show(True)
            owner.pdf_pages_panel.Hide()
            owner.pdf_preview_container.Hide()
            update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
            owner.filePreview.Layout()
            return
        except Exception as exc:
            owner.preview_text.SetValue(tr("unable_preview_file", exc=exc))
            owner.preview_text.Show(True)
            owner.pdf_pages_panel.Hide()
            owner.pdf_preview_container.Hide()
            owner.filePreview.Layout()
            return

    if can_preview_office:
        try:
            cursor_context = owner.busy_cursor() if hasattr(owner, "busy_cursor") else nullcontext()
            with cursor_context:
                preview_pdf_path = _resolve_preview_pdf_path(path)
                if preview_pdf_path is None:
                    raise RuntimeError(tr("unable_preview_file"))
                show_pdf_feed(owner, preview_pdf_path)
                update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
                update_pdf_save_button_state(owner)
                return
        except Exception as exc:
            owner.preview_text.SetValue(tr("unable_preview_file", exc=exc))
            owner.preview_text.Show(True)
            owner.pdf_pages_panel.Hide()
            owner.pdf_preview_container.Hide()
            owner.filePreview.Layout()
            return

    update_preview_toolbar_visibility(owner, is_pdf=False, is_image=False)
    owner.preview_text.SetValue("")
    owner.preview_text.Show(False)
    owner.filePreview.Layout()


# Preview action handlers
def _get_preview_owner_from_event(event, fallback_owner=None):
    if fallback_owner is not None:
        owner = fallback_owner
    elif event is not None and hasattr(event, "GetEventObject"):
        owner = event.GetEventObject()
    else:
        owner = None

    while owner is not None and not hasattr(owner, "current_preview_path"):
        owner = owner.GetParent() if hasattr(owner, "GetParent") else None

    # EVT_MENU events may come from menu/menu-item objects that are not in the window tree.
    if owner is None:
        for top_level in wx.GetTopLevelWindows():
            if hasattr(top_level, "current_preview_path"):
                owner = top_level
                break

    return owner

def on_preview_edit(event):
    owner = _get_preview_owner_from_event(event)
    if owner and owner.current_preview_path and os.path.isfile(owner.current_preview_path):
        try:
            os.startfile(owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
    else:
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)


def on_preview_delete(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not owner.current_preview_path or not os.path.isfile(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return
    dialog = wx.MessageDialog(
        owner,
        tr("confirm_delete", path=owner.current_preview_path),
        tr("preview_delete_button"),
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    if dialog.ShowModal() == wx.ID_YES:
        try:
            discard_pdf_changes(owner.current_preview_path)
            os.remove(owner.current_preview_path)
            show_file_preview(owner, None)
            owner.load_folder(owner.path_box.GetValue())
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
    dialog.Destroy()


def _refresh_preview_after_pdf_save(owner, saved_path):
    owner.load_folder(owner.path_box.GetValue())
    show_file_preview(owner, saved_path)

    current_folder = os.path.normpath(owner.path_box.GetValue())
    saved_folder = os.path.normpath(os.path.dirname(saved_path))
    if current_folder != saved_folder:
        return

    target_name = os.path.basename(saved_path)
    for index in range(owner.list.GetItemCount()):
        state_mask = wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED
        owner.list.SetItemState(index, 0, state_mask)
        if owner.list.GetItemText(index) != target_name:
            continue
        owner.list.SetItemState(index, state_mask, state_mask)
        owner.list.EnsureVisible(index)
        break


def on_preview_save(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return
    try:
        with owner.busy_cursor():
            save_pdf(owner.current_preview_path)
            update_pdf_save_button_state(owner)
            _refresh_preview_after_pdf_save(owner, owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_cancel(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    if not has_unsaved_pdf_changes(owner.current_preview_path):
        return

    try:
        with owner.busy_cursor():
            discard_pdf_changes(owner.current_preview_path)
            _refresh_preview_after_pdf_save(owner, owner.current_preview_path)
            update_pdf_save_button_state(owner)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def _prompt_preview_save_as_path(owner):
    current_path = getattr(owner, "current_preview_path", None)
    if not is_pdf_file(current_path):
        return None

    current_name = os.path.basename(current_path)
    dialog = wx.TextEntryDialog(owner, "Enter new file name:", tr("preview_save_as_button"), value=current_name)
    result = dialog.ShowModal()
    new_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not new_name:
        return None

    original_ext = os.path.splitext(current_name)[1]
    if original_ext and not os.path.splitext(new_name)[1]:
        new_name += original_ext

    new_path = os.path.join(os.path.dirname(current_path), new_name)
    if os.path.normpath(new_path) == os.path.normpath(current_path):
        return new_path

    if os.path.exists(new_path):
        dialog = wx.MessageDialog(
            owner,
            f"{new_name} already exists. Overwrite it?",
            tr("preview_save_as_button"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        should_overwrite = dialog.ShowModal() == wx.ID_YES
        dialog.Destroy()
        if not should_overwrite:
            return None

    return new_path


def _get_preview_dialog_initial_dir(owner):
    search_box = getattr(owner, "search_box", None)
    if search_box is not None:
        candidate = str(search_box.GetValue()).strip()
        if candidate:
            normalized_candidate = os.path.abspath(candidate)
            if os.path.isdir(normalized_candidate):
                return normalized_candidate

            candidate_parent = os.path.dirname(normalized_candidate)
            if candidate_parent and os.path.isdir(candidate_parent):
                return candidate_parent

    current_path = getattr(owner, "current_preview_path", None)
    if isinstance(current_path, str) and current_path:
        current_parent = os.path.dirname(os.path.abspath(current_path))
        if current_parent and os.path.isdir(current_parent):
            return current_parent

    return os.getcwd()


def _restore_dialog_geometry(dialog, settings_key):
    settings = load_settings()
    size = settings.get(settings_key)
    if isinstance(size, list) and len(size) == 2:
        try:
            width, height = int(size[0]), int(size[1])
        except (TypeError, ValueError):
            width, height = None, None
        if width is not None and height is not None and width > 100 and height > 100:
            dialog.SetSize((width, height))

    position = settings.get(f"{settings_key}_position")
    if isinstance(position, list) and len(position) == 2:
        try:
            x, y = int(position[0]), int(position[1])
        except (TypeError, ValueError):
            x, y = None, None
        if x is not None and y is not None:
            dialog.SetPosition((x, y))


def _save_dialog_geometry(dialog, settings_key):
    size = dialog.GetSize()
    position = dialog.GetPosition()
    update_settings(
        {
            settings_key: [int(size.x), int(size.y)],
            f"{settings_key}_position": [int(position.x), int(position.y)],
        }
    )


def _show_import_pdf_dialog(owner, page_count):
    dialog = wx.Dialog(owner, title=tr("import_pdf_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    source_label = wx.StaticText(panel, label=tr("import_pdf_source_label"))
    source_text = wx.TextCtrl(panel)
    browse_btn = wx.Button(panel, label=tr("import_pdf_browse_button"))

    def browse_for_pdf(_):
        file_dialog = wx.FileDialog(
            dialog,
            tr("import_pdf_file_dialog_title"),
            defaultDir=_get_preview_dialog_initial_dir(owner),
            wildcard="PDF files (*.pdf)|*.pdf",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )
        if file_dialog.ShowModal() == wx.ID_OK:
            source_text.SetValue(file_dialog.GetPath())
        file_dialog.Destroy()

    browse_btn.Bind(wx.EVT_BUTTON, browse_for_pdf)

    destination_box = wx.StaticBox(panel, label=tr("import_pdf_destination_label"))
    destination_sizer = wx.StaticBoxSizer(destination_box, wx.VERTICAL)
    at_begin_radio = wx.RadioButton(panel, label=tr("move_page_at_begin"), style=wx.RB_GROUP)
    after_page_radio = wx.RadioButton(panel, label=tr("import_pdf_after_page"))
    at_end_radio = wx.RadioButton(panel, label=tr("move_page_at_end"))
    page_number_spin = wx.SpinCtrl(panel, min=1, max=max(1, page_count), initial=max(1, min(page_count, (get_selected_pdf_page_index(owner) or 0) + 1)), size=(80, -1))

    def update_after_page_state(_):
        enabled = after_page_radio.GetValue() and page_count > 0
        page_number_spin.Enable(enabled)

    at_begin_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    after_page_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    at_end_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    at_end_radio.SetValue(True)
    update_after_page_state(None)

    destination_sizer.Add(at_begin_radio, 0, wx.TOP, 3)
    after_page_sizer = wx.BoxSizer(wx.HORIZONTAL)
    after_page_sizer.Add(after_page_radio, 0, wx.RIGHT, 6)
    after_page_sizer.Add(page_number_spin, 0)
    destination_sizer.Add(after_page_sizer, 0, wx.TOP, 3)
    destination_sizer.Add(at_end_radio, 0)

    source_row = wx.BoxSizer(wx.HORIZONTAL)
    source_row.Add(source_text, 1, wx.RIGHT, 8)
    source_row.Add(browse_btn, 0)

    ok_btn = wx.Button(panel, wx.ID_OK)
    cancel_btn = wx.Button(panel, wx.ID_CANCEL, tr("preview_cancel_button"))
    ok_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_TICK_MARK", wx.ART_INFORMATION), wx.ART_BUTTON, (16, 16))
    if ok_bmp.IsOk():
        ok_btn.SetBitmap(ok_bmp)
    cancel_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_CROSS_MARK", wx.ART_DELETE), wx.ART_BUTTON, (16, 16))
    if cancel_bmp.IsOk():
        cancel_btn.SetBitmap(cancel_bmp)
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(source_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(source_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(destination_sizer, 0, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    _restore_dialog_geometry(dialog, "import_pdf_dialog_size")

    result = dialog.ShowModal()
    _save_dialog_geometry(dialog, "import_pdf_dialog_size")
    if result != wx.ID_OK:
        dialog.Destroy()
        return None

    source_path = source_text.GetValue().strip()
    if not source_path:
        dialog.Destroy()
        wx.MessageBox(tr("import_pdf_source_required"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return None

    if at_begin_radio.GetValue():
        insert_at_index = 0
    elif after_page_radio.GetValue():
        insert_at_index = page_number_spin.GetValue()
    else:
        insert_at_index = page_count

    result = {
        "source_path": source_path,
        "insert_at_index": insert_at_index,
    }
    dialog.Destroy()
    return result


def _parse_page_numbers_input(text, page_count):
    tokens = [token.strip() for token in str(text).split(",") if token.strip()]
    if not tokens:
        raise ValueError(tr("export_pdf_page_numbers_invalid"))

    page_indices = []
    seen = set()
    for token in tokens:
        if "-" in token:
            parts = [part.strip() for part in token.split("-", 1)]
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            start_page = int(parts[0])
            end_page = int(parts[1])
            step = 1 if end_page >= start_page else -1
            page_numbers = range(start_page, end_page + step, step)
        else:
            if not token.isdigit():
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            page_numbers = [int(token)]

        for page_number in page_numbers:
            if not 1 <= page_number <= page_count:
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            page_index = page_number - 1
            if page_index in seen:
                continue
            seen.add(page_index)
            page_indices.append(page_index)

    if not page_indices:
        raise ValueError(tr("export_pdf_page_numbers_invalid"))
    return page_indices


def _show_export_pages_dialog(owner, page_count):
    dialog = wx.Dialog(owner, title=tr("export_pdf_pages_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    export_initial_dir = _get_preview_dialog_initial_dir(owner)
    search_box = getattr(owner, "search_box", None)
    if search_box is not None:
        search_box_value = str(search_box.GetValue()).strip()
        if search_box_value and os.path.isdir(search_box_value):
            export_initial_dir = os.path.abspath(search_box_value)

    page_numbers_label = wx.StaticText(panel, label=tr("export_pdf_page_numbers_label"))
    selected_index = get_selected_pdf_page_index(owner)
    default_value = str(selected_index + 1) if selected_index is not None else ""
    page_numbers_text = wx.TextCtrl(panel, value=default_value)

    current_path = owner.current_preview_path
    base_name, _ = os.path.splitext(os.path.basename(current_path))
    output_file_label = wx.StaticText(panel, label=tr("export_pdf_file_name_label"))
    output_file_text = wx.TextCtrl(
        panel,
        value=os.path.join(export_initial_dir, f"{base_name}_pages.pdf"),
    )
    browse_btn = wx.Button(panel, label=tr("import_pdf_browse_button"))

    def browse_for_output(_):
        file_dialog = wx.FileDialog(
            dialog,
            tr("export_pdf_save_dialog_title"),
            defaultDir=export_initial_dir,
            defaultFile=os.path.basename(output_file_text.GetValue().strip()) or f"{base_name}_pages.pdf",
            wildcard="PDF files (*.pdf)|*.pdf",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if file_dialog.ShowModal() == wx.ID_OK:
            output_file_text.SetValue(file_dialog.GetPath())
        file_dialog.Destroy()

    browse_btn.Bind(wx.EVT_BUTTON, browse_for_output)

    ok_btn = wx.Button(panel, wx.ID_OK)
    cancel_btn = wx.Button(panel, wx.ID_CANCEL, tr("preview_cancel_button"))
    ok_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_TICK_MARK", wx.ART_INFORMATION), wx.ART_BUTTON, (16, 16))
    if ok_bmp.IsOk():
        ok_btn.SetBitmap(ok_bmp)
    cancel_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_CROSS_MARK", wx.ART_DELETE), wx.ART_BUTTON, (16, 16))
    if cancel_bmp.IsOk():
        cancel_btn.SetBitmap(cancel_bmp)
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(page_numbers_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(page_numbers_text, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
    output_file_sizer = wx.BoxSizer(wx.HORIZONTAL)
    output_file_sizer.Add(output_file_text, 1, wx.RIGHT, 8)
    output_file_sizer.Add(browse_btn, 0)
    root_sizer.Add(output_file_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(output_file_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.TOP, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    _restore_dialog_geometry(dialog, "export_pdf_pages_dialog_size")

    result = dialog.ShowModal()
    _save_dialog_geometry(dialog, "export_pdf_pages_dialog_size")
    if result != wx.ID_OK:
        dialog.Destroy()
        return None

    page_numbers_value = page_numbers_text.GetValue().strip()
    output_path = output_file_text.GetValue().strip()
    dialog.Destroy()
    return {
        "page_numbers_value": page_numbers_value,
        "output_path": output_path,
    }


def on_preview_save_as(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    new_path = _prompt_preview_save_as_path(owner)
    if not new_path:
        return

    try:
        with owner.busy_cursor():
            saved_path = save_pdf_as(owner.current_preview_path, new_path)
            update_pdf_save_button_state(owner)
            _refresh_preview_after_pdf_save(owner, saved_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_import_menu(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None:
        return

    menu = wx.Menu()
    build_import_menu(owner, menu)
    anchor = (0, owner.preview_import_from_file_btn.GetSize().GetHeight())
    owner.preview_import_from_file_btn.PopupMenu(menu, anchor)
    menu.Destroy()


def _show_import_from_scanner_dialog(owner, page_count):
    dialog = wx.Dialog(owner, title=tr("preview_import_from_scanner_button"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    destination_box = wx.StaticBox(panel, label=tr("import_pdf_destination_label"))
    destination_sizer = wx.StaticBoxSizer(destination_box, wx.VERTICAL)
    at_begin_radio = wx.RadioButton(panel, label=tr("move_page_at_begin"), style=wx.RB_GROUP)
    after_page_radio = wx.RadioButton(panel, label=tr("import_pdf_after_page"))
    at_end_radio = wx.RadioButton(panel, label=tr("move_page_at_end"))
    page_number_spin = wx.SpinCtrl(panel, min=1, max=max(1, page_count), initial=max(1, min(page_count, (get_selected_pdf_page_index(owner) or 0) + 1)), size=(80, -1))

    def update_after_page_state(_):
        enabled = after_page_radio.GetValue() and page_count > 0
        page_number_spin.Enable(enabled)

    at_begin_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    after_page_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    at_end_radio.Bind(wx.EVT_RADIOBUTTON, update_after_page_state)
    at_end_radio.SetValue(True)
    update_after_page_state(None)

    destination_sizer.Add(at_begin_radio, 0, wx.TOP, 3)
    after_page_sizer = wx.BoxSizer(wx.HORIZONTAL)
    after_page_sizer.Add(after_page_radio, 0, wx.RIGHT, 6)
    after_page_sizer.Add(page_number_spin, 0)
    destination_sizer.Add(after_page_sizer, 0, wx.TOP, 3)
    destination_sizer.Add(at_end_radio, 0)

    ok_btn = wx.Button(panel, wx.ID_OK)
    cancel_btn = wx.Button(panel, wx.ID_CANCEL, tr("preview_cancel_button"))
    ok_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_TICK_MARK", wx.ART_INFORMATION), wx.ART_BUTTON, (16, 16))
    if ok_bmp.IsOk():
        ok_btn.SetBitmap(ok_bmp)
    cancel_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_CROSS_MARK", wx.ART_DELETE), wx.ART_BUTTON, (16, 16))
    if cancel_bmp.IsOk():
        cancel_btn.SetBitmap(cancel_bmp)
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(destination_sizer, 0, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    _restore_dialog_geometry(dialog, "import_pdf_dialog_size")

    result = dialog.ShowModal()
    _save_dialog_geometry(dialog, "import_pdf_dialog_size")
    if result != wx.ID_OK:
        dialog.Destroy()
        return None

    if at_begin_radio.GetValue():
        insert_at_index = 0
    elif after_page_radio.GetValue():
        insert_at_index = page_number_spin.GetValue()
    else:
        insert_at_index = page_count

    dialog.Destroy()
    return {
        "insert_at_index": insert_at_index,
    }


def on_preview_import_from_file(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        page_count = get_pdf_page_count(owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return

    dialog_result = _show_import_pdf_dialog(owner, page_count)
    if dialog_result is None:
        return

    source_paths = dialog_result.get("source_paths")
    if source_paths is None:
        source_path = dialog_result.get("source_path")
        if source_path is None:
            return
        source_paths = [source_path]

    initial_insert_index = dialog_result.get("insert_at_index", 0)
    try:
        with owner.busy_cursor():
            current_insert_index = initial_insert_index
            for source_path in source_paths:
                import_pdf_pages(owner.current_preview_path, source_path, current_insert_index)
                current_insert_index += get_pdf_page_count(source_path)
            show_pdf_feed(owner, owner.current_preview_path)
            update_pdf_save_button_state(owner)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_import_from_scanner(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        page_count = get_pdf_page_count(owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return

    dialog_result = _show_import_from_scanner_dialog(owner, page_count)
    if dialog_result is None:
        return

    wx.MessageBox(
        tr("scan_not_available_message"),
        tr("preview_import_from_scanner_button"),
        wx.OK | wx.ICON_INFORMATION,
    )


def on_preview_export_pages(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        page_count = get_pdf_page_count(owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return

    dialog_result = _show_export_pages_dialog(owner, page_count)
    if dialog_result is None:
        return

    try:
        page_indices = _parse_page_numbers_input(dialog_result["page_numbers_value"], page_count)
    except ValueError as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    output_path = dialog_result["output_path"].strip()
    if not output_path:
        wx.MessageBox(tr("export_pdf_file_name_required"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        with owner.busy_cursor():
            export_pdf_pages(owner.current_preview_path, page_indices, output_path)
        export_dir = os.path.dirname(os.path.abspath(output_path))
        current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
        current_folder_norm = os.path.normpath(current_folder) if current_folder else ""
        export_dir_norm = os.path.normpath(export_dir) if export_dir else ""

        # Refresh only selected/current folder when export target is that same folder.
        if current_folder_norm and export_dir_norm and current_folder_norm == export_dir_norm:
            current_tree_item = owner.tree.GetSelection() if hasattr(owner, "tree") else None
            if current_tree_item is not None and current_tree_item.IsOk():
                current_tree_path = owner.tree.GetItemData(current_tree_item)
                if isinstance(current_tree_path, str) and os.path.isdir(current_tree_path):
                    if os.path.normpath(current_tree_path) == current_folder_norm:
                        owner.populate_tree_node(current_tree_item, current_tree_path)

            if os.path.isdir(current_folder):
                owner.load_folder(current_folder)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_zoom_in(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not getattr(owner, "current_preview_path", None):
        return

    if is_pdf_file(owner.current_preview_path):
        with owner.busy_cursor():
            owner.pdf_preview_zoom = min(owner.pdf_preview_zoom * 1.25, 3.0)
            owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
            show_pdf_feed(owner, owner.current_preview_path)
        return

    if is_office_preview_allowed(owner, owner.current_preview_path):
        with owner.busy_cursor():
            owner.pdf_preview_zoom = min(getattr(owner, "pdf_preview_zoom", 1.0) * 1.25, 3.0)
            owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
            preview_pdf_path = office_preview.convert_office_to_preview_pdf(owner.current_preview_path)
            show_pdf_feed(owner, preview_pdf_path)
        return

    if can_preview_html(owner.current_preview_path):
        with owner.busy_cursor():
            owner.current_html_zoom = min(getattr(owner, "current_html_zoom", 1.0) * 1.25, 4.0)
            show_html_preview(owner, owner.current_preview_path)
        return

    if image_utils.can_preview_image(owner.current_preview_path):
        with owner.busy_cursor():
            owner.current_image_zoom = min(getattr(owner, "current_image_zoom", 1.0) * 1.25, 8.0)
            if owner.current_image_preview is None or not owner.current_image_preview.IsOk():
                image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            else:
                image_utils.refresh_image_preview_bitmap(owner)
        return

    if hasattr(owner, "preview_zoom_in_btn"):
        owner.preview_zoom_in_btn.Enable(False)


def on_preview_zoom_out(event):
    owner = _get_preview_owner_from_event(event)
    if not owner or not getattr(owner, "current_preview_path", None):
        return

    if is_pdf_file(owner.current_preview_path):
        with owner.busy_cursor():
            owner.pdf_preview_zoom = max(owner.pdf_preview_zoom / 1.25, 0.4)
            owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
            show_pdf_feed(owner, owner.current_preview_path)
        return

    if is_office_preview_allowed(owner, owner.current_preview_path):
        with owner.busy_cursor():
            owner.pdf_preview_zoom = max(getattr(owner, "pdf_preview_zoom", 1.0) / 1.25, 0.4)
            owner.pdf_page_view_mode = PAGE_VIEW_MODE_MANUAL
            preview_pdf_path = office_preview.convert_office_to_preview_pdf(owner.current_preview_path)
            show_pdf_feed(owner, preview_pdf_path)
        return

    if can_preview_html(owner.current_preview_path):
        with owner.busy_cursor():
            owner.current_html_zoom = max(getattr(owner, "current_html_zoom", 1.0) / 1.25, 0.2)
            show_html_preview(owner, owner.current_preview_path)
        return

    if image_utils.can_preview_image(owner.current_preview_path):
        with owner.busy_cursor():
            owner.current_image_zoom = max(getattr(owner, "current_image_zoom", 1.0) / 1.25, 0.1)
            if owner.current_image_preview is None or not owner.current_image_preview.IsOk():
                image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            else:
                image_utils.refresh_image_preview_bitmap(owner)
        return

    if hasattr(owner, "preview_zoom_out_btn"):
        owner.preview_zoom_out_btn.Enable(False)


def on_preview_rotate(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, 90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_rotate_all_left(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, -90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_rotate_left(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            page_index = get_selected_pdf_page_index(owner)
            if page_index is None:
                wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
                return
            try:
                with owner.busy_cursor():
                    rotate_pdf_page(owner.current_preview_path, page_index, -90)
                    show_pdf_feed(owner, owner.current_preview_path)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            try:
                with owner.busy_cursor():
                    image_utils.rotate_image_file(owner.current_preview_path, clockwise=False)
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return


def _wheel_steps(event):
    delta = event.GetWheelDelta() or 120
    return max(1, abs(event.GetWheelRotation()) // delta)


def _is_mouse_over(window):
    if window is None:
        return False
    try:
        if not window.IsShownOnScreen() or not window.IsEnabled():
            return False
        mouse_screen = wx.GetMousePosition()
        mouse_client = window.ScreenToClient(mouse_screen)
        return window.GetClientRect().Contains(mouse_client)
    except Exception:
        return False


def on_preview_rotate_buttons_wheel(event):
    if event.GetWheelRotation() == 0:
        event.Skip()
        return

    owner = event.GetEventObject()
    while owner is not None and not hasattr(owner, "preview_rotate_menu_btn"):
        owner = owner.GetParent() if hasattr(owner, "GetParent") else None

    if owner is not None:

        # Allow wheel-zoom while cursor is over the preview image area.
        if _is_mouse_over(getattr(owner, "pdf_preview", None)) or _is_mouse_over(getattr(owner, "pdf_preview_container", None)):
            zoom_func = on_preview_zoom_in if event.GetWheelRotation() > 0 else on_preview_zoom_out
            for _ in range(_wheel_steps(event)):
                zoom_func(event)
            return

    event.Skip()


def on_preview_rotate_right(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if is_pdf_file(owner.current_preview_path):
            page_index = get_selected_pdf_page_index(owner)
            if page_index is None:
                wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
                return
            try:
                with owner.busy_cursor():
                    rotate_pdf_page(owner.current_preview_path, page_index, 90)
                    show_pdf_feed(owner, owner.current_preview_path)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if image_utils.can_preview_image(owner.current_preview_path):
            try:
                with owner.busy_cursor():
                    image_utils.rotate_image_file(owner.current_preview_path, clockwise=True)
                    image_utils.show_image_preview(owner, owner.current_preview_path, tr)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
            return

        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return


def on_preview_rotate_all_right(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                rotate_pdf(owner.current_preview_path, 90)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


# def on_preview_auto_rotate(event):
#     owner = _get_preview_owner_from_event(event)
#     if owner:
#         if not is_pdf_file(owner.current_preview_path):
#             wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
#             return
#         try:
#             with owner.busy_cursor():
#                 auto_rotate_pdf(owner.current_preview_path)
#                 show_pdf_feed(owner, owner.current_preview_path)
#         except Exception as exc:
#             wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_remove_page(event, owner=None):
    owner = _get_preview_owner_from_event(event, fallback_owner=owner)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return

        page_index = get_selected_pdf_page_index(owner)
        if page_index is None:
            wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return

        dialog = wx.MessageDialog(
            owner,
            tr("confirm_remove_page", page_no=page_index + 1),
            tr("preview_remove_page_button"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        if dialog.ShowModal() == wx.ID_YES:
            try:
                with owner.busy_cursor():
                    remove_pdf_page(owner.current_preview_path, page_index)
                    ## save_pdf(owner.current_preview_path)
                    ## owner.refresh_list_item_size(owner.current_preview_path)
                    show_pdf_feed(owner, owner.current_preview_path)
                    update_pdf_save_button_state(owner)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        dialog.Destroy()


def _show_move_page_dialog(owner, page_count, default_source_page_no):
    dialog = wx.Dialog(owner, title=tr("move_page_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    source_label = wx.StaticText(panel, label=tr("move_page_source_label"))
    source_spin = wx.SpinCtrl(panel, min=1, max=page_count, initial=default_source_page_no)

    destination_label = wx.StaticText(panel, label=tr("move_page_destination_label"))
    destination_choice = wx.Choice(
        panel,
        choices=[
            tr("move_page_at_begin"),
            tr("move_page_before"),
            tr("move_page_after"),
            tr("move_page_at_end"),
        ],
    )
    destination_choice.SetSelection(3)

    destination_page_label = wx.StaticText(panel, label=tr("move_page_destination_page_label"))
    destination_page_spin = wx.SpinCtrl(panel, min=1, max=page_count, initial=default_source_page_no)

    def update_destination_page_state(_):
        mode = destination_choice.GetSelection()
        needs_page_number = mode in (1, 2)
        destination_page_label.Enable(needs_page_number)
        destination_page_spin.Enable(needs_page_number)

    destination_choice.Bind(wx.EVT_CHOICE, update_destination_page_state)
    update_destination_page_state(None)

    fields = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
    fields.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(source_spin, 1, wx.EXPAND)
    fields.Add(destination_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(destination_choice, 1, wx.EXPAND)
    fields.Add(destination_page_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(destination_page_spin, 1, wx.EXPAND)
    fields.AddGrowableCol(1, 1)

    ok_btn = wx.Button(panel, wx.ID_OK)
    cancel_btn = wx.Button(panel, wx.ID_CANCEL)
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(fields, 1, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    if dialog.ShowModal() != wx.ID_OK:
        dialog.Destroy()
        return None

    result = {
        "source_page_no": source_spin.GetValue(),
        "destination_mode": destination_choice.GetSelection(),
        "destination_page_no": destination_page_spin.GetValue(),
    }
    dialog.Destroy()
    return result


def _resolve_move_destination_index(page_count, destination_mode, destination_page_no):
    if destination_mode == 0:
        return 0
    if destination_mode == 1:
        return max(0, min(page_count - 1, destination_page_no - 1))
    if destination_mode == 2:
        return max(0, min(page_count - 1, destination_page_no))
    return page_count - 1


def on_preview_move_page(event):
    owner = _get_preview_owner_from_event(event)
    if owner is None or not is_pdf_file(owner.current_preview_path):
        wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    try:
        page_count = get_pdf_page_count(owner.current_preview_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        return

    if page_count <= 0:
        return

    selected_index = get_selected_pdf_page_index(owner)
    default_source_page_no = (selected_index + 1) if selected_index is not None else 1
    dialog_result = _show_move_page_dialog(owner, page_count, default_source_page_no)
    if dialog_result is None:
        return

    source_index = dialog_result["source_page_no"] - 1
    destination_index = _resolve_move_destination_index(
        page_count,
        dialog_result["destination_mode"],
        dialog_result["destination_page_no"],
    )

    if source_index == destination_index:
        return

    try:
        with owner.busy_cursor():
            move_pdf_page(owner.current_preview_path, source_index, destination_index)
            show_pdf_feed(owner, owner.current_preview_path)
            update_pdf_save_button_state(owner)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_optimize(event):
    ## Auto-rotate the PDF before optimizing to avoid cutting page.
    ## on_preview_auto_rotate(event)

    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                optimize_pdf(owner.current_preview_path)
                save_pdf(owner.current_preview_path)
                owner.refresh_list_item_size(owner.current_preview_path)
                update_pdf_save_button_state(owner)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_adjust_page_width(event):
    owner = _get_preview_owner_from_event(event)
    if owner:
        if not is_pdf_file(owner.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with owner.busy_cursor():
                adjust_page_width(owner.current_preview_path)
                update_pdf_save_button_state(owner)
                show_pdf_feed(owner, owner.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)


def on_preview_right_click(event):
    """Context menu for preview pane."""
    owner = event.GetEventObject()
    while owner and not hasattr(owner, 'filePreview'):
        owner = owner.GetParent()
    if not owner:
        return

    icon_manager = getattr(owner, "icon_manager", None)
    menu = wx.Menu()

    _build_import_export_menu(owner, menu)
    menu.AppendSeparator()
    build_save_menu(owner, menu)
    cancel_item = menu.Append(-1, tr("preview_cancel_button"))
    icon_manager.set_menu_icon2(cancel_item, "cancel")

    menu.AppendSeparator()
    zoom_in_item = menu.Append(-1, tr("preview_zoom_in_button"))
    icon_manager.set_menu_icon(zoom_in_item, wx.ART_PLUS)
    zoom_out_item = menu.Append(-1, tr("preview_zoom_out_button"))
    icon_manager.set_menu_icon(zoom_out_item, wx.ART_MINUS)
    menu.AppendSeparator()
    build_page_view_mode_menu(owner, menu)
    menu.AppendSeparator()
    rotation_menu_items = build_rotation_menu(owner, menu)
    menu.AppendSeparator()
    move_page_item = menu.Append(-1, tr("preview_move_page_button"))
    icon_manager.set_menu_icon(move_page_item, wx.ART_GO_FORWARD)
    remove_page_item = menu.Append(-1, tr("preview_remove_page_button"))
    icon_manager.set_menu_icon2(remove_page_item, "delete")
    menu.AppendSeparator()
    adjust_page_width_item = menu.Append(-1, tr("preview_adjust_page_width_button"))
    icon_manager.set_menu_icon(adjust_page_width_item, wx.ART_REPORT_VIEW)
    optimize_item = menu.Append(-1, tr("preview_optimize_button"))
    icon_manager.set_menu_icon2(optimize_item, "ok")

    current_path = getattr(owner, "current_preview_path", None)
    is_pdf_preview = is_pdf_file(current_path)
    can_rotate_image = bool(current_path) and image_utils.can_preview_image(current_path)
    can_zoom_preview = is_pdf_preview or can_rotate_image or (bool(current_path) and (can_preview_html(current_path) or can_preview_text_file(current_path) or is_office_preview_allowed(owner, current_path)))
    remove_page_item.Enable(is_pdf_preview and get_selected_pdf_page_index(owner) is not None)
    move_page_item.Enable(is_pdf_preview)
    cancel_item.Enable(is_pdf_preview and has_unsaved_pdf_changes(current_path))
    adjust_page_width_item.Enable(is_pdf_preview)
    optimize_item.Enable(is_pdf_preview)
    zoom_in_item.Enable(can_zoom_preview)
    zoom_out_item.Enable(can_zoom_preview)

    owner.Bind(wx.EVT_MENU, on_preview_cancel, cancel_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_in, zoom_in_item)
    owner.Bind(wx.EVT_MENU, on_preview_zoom_out, zoom_out_item)
    owner.Bind(wx.EVT_MENU, on_preview_move_page, move_page_item)
    owner.Bind(wx.EVT_MENU, lambda evt: on_preview_remove_page(evt, owner=owner), remove_page_item)
    owner.Bind(wx.EVT_MENU, on_preview_optimize, optimize_item)
    owner.Bind(wx.EVT_MENU, on_preview_adjust_page_width, adjust_page_width_item)

    popup_window = owner.filePreview
    if event is not None:
        try:
            obj = event.GetEventObject()
            if isinstance(obj, wx.Window):
                popup_window = obj
        except Exception:
            pass

    popup_window.PopupMenu(menu)
    menu.Destroy()
