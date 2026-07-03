import os
from contextlib import contextmanager
import wx

from pdf_utils import get_pdf_page_previews, is_pdf_file, move_pdf_page, rotate_pdf, rotate_pdf_page, optimize_pdf, ajust_page_width
from localization import tr, load_locale, available_locales
from window_tools import load_settings, update_settings, save_window_geometry, restore_window_geometry
import tree_utils


class PdfPageDropTarget(wx.DropTarget):
    def __init__(self, owner, page_index, page_panel, insert_before=None):
        super().__init__(wx.TextDataObject())
        self.owner = owner
        self.page_index = page_index
        self.page_panel = page_panel
        self.insert_before = insert_before
        self.data = wx.TextDataObject()
        self.SetDataObject(self.data)

    def OnEnter(self, x, y, d):
        try:
            if self.owner and self.page_panel:
                self.owner.show_drag_overlay(self.page_index, self.page_panel, x, y)
                self.owner.show_drop_frame(self.page_index, self.page_panel, x, y)
        except Exception:
            pass
        return wx.DragCopy

    def OnDragOver(self, x, y, d):
        try:
            if self.owner and self.page_panel:
                self.owner.show_drag_overlay(self.page_index, self.page_panel, x, y)
                self.owner.show_drop_frame(self.page_index, self.page_panel, x, y)
        except Exception:
            pass
        return wx.DragCopy

    def OnLeave(self):
        try:
            self.owner.hide_drag_overlay()
            self.owner.hide_drop_frame()
        except Exception:
            pass
        self.page_panel = None

    def OnDrop(self, x, y):
        try:
            self.owner.hide_drag_overlay()
            self.owner.hide_drop_frame()
        except Exception:
            pass
        return True

    def OnData(self, x, y, default):
        try:
            self.GetData()
            if self.insert_before is not None:
                insert_before = self.insert_before
            else:
                try:
                    size = self.page_panel.GetSize()
                    insert_before = y < (size.y // 2)
                except Exception:
                    insert_before = True

            if self.owner:
                self.owner.handle_pdf_page_drop(self.page_index, self.data.GetText(), insert_before=insert_before)
        except Exception:
            pass
        return wx.DragCopy


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

    def create_bitmap_button(self, parent, art_id, tooltip=None, icon_size=(24, 24), button_size=(32, 32)):
        bmp = wx.ArtProvider.GetBitmap(art_id, wx.ART_TOOLBAR, icon_size)
        button = wx.BitmapButton(parent, bitmap=bmp, size=button_size)
        if tooltip:
            button.SetToolTip(tooltip)
        return button

    def create_joined_art_bitmap(self, art_id, client=wx.ART_TOOLBAR, size=(24, 24)):
        first = wx.ArtProvider.GetBitmap(art_id, client, size)
        second = wx.ArtProvider.GetBitmap(art_id, client, size)
        if not first.IsOk():
            return first
        if not second.IsOk():
            return first

        width, height = size
        joined = wx.Bitmap(width, height, depth=32)
        joined.UseAlpha()
        dc = wx.MemoryDC(joined)
        dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
        dc.Clear()

        offset_x = max(3, width // 3)
        dc.DrawBitmap(first, 0, 0, True)
        dc.DrawBitmap(second, offset_x, 0, True)
        dc.SelectObject(wx.NullBitmap)
        return joined

    def init_list_images(self):
        self.list_images = wx.ImageList(16, 16)
        self.list_icon_cache = {}

        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        if not folder_bmp.IsOk():
            folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, (16, 16))

        file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
        if not file_bmp.IsOk():
            file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (16, 16))

        self.list_icon_cache["__folder__"] = self.list_images.Add(folder_bmp)
        self.list_icon_cache["__file__"] = self.list_images.Add(file_bmp)
        self.list.SetImageList(self.list_images, wx.IMAGE_LIST_SMALL)

    def get_list_icon_index(self, path, is_dir):
        if is_dir:
            return self.list_icon_cache["__folder__"]

        ext = os.path.splitext(path)[1].lower()
        if not ext:
            return self.list_icon_cache["__file__"]

        cached = self.list_icon_cache.get(ext)
        if cached is not None:
            return cached

        bmp = self.create_extension_icon_bitmap(ext)
        self.list_icon_cache[ext] = self.list_images.Add(bmp)
        return self.list_icon_cache[ext]

    def create_extension_icon_bitmap(self, ext):
        size = 16
        bmp = wx.Bitmap(size, size, depth=32)
        bmp.UseAlpha()

        dc = wx.MemoryDC(bmp)
        dc.SetBackground(wx.Brush(wx.Colour(0, 0, 0, 0)))
        dc.Clear()

        color = self.get_extension_color(ext)
        dc.SetBrush(wx.Brush(color))
        dc.SetPen(wx.Pen(color))
        dc.DrawRoundedRectangle(0, 0, size, size, 3)

        text = (ext[1:3] if ext.startswith(".") else ext[:2]).upper() or "?"
        font = wx.Font(7, wx.FONTFAMILY_SWISS, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
        dc.SetFont(font)
        dc.SetTextForeground(wx.Colour(255, 255, 255))
        tw, th = dc.GetTextExtent(text)
        dc.DrawText(text, max(0, (size - tw) // 2), max(0, (size - th) // 2))

        dc.SelectObject(wx.NullBitmap)
        return bmp

    def get_extension_color(self, ext):
        value = 0
        for index, ch in enumerate(ext):
            value += (index + 17) * ord(ch)
        red = 80 + (value % 120)
        green = 70 + ((value // 7) % 130)
        blue = 80 + ((value // 13) % 120)
        return wx.Colour(red, green, blue)

    def build_ui(self):
        panel = wx.Panel(self)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ===== Toolbar =====
        toolbar = wx.BoxSizer(wx.HORIZONTAL)

        self.back_btn = self.create_bitmap_button(panel, wx.ART_GO_BACK, tr("back_button"))
        self.forward_btn = self.create_bitmap_button(panel, wx.ART_GO_FORWARD, tr("forward_button"))

        self.path_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)

        self.search_box = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
        self.search_box.SetHint(tr("search_hint"))

        self.hidden_chk = wx.CheckBox(panel, label=tr("show_hidden_checkbox"))
        self.language_combo = wx.ComboBox(panel, choices=["EN", "UA"], style=wx.CB_READONLY)
        self.language_combo.SetValue("UA" if self.current_locale == "uk" else "EN")

        toolbar.Add(self.back_btn, 0, wx.RIGHT, 5)
        toolbar.Add(self.forward_btn, 0, wx.RIGHT, 10)
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
        self.init_list_images()

        self.filePreview = wx.Panel(self.fileSplitter, style=wx.BORDER_SUNKEN)
        self.preview_toolbar = wx.BoxSizer(wx.HORIZONTAL)

        preview_icon_size = (16, 16)
        preview_button_size = (24, 24)

        self.preview_edit_btn = self.create_bitmap_button(self.filePreview, wx.ART_FIND, tr("preview_edit_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_delete_btn = self.create_bitmap_button(self.filePreview, wx.ART_DELETE, tr("preview_delete_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_zoom_out_btn = self.create_bitmap_button(self.filePreview, wx.ART_MINUS, tr("preview_zoom_out_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_zoom_in_btn = self.create_bitmap_button(self.filePreview, wx.ART_PLUS, tr("preview_zoom_in_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_rotate_all_left_btn = self.create_bitmap_button(self.filePreview, wx.ART_UNDO, tr("preview_rotate_all_left_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_rotate_left_btn = self.create_bitmap_button(self.filePreview, wx.ART_UNDO, tr("preview_rotate_left_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_rotate_right_btn = self.create_bitmap_button(self.filePreview, wx.ART_REDO, tr("preview_rotate_right_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_rotate_all_right_btn = self.create_bitmap_button(self.filePreview, wx.ART_REDO, tr("preview_rotate_all_right_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_optimize_btn = self.create_bitmap_button(self.filePreview, wx.ART_TICK_MARK, tr("preview_optimize_button"), icon_size=preview_icon_size, button_size=preview_button_size)
        self.preview_ajust_page_width_btn = self.create_bitmap_button(self.filePreview, wx.ART_REPORT_VIEW, tr("preview_ajust_page_width_button"), icon_size=preview_icon_size, button_size=preview_button_size)

        joined_toolbar_undo = self.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_TOOLBAR, size=(16, 16))
        if joined_toolbar_undo.IsOk():
            self.preview_rotate_all_left_btn.SetBitmapLabel(joined_toolbar_undo)

        joined_toolbar_redo = self.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_TOOLBAR, size=(16, 16))
        if joined_toolbar_redo.IsOk():
            self.preview_rotate_all_right_btn.SetBitmapLabel(joined_toolbar_redo)

        self.preview_toolbar.Add(self.preview_edit_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_delete_btn, 0, wx.RIGHT, 15)
        self.preview_toolbar.Add(self.preview_zoom_out_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_zoom_in_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_rotate_all_left_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_rotate_left_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_rotate_right_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_rotate_all_right_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_optimize_btn, 0, wx.RIGHT, 5)
        self.preview_toolbar.Add(self.preview_ajust_page_width_btn, 0)

        self.preview_rotate_left_btn.Enable(False)
        self.preview_rotate_right_btn.Enable(False)

        self.preview_text = wx.TextCtrl(
            self.filePreview,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.HSCROLL | wx.VSCROLL,
        )
        self.preview_text.SetValue(tr("preview_select_file"))
        self.preview_text.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)

        self.pdf_pages_panel = wx.ScrolledWindow(self.filePreview, style=wx.HSCROLL | wx.VSCROLL)
        self.pdf_pages_panel.SetScrollRate(10, 0)
        self.pdf_pages_panel.Hide()
        self.pdf_pages_panel.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)
        self.pdf_pages_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pdf_pages_panel.SetSizer(self.pdf_pages_sizer)

        self.pdf_preview = wx.StaticBitmap(self.filePreview)
        self.pdf_preview.Hide()
        self.pdf_preview.SetMinSize((250, 250))
        self.pdf_preview.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)

        self.filePreview.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)

        preview_sizer = wx.BoxSizer(wx.VERTICAL)
        preview_sizer.Add(self.preview_toolbar, 0, wx.EXPAND | wx.ALL, 5)
        preview_sizer.Add(self.preview_text, 1, wx.EXPAND | wx.ALL, 5)
        preview_sizer.Add(self.pdf_pages_panel, 1, wx.EXPAND | wx.ALL, 5)
        preview_sizer.Add(self.pdf_preview, 1, wx.EXPAND | wx.ALL, 5)
        self.filePreview.SetSizer(preview_sizer)

        self.fileSplitter.SplitHorizontally(self.list, self.filePreview, 400)

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
        current_folder = self.path_box.GetValue()
        if os.path.isdir(current_folder):
            update_settings({"last_folder": current_folder})

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
        self.show_file_preview(self.current_preview_path)

    def create_drag_overlay(self):
        if self.drag_overlay is None:
            self.drag_overlay = wx.PopupWindow(self, style=wx.BORDER_SIMPLE)
            panel = wx.Panel(self.drag_overlay)
            panel.SetBackgroundColour(wx.Colour(255, 255, 255))
            self.drag_overlay_text = wx.StaticText(panel, label="")
            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(self.drag_overlay_text, 0, wx.ALL, 5)
            panel.SetSizer(sizer)
            panel.Fit()
            self.drag_overlay.SetSize(panel.GetSize())
        return self.drag_overlay

    def show_drag_overlay(self, page_index, page_panel, x, y):
        overlay = self.create_drag_overlay()
        self.drag_overlay_text.SetLabel(tr("drop_overlay_label", page_index=page_index + 1))
        overlay.Fit()
        position = page_panel.ClientToScreen(wx.Point(x, y))
        overlay.Move(position + wx.Point(16, 16))
        overlay.Show(True)
        overlay.Raise()

    def hide_drag_overlay(self):
        if self.drag_overlay is not None:
            self.drag_overlay.Hide()
        # also hide drop frame if visible
        if getattr(self, "drop_frame", None) is not None:
            self.drop_frame.Hide()
        # restore highlighted panel
        try:
            if getattr(self, "_highlighted_panel", None) is not None:
                p = self._highlighted_panel
                if getattr(p, "_orig_bg", None) is not None:
                    p.SetBackgroundColour(p._orig_bg)
                p.Refresh()
                self._highlighted_panel = None
        except Exception:
            pass

    def create_drop_frame(self):
        if getattr(self, "drop_frame", None) is None:
            self.drop_frame = wx.PopupWindow(self, style=wx.BORDER_NONE)
            panel = wx.Panel(self.drop_frame)
            panel.SetBackgroundColour(wx.Colour(0, 120, 215))
            self.drop_frame.SetBackgroundColour(wx.Colour(0, 120, 215))
            panel.SetSize((10, 4))
        return self.drop_frame

    def show_drop_frame(self, page_index, page_panel, x, y):
        # place a thin blue bar between pages to indicate insertion point
        frame = self.create_drop_frame()
        size = page_panel.GetSize()
        half_y = size.y // 2
        # determine before/after based on y
        insert_before = y < half_y
        width = max(20, size.x - 6)
        height = 4
        frame.SetSize((width, height))
        if insert_before:
            # position at top edge
            screen_pos = page_panel.ClientToScreen(wx.Point(3, 0))
            frame.Move(screen_pos + wx.Point(0, -2))
            # set insert text in drag overlay
            overlay = self.create_drag_overlay()
            self.drag_overlay_text.SetLabel(tr("insert_before"))
            overlay.Fit()
        else:
            # position at bottom edge
            screen_pos = page_panel.ClientToScreen(wx.Point(3, size.y))
            frame.Move(screen_pos + wx.Point(0, -2))
            overlay = self.create_drag_overlay()
            self.drag_overlay_text.SetLabel(tr("insert_after"))
            overlay.Fit()
        # highlight entire panel
        try:
            if getattr(page_panel, "_orig_bg", None) is None:
                page_panel._orig_bg = page_panel.GetBackgroundColour()
            page_panel.SetBackgroundColour(wx.Colour(230, 245, 255))
            page_panel.Refresh()
            self._highlighted_panel = page_panel
        except Exception:
            pass
        frame.Show(True)

    def hide_drop_frame(self):
        if getattr(self, "drop_frame", None) is not None:
            self.drop_frame.Hide()

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
        if not os.path.isdir(path):
            return

        if add_history:
            self.history = self.history[:self.history_index + 1]
            self.history.append(path)
            self.history_index += 1

        self.path_box.SetValue(path)
        self.load_folder(path)

    def go_back(self, _):
        if self.history_index > 0:
            self.history_index -= 1
            self.open_path(self.history[self.history_index], add_history=False)

    def go_forward(self, _):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            self.open_path(self.history[self.history_index], add_history=False)

    # ---------------- LIST ----------------
    def load_folder(self, path):
        self.list.DeleteAllItems()

        try:
            items = os.listdir(path)
        except PermissionError:
            return

        filter_text = self.search_box.GetValue().lower()

        for name in items:
            if not self.show_hidden and (name.startswith(".") or name.startswith("$")):
                continue

            if filter_text and filter_text not in name.lower():
                continue

            full = os.path.join(path, name)

            if os.path.isdir(full):
                typ = tr("file_type_folder")
                size = ""
                image_index = self.get_list_icon_index(full, is_dir=True)
            else:
                typ = tr("file_type_file")
                try:
                    size = f"{os.path.getsize(full)//1024} {tr('file_size_unit_kb')}"
                except:
                    size = ""
                image_index = self.get_list_icon_index(full, is_dir=False)

            i = self.list.InsertItem(self.list.GetItemCount(), name, image_index)
            self.list.SetItem(i, 1, typ)
            self.list.SetItem(i, 2, size)

    def clear_pdf_feed(self):
        self.selected_pdf_page_panel = None
        self.pdf_pages_panel.DestroyChildren()
        self.pdf_pages_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.pdf_pages_panel.SetSizer(self.pdf_pages_sizer)
        self.update_rotate_page_buttons_state()

    def get_pdf_page_panel_from_event(self, event):
        obj = event.GetEventObject()
        while obj is not None and not hasattr(obj, "page_index"):
            obj = obj.GetParent()
        return obj

    def get_selected_pdf_page_index(self):
        if self.selected_pdf_page_panel is None:
            return None
        return getattr(self.selected_pdf_page_panel, "page_index", None)

    def update_rotate_page_buttons_state(self):
        can_rotate_selected_page = (
            is_pdf_file(self.current_preview_path)
            and self.get_selected_pdf_page_index() is not None
        )
        self.preview_rotate_left_btn.Enable(can_rotate_selected_page)
        self.preview_rotate_right_btn.Enable(can_rotate_selected_page)

    def select_pdf_page(self, page_panel):
        if self.selected_pdf_page_panel is page_panel:
            return

        if self.selected_pdf_page_panel is not None:
            self.selected_pdf_page_panel.SetBackgroundColour(wx.NullColour)
            self.selected_pdf_page_panel.Refresh()

        self.selected_pdf_page_panel = page_panel
        self.selected_pdf_page_panel.SetBackgroundColour(wx.Colour(200, 230, 255))
        self.selected_pdf_page_panel.Refresh()
        self.update_rotate_page_buttons_state()

    def on_pdf_page_select(self, event):
        page_panel = self.get_pdf_page_panel_from_event(event)
        if page_panel is None:
            return

        self.select_pdf_page(page_panel)
        self._pdf_drag_start_panel = page_panel
        self._pdf_drag_start_pos = event.GetPosition()
        event.Skip()

    def on_pdf_page_drag_motion(self, event):
        if not event.Dragging() or not event.LeftIsDown():
            return

        page_panel = self.get_pdf_page_panel_from_event(event)
        if page_panel is None or page_panel is not getattr(self, "_pdf_drag_start_panel", None):
            return

        start_pos = getattr(self, "_pdf_drag_start_pos", None)
        if start_pos is None:
            return

        current_pos = event.GetPosition()
        if abs(current_pos.x - start_pos.x) < 5 and abs(current_pos.y - start_pos.y) < 5:
            return

        self._pdf_drag_start_pos = None
        self._start_pdf_page_drag(page_panel)

    def _start_pdf_page_drag(self, page_panel):
        page_index = getattr(page_panel, "page_index", None)
        if page_index is None:
            return

        payload = f"{self.current_pdf_path}\n{page_index}"
        data = wx.TextDataObject(payload)
        source = wx.DropSource(page_panel)
        source.SetData(data)
        source.DoDragDrop(wx.Drag_AllowMove)

    def handle_pdf_page_drop(self, target_index, payload, insert_before=True):
        try:
            with self.busy_cursor():
                source_path, source_index = payload.split("\n", 1)
                source_index = int(source_index)
                if not is_pdf_file(source_path) or not is_pdf_file(self.current_pdf_path):
                    return
                if source_path != self.current_pdf_path:
                    return

                # determine final target index depending on insert_before
                try:
                    page_count, _, _ = get_pdf_page_previews(self.current_pdf_path, max_pages=1)
                except Exception:
                    page_count = None

                if insert_before:
                    to_index = target_index
                else:
                    to_index = target_index + 1

                if page_count is not None:
                    # clamp to valid range
                    to_index = max(0, min(to_index, page_count - 1))

                move_pdf_page(self.current_pdf_path, source_index, to_index)
                # compute resulting index of moved page to support undo
                if source_index < to_index:
                    result_index = to_index - 1
                else:
                    result_index = to_index
                # push undo record: (path, original_index, result_index)
                try:
                    self.undo_stack.append((self.current_pdf_path, source_index, result_index))
                except Exception:
                    pass
                self.show_pdf_feed(self.current_pdf_path)
        except Exception as exc:
            wx.MessageBox(
                tr("unable_move_pdf_page", exc=exc),
                tr("page_move_error_title"),
                style=wx.OK | wx.ICON_ERROR,
            )

    def show_pdf_feed(self, path):
        with self.busy_cursor():
            try:
                self.current_pdf_path = path
                self.clear_pdf_feed()
                max_height = max(100, min(1000, int(270 * self.pdf_preview_zoom)))
                page_count, shown_pages, previews = get_pdf_page_previews(path, max_height=max_height)

                gap_width = 22
                page_height = 180
                if previews:
                    first_bitmap = previews[0][1]
                    page_height = max(160, first_bitmap.GetSize().y)

                leading_gap = wx.Panel(self.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
                leading_gap.SetMinSize((gap_width, page_height))
                leading_gap.page_index = 0
                leading_gap.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)
                leading_gap.SetDropTarget(PdfPageDropTarget(self, 0, leading_gap, insert_before=True))
                self.pdf_pages_sizer.Add(leading_gap, 0, wx.ALL, 0)

                for index, (page_no, bitmap) in enumerate(previews):
                    page_panel = wx.Panel(self.pdf_pages_panel, style=wx.BORDER_SIMPLE)
                    page_panel.page_index = index
                    page_panel.SetDropTarget(PdfPageDropTarget(self, index, page_panel))
                    page_panel.Bind(wx.EVT_LEFT_DOWN, self.on_pdf_page_select)
                    page_panel.Bind(wx.EVT_MOTION, self.on_pdf_page_drag_motion)
                    page_panel.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)

                    page_sizer = wx.BoxSizer(wx.VERTICAL)
                    page_label = wx.StaticText(page_panel, label=tr("page_label", page_no=page_no, page_count=page_count))
                    page_bitmap = wx.StaticBitmap(page_panel, bitmap=bitmap)

                    page_label.Bind(wx.EVT_LEFT_DOWN, self.on_pdf_page_select)
                    page_label.Bind(wx.EVT_MOTION, self.on_pdf_page_drag_motion)
                    page_label.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)
                    page_bitmap.Bind(wx.EVT_LEFT_DOWN, self.on_pdf_page_select)
                    page_bitmap.Bind(wx.EVT_MOTION, self.on_pdf_page_drag_motion)
                    page_bitmap.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)

                    page_sizer.Add(page_label, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                    page_sizer.Add(page_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 3)
                    page_panel.SetSizer(page_sizer)

                    self.pdf_pages_sizer.Add(page_panel, 0, wx.ALL, 3)

                    gap_panel = wx.Panel(self.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
                    gap_panel.SetMinSize((gap_width, page_height))
                    gap_panel.page_index = index + 1
                    gap_panel.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)
                    gap_panel.SetDropTarget(PdfPageDropTarget(self, index + 1, gap_panel, insert_before=True))
                    self.pdf_pages_sizer.Add(gap_panel, 0, wx.ALL, 0)

                trailing_gap = wx.Panel(self.pdf_pages_panel, size=(gap_width, page_height), style=wx.BORDER_NONE)
                trailing_gap.SetMinSize((gap_width, page_height))
                trailing_gap.page_index = page_count
                trailing_gap.Bind(wx.EVT_CONTEXT_MENU, self.on_preview_right_click)
                trailing_gap.SetDropTarget(PdfPageDropTarget(self, page_count, trailing_gap, insert_before=False))
                self.pdf_pages_sizer.Add(trailing_gap, 0, wx.ALL, 0)

                if page_count > shown_pages:
                    note = wx.StaticText(
                        self.pdf_pages_panel,
                        label=tr("showing_first_pages", shown_pages=shown_pages, page_count=page_count),
                    )
                    self.pdf_pages_sizer.Add(note, 0, wx.ALIGN_CENTER | wx.ALL, 3)
            except Exception as exc:
                self.preview_text.SetValue(tr("unable_preview_pdf", exc=exc))
                self.preview_text.Show(True)
                self.pdf_pages_panel.Hide()
                self.filePreview.Layout()
                return

        self.preview_text.Show(False)
        self.pdf_pages_panel.Show(True)
        self.pdf_pages_panel.SetVirtualSize((1, 1))
        self.pdf_pages_panel.Layout()
        self.filePreview.Layout()

    def show_file_preview(self, path):
        self.current_preview_path = path
        self.selected_pdf_page_panel = None
        self.update_rotate_page_buttons_state()
        self.preview_text.Show(False)
        self.pdf_pages_panel.Hide()
        self.pdf_preview.Hide()

        if not path:
            self.preview_text.SetValue(tr("preview_select_file"))
            self.preview_text.Show(True)
            self.filePreview.Layout()
            return

        if os.path.isdir(path):
            self.preview_text.SetValue(tr("folder_selected", path=path))
            self.preview_text.Show(True)
            self.filePreview.Layout()
            return

        if not os.path.isfile(path):
            self.preview_text.SetValue(tr("no_preview_available"))
            self.preview_text.Show(True)
            self.filePreview.Layout()
            return

        if is_pdf_file(path):
            self.show_pdf_feed(path)
            return

        try:
            with open(path, "r", encoding="utf-8") as handle:
                content = handle.read(12000)
        except UnicodeDecodeError:
            try:
                with open(path, "r", encoding="latin-1") as handle:
                    content = handle.read(12000)
            except Exception as exc:
                self.preview_text.SetValue(tr("unable_preview_file", exc=exc))
                self.preview_text.Show(True)
                self.filePreview.Layout()
                return
        except Exception as exc:
            self.preview_text.SetValue(tr("unable_preview_file", exc=exc))
            self.preview_text.Show(True)
            self.filePreview.Layout()
            return

        if not content.strip():
            self.preview_text.SetValue(tr("empty_file"))
            self.preview_text.Show(True)
            self.filePreview.Layout()
            return

        if len(content) >= 12000:
            content = content[:12000] + tr("preview_truncated_suffix")

        self.preview_text.SetValue(content)
        self.preview_text.Show(True)
        self.filePreview.Layout()

    # ---------------- CONTEXT MENU ----------------
    def on_preview_edit(self, event):
        if not self.current_preview_path or not os.path.isfile(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            os.startfile(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_delete(self, event):
        if not self.current_preview_path or not os.path.isfile(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        dialog = wx.MessageDialog(
            self,
            tr("confirm_delete", path=self.current_preview_path),
            tr("preview_delete_button"),
            wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
        )
        if dialog.ShowModal() == wx.ID_YES:
            try:
                os.remove(self.current_preview_path)
                self.show_file_preview(None)
                self.load_folder(self.path_box.GetValue())
            except Exception as exc:
                wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)
        dialog.Destroy()

    def on_preview_zoom_in(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        with self.busy_cursor():
            self.pdf_preview_zoom = min(self.pdf_preview_zoom * 1.25, 3.0)
            self.show_pdf_feed(self.current_preview_path)

    def on_preview_zoom_out(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        with self.busy_cursor():
            self.pdf_preview_zoom = max(self.pdf_preview_zoom / 1.25, 0.4)
            self.show_pdf_feed(self.current_preview_path)

    def on_preview_rotate(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                rotate_pdf(self.current_preview_path, 90)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_rotate_all_left(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                rotate_pdf(self.current_preview_path, -90)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_rotate_left(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        page_index = self.get_selected_pdf_page_index()
        if page_index is None:
            wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                rotate_pdf_page(self.current_preview_path, page_index, -90)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_rotate_right(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        page_index = self.get_selected_pdf_page_index()
        if page_index is None:
            wx.MessageBox(tr("select_pdf_page"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                rotate_pdf_page(self.current_preview_path, page_index, 90)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_rotate_all_right(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                rotate_pdf(self.current_preview_path, 90)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_optimize(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                optimize_pdf(self.current_preview_path)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_preview_ajust_page_width(self, event):
        if not is_pdf_file(self.current_preview_path):
            wx.MessageBox(tr("no_preview_available"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
            return
        try:
            with self.busy_cursor():
                ajust_page_width(self.current_preview_path)
                self.show_pdf_feed(self.current_preview_path)
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), wx.OK | wx.ICON_ERROR)

    def on_right_click(self, event):
        menu = wx.Menu()

        open_item = menu.Append(-1, tr("context_open"))
        rename_item = menu.Append(-1, tr("context_rename"))
        delete_item = menu.Append(-1, tr("context_delete"))

        self.PopupMenu(menu)
        menu.Destroy()

    def on_preview_right_click(self, event):
        menu = wx.Menu()

        def set_menu_icon(item, art_id=None, bitmap=None):
            if bitmap is None:
                bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
            if bitmap.IsOk():
                item.SetBitmap(bitmap)

        edit_item = menu.Append(-1, tr("preview_edit_button"))
        set_menu_icon(edit_item, wx.ART_FIND)
        delete_item = menu.Append(-1, tr("preview_delete_button"))
        set_menu_icon(delete_item, wx.ART_DELETE)
        menu.AppendSeparator()
        zoom_in_item = menu.Append(-1, tr("preview_zoom_in_button"))
        set_menu_icon(zoom_in_item, wx.ART_PLUS)
        zoom_out_item = menu.Append(-1, tr("preview_zoom_out_button"))
        set_menu_icon(zoom_out_item, wx.ART_MINUS)
        menu.AppendSeparator()
        rotate_all_left_item = menu.Append(-1, tr("preview_rotate_all_left_button"))
        joined_menu_undo = self.create_joined_art_bitmap(wx.ART_UNDO, client=wx.ART_MENU, size=(16, 16))
        set_menu_icon(rotate_all_left_item, bitmap=joined_menu_undo)
        rotate_left_item = menu.Append(-1, tr("preview_rotate_left_button"))
        set_menu_icon(rotate_left_item, wx.ART_UNDO)
        rotate_right_item = menu.Append(-1, tr("preview_rotate_right_button"))
        set_menu_icon(rotate_right_item, wx.ART_REDO)
        rotate_all_right_item = menu.Append(-1, tr("preview_rotate_all_right_button"))
        joined_menu_redo = self.create_joined_art_bitmap(wx.ART_REDO, client=wx.ART_MENU, size=(16, 16))
        set_menu_icon(rotate_all_right_item, bitmap=joined_menu_redo)
        menu.AppendSeparator()
        optimize_item = menu.Append(-1, tr("preview_optimize_button"))
        set_menu_icon(optimize_item, wx.ART_TICK_MARK)
        ajust_page_width_item = menu.Append(-1, tr("preview_ajust_page_width_button"))
        set_menu_icon(ajust_page_width_item, wx.ART_REPORT_VIEW)

        self.Bind(wx.EVT_MENU, self.on_preview_edit, edit_item)
        self.Bind(wx.EVT_MENU, self.on_preview_delete, delete_item)
        self.Bind(wx.EVT_MENU, self.on_preview_zoom_in, zoom_in_item)
        self.Bind(wx.EVT_MENU, self.on_preview_zoom_out, zoom_out_item)
        self.Bind(wx.EVT_MENU, self.on_preview_rotate_all_left, rotate_all_left_item)
        self.Bind(wx.EVT_MENU, self.on_preview_rotate_left, rotate_left_item)
        self.Bind(wx.EVT_MENU, self.on_preview_rotate_right, rotate_right_item)
        self.Bind(wx.EVT_MENU, self.on_preview_rotate_all_right, rotate_all_right_item)
        self.Bind(wx.EVT_MENU, self.on_preview_optimize, optimize_item)
        self.Bind(wx.EVT_MENU, self.on_preview_ajust_page_width, ajust_page_width_item)

        popup_window = self.filePreview
        if event is not None:
            try:
                obj = event.GetEventObject()
                if isinstance(obj, wx.Window):
                    popup_window = obj
            except Exception:
                pass

        popup_window.PopupMenu(menu)
        menu.Destroy()

    # ---------------- EVENTS ----------------
    def bind_events(self):
        self.back_btn.Bind(wx.EVT_BUTTON, self.go_back)
        self.forward_btn.Bind(wx.EVT_BUTTON, self.go_forward)

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

        self.preview_edit_btn.Bind(wx.EVT_BUTTON, self.on_preview_edit)
        self.preview_delete_btn.Bind(wx.EVT_BUTTON, self.on_preview_delete)
        self.preview_zoom_in_btn.Bind(wx.EVT_BUTTON, self.on_preview_zoom_in)
        self.preview_zoom_out_btn.Bind(wx.EVT_BUTTON, self.on_preview_zoom_out)
        self.preview_rotate_all_left_btn.Bind(wx.EVT_BUTTON, self.on_preview_rotate_all_left)
        self.preview_rotate_left_btn.Bind(wx.EVT_BUTTON, self.on_preview_rotate_left)
        self.preview_rotate_right_btn.Bind(wx.EVT_BUTTON, self.on_preview_rotate_right)
        self.preview_rotate_all_right_btn.Bind(wx.EVT_BUTTON, self.on_preview_rotate_all_right)
        self.preview_optimize_btn.Bind(wx.EVT_BUTTON, self.on_preview_optimize)
        self.preview_ajust_page_width_btn.Bind(wx.EVT_BUTTON, self.on_preview_ajust_page_width)

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
        self.show_file_preview(path)

    def on_open_item(self, event):
        name = event.GetText()
        path = os.path.join(self.path_box.GetValue(), name)

        if os.path.isdir(path):
            self.open_path(path)

    def on_path_enter(self, event):
        self.open_path(self.path_box.GetValue())

    def on_toggle_hidden(self, event):
        self.show_hidden = self.hidden_chk.GetValue()
        self.refresh()

    def refresh(self):
        self.load_folder(self.path_box.GetValue())


if __name__ == "__main__":
    app = wx.App(False)
    frame = FileExplorer()
    frame.Show()
    app.MainLoop()