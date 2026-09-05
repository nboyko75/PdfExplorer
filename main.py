import ntpath
import os
import sys
from contextlib import contextmanager
import wx

from file_operations.pdf_utils import discard_pdf_changes, get_unsaved_pdf_paths, is_pdf_file, move_pdf_page, save_pdf
from localization import tr, load_locale, available_locales
from controls.window_tools import load_settings, update_settings, save_window_geometry, restore_window_geometry
from controls.options_form import show_options_form
from controls.splitter_utils import normalize_shortcuts_sash
import controls.tree_utils as tree_utils
import controls.drag_and_drop as drag_and_drop
import controls.favorite_panel as favorite_panel
import file_operations.image_utils as image_utils
import controls.navigation_utils as navigation_utils
import controls.file_preview as file_preview
import controls.filelist as filelist
import controls.scan_form as scan_form
import controls.about_form as about_form
import controls.help_form as help_form


LANGUAGE_CHOICES = [
    ("EN", "en"),
    ("UA", "uk"),
    ("DE", "de"),
    ("FR", "fr"),
    ("ES", "es"),
    ("IT", "it"),
    ("PT-BR", "pt_br"),
    ("JA", "ja"),
    ("KO", "ko"),
    ("ZH-CN", "zh_cn"),
    ("RU", "ru"),
]
LANGUAGE_LABEL_BY_CODE = {code: label for label, code in LANGUAGE_CHOICES}
LANGUAGE_CODE_BY_LABEL = {label: code for label, code in LANGUAGE_CHOICES}
LANGUAGE_CHOICES_SORTED = sorted(LANGUAGE_CHOICES, key=lambda item: item[0])
SUPPORTED_LOCALES = set(LANGUAGE_LABEL_BY_CODE.keys())


class FileExplorer(wx.Frame):
    def __init__(self, initial_path=None):
        super().__init__(None, title=tr("app_title"), size=(1400, 900))

        icon_path = os.path.join(os.path.dirname(__file__), "images", "main.ico")
        if os.path.isfile(icon_path):
            self.SetIcon(wx.Icon(icon_path))

        settings = load_settings()
        self.history = []
        self.history_index = -1
        self.show_hidden = bool(settings.get("show_hidden", False))
        self.preview_enabled = bool(settings.get("preview_enabled", True))
        self.office_preview_enabled = bool(settings.get("office_preview_enabled", False))
        self.current_pdf_path = None
        self.selected_pdf_page_panel = None
        self.drag_overlay = None
        self.drag_overlay_text = None
        self.undo_stack = []
        self._highlighted_panel = None
        self.current_preview_path = None
        self.current_image_preview = None
        self.current_image_zoom = 1.0
        self.list_sort_column = None
        self.list_sort_direction = 0
        self.file_clipboard_paths = []
        self.file_clipboard_mode = None
        saved_locale = str(settings.get("ui_locale", "uk")).lower()
        saved_locale = saved_locale.replace("-", "_")
        if saved_locale == "ua":
            saved_locale = "uk"
        self.current_locale = saved_locale if saved_locale in SUPPORTED_LOCALES else "uk"
        self.pdf_preview_zoom = 1.0
        self.main_splitter = None
        self.favorite_splitter = None
        self.favorite_panel = None
        self.favorite_list = None
        self.favorite_content_splitter = None
        self.favorite_standard_shortcuts_splitter_sash = normalize_shortcuts_sash(settings.get("favorite_standard_shortcuts_splitter_sash", 120))
        self.favorite_panel_above_tree = bool(settings.get("favorite_panel_above_tree", False))
        self.favorite_paths = []
        for favorite_path in settings.get("favorite_paths", []):
            if isinstance(favorite_path, str) and os.path.isdir(favorite_path):
                normalized = os.path.normpath(favorite_path)
                if normalized not in self.favorite_paths:
                    self.favorite_paths.append(normalized)
        self.standard_shortcuts_visible = bool(settings.get("standard_shortcuts_visible", False))
        self.standard_shortcuts_visibility = {
            "desktop": True,
            "documents": True,
            "downloads": False,
            "images": False,
            "music": False,
            "video": False,
            "recycle_bin": True,
        }
        saved_shortcuts = settings.get("standard_shortcuts_visibility")
        if isinstance(saved_shortcuts, dict):
            for key, value in saved_shortcuts.items():
                legacy_key = "downloads" if key == "download" else key
                if legacy_key in self.standard_shortcuts_visibility:
                    self.standard_shortcuts_visibility[legacy_key] = bool(value)
        saved_page_view_mode = str(settings.get("pdf_page_view_mode", "1_page_wide"))
        if saved_page_view_mode not in file_preview.VALID_PAGE_VIEW_MODES:
            saved_page_view_mode = file_preview.PAGE_VIEW_MODE_1_TALL
        self.pdf_page_view_mode = saved_page_view_mode
        if saved_page_view_mode in file_preview.FIXED_PAGE_VIEW_MODES:
            self.pdf_page_view_selected_mode = saved_page_view_mode
        else:
            self.pdf_page_view_selected_mode = file_preview.PAGE_VIEW_MODE_1_TALL
        self.updating_tree = False

        load_locale(self.current_locale)
        self.build_ui()
        self.restore_list_view_state(settings)
        self.bind_events()

        restore_window_geometry(self, settings)
        wx.CallAfter(self.restore_splitter_positions, settings)

        opened_initial_path = False
        if initial_path:
            opened_initial_path = self.open_location(initial_path, add_history=False)

        last_folder = settings.get("last_folder")
        if not opened_initial_path and last_folder and os.path.isdir(last_folder):
            self.open_path(last_folder, add_history=False)
            wx.CallAfter(self.select_tree_item_by_path, last_folder)
        elif not opened_initial_path:
            self.open_path(os.path.expanduser("~"))

        # global key hook for undo
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key)
        self.Bind(wx.EVT_CLOSE, self.on_close)

    # ---------------- UI ----------------
    @contextmanager
    def busy_cursor(self):
        was_busy = wx.IsBusy()
        if not was_busy:
            wx.BeginBusyCursor()
        try:
            yield
        finally:
            if not was_busy and wx.IsBusy():
                wx.EndBusyCursor()

    def _build_main_menu_bar(self):
        if not hasattr(self, "icon_manager") or self.icon_manager is None:
            self.icon_manager = image_utils.IconManager()

        self.menu_bar = wx.MenuBar()

        self.file_menu = wx.Menu()
        self.file_scan_item = self.file_menu.Append(wx.ID_ANY, tr("scan"))
        self.file_open_item = self.file_menu.Append(wx.ID_ANY, tr("context_open"))
        self.file_rename_item = self.file_menu.Append(wx.ID_ANY, tr("context_rename"))
        self.file_new_folder_item = self.file_menu.Append(wx.ID_ANY, tr("context_new_folder"))
        self.file_refresh_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_refresh')}\tF5")
        self.file_print_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_print')}\tCtrl+P")
        self.file_menu.AppendSeparator()
        self.file_copy_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_copy')}\tCtrl+C")
        self.file_cut_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_cut')}\tCtrl+X")
        self.file_paste_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_paste')}\tCtrl+V")
        self.file_delete_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_remove_to_recycle_bin')}\tCtrl+D")
        self.file_delete_permanent_item = self.file_menu.Append(wx.ID_ANY, f"{tr('context_delete')}\tShift+Del")
        self.file_menu.AppendSeparator()
        self.file_archive_item = self.file_menu.Append(wx.ID_ANY, tr("context_add_to_archive"))
        self.file_extract_archive_item = self.file_menu.Append(wx.ID_ANY, tr("context_extract_from_archive_here"))
        self.file_extract_archive_into_item = self.file_menu.Append(wx.ID_ANY, tr("context_extract_from_archive_into"))
        self.file_menu.AppendSeparator()
        self.file_options_item = self.file_menu.Append(wx.ID_ANY, tr("menu_file_options"))
        self.file_quit_item = self.file_menu.Append(wx.ID_ANY, tr("exit_button"))
        self.menu_bar.Append(self.file_menu, tr("menu_file"))

        self.navigation_menu = wx.Menu()
        self.nav_back_item = self.navigation_menu.Append(wx.ID_ANY, tr("back_button"))
        self.nav_forward_item = self.navigation_menu.Append(wx.ID_ANY, tr("forward_button"))
        self.nav_up_item = self.navigation_menu.Append(wx.ID_ANY, tr("folder_up_button"))
        self.navigation_menu.AppendSeparator()
        self.nav_add_to_favourite_item = self.navigation_menu.Append(wx.ID_ANY, tr("favorite_add_menu_item"))
        self.nav_remove_from_favourite_item = self.navigation_menu.Append(wx.ID_ANY, tr("favorite_remove_menu_item"))
        self.navigation_menu.AppendSeparator()
        self.nav_search_item = self.navigation_menu.Append(wx.ID_ANY, tr("search_in_files_button"))
        self.menu_bar.Append(self.navigation_menu, tr("menu_navigation"))

        self.document_menu = wx.Menu()
        self.doc_import_item = self.document_menu.Append(wx.ID_ANY, tr("preview_import_from_file_button"))
        self.doc_import_scanner_item = self.document_menu.Append(wx.ID_ANY, tr("preview_import_from_scanner_button"))
        self.doc_export_item = self.document_menu.Append(wx.ID_ANY, tr("preview_export_pages_button"))
        self.document_menu.AppendSeparator()
        self.doc_save_item = self.document_menu.Append(wx.ID_ANY, tr("preview_save_button"))
        self.doc_cancel_item = self.document_menu.Append(wx.ID_ANY, tr("preview_cancel_button"))
        self.document_menu.AppendSeparator()
        self.doc_zoom_in_item = self.document_menu.Append(wx.ID_ANY, tr("preview_zoom_in_button"))
        self.doc_zoom_out_item = self.document_menu.Append(wx.ID_ANY, tr("preview_zoom_out_button"))
        self.document_menu.AppendSeparator()
        self.doc_1_page_wide_item = self.document_menu.Append(wx.ID_ANY, tr("preview_show_1_page_wide"))
        self.doc_2_pages_wide_item = self.document_menu.Append(wx.ID_ANY, tr("preview_show_2_pages_wide"))
        self.doc_1_page_tall_item = self.document_menu.Append(wx.ID_ANY, tr("preview_show_1_page_tall"))
        self.doc_manual_scale_item = self.document_menu.Append(wx.ID_ANY, tr("preview_show_manual_scale"))
        self.document_menu.AppendSeparator()
        self.doc_rotate_all_left_item = self.document_menu.Append(wx.ID_ANY, tr("preview_rotate_all_left_button"))
        self.doc_rotate_left_item = self.document_menu.Append(wx.ID_ANY, tr("preview_rotate_left_button"))
        self.doc_rotate_right_item = self.document_menu.Append(wx.ID_ANY, tr("preview_rotate_right_button"))
        self.doc_rotate_all_right_item = self.document_menu.Append(wx.ID_ANY, tr("preview_rotate_all_right_button"))
        self.document_menu.AppendSeparator()
        self.doc_move_page_item = self.document_menu.Append(wx.ID_ANY, tr("preview_move_page_button"))
        self.doc_remove_page_item = self.document_menu.Append(wx.ID_ANY, tr("preview_remove_page_button"))
        self.doc_adjust_page_width_item = self.document_menu.Append(wx.ID_ANY, tr("preview_adjust_page_width_button"))
        self.doc_optimize_item = self.document_menu.Append(wx.ID_ANY, tr("preview_optimize_button"))
        self.doc_optimize_all_item = self.document_menu.Append(wx.ID_ANY, tr("tree_optimize_all_pdf"))
        self.doc_adjust_all_page_width_item = self.document_menu.Append(wx.ID_ANY, tr("tree_adjust_page_width_all_pdf"))
        self.menu_bar.Append(self.document_menu, tr("menu_document"))

        self.help_menu = wx.Menu()
        self.help_manual_item = self.help_menu.Append(wx.ID_HELP, f"{tr('menu_app_manual')}\tF1")
        self.help_about_item = self.help_menu.Append(wx.ID_ANY, tr("menu_about"))
        self.menu_bar.Append(self.help_menu, tr("menu_help"))

        self.SetMenuBar(self.menu_bar)
        self._apply_main_menu_icons()

        self._bind_main_menu_items()
        self._update_main_menu_state()

    def _apply_main_menu_icons(self):
        if not hasattr(self, "icon_manager") or self.icon_manager is None:
            self.icon_manager = image_utils.IconManager()

        self.icon_manager.set_menu_icon2(self.file_scan_item, "scan")
        self.icon_manager.set_menu_icon2(self.file_open_item, "file_view")
        self.icon_manager.set_menu_icon(self.file_rename_item, art_id=wx.ART_EDIT)
        self.icon_manager.set_menu_icon(self.file_new_folder_item, art_id=wx.ART_FOLDER)
        self.icon_manager.set_menu_icon(self.file_refresh_item, art_id=wx.ART_REDO)
        self.icon_manager.set_menu_icon(self.file_print_item, art_id=wx.ART_PRINT)
        self.icon_manager.set_menu_icon2(self.file_copy_item, "copy")
        self.icon_manager.set_menu_icon(self.file_cut_item, art_id=wx.ART_CUT)
        self.icon_manager.set_menu_icon(self.file_paste_item, art_id=wx.ART_PASTE)
        self.icon_manager.set_menu_icon2(self.file_delete_item, "recycle_bin")
        self.icon_manager.set_menu_icon(self.file_delete_permanent_item, art_id=wx.ART_DELETE)
        self.icon_manager.set_menu_icon2(self.file_archive_item, "add_to_archive")
        self.icon_manager.set_menu_icon2(self.file_extract_archive_item, "extract_from_archive")
        self.icon_manager.set_menu_icon2(self.file_extract_archive_into_item, "extract_from_archive")
        self.icon_manager.set_menu_icon2(self.file_options_item, "setup")
        self.icon_manager.set_menu_icon(self.file_quit_item, art_id=wx.ART_QUIT)

        self.icon_manager.set_menu_icon(self.nav_back_item, art_id=wx.ART_GO_BACK)
        self.icon_manager.set_menu_icon(self.nav_forward_item, art_id=wx.ART_GO_FORWARD)
        self.icon_manager.set_menu_icon(self.nav_up_item, art_id=wx.ART_GO_UP)
        self.icon_manager.set_menu_icon2(self.nav_add_to_favourite_item, "add_to_favorites")
        self.icon_manager.set_menu_icon2(self.nav_remove_from_favourite_item, "remove_from_favorites")
        self.icon_manager.set_menu_icon(self.nav_search_item, art_id=wx.ART_FIND)

        self.icon_manager.set_menu_icon(self.help_manual_item, art_id=wx.ART_HELP)
        self.icon_manager.set_menu_icon(self.help_about_item, art_id=wx.ART_INFORMATION)

        self.icon_manager.set_menu_icon(self.doc_import_item, art_id=wx.ART_FILE_OPEN)
        self.icon_manager.set_menu_icon2(self.doc_import_scanner_item, "scan")
        export_art_id = getattr(wx, "ART_FILE_SAVE_AS", wx.ART_FILE_SAVE)
        self.icon_manager.set_menu_icon(self.doc_export_item, art_id=export_art_id)
        self.icon_manager.set_menu_icon2(self.doc_save_item, "save")
        self.icon_manager.set_menu_icon2(self.doc_cancel_item, "cancel")
        self.icon_manager.set_menu_icon(self.doc_zoom_in_item, art_id=wx.ART_PLUS)
        self.icon_manager.set_menu_icon(self.doc_zoom_out_item, art_id=wx.ART_MINUS)
        self.icon_manager.set_menu_icon(self.doc_rotate_all_left_item, art_id=wx.ART_UNDO)
        self.icon_manager.set_menu_icon(self.doc_rotate_left_item, art_id=wx.ART_UNDO)
        self.icon_manager.set_menu_icon(self.doc_rotate_right_item, art_id=wx.ART_REDO)
        self.icon_manager.set_menu_icon(self.doc_rotate_all_right_item, art_id=wx.ART_REDO)
        self.icon_manager.set_menu_icon(self.doc_move_page_item, art_id=wx.ART_GO_FORWARD)
        self.icon_manager.set_menu_icon2(self.doc_remove_page_item, "delete")
        self.icon_manager.set_menu_icon(self.doc_adjust_page_width_item, art_id=wx.ART_REPORT_VIEW)
        self.icon_manager.set_menu_icon2(self.doc_optimize_item, "ok")
        self.icon_manager.set_menu_icon2(self.doc_optimize_all_item, "ok")
        self.icon_manager.set_menu_icon(self.doc_adjust_all_page_width_item, art_id=wx.ART_REPORT_VIEW)

    def _bind_main_menu_items(self):
        self.Bind(wx.EVT_MENU, self.on_list_scan, self.file_scan_item)
        self.Bind(wx.EVT_MENU, self.on_list_open, self.file_open_item)
        self.Bind(wx.EVT_MENU, self.on_list_rename, self.file_rename_item)
        self.Bind(wx.EVT_MENU, self.on_list_new_folder, self.file_new_folder_item)
        self.Bind(wx.EVT_MENU, self.on_refresh_menu, self.file_refresh_item)
        self.Bind(wx.EVT_MENU, self.on_list_print, self.file_print_item)
        self.Bind(wx.EVT_MENU, self.on_list_copy, self.file_copy_item)
        self.Bind(wx.EVT_MENU, self.on_list_cut, self.file_cut_item)
        self.Bind(wx.EVT_MENU, self.on_list_paste, self.file_paste_item)
        self.Bind(wx.EVT_MENU, self.on_list_delete, self.file_delete_item)
        self.Bind(wx.EVT_MENU, self.on_list_delete_permanent, self.file_delete_permanent_item)
        self.Bind(wx.EVT_MENU, lambda event: filelist._archive_selected_path(self, filelist.get_selected_list_paths(self)), self.file_archive_item)
        self.Bind(wx.EVT_MENU, lambda event: filelist._extract_selected_archive_here(self, filelist.get_selected_list_path(self)), self.file_extract_archive_item)
        self.Bind(wx.EVT_MENU, lambda event: filelist._extract_selected_archive_into(self, filelist.get_selected_list_path(self)), self.file_extract_archive_into_item)
        self.Bind(wx.EVT_MENU, self.on_file_options, self.file_options_item)
        self.Bind(wx.EVT_MENU, self.on_exit, self.file_quit_item)

        self.Bind(wx.EVT_MENU, self.go_back, self.nav_back_item)
        self.Bind(wx.EVT_MENU, self.go_forward, self.nav_forward_item)
        self.Bind(wx.EVT_MENU, self.on_folder_up, self.nav_up_item)
        self.Bind(wx.EVT_MENU, self.on_nav_add_to_favourite, self.nav_add_to_favourite_item)
        self.Bind(wx.EVT_MENU, self.on_nav_remove_from_favourite, self.nav_remove_from_favourite_item)
        self.Bind(wx.EVT_MENU, self.on_search_in_files, self.nav_search_item)

        self.Bind(wx.EVT_MENU, file_preview.on_preview_import_from_file, self.doc_import_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_import_from_scanner, self.doc_import_scanner_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_export_pages, self.doc_export_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_save, self.doc_save_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_cancel, self.doc_cancel_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_zoom_in, self.doc_zoom_in_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_zoom_out, self.doc_zoom_out_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_show_1_page_wide, self.doc_1_page_wide_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_show_2_pages_wide, self.doc_2_pages_wide_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_show_1_page_tall, self.doc_1_page_tall_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_show_manual_scale, self.doc_manual_scale_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_rotate_all_left, self.doc_rotate_all_left_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_rotate_left, self.doc_rotate_left_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_rotate_right, self.doc_rotate_right_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_rotate_all_right, self.doc_rotate_all_right_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_move_page, self.doc_move_page_item)
        self.Bind(wx.EVT_MENU, lambda event: file_preview.on_preview_remove_page(event, owner=self), self.doc_remove_page_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_adjust_page_width, self.doc_adjust_page_width_item)
        self.Bind(wx.EVT_MENU, file_preview.on_preview_optimize, self.doc_optimize_item)
        self.Bind(wx.EVT_MENU, lambda event: tree_utils.optimize_all_pdf_in_path(self, self.path_box.GetValue() if hasattr(self, "path_box") else self.current_preview_path), self.doc_optimize_all_item)
        self.Bind(wx.EVT_MENU, lambda event: tree_utils.adjust_page_width_all_pdf_in_path(self, self.path_box.GetValue() if hasattr(self, "path_box") else self.current_preview_path), self.doc_adjust_all_page_width_item)

        self.Bind(wx.EVT_MENU, self.on_app_manual, self.help_manual_item)
        self.Bind(wx.EVT_MENU, self.on_about, self.help_about_item)

    def _update_main_menu_state(self):
        if not hasattr(self, "file_menu"):
            return

        current_path = self.path_box.GetValue() if hasattr(self, "path_box") and self.path_box is not None else ""
        selected_items = filelist.get_selected_list_paths(self) if hasattr(self, "list") and self.list is not None else []
        has_single_selection = len(selected_items) == 1 and os.path.exists(selected_items[0])
        can_paste = bool(current_path and os.path.isdir(current_path) and filelist._can_paste_into_directory(self, current_path))
        current_preview = getattr(self, "current_preview_path", None)

        self.file_scan_item.Enable(True)
        self.file_open_item.Enable(has_single_selection)
        self.file_rename_item.Enable(has_single_selection)
        self.file_new_folder_item.Enable(bool(current_path and os.path.isdir(current_path)))
        self.file_refresh_item.Enable(True)
        self.file_print_item.Enable(bool((selected_items and all(os.path.isfile(path) for path in selected_items)) or (current_preview and os.path.isfile(current_preview)) or (current_path and os.path.isfile(current_path))))
        self.file_copy_item.Enable(bool(selected_items))
        self.file_cut_item.Enable(bool(selected_items))
        self.file_paste_item.Enable(can_paste)
        self.file_delete_item.Enable(bool(selected_items))
        self.file_delete_permanent_item.Enable(bool(selected_items))
        self.file_archive_item.Enable(bool(selected_items) and all(os.path.exists(path) and not filelist._is_archive_file(path) for path in selected_items))
        can_extract_archive = len(selected_items) == 1 and os.path.exists(selected_items[0]) and filelist._is_archive_file(selected_items[0])
        self.file_extract_archive_item.Enable(can_extract_archive)
        self.file_extract_archive_into_item.Enable(can_extract_archive)

        self.nav_back_item.Enable(bool(getattr(self, "history", [])))
        self.nav_forward_item.Enable(bool(getattr(self, "history", [])) and self.history_index < len(self.history) - 1)
        parent_folder = ntpath.dirname(current_path) if current_path else ""
        self.nav_up_item.Enable(bool(current_path and os.path.isdir(current_path) and parent_folder and ntpath.normpath(parent_folder) != ntpath.normpath(current_path)))
        if hasattr(self, "nav_add_to_favourite_item") and hasattr(self, "nav_remove_from_favourite_item"):
            has_folder = bool(current_path and os.path.isdir(current_path))
            is_favourite = has_folder and self._is_favorite_path(current_path)
            self.nav_add_to_favourite_item.Enable(has_folder and not is_favourite)
            self.nav_remove_from_favourite_item.Enable(has_folder and is_favourite)
        self.nav_search_item.Enable(True)

        is_pdf_preview = bool(current_preview and is_pdf_file(current_preview))
        is_image_preview = bool(current_preview and image_utils.can_preview_image(current_preview))
        is_office_preview = bool(current_preview and file_preview.is_office_preview_allowed(self, current_preview))
        is_html_preview = bool(current_preview and file_preview.can_preview_html(current_preview))
        is_previewable = bool(current_preview) and (is_pdf_preview or is_image_preview or is_office_preview or is_html_preview)

        self.doc_import_item.Enable(is_pdf_preview)
        self.doc_import_scanner_item.Enable(is_pdf_preview)
        self.doc_export_item.Enable(is_pdf_preview)
        self.doc_save_item.Enable(is_pdf_preview and file_preview.has_unsaved_pdf_changes(self.current_preview_path))
        self.doc_cancel_item.Enable(is_pdf_preview and file_preview.has_unsaved_pdf_changes(self.current_preview_path))
        self.doc_zoom_in_item.Enable(is_previewable)
        self.doc_zoom_out_item.Enable(is_previewable)
        self.doc_1_page_wide_item.Enable(is_previewable)
        self.doc_2_pages_wide_item.Enable(is_previewable)
        self.doc_1_page_tall_item.Enable(is_previewable)
        self.doc_manual_scale_item.Enable(is_previewable)
        self.doc_rotate_all_left_item.Enable(is_pdf_preview)
        self.doc_rotate_left_item.Enable(is_pdf_preview or is_image_preview)
        self.doc_rotate_right_item.Enable(is_pdf_preview or is_image_preview)
        self.doc_rotate_all_right_item.Enable(is_pdf_preview)
        self.doc_move_page_item.Enable(is_pdf_preview)
        self.doc_remove_page_item.Enable(is_pdf_preview and file_preview.get_selected_pdf_page_index(self) is not None)
        self.doc_adjust_page_width_item.Enable(is_pdf_preview)
        self.doc_optimize_item.Enable(is_pdf_preview)
        batch_target = getattr(self, "current_preview_path", None) or (self.path_box.GetValue() if hasattr(self, "path_box") and self.path_box is not None else "")
        is_batch_target = bool(batch_target and (os.path.isdir(batch_target) or is_pdf_file(batch_target)))
        self.doc_optimize_all_item.Enable(is_batch_target)
        self.doc_adjust_all_page_width_item.Enable(is_batch_target)

    def on_refresh_menu(self, _):
        current_folder = self.path_box.GetValue() if hasattr(self, "path_box") else ""
        if current_folder and os.path.isdir(current_folder):
            self.load_folder(current_folder)
            tree_utils.refresh_tree_selection_and_filelist(self)
        else:
            self.refresh_tree_placeholders()

    def on_list_print(self, _):
        filelist.on_list_print(self, _)

    def on_app_manual(self, _):
        help_form.show_app_manual_form(self)

    def on_about(self, _):
        about_form.show_about_form(self)

    def build_ui(self):
        if not hasattr(self, "icon_manager") or self.icon_manager is None:
            self.icon_manager = image_utils.IconManager()

        self._build_main_menu_bar()

        panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ===== Toolbar =====
        toolbar = wx.BoxSizer(wx.HORIZONTAL)

        self.back_btn = image_utils.create_bitmap_button(panel, wx.ART_GO_BACK, tr("back_button"))
        self.forward_btn = image_utils.create_bitmap_button(panel, wx.ART_GO_FORWARD, tr("forward_button"))
        self.exit_btn = image_utils.create_bitmap_button(panel, wx.ART_QUIT, tr("exit_button"))
        self.search_in_files_btn = image_utils.create_bitmap_button(panel, wx.ART_FIND, tr("search_in_files_button"))

        self.path_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)

        self.hidden_chk = wx.CheckBox(panel, label=tr("show_hidden_checkbox"))
        self.hidden_chk.SetValue(self.show_hidden)

        toolbar.Add(self.back_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar.Add(self.forward_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar.Add(self.search_in_files_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.exit_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.path_box, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.hidden_chk, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)

        # ===== Split view =====
        self.main_splitter = wx.SplitterWindow(panel)

        self.favorite_splitter = wx.SplitterWindow(self.main_splitter)
        self.tree = wx.TreeCtrl(self.favorite_splitter, style=wx.TR_HAS_BUTTONS)
        self.init_tree_images()
        self.filePanel = wx.Panel(self.main_splitter)

        favorite_panel.build_favorite_panel(self, self.favorite_splitter)

        self.favorite_splitter.SplitHorizontally(self.tree, self.favorite_panel, 180)
        if self.favorite_panel_above_tree:
            self.favorite_splitter.Unsplit(self.tree)
            self.favorite_splitter.SplitHorizontally(self.favorite_panel, self.tree, 180)
        self._apply_favorite_panel_position()
        self.main_splitter.SplitVertically(self.favorite_splitter, self.filePanel, 320)

        self.fileSplitter = wx.SplitterWindow(self.filePanel)

        filelist.build_list_panel(self, self.fileSplitter)

        file_preview.build_file_preview_pane(self, self.fileSplitter)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.fileSplitter, 1, wx.EXPAND)
        self.filePanel.SetSizer(sizer)

        main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.main_splitter, 1, wx.EXPAND)

        panel.SetSizer(main_sizer)

        tree_utils.init_tree(self)

    def init_tree_images(self):
        return tree_utils.init_tree_images(self)

    def _normalize_favorite_path(self, path):
        if not isinstance(path, str):
            return ""
        normalized = os.path.normpath(path)
        return normalized or ""

    def _is_favorite_path(self, path):
        normalized = self._normalize_favorite_path(path)
        if not normalized:
            return False
        normalized_case = os.path.normcase(normalized)
        return any(os.path.normcase(self._normalize_favorite_path(favorite_path)) == normalized_case for favorite_path in self.favorite_paths)

    def _add_favorite_path(self, path):
        if not isinstance(path, str) or not os.path.isdir(path):
            return False
        normalized = self._normalize_favorite_path(path)
        if not normalized:
            return False
        if any(os.path.normcase(self._normalize_favorite_path(existing)) == os.path.normcase(normalized) for existing in self.favorite_paths):
            return False
        self.favorite_paths.append(normalized)
        self._refresh_favorite_list()
        self.save_splitter_positions()
        return True

    def _remove_favorite_path(self, path):
        if not isinstance(path, str):
            return False
        normalized = self._normalize_favorite_path(path)
        original_count = len(self.favorite_paths)
        self.favorite_paths = [favorite_path for favorite_path in self.favorite_paths if os.path.normcase(self._normalize_favorite_path(favorite_path)) != os.path.normcase(normalized)]
        if len(self.favorite_paths) == original_count:
            return False
        self._refresh_favorite_list()
        self.save_splitter_positions()
        return True

    def _reorder_favorite_paths(self, from_index, to_index):
        if not isinstance(from_index, int) or not isinstance(to_index, int):
            return False
        if not self.favorite_paths or not (0 <= from_index < len(self.favorite_paths)):
            return False
        if to_index < 0:
            to_index = 0
        if to_index >= len(self.favorite_paths):
            to_index = len(self.favorite_paths) - 1
        if from_index == to_index:
            return False

        moved_path = self.favorite_paths.pop(from_index)
        self.favorite_paths.insert(to_index, moved_path)
        self._refresh_favorite_list()
        if getattr(self, "favorite_list", None) is not None:
            try:
                self.favorite_list.Select(to_index)
                self.favorite_list.EnsureVisible(to_index)
            except Exception:
                pass
        self.save_splitter_positions()
        return True

    def _apply_favorite_list_layout(self):
        favorite_panel._apply_favorite_list_layout(self)

    def _refresh_favorite_list(self):
        favorite_panel.refresh_favorite_list(self)

    def _refresh_standard_shortcuts_list(self):
        favorite_panel.refresh_standard_shortcuts_list(self)

    def _apply_favorite_panel_position(self, sash_position=None):
        favorite_panel.apply_favorite_panel_position(self, sash_position=sash_position)

    def _toggle_favorite_panel_position(self, panel_above_tree):
        favorite_panel.toggle_favorite_panel_position(self, panel_above_tree)

    def on_move_favorite_up(self, _):
        self._toggle_favorite_panel_position(True)

    def on_move_favorite_down(self, _):
        self._toggle_favorite_panel_position(False)

    def on_favorite_row_move_up(self, _):
        favorite_panel.on_favorite_row_move_up(self, _)

    def on_favorite_row_move_down(self, _):
        favorite_panel.on_favorite_row_move_down(self, _)

    def on_favorite_list_select(self, event):
        index = event.GetIndex()
        if not (0 <= index < len(self.favorite_paths)):
            return
        selected_path = self.favorite_paths[index]
        if os.path.isdir(selected_path):
            self.open_path(selected_path, add_history=True)
            self.select_tree_item_by_path(selected_path)

    def on_favorite_list_activate(self, event):
        self.on_favorite_list_select(event)

    def on_favorite_begin_drag(self, event):
        favorite_panel.on_favorite_begin_drag(self, event)

    def on_favorite_end_drag(self, event):
        favorite_panel.on_favorite_end_drag(self, event)

    def on_favorite_right_click(self, event):
        favorite_panel.on_favorite_right_click(self, event)

    def on_standard_shortcut_right_click(self, event):
        favorite_panel.on_standard_shortcut_right_click(self, event)

    def on_standard_shortcut_list_activate(self, event):
        favorite_panel.on_standard_shortcut_list_activate(self, event)

    def on_toggle_standard_shortcuts(self, _):
        favorite_panel.toggle_standard_shortcuts_panel(self)

    def on_remove_favorite_from_context(self, _):
        favorite_panel.on_remove_favorite_from_context(self, _)

    def on_nav_add_to_favourite(self, _):
        current_folder = self.path_box.GetValue() if hasattr(self, "path_box") else ""
        if current_folder and os.path.isdir(current_folder):
            self._add_favorite_path(current_folder)
            self._update_main_menu_state()

    def on_nav_remove_from_favourite(self, _):
        current_folder = self.path_box.GetValue() if hasattr(self, "path_box") else ""
        if current_folder and os.path.isdir(current_folder):
            self._remove_favorite_path(current_folder)
            self._update_main_menu_state()

    def refresh_tree_placeholders(self):
        return tree_utils.refresh_tree_placeholders(self)

    def find_tree_item_by_path(self, path):
        return tree_utils.find_tree_item_by_path(self, path)

    def _find_tree_child_path(self, parent, normalized_path):
        return tree_utils.find_tree_child_path(self, parent, normalized_path)

    def select_tree_item_by_path(self, path):
        return tree_utils.select_tree_item_by_path(self, path)

    def save_last_folder(self):
        navigation_utils.save_last_folder(self)

    def save_splitter_positions(self):
        main_sash = None
        preview_sash = None
        favorite_sash = None

        if self.main_splitter is not None and self.main_splitter.IsSplit():
            main_sash = int(self.main_splitter.GetSashPosition())

        if self.fileSplitter is not None and self.fileSplitter.IsSplit():
            preview_sash = int(self.fileSplitter.GetSashPosition())

        if self.favorite_splitter is not None and self.favorite_splitter.IsSplit():
            favorite_sash = int(self.favorite_splitter.GetSashPosition())

        if self.favorite_content_splitter is not None and self.favorite_content_splitter.IsSplit():
            favorite_standard_shortcuts_sash = int(self.favorite_content_splitter.GetSashPosition())
        else:
            favorite_standard_shortcuts_sash = self.favorite_standard_shortcuts_splitter_sash

        persisted_page_view_mode = self.pdf_page_view_mode
        if persisted_page_view_mode == file_preview.PAGE_VIEW_MODE_MANUAL:
            persisted_page_view_mode = getattr(
                self,
                "pdf_page_view_selected_mode",
                file_preview.PAGE_VIEW_MODE_1_TALL,
            )
        if persisted_page_view_mode not in file_preview.VALID_PAGE_VIEW_MODES:
            persisted_page_view_mode = file_preview.PAGE_VIEW_MODE_1_TALL

        update_settings(
            {
                "main_splitter_sash": main_sash,
                "preview_splitter_sash": preview_sash,
                "favorite_splitter_sash": favorite_sash,
                "favorite_standard_shortcuts_splitter_sash": int(favorite_standard_shortcuts_sash),
                "favorite_panel_above_tree": bool(self.favorite_panel_above_tree),
                "favorite_paths": list(self.favorite_paths),
                "standard_shortcuts_visible": bool(self.standard_shortcuts_visible),
                "standard_shortcuts_visibility": dict(self.standard_shortcuts_visibility),
                "pdf_page_view_mode": persisted_page_view_mode,
            }
        )

    def restore_splitter_positions(self, settings=None):
        if settings is None:
            settings = load_settings()

        main_sash = settings.get("main_splitter_sash")
        if isinstance(main_sash, int) and self.main_splitter is not None and self.main_splitter.IsSplit():
            self.main_splitter.SetSashPosition(max(100, main_sash))

        preview_sash = settings.get("preview_splitter_sash")
        if isinstance(preview_sash, int) and self.fileSplitter is not None and self.fileSplitter.IsSplit():
            self.fileSplitter.SetSashPosition(max(100, preview_sash))

        favorite_sash = settings.get("favorite_splitter_sash")
        favorite_above_tree = bool(settings.get("favorite_panel_above_tree", False))
        favorite_standard_shortcuts_sash = settings.get("favorite_standard_shortcuts_splitter_sash")
        if isinstance(favorite_standard_shortcuts_sash, (int, float)):
            self.favorite_standard_shortcuts_splitter_sash = normalize_shortcuts_sash(favorite_standard_shortcuts_sash)
        saved_standard_shortcuts_visible = settings.get("standard_shortcuts_visible", False)
        if hasattr(self, "standard_shortcuts_visible"):
            self.standard_shortcuts_visible = bool(saved_standard_shortcuts_visible)
        if hasattr(self, "favorite_splitter") and self.favorite_splitter is not None and self.favorite_splitter.IsSplit():
            if favorite_sash is not None:
                self.favorite_panel_above_tree = favorite_above_tree
                self._apply_favorite_panel_position(sash_position=int(favorite_sash))
            else:
                self.favorite_panel_above_tree = favorite_above_tree
                self._apply_favorite_panel_position()
        if self.favorite_content_splitter is not None:
            if self.standard_shortcuts_visible and not self.favorite_content_splitter.IsSplit():
                try:
                    sash = normalize_shortcuts_sash(self.favorite_standard_shortcuts_splitter_sash)
                    self.favorite_content_splitter.SplitHorizontally(
                        self.favorite_list,
                        self.standard_shortcuts_panel,
                        sash,
                    )
                except Exception:
                    pass
            if self.favorite_content_splitter.IsSplit():
                self.favorite_content_splitter.SetSashPosition(normalize_shortcuts_sash(self.favorite_standard_shortcuts_splitter_sash))
            if hasattr(self, "favorite_panel") and self.favorite_panel is not None and hasattr(self.favorite_panel, "GetSizer"):
                self.favorite_panel.GetSizer().Layout()

    def on_close(self, event):
        unsaved_pdf_paths = get_unsaved_pdf_paths()
        if unsaved_pdf_paths:
            dialog = wx.MessageDialog(
                self,
                tr("confirm_save_before_exit", count=len(unsaved_pdf_paths)),
                tr("app_title"),
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING,
            )
            dialog.SetYesNoCancelLabels(tr("confirm_yes"), tr("confirm_no"), tr("cancel_button"))
            result = dialog.ShowModal()
            dialog.Destroy()

            if result == wx.ID_CANCEL:
                event.Veto()
                return

            try:
                with self.busy_cursor():
                    if result == wx.ID_YES:
                        for path in unsaved_pdf_paths:
                            save_pdf(path)
                    else:
                        for path in unsaved_pdf_paths:
                            discard_pdf_changes(path)
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
                event.Veto()
                return

        try:
            self.save_splitter_positions()
            self.save_list_view_state()
            save_window_geometry(self)
            self.save_last_folder()
        except Exception:
            pass
        event.Skip()

    def refresh_locale(self):
        self.SetTitle(tr("app_title"))
        self.back_btn.SetToolTip(tr("back_button"))
        self.forward_btn.SetToolTip(tr("forward_button"))
        self.exit_btn.SetToolTip(tr("exit_button"))
        self.search_in_files_btn.SetToolTip(tr("search_in_files_button"))
        if hasattr(self, "search_box"):
            self.search_box.SetHint(tr("search_hint"))
        if hasattr(self, "filter_label"):
            self.filter_label.SetLabel(tr("filter_label"))
        self.hidden_chk.SetLabel(tr("show_hidden_checkbox"))
        if hasattr(self, "menu_bar") and self.menu_bar is not None:
            self.file_menu.SetTitle(tr("menu_file"))
            self.navigation_menu.SetTitle(tr("menu_navigation"))
            self.document_menu.SetTitle(tr("menu_document"))
            self.help_menu.SetTitle(tr("menu_help"))
            self.file_scan_item.SetItemLabel(tr("scan"))
            self.file_open_item.SetItemLabel(tr("context_open"))
            self.file_rename_item.SetItemLabel(tr("context_rename"))
            self.file_new_folder_item.SetItemLabel(tr("context_new_folder"))
            self.file_refresh_item.SetItemLabel(tr("context_refresh"))
            self.file_copy_item.SetItemLabel(tr("context_copy"))
            self.file_cut_item.SetItemLabel(tr("context_cut"))
            self.file_paste_item.SetItemLabel(tr("context_paste"))
            self.file_delete_item.SetItemLabel(tr("context_remove_to_recycle_bin"))
            self.file_delete_permanent_item.SetItemLabel(tr("context_delete"))
            self.file_options_item.SetItemLabel(tr("menu_file_options"))
            self.file_quit_item.SetItemLabel(tr("exit_button"))
            self.nav_back_item.SetItemLabel(tr("back_button"))
            self.nav_forward_item.SetItemLabel(tr("forward_button"))
            self.nav_up_item.SetItemLabel(tr("folder_up_button"))
            self.nav_search_item.SetItemLabel(tr("search_in_files_button"))
            self.help_about_item.SetItemLabel(tr("menu_about"))
            self.doc_import_item.SetItemLabel(tr("preview_import_from_file_button"))
            self.doc_import_scanner_item.SetItemLabel(tr("preview_import_from_scanner_button"))
            self.doc_export_item.SetItemLabel(tr("preview_export_pages_button"))
            self.doc_save_item.SetItemLabel(tr("preview_save_button"))
            self.doc_cancel_item.SetItemLabel(tr("preview_cancel_button"))
            self.doc_zoom_in_item.SetItemLabel(tr("preview_zoom_in_button"))
            self.doc_zoom_out_item.SetItemLabel(tr("preview_zoom_out_button"))
            self.doc_1_page_wide_item.SetItemLabel(tr("preview_show_1_page_wide"))
            self.doc_2_pages_wide_item.SetItemLabel(tr("preview_show_2_pages_wide"))
            self.doc_1_page_tall_item.SetItemLabel(tr("preview_show_1_page_tall"))
            self.doc_manual_scale_item.SetItemLabel(tr("preview_show_manual_scale"))
            self.doc_rotate_all_left_item.SetItemLabel(tr("preview_rotate_all_left_button"))
            self.doc_rotate_left_item.SetItemLabel(tr("preview_rotate_left_button"))
            self.doc_rotate_right_item.SetItemLabel(tr("preview_rotate_right_button"))
            self.doc_rotate_all_right_item.SetItemLabel(tr("preview_rotate_all_right_button"))
            self.doc_move_page_item.SetItemLabel(tr("preview_move_page_button"))
            self.doc_remove_page_item.SetItemLabel(tr("preview_remove_page_button"))
            self.doc_adjust_page_width_item.SetItemLabel(tr("preview_adjust_page_width_button"))
            self.doc_optimize_item.SetItemLabel(tr("preview_optimize_button"))
        for index, key in enumerate(("name_column", "type_column", "size_column", "modified_column")):
            column = self.list.GetColumn(index)
            column.SetMask(wx.LIST_MASK_TEXT)
            column.SetText(tr(key))
            if hasattr(column, "SetImage"):
                column.SetImage(-1)
            self.list.SetColumn(index, column)
        self.update_list_sort_header_icons()
        ## self.preview_edit_btn.SetToolTip(tr("preview_edit_button"))
        self.preview_save_btn.SetToolTip(tr("preview_save_button"))
        self.preview_cancel_btn.SetToolTip(tr("preview_cancel_button"))
        ## self.preview_delete_btn.SetToolTip(tr("preview_delete_button"))
        self.preview_zoom_in_btn.SetToolTip(tr("preview_zoom_in_button"))
        self.preview_zoom_out_btn.SetToolTip(tr("preview_zoom_out_button"))
        self.preview_rotate_menu_btn.SetToolTip(tr("preview_rotate_button"))
        ## self.preview_auto_rotate_btn.SetToolTip(tr("preview_auto_rotate_button"))
        file_preview.sync_pdf_page_view_mode_controls(self)
        self.preview_optimize_btn.SetToolTip(tr("preview_optimize_button"))
        self.preview_adjust_page_width_btn.SetToolTip(tr("preview_adjust_page_width_button"))
        self.preview_import_from_file_btn.SetToolTip(tr("preview_import_button"))
        self.preview_export_pages_btn.SetToolTip(tr("preview_export_pages_button"))
        self.preview_remove_page_btn.SetToolTip(tr("preview_remove_page_button"))
        self.preview_move_page_btn.SetToolTip(tr("preview_move_page_button"))
        self.list_scan_btn.SetToolTip(tr("scan"))
        self.list_open_btn.SetToolTip(tr("context_open"))
        self.list_rename_btn.SetToolTip(tr("context_rename"))
        self.list_up_btn.SetToolTip(tr("folder_up_button"))
        self.list_new_folder_btn.SetToolTip(tr("context_new_folder"))
        self.list_print_btn.SetToolTip(tr("context_print"))
        self.list_copy_btn.SetToolTip(tr("context_copy"))
        self.list_cut_btn.SetToolTip(tr("context_cut"))
        self.list_paste_btn.SetToolTip(tr("context_paste"))
        self.list_delete_btn.SetToolTip(tr("context_remove_to_recycle_bin"))
        ## self.list_delete_permanent_btn.SetToolTip(tr("context_delete"))
        self.refresh_tree_placeholders()
        self.load_folder(self.path_box.GetValue())
        file_preview.show_file_preview(self, self.current_preview_path)

    def set_pdf_page_view_mode(self, mode, refresh_preview=True):
        if mode not in file_preview.VALID_PAGE_VIEW_MODES:
            return

        if self.pdf_page_view_mode == mode:
            file_preview.sync_pdf_page_view_mode_controls(self)
            return

        self.pdf_page_view_mode = mode
        if mode in file_preview.FIXED_PAGE_VIEW_MODES:
            self.pdf_page_view_selected_mode = mode
        file_preview.sync_pdf_page_view_mode_controls(self)

        if refresh_preview:
            if is_pdf_file(self.current_preview_path):
                file_preview.show_pdf_feed(self, self.current_preview_path)
            elif self.current_preview_path:
                file_preview.refresh_preview_for_page_view_mode(self, self.current_preview_path)

    def show_file_preview(self, path):
        file_preview.show_file_preview(self, path)

    def confirm_preview_change(self, path):
        return file_preview.confirm_preview_change(self, path)

    def show_pdf_feed(self, path):
        file_preview.show_pdf_feed(self, path)

    def on_key(self, event):
        # Handle Ctrl+Z for undo
        try:
            key_code = event.GetKeyCode()
            if event.ControlDown() and key_code == 90:  # 'Z'
                self.undo_last_move()
                return
            if event.ControlDown() and key_code == 70:  # 'F'
                self.on_search_in_files()
                return
            if event.ControlDown() and key_code == 80:  # 'P'
                selected_list_paths = filelist.get_selected_list_paths(self) if hasattr(self, "list") and self.list is not None else []
                path = selected_list_paths[0] if len(selected_list_paths) == 1 else None
                if not path:
                    path = getattr(self, "current_preview_path", None)
                if not path:
                    path = filelist._resolve_tree_selection_path(self)
                if path and os.path.isfile(path):
                    filelist.on_list_print(self, None)
                    return
                if path and os.path.isdir(path):
                    wx.MessageBox(tr("print_no_selection"), tr("print_dialog_title"), style=wx.OK | wx.ICON_INFORMATION)
                    return
                filelist.on_list_print(self, None)
                return
            if event.ControlDown() and key_code == ord("D"):
                filelist.on_list_delete(self, None)
                return
            if event.ShiftDown() and key_code == wx.WXK_DELETE:
                filelist.on_list_delete_permanent(self, None)
                return
            if key_code == wx.WXK_F5:
                current_folder = self.path_box.GetValue() if hasattr(self, "path_box") else ""
                if current_folder and os.path.isdir(current_folder):
                    self.load_folder(current_folder)
                tree_utils.refresh_tree_selection_and_filelist(self)
                return
            if filelist.handle_file_ops_shortcut(self, event):
                return
        except Exception:
            pass
        event.Skip()

    def undo_last_move(self):
        if not self.undo_stack:
            wx.MessageBox(tr("undo_no_action"), tr("undo_title"), style=wx.OK | wx.ICON_INFORMATION)
            return
        path, orig_index, result_index = self.undo_stack.pop()
        try:
            with self.busy_cursor():
                move_pdf_page(path, result_index, orig_index)
                # refresh view if current file matches
                if path == self.current_pdf_path:
                    self.show_pdf_feed(self.current_pdf_path)
            wx.MessageBox(tr("undo_done"), tr("undo_title"), style=wx.OK | wx.ICON_INFORMATION)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("undo_title"), style=wx.OK | wx.ICON_ERROR)

    # ---------------- NAVIGATION ----------------
    def open_path(self, path, add_history=True):
        return navigation_utils.open_path(self, path, add_history=add_history)

    def open_recycle_bin(self, add_history=True):
        return navigation_utils.open_recycle_bin(self, add_history=add_history)

    def open_location(self, path, add_history=True):
        if not isinstance(path, str) or not path:
            return False

        if navigation_utils.is_virtual_shell_path(path):
            return self.open_path(path, add_history=add_history)

        normalized_path = os.path.abspath(path)
        if os.path.isdir(normalized_path):
            return self.open_path(normalized_path, add_history=add_history)

        if os.path.isfile(normalized_path) and is_pdf_file(normalized_path):
            return self.open_pdf_file(normalized_path, add_history=add_history)

        return False

    def open_pdf_file(self, path, add_history=True):
        normalized_path = os.path.abspath(path)
        parent_folder = os.path.dirname(normalized_path)
        if not parent_folder or not os.path.isdir(parent_folder):
            return False

        if not self.open_path(parent_folder, add_history=add_history):
            return False

        self._syncing_tree_from_path = True
        try:
            self.select_tree_item_by_path(parent_folder)
        finally:
            self._syncing_tree_from_path = False

        if not self.select_list_item_by_path(normalized_path):
            return False

        file_preview.show_file_preview(self, normalized_path)
        return True

    def go_back(self, _):
        navigation_utils.go_back(self, _)

    def go_forward(self, _):
        navigation_utils.go_forward(self, _)

    def on_folder_up(self, _):
        filelist.on_folder_up(self, _)

    # ---------------- LIST ----------------
    def load_folder(self, path):
        navigation_utils.load_folder(self, path)

    def refresh_list_item_size(self, path):
        return filelist.refresh_list_item_size(self, path)

    def select_list_item_by_path(self, path):
        return filelist.select_list_item_by_path(self, path)

    def on_preview_resize(self, event):
        image_utils.refresh_image_preview_bitmap(self)

        if is_pdf_file(self.current_preview_path):
            if not getattr(self, "_pdf_preview_resize_refresh_pending", False):
                self._pdf_preview_resize_refresh_pending = True

                def _refresh_pdf_preview_after_resize():
                    self._pdf_preview_resize_refresh_pending = False
                    if is_pdf_file(self.current_preview_path):
                        file_preview.show_pdf_feed(self, self.current_preview_path)

                wx.CallAfter(_refresh_pdf_preview_after_resize)

        event.Skip()

    # --------- EVENTS ----------------
    def bind_events(self):
        self.back_btn.Bind(wx.EVT_BUTTON, self.go_back)
        self.forward_btn.Bind(wx.EVT_BUTTON, self.go_forward)
        self.exit_btn.Bind(wx.EVT_BUTTON, self.on_exit)
        self.search_in_files_btn.Bind(wx.EVT_BUTTON, self.on_search_in_files)

        self.path_box.Bind(wx.EVT_TEXT_ENTER, self.on_path_enter)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, lambda e: self.refresh())
        self.hidden_chk.Bind(wx.EVT_CHECKBOX, self.on_toggle_hidden)

        tree_utils.bind_tree_events(self)
        filelist.bind_list_events(self)

        file_preview.bind_preview_events(self)
        self.filePreview.Bind(wx.EVT_SIZE, self.on_preview_resize)

    def on_tree_expand(self, event):
        return tree_utils.on_tree_expand(self, event)

    def on_tree_select(self, event):
        result = tree_utils.on_tree_select(self, event)
        self._update_main_menu_state()
        return result

    def on_tree_activated(self, event):
        return tree_utils.on_tree_activated(self, event)

    def on_tree_begin_drag(self, event):
        return tree_utils.on_tree_begin_drag(self, event)

    def on_tree_right_click(self, event):
        return tree_utils.on_tree_right_click(self, event)

    def on_list_select(self, event):
        filelist.on_list_select(self, event)
        self._update_main_menu_state()

    def on_list_begin_drag(self, event):
        filelist.on_list_begin_drag(self, event)

    def on_list_deselect(self, event):
        filelist.on_list_deselect(self, event)
        self._update_main_menu_state()

    def on_right_click(self, event):
        filelist.on_right_click(self, event)

    def get_selected_list_path(self):
        return filelist.get_selected_list_path(self)

    def on_scan_form(self, _=None):
        scan_form.on_scan_form(self)

    def on_list_scan(self, _):
        filelist.on_list_scan(self, _)

    def on_list_open(self, _, path=None):
        filelist.on_list_open(self, _, path=path)

    def on_list_rename(self, _):
        filelist.on_list_rename(self, _)

    def on_list_new_folder(self, _):
        filelist.on_list_new_folder(self, _)

    def on_list_copy(self, _):
        filelist.on_list_copy(self, _)

    def on_list_cut(self, _):
        filelist.on_list_cut(self, _)

    def on_list_paste(self, _):
        filelist.on_list_paste(self, _)

    def on_list_delete(self, _):
        filelist.on_list_delete(self, _)

    def on_list_delete_permanent(self, _):
        filelist.on_list_delete_permanent(self, _)

    def on_open_item(self, event):
        filelist.on_open_item(self, event)

    def on_list_column_click(self, event):
        filelist.on_list_column_click(self, event)

    def update_list_sort_header_icons(self):
        filelist.update_list_sort_header_icons(self)

    def update_list_toolbar_buttons(self):
        filelist.update_list_toolbar_buttons(self)

    def save_list_view_state(self):
        filelist.save_list_view_state(self)

    def restore_list_view_state(self, settings=None):
        filelist.restore_list_view_state(self, settings=settings)

    def on_path_enter(self, event):
        path = self.path_box.GetValue()
        if not self.open_location(path):
            return

        if os.path.isdir(path):
            self._syncing_tree_from_path = True
            try:
                self.select_tree_item_by_path(path)
            finally:
                self._syncing_tree_from_path = False

    def on_file_options(self, _):
        show_options_form(self)

    def on_exit(self, _):
        self.Close()

    def on_search_in_files(self, _=None):
        import controls.search_form as search_form
        search_form.show_search_form(self)

    def on_toggle_hidden(self, event):
        self.show_hidden = bool(self.hidden_chk.GetValue())
        update_settings({"show_hidden": self.show_hidden})

        tree_utils.refresh_tree_root(self)
        if hasattr(self, "path_box") and hasattr(self, "select_tree_item_by_path"):
            current_path = self.path_box.GetValue()
            if isinstance(current_path, str) and current_path:
                self.select_tree_item_by_path(os.path.dirname(current_path))
        if hasattr(self, "tree") and self.tree is not None:
            tree_utils.refresh_tree_selection_and_filelist(self)
        if hasattr(self, "refresh"):
            self.refresh()

    def refresh(self):
        self.load_folder(self.path_box.GetValue())


if __name__ == "__main__":
    app = wx.App(False)
    wx.InitAllImageHandlers()
    initial_path = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    frame = FileExplorer(initial_path=initial_path)
    frame.Show()
    app.MainLoop()