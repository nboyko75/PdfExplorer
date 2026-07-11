import os
import sys
from contextlib import contextmanager
import wx

from file_operations.pdf_utils import discard_pdf_changes, get_pdf_page_previews, get_unsaved_pdf_paths, is_pdf_file, move_pdf_page, save_pdf
from localization import tr, load_locale, available_locales
from controls.window_tools import load_settings, update_settings, save_window_geometry, restore_window_geometry
import controls.tree_utils as tree_utils
import file_operations.image_utils as image_utils
import file_operations.pdf_dragdrop as pdf_dragdrop
import controls.navigation_utils as navigation_utils
import controls.file_preview as file_preview
import controls.filelist as filelist
import controls.scanform as scanform


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

        self.history = []
        self.history_index = -1
        self.show_hidden = False
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
        settings = load_settings()
        saved_locale = str(settings.get("ui_locale", "uk")).lower()
        saved_locale = saved_locale.replace("-", "_")
        if saved_locale == "ua":
            saved_locale = "uk"
        self.current_locale = saved_locale if saved_locale in SUPPORTED_LOCALES else "uk"
        self.pdf_preview_zoom = 1.0
        self.main_splitter = None
        saved_page_view_mode = str(settings.get("pdf_page_view_mode", "1_page_wide"))
        if saved_page_view_mode not in file_preview.VALID_PAGE_VIEW_MODES:
            saved_page_view_mode = file_preview.PAGE_VIEW_MODE_1_TALL
        self.pdf_page_view_mode = saved_page_view_mode
        if saved_page_view_mode in file_preview.FIXED_PAGE_VIEW_MODES:
            self.pdf_page_view_selected_mode = saved_page_view_mode
        else:
            self.pdf_page_view_selected_mode = file_preview.PAGE_VIEW_MODE_1_TALL

        load_locale(self.current_locale)
        self.build_ui()
        self.bind_events()

        restore_window_geometry(self, settings)
        self.restore_splitter_positions(settings)
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

    def build_ui(self):
        panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ===== Toolbar =====
        toolbar = wx.BoxSizer(wx.HORIZONTAL)

        self.back_btn = image_utils.create_bitmap_button(panel, wx.ART_GO_BACK, tr("back_button"))
        self.forward_btn = image_utils.create_bitmap_button(panel, wx.ART_GO_FORWARD, tr("forward_button"))
        self.exit_btn = image_utils.create_bitmap_button(panel, wx.ART_QUIT, tr("exit_button"))

        self.path_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)

        self.search_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search_box.SetHint(tr("search_hint"))

        self.hidden_chk = wx.CheckBox(panel, label=tr("show_hidden_checkbox"))
        self.language_combo = wx.ComboBox(panel, choices=[label for label, _ in LANGUAGE_CHOICES_SORTED], style=wx.CB_READONLY)
        self.language_combo.SetValue(LANGUAGE_LABEL_BY_CODE.get(self.current_locale, "UA"))

        toolbar.Add(self.back_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar.Add(self.forward_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 5)
        toolbar.Add(self.exit_btn, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.path_box, 1, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.search_box, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.hidden_chk, 0, wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, 10)
        toolbar.Add(self.language_combo, 0, wx.ALIGN_CENTER_VERTICAL)

        # ===== Split view =====
        self.main_splitter = wx.SplitterWindow(panel)

        self.tree = wx.TreeCtrl(self.main_splitter, style=wx.TR_HAS_BUTTONS)
        self.init_tree_images()
        self.filePanel = wx.Panel(self.main_splitter)
        self.main_splitter.SplitVertically(self.tree, self.filePanel, 320)

        self.fileSplitter = wx.SplitterWindow(self.filePanel)

        self.icon_manager = image_utils.IconManager()

        self.list_host_panel = wx.Panel(self.fileSplitter)
        self.list_toolbar = wx.BoxSizer(wx.HORIZONTAL)

        list_btn_icon_size = (16, 16)
        list_btn_size = (24, 24)
        self.list_scan_btn = image_utils.create_bitmap_button2(
            self.list_host_panel,
            self.icon_manager,
            "scan",
            tr("scan"),
            icon_size=list_btn_icon_size,
            button_size=list_btn_size,
        )
        self.list_open_btn = image_utils.create_bitmap_button(
            self.list_host_panel,
            wx.ART_FIND,
            tr("context_open"),
            icon_size=list_btn_icon_size,
            button_size=list_btn_size,
        )
        self.list_rename_btn = image_utils.create_bitmap_button(
            self.list_host_panel,
            wx.ART_EDIT,
            tr("context_rename"),
            icon_size=list_btn_icon_size,
            button_size=list_btn_size,
        )
        self.list_delete_btn = image_utils.create_bitmap_button(
            self.list_host_panel,
            wx.ART_DELETE,
            tr("context_delete"),
            icon_size=list_btn_icon_size,
            button_size=list_btn_size,
        )

        self.list_toolbar.Add(self.list_scan_btn, 0, wx.RIGHT, 3)
        self.list_toolbar.Add(self.list_open_btn, 0, wx.RIGHT, 3)
        self.list_toolbar.Add(self.list_rename_btn, 0, wx.RIGHT, 3)
        self.list_toolbar.Add(self.list_delete_btn, 0)
        self.update_list_toolbar_buttons()

        self.list = wx.ListCtrl(self.list_host_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list.InsertColumn(0, tr("name_column"), width=450)
        self.list.InsertColumn(1, tr("type_column"), width=120)
        self.list.InsertColumn(2, tr("size_column"), width=120)
        image_utils.init_list_images(self)

        list_host_sizer = wx.BoxSizer(wx.VERTICAL)
        list_host_sizer.Add(self.list_toolbar, 0, wx.EXPAND | wx.ALL, 4)
        list_host_sizer.Add(self.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        self.list_host_panel.SetSizer(list_host_sizer)

        file_preview.build_file_preview_pane(self, self.fileSplitter)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.fileSplitter, 1, wx.EXPAND)
        self.filePanel.SetSizer(sizer)

        main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(self.main_splitter, 1, wx.EXPAND)

        panel.SetSizer(main_sizer)

        self.init_tree()

    def init_tree_images(self):
        return tree_utils.init_tree_images(self)

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

        if self.main_splitter is not None and self.main_splitter.IsSplit():
            main_sash = int(self.main_splitter.GetSashPosition())

        if self.fileSplitter is not None and self.fileSplitter.IsSplit():
            preview_sash = int(self.fileSplitter.GetSashPosition())

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

    def on_close(self, event):
        unsaved_pdf_paths = get_unsaved_pdf_paths()
        if unsaved_pdf_paths:
            dialog = wx.MessageDialog(
                self,
                tr("confirm_save_before_exit", count=len(unsaved_pdf_paths)),
                tr("app_title"),
                wx.YES_NO | wx.CANCEL | wx.CANCEL_DEFAULT | wx.ICON_WARNING,
            )
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
        self.search_box.SetHint(tr("search_hint"))
        self.hidden_chk.SetLabel(tr("show_hidden_checkbox"))
        self.language_combo.SetValue(LANGUAGE_LABEL_BY_CODE.get(self.current_locale, "UA"))
        for index, key in enumerate(("name_column", "type_column", "size_column")):
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
        self.preview_auto_rotate_btn.SetToolTip(tr("preview_auto_rotate_button"))
        file_preview.sync_pdf_page_view_mode_controls(self)
        self.preview_optimize_btn.SetToolTip(tr("preview_optimize_button"))
        self.preview_ajust_page_width_btn.SetToolTip(tr("preview_adjust_page_width_button"))
        self.preview_import_from_file_btn.SetToolTip(tr("preview_import_from_file_button"))
        self.preview_export_pages_btn.SetToolTip(tr("preview_export_pages_button"))
        self.preview_remove_page_btn.SetToolTip(tr("preview_remove_page_button"))
        self.preview_move_page_btn.SetToolTip(tr("preview_move_page_button"))
        self.list_scan_btn.SetToolTip(tr("scan"))
        self.list_open_btn.SetToolTip(tr("context_open"))
        self.list_rename_btn.SetToolTip(tr("context_rename"))
        self.list_delete_btn.SetToolTip(tr("context_delete"))
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

        if refresh_preview and is_pdf_file(self.current_preview_path):
            file_preview.show_pdf_feed(self, self.current_preview_path)

    def create_drag_overlay(self):
        return pdf_dragdrop.create_drag_overlay(self)

    def show_drag_overlay(self, page_index, page_panel, x, y):
        pdf_dragdrop.show_drag_overlay(self, page_index, page_panel, x, y)

    def hide_drag_overlay(self):
        pdf_dragdrop.hide_drag_overlay(self)

    def create_drop_frame(self):
        return pdf_dragdrop.create_drop_frame(self)

    def show_drop_frame(self, page_index, page_panel, x, y):
        pdf_dragdrop.show_drop_frame(self, page_index, page_panel, x, y)

    def hide_drop_frame(self):
        pdf_dragdrop.hide_drop_frame(self)

    def show_file_preview(self, path):
        file_preview.show_file_preview(self, path)

    def confirm_preview_change(self, path):
        return file_preview.confirm_preview_change(self, path)

    def show_pdf_feed(self, path):
        file_preview.show_pdf_feed(self, path)

    def get_pdf_page_panel_from_event(self, event):
        return file_preview.get_pdf_page_panel_from_event(self, event)

    def get_selected_pdf_page_index(self):
        return file_preview.get_selected_pdf_page_index(self)

    def on_language_change(self, event):
        value = self.language_combo.GetValue()
        self.current_locale = LANGUAGE_CODE_BY_LABEL.get(value, "en")
        update_settings({"ui_locale": self.current_locale})
        load_locale(self.current_locale)
        self.refresh_locale()

    def on_key(self, event):
        # Handle Ctrl+Z for undo
        try:
            if event.ControlDown() and event.GetKeyCode() == 90:  # 'Z'
                self.undo_last_move()
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

    # ---------------- TREE ----------------
    def normalize_tree_path(self, path):
        return tree_utils.normalize_tree_path(path)

    def populate_tree_node(self, item, path):
        return tree_utils.populate_tree_node(self, item, path)

    def init_tree(self):
        return tree_utils.init_tree(self)

    def get_drives(self):
        return tree_utils.get_drives()

    # ---------------- NAVIGATION ----------------
    def open_path(self, path, add_history=True):
        return navigation_utils.open_path(self, path, add_history=add_history)

    def open_location(self, path, add_history=True):
        if not isinstance(path, str) or not path:
            return False

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

        self.path_box.Bind(wx.EVT_TEXT_ENTER, self.on_path_enter)
        self.search_box.Bind(wx.EVT_TEXT_ENTER, lambda e: self.refresh())
        self.hidden_chk.Bind(wx.EVT_CHECKBOX, self.on_toggle_hidden)
        self.language_combo.Bind(wx.EVT_COMBOBOX, self.on_language_change)

        self.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.on_tree_expand)
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGING, self.on_tree_select)
        self.tree.Bind(wx.EVT_CONTEXT_MENU, self.on_tree_right_click)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_list_select)
        self.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.on_list_deselect)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_open_item)
        self.list.Bind(wx.EVT_RIGHT_DOWN, self.on_right_click)
        self.list.Bind(wx.EVT_LIST_COL_CLICK, self.on_list_column_click)
        self.list_scan_btn.Bind(wx.EVT_BUTTON, self.on_list_scan)
        self.list_open_btn.Bind(wx.EVT_BUTTON, self.on_list_open)
        self.list_rename_btn.Bind(wx.EVT_BUTTON, self.on_list_rename)
        self.list_delete_btn.Bind(wx.EVT_BUTTON, self.on_list_delete)

        file_preview.bind_preview_events(self)
        self.filePreview.Bind(wx.EVT_SIZE, self.on_preview_resize)

    def on_tree_expand(self, event):
        return tree_utils.on_tree_expand(self, event)

    def on_tree_select(self, event):
        return tree_utils.on_tree_select(self, event)

    def on_tree_right_click(self, event):
        return tree_utils.on_tree_right_click(self, event)

    def on_list_select(self, event):
        filelist.on_list_select(self, event)

    def on_list_deselect(self, event):
        filelist.on_list_deselect(self, event)

    def on_right_click(self, event):
        filelist.on_right_click(self, event)

    def get_selected_list_path(self):
        return filelist.get_selected_list_path(self)

    def on_scan_form(self, _=None):
        scanform.on_scan_form(self)

    def on_list_scan(self, _):
        filelist.on_list_scan(self, _)

    def on_list_open(self, _):
        filelist.on_list_open(self, _)

    def on_list_rename(self, _):
        filelist.on_list_rename(self, _)

    def on_list_delete(self, _):
        filelist.on_list_delete(self, _)

    def on_open_item(self, event):
        filelist.on_open_item(self, event)

    def on_list_column_click(self, event):
        filelist.on_list_column_click(self, event)

    def update_list_sort_header_icons(self):
        filelist.update_list_sort_header_icons(self)

    def update_list_toolbar_buttons(self):
        filelist.update_list_toolbar_buttons(self)

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

    def on_exit(self, _):
        self.Close()

    def on_toggle_hidden(self, event):
        self.show_hidden = self.hidden_chk.GetValue()
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