import os
import shutil
import sys

import wx

from localization import tr
from file_operations.pdf_utils import get_pdf_page_count, is_pdf_file, move_pdf_page
import file_operations.copy_and_paste as copy_and_paste

if not hasattr(wx, "DATADOBJECT_PREFERRED"):
    wx.DATADOBJECT_PREFERRED = 0

INTERNAL_DRAG_MARKER = "pdfexplorer_internal_move"


class BaseFileSystemDropTarget(wx.DropTarget):
    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.file_data = wx.FileDataObject()
        self.text_data = wx.TextDataObject()
        self.data_object = None

        if hasattr(wx, "DataObjectComposite"):
            self.data_object = wx.DataObjectComposite()
            if hasattr(wx, "DATADOBJECT_PREFERRED"):
                self.data_object.Add(self.text_data, wx.DATADOBJECT_PREFERRED)
            else:
                self.data_object.Add(self.text_data)
            self.data_object.Add(self.file_data)
            self.SetDataObject(self.data_object)
        else:
            self.SetDataObject(self.file_data)

    def _resolve_drop_helpers(self):
        compat_module = sys.modules.get("controls.filelist")
        build_helper = getattr(compat_module, "_build_non_conflicting_path", None)
        refresh_helper = getattr(compat_module, "_refresh_after_fs_change", None)
        if build_helper is None:
            build_helper = _build_non_conflicting_path
        if refresh_helper is None:
            refresh_helper = _refresh_after_fs_change
        return build_helper, refresh_helper

    def _resolve_drop_target_dir(self, x, y):
        raise NotImplementedError

    def _apply_drop(self, target_dir, filenames, move_files):
        build_non_conflicting_path, refresh_after_fs_change = self._resolve_drop_helpers()
        errors = []
        affected_dirs = [target_dir]
        seen_dirs = {os.path.normcase(os.path.normpath(target_dir))} if isinstance(target_dir, str) and target_dir else set()

        for source_path in filenames:
            if not isinstance(source_path, str) or not source_path:
                continue

            source_name = os.path.basename(source_path.rstrip("\\/"))
            destination_path = os.path.join(target_dir, source_name)
            overwrite_target = False

            if os.path.exists(destination_path):
                overwrite_choice = copy_and_paste._confirm_overwrite_existing_path(self.owner, destination_path)
                if overwrite_choice is None:
                    continue
                if overwrite_choice is False:
                    destination_path = build_non_conflicting_path(destination_path)
                else:
                    overwrite_target = True

            if move_files:
                source_parent = os.path.dirname(source_path)
                if isinstance(source_parent, str) and source_parent and os.path.isdir(source_parent):
                    normalized = os.path.normcase(os.path.normpath(source_parent))
                    if normalized not in seen_dirs:
                        affected_dirs.append(source_parent)
                        seen_dirs.add(normalized)

            try:
                if move_files:
                    if overwrite_target and os.path.exists(destination_path):
                        if os.path.isdir(destination_path):
                            shutil.rmtree(destination_path)
                        else:
                            os.remove(destination_path)
                    shutil.move(source_path, destination_path)
                elif os.path.isdir(source_path):
                    if overwrite_target and os.path.exists(destination_path):
                        shutil.rmtree(destination_path)
                    shutil.copytree(source_path, destination_path)
                else:
                    if overwrite_target and os.path.exists(destination_path):
                        os.remove(destination_path)
                    shutil.copy2(source_path, destination_path)
            except Exception as exc:
                errors.append(f"{source_path}: {exc}")

        if errors:
            wx.MessageBox("\n".join(errors), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        else:
            refresh_after_fs_change(self.owner, affected_dirs=affected_dirs)

        return True

    def _read_drag_payload(self):
        internal_marker = None
        filenames = []

        if hasattr(self, "text_data"):
            try:
                payload = self.text_data.GetText()
            except Exception:
                payload = ""
            if isinstance(payload, str) and payload.startswith(INTERNAL_DRAG_MARKER + "\n"):
                parts = payload.split("\n", 1)
                if len(parts) == 2:
                    internal_marker = parts[0]
                    filenames = [item for item in parts[1].split("\n") if item]

        if not filenames and hasattr(self.file_data, "GetFilenames"):
            filenames = list(self.file_data.GetFilenames())

        return internal_marker, filenames

    def OnDrop(self, x, y):
        if not self.GetData():
            return False

        internal_marker, filenames = self._read_drag_payload()
        if not filenames:
            return False

        target_dir = self._resolve_drop_target_dir(x, y)
        if not isinstance(target_dir, str) or not os.path.isdir(target_dir):
            return False

        move_files = internal_marker == INTERNAL_DRAG_MARKER
        self._apply_drop(target_dir, filenames, move_files)
        return True

    def OnData(self, x, y, default):
        if not self.GetData():
            return default

        internal_marker, filenames = self._read_drag_payload()
        if not filenames:
            return default

        target_dir = self._resolve_drop_target_dir(x, y)
        if not isinstance(target_dir, str) or not os.path.isdir(target_dir):
            return default

        move_files = internal_marker == INTERNAL_DRAG_MARKER
        return wx.DragMove if move_files else wx.DragCopy

    def OnDropFiles(self, x, y, filenames):
        if not filenames:
            return False

        target_dir = self._resolve_drop_target_dir(x, y)
        if not isinstance(target_dir, str) or not os.path.isdir(target_dir):
            return False

        self._apply_drop(target_dir, filenames, move_files=False)
        return True


class FileListDropTarget(BaseFileSystemDropTarget):
    def _resolve_drop_target_dir(self, x, y):
        if hasattr(self.owner, "list") and self.owner.list is not None:
            try:
                hit_index, _ = self.owner.list.HitTest((x, y))
            except Exception:
                hit_index = wx.NOT_FOUND
            if hit_index != wx.NOT_FOUND and hasattr(self.owner.list, "GetItemText"):
                try:
                    item_name = self.owner.list.GetItemText(hit_index)
                except Exception:
                    item_name = ""
                if isinstance(item_name, str) and item_name:
                    current_dir = self.owner.path_box.GetValue() if hasattr(self.owner, "path_box") else ""
                    candidate_dir = os.path.join(current_dir, item_name) if isinstance(current_dir, str) else ""
                    if isinstance(candidate_dir, str) and os.path.isdir(candidate_dir):
                        return candidate_dir

        if hasattr(self.owner, "path_box"):
            target_dir = self.owner.path_box.GetValue()
            if isinstance(target_dir, str) and os.path.isdir(target_dir):
                return target_dir
        return None


class TreeDropTarget(BaseFileSystemDropTarget):
    def _resolve_drop_target_dir(self, x, y):
        if hasattr(self.owner, "tree") and self.owner.tree is not None:
            try:
                item, _ = self.owner.tree.HitTest((x, y))
            except Exception:
                item = None
            if item is not None and getattr(item, "IsOk", lambda: False)():
                item_path = self.owner.tree.GetItemData(item)
                if isinstance(item_path, str) and os.path.isdir(item_path):
                    return item_path

        if hasattr(self.owner, "path_box"):
            target_dir = self.owner.path_box.GetValue()
            if isinstance(target_dir, str) and os.path.isdir(target_dir):
                return target_dir
        return None


_build_non_conflicting_path = __import__("file_operations.copy_and_paste", fromlist=["_build_non_conflicting_path"])._build_non_conflicting_path


def _refresh_after_fs_change(owner, affected_dirs=None, preferred_preview_path=None):
    compat_module = sys.modules.get("controls.filelist")
    compat_helper = getattr(compat_module, "_refresh_after_fs_change", None)
    if compat_helper is not None and compat_helper is not _refresh_after_fs_change:
        return compat_helper(owner, affected_dirs=affected_dirs, preferred_preview_path=preferred_preview_path)

    if hasattr(owner, "path_box"):
        current_folder = owner.path_box.GetValue() if hasattr(owner.path_box, "GetValue") else ""
        if isinstance(current_folder, str) and current_folder and os.path.isdir(current_folder):
            if hasattr(owner, "load_folder"):
                owner.load_folder(current_folder)

    if preferred_preview_path and os.path.isfile(preferred_preview_path):
        if hasattr(owner, "current_preview_path"):
            owner.current_preview_path = preferred_preview_path
        if hasattr(owner, "show_file_preview"):
            owner.show_file_preview(preferred_preview_path)

    if affected_dirs is not None:
        for folder in affected_dirs:
            if isinstance(folder, str) and folder and hasattr(owner, "load_folder"):
                try:
                    owner.load_folder(folder)
                except Exception:
                    pass


def on_list_begin_drag(owner, event):
    list_ctrl = getattr(owner, "list", None)
    if list_ctrl is None:
        return

    current_folder = ""
    path_box = getattr(owner, "path_box", None)
    if path_box is not None and hasattr(path_box, "GetValue"):
        current_folder = path_box.GetValue() or ""

    selected_paths = []
    index = list_ctrl.GetFirstSelected()
    while index != wx.NOT_FOUND:
        name = list_ctrl.GetItemText(index)
        if isinstance(name, str):
            selected_paths.append(os.path.join(current_folder, name))
        index = list_ctrl.GetNextSelected(index)

    file_paths = [path for path in selected_paths if path and os.path.exists(path)]
    if not file_paths:
        return

    file_data = wx.FileDataObject()
    for path in file_paths:
        file_data.AddFile(path)

    drag_source = wx.DropSource(list_ctrl)
    drag_source.SetData(file_data)
    drag_source.DoDragDrop(wx.Drag_AllowMove)


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
                owner_drop_handler = getattr(self.owner, "handle_pdf_page_drop", None)
                if callable(owner_drop_handler):
                    owner_drop_handler(self.page_index, self.data.GetText(), insert_before=insert_before)
                else:
                    handle_pdf_page_drop(self.owner, self.page_index, self.data.GetText(), insert_before=insert_before)
        except Exception:
            pass
        return wx.DragCopy


def create_drag_overlay(owner):
    if owner.drag_overlay is None:
        owner.drag_overlay = wx.PopupWindow(owner, style=wx.BORDER_SIMPLE)
        panel = wx.Panel(owner.drag_overlay)
        panel.SetBackgroundColour(wx.Colour(255, 255, 255))
        owner.drag_overlay_text = wx.StaticText(panel, label="")
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(owner.drag_overlay_text, 0, wx.ALL, 5)
        panel.SetSizer(sizer)
        panel.Fit()
        owner.drag_overlay.SetSize(panel.GetSize())
    return owner.drag_overlay


def show_drag_overlay(owner, page_index, page_panel, x, y):
    overlay = create_drag_overlay(owner)
    owner.drag_overlay_text.SetLabel(tr("drop_overlay_label", page_index=page_index + 1))
    overlay.Fit()
    position = page_panel.ClientToScreen(wx.Point(x, y))
    overlay.Move(position + wx.Point(16, 16))
    overlay.Show(True)
    overlay.Raise()


def hide_drag_overlay(owner):
    if owner.drag_overlay is not None:
        owner.drag_overlay.Hide()
    if getattr(owner, "drop_frame", None) is not None:
        owner.drop_frame.Hide()
    try:
        if getattr(owner, "_highlighted_panel", None) is not None:
            panel = owner._highlighted_panel
            if getattr(panel, "_orig_bg", None) is not None:
                panel.SetBackgroundColour(panel._orig_bg)
            panel.Refresh()
            owner._highlighted_panel = None
    except Exception:
        pass


def create_drop_frame(owner):
    if getattr(owner, "drop_frame", None) is None:
        owner.drop_frame = wx.PopupWindow(owner, style=wx.BORDER_NONE)
        panel = wx.Panel(owner.drop_frame)
        panel.SetBackgroundColour(wx.Colour(0, 120, 215))
        owner.drop_frame.SetBackgroundColour(wx.Colour(0, 120, 215))
        panel.SetSize((10, 4))
    return owner.drop_frame


def show_drop_frame(owner, page_index, page_panel, x, y):
    frame = create_drop_frame(owner)
    size = page_panel.GetSize()
    half_y = size.y // 2
    insert_before = y < half_y
    width = max(20, size.x - 6)
    height = 4
    frame.SetSize((width, height))

    if insert_before:
        screen_pos = page_panel.ClientToScreen(wx.Point(3, 0))
        frame.Move(screen_pos + wx.Point(0, -2))
        overlay = create_drag_overlay(owner)
        owner.drag_overlay_text.SetLabel(tr("insert_before"))
        overlay.Fit()
    else:
        screen_pos = page_panel.ClientToScreen(wx.Point(3, size.y))
        frame.Move(screen_pos + wx.Point(0, -2))
        overlay = create_drag_overlay(owner)
        owner.drag_overlay_text.SetLabel(tr("insert_after"))
        overlay.Fit()

    try:
        if getattr(page_panel, "_orig_bg", None) is None:
            page_panel._orig_bg = page_panel.GetBackgroundColour()
        page_panel.SetBackgroundColour(wx.Colour(230, 245, 255))
        page_panel.Refresh()
        owner._highlighted_panel = page_panel
    except Exception:
        pass
    frame.Show(True)


def hide_drop_frame(owner):
    if getattr(owner, "drop_frame", None) is not None:
        owner.drop_frame.Hide()


def _get_page_panel_from_event(event):
    obj = event.GetEventObject()
    while obj is not None and not hasattr(obj, "page_index"):
        obj = obj.GetParent()
    return obj


def on_pdf_page_drag_motion(owner, event):
    if not event.Dragging() or not event.LeftIsDown():
        return

    get_page_panel = getattr(owner, "get_pdf_page_panel_from_event", None)
    if callable(get_page_panel):
        page_panel = get_page_panel(event)
    else:
        page_panel = _get_page_panel_from_event(event)

    if page_panel is None or page_panel is not getattr(owner, "_pdf_drag_start_panel", None):
        return

    start_pos = getattr(owner, "_pdf_drag_start_pos", None)
    if start_pos is None:
        return

    current_pos = event.GetPosition()
    if abs(current_pos.x - start_pos.x) < 5 and abs(current_pos.y - start_pos.y) < 5:
        return

    owner._pdf_drag_start_pos = None
    start_pdf_page_drag(owner, page_panel)


def start_pdf_page_drag(owner, page_panel):
    page_index = getattr(page_panel, "page_index", None)
    if page_index is None:
        return

    payload = f"{owner.current_pdf_path}\n{page_index}"
    data = wx.TextDataObject(payload)
    source = wx.DropSource(page_panel)
    source.SetData(data)
    source.DoDragDrop(wx.Drag_AllowMove)


def handle_pdf_page_drop(owner, target_index, payload, insert_before=True):
    try:
        with owner.busy_cursor():
            source_path, source_index = payload.split("\n", 1)
            source_index = int(source_index)
            if not is_pdf_file(source_path) or not is_pdf_file(owner.current_pdf_path):
                return
            if source_path != owner.current_pdf_path:
                return

            try:
                page_count = get_pdf_page_count(owner.current_pdf_path)
            except Exception:
                page_count = None

            if page_count is None:
                return

            if source_index == target_index:
                return

            if source_index < target_index and insert_before:
                target_index -= 1

            if source_index < target_index and not insert_before:
                target_index -= 1

            try:
                move_pdf_page(owner.current_pdf_path, source_index, target_index)
            except Exception:
                pass
    except Exception:
        pass
