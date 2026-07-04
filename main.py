import os
from contextlib import contextmanager
import wx

from pdf_utils import get_pdf_page_previews, is_pdf_file, move_pdf_page
from localization import tr, load_locale, available_locales
from window_tools import load_settings, update_settings, save_window_geometry, restore_window_geometry
import tree_utils
import image_utils
import pdf_dragdrop
import navigation_utils
import file_preview


class FileExplorer(wx.Frame):
    def __init__(self):
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
        settings = load_settings()
        saved_locale = str(settings.get("ui_locale", "uk")).lower()
        if saved_locale == "ua":
            saved_locale = "uk"
        self.current_locale = saved_locale if saved_locale in ("en", "uk") else "uk"
        self.pdf_preview_zoom = 1.0

        load_locale(self.current_locale)
        self.build_ui()
        self.bind_events()

        restore_window_geometry(self, settings)

        last_folder = settings.get("last_folder")
        if last_folder and os.path.isdir(last_folder):
            self.open_path(last_folder, add_history=False)
            wx.CallAfter(self.select_tree_item_by_path, last_folder)
        else:
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
        self.language_combo = wx.ComboBox(panel, choices=["EN", "UA"], style=wx.CB_READONLY)
        self.language_combo.SetValue("UA" if self.current_locale == "uk" else "EN")

        toolbar.Add(self.back_btn, 0, wx.RIGHT, 5)
        toolbar.Add(self.forward_btn, 0, wx.RIGHT, 5)
        toolbar.Add(self.exit_btn, 0, wx.RIGHT, 10)
        toolbar.Add(self.path_box, 1, wx.RIGHT, 10)
        toolbar.Add(self.search_box, 0, wx.RIGHT, 10)
        toolbar.Add(self.hidden_chk, 0, wx.RIGHT, 10)
        toolbar.Add(self.language_combo, 0)

        # ===== Split view =====
        splitter = wx.SplitterWindow(panel)

        self.tree = wx.TreeCtrl(splitter, style=wx.TR_HAS_BUTTONS)
        self.init_tree_images()
        self.filePanel = wx.Panel(splitter)
        splitter.SplitVertically(self.tree, self.filePanel, 320)

        self.fileSplitter = wx.SplitterWindow(self.filePanel)

        self.list = wx.ListCtrl(self.fileSplitter, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list.InsertColumn(0, tr("name_column"), width=450)
        self.list.InsertColumn(1, tr("type_column"), width=120)
        self.list.InsertColumn(2, tr("size_column"), width=120)
        image_utils.init_list_images(self)

        file_preview.build_file_preview_pane(self, self.fileSplitter)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.fileSplitter, 1, wx.EXPAND)
        self.filePanel.SetSizer(sizer)

        main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 5)
        main_sizer.Add(splitter, 1, wx.EXPAND)

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

    def on_close(self, event):
        try:
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
        self.language_combo.SetValue("UA" if self.current_locale == "uk" else "EN")
        name_col = self.list.GetColumn(0)
        name_col.SetText(tr("name_column"))
        self.list.SetColumn(0, name_col)
        type_col = self.list.GetColumn(1)
        type_col.SetText(tr("type_column"))
        self.list.SetColumn(1, type_col)
        size_col = self.list.GetColumn(2)
        size_col.SetText(tr("size_column"))
        self.list.SetColumn(2, size_col)
        self.preview_edit_btn.SetToolTip(tr("preview_edit_button"))
        self.preview_delete_btn.SetToolTip(tr("preview_delete_button"))
        self.preview_zoom_in_btn.SetToolTip(tr("preview_zoom_in_button"))
        self.preview_zoom_out_btn.SetToolTip(tr("preview_zoom_out_button"))
        self.preview_rotate_all_left_btn.SetToolTip(tr("preview_rotate_all_left_button"))
        self.preview_rotate_left_btn.SetToolTip(tr("preview_rotate_left_button"))
        self.preview_rotate_right_btn.SetToolTip(tr("preview_rotate_right_button"))
        self.preview_rotate_all_right_btn.SetToolTip(tr("preview_rotate_all_right_button"))
        self.preview_optimize_btn.SetToolTip(tr("preview_optimize_button"))
        self.preview_ajust_page_width_btn.SetToolTip(tr("preview_ajust_page_width_button"))
        self.refresh_tree_placeholders()
        self.load_folder(self.path_box.GetValue())
        file_preview.show_file_preview(self, self.current_preview_path)

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

    def show_pdf_feed(self, path):
        file_preview.show_pdf_feed(self, path)

    def on_language_change(self, event):
        value = self.language_combo.GetValue().upper()
        self.current_locale = "uk" if value == "UA" else "en"
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
        navigation_utils.open_path(self, path, add_history=add_history)

    def go_back(self, _):
        navigation_utils.go_back(self, _)

    def go_forward(self, _):
        navigation_utils.go_forward(self, _)

    # ---------------- LIST ----------------
    def load_folder(self, path):
        navigation_utils.load_folder(self, path)

    def on_preview_resize(self, event):
        image_utils.refresh_image_preview_bitmap(self)
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
        self.tree.Bind(wx.EVT_TREE_SEL_CHANGED, self.on_tree_select)
        self.tree.Bind(wx.EVT_CONTEXT_MENU, self.on_tree_right_click)
        self.list.Bind(wx.EVT_LIST_ITEM_SELECTED, self.on_list_select)
        self.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_open_item)
        self.list.Bind(wx.EVT_RIGHT_DOWN, self.on_right_click)

        file_preview.bind_preview_events(self)
        self.filePreview.Bind(wx.EVT_SIZE, self.on_preview_resize)

    def on_tree_expand(self, event):
        return tree_utils.on_tree_expand(self, event)

    def on_tree_select(self, event):
        return tree_utils.on_tree_select(self, event)

    def on_tree_right_click(self, event):
        return tree_utils.on_tree_right_click(self, event)

    def on_list_select(self, event):
        index = event.GetIndex()
        name = self.list.GetItemText(index)
        path = os.path.join(self.path_box.GetValue(), name)
        file_preview.show_file_preview(self, path)

    def on_right_click(self, event):
        menu = wx.Menu()

        open_item = menu.Append(-1, tr("context_open"))
        rename_item = menu.Append(-1, tr("context_rename"))
        delete_item = menu.Append(-1, tr("context_delete"))

        self.PopupMenu(menu)
        menu.Destroy()

    def on_open_item(self, event):
        name = event.GetText()
        path = os.path.join(self.path_box.GetValue(), name)

        if os.path.isdir(path):
            self.open_path(path)

    def on_path_enter(self, event):
        self.open_path(self.path_box.GetValue())

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
    frame = FileExplorer()
    frame.Show()
    app.MainLoop()