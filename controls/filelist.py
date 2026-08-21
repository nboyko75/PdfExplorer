import os
import shutil

import wx

from localization import tr
from file_operations.pdf_utils import discard_pdf_changes, is_pdf_file
from file_operations.office_preview import is_office_file_open
import file_operations.copy_and_paste as copy_and_paste
import file_operations.image_utils as image_utils
import controls.file_preview as file_preview
import controls.drag_and_drop as drag_and_drop
from controls.window_tools import load_settings, update_settings


class FileListDropTarget(drag_and_drop.FileListDropTarget):
    def OnDropFiles(self, x, y, filenames):
        if not filenames:
            return False

        if not hasattr(self.owner, "path_box"):
            return False

        target_dir = self.owner.path_box.GetValue()
        if not isinstance(target_dir, str) or not os.path.isdir(target_dir):
            return False

        errors = []
        for source_path in filenames:
            if not isinstance(source_path, str) or not source_path:
                continue

            source_name = os.path.basename(source_path.rstrip("\\/"))
            destination_path = os.path.join(target_dir, source_name)
            if os.path.exists(destination_path):
                destination_path = _build_non_conflicting_path(destination_path)

            try:
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, destination_path)
                else:
                    shutil.copy2(source_path, destination_path)
            except Exception as exc:
                errors.append(f"{source_path}: {exc}")

        if errors:
            wx.MessageBox("\n".join(errors), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        else:
            _refresh_after_fs_change(self.owner, affected_dirs=[target_dir])

        return True


CLIPBOARD_MODE_COPY = copy_and_paste.CLIPBOARD_MODE_COPY
CLIPBOARD_MODE_CUT = copy_and_paste.CLIPBOARD_MODE_CUT


def _set_clipboard(owner, paths, mode):
    return copy_and_paste._set_clipboard(owner, paths, mode, update_list_toolbar_buttons)


def _get_clipboard_paths(owner):
    return copy_and_paste._get_clipboard_paths(owner)


def _get_clipboard_mode(owner):
    return copy_and_paste._get_clipboard_mode(owner)


def _can_paste_into_directory(owner, target_dir):
    return copy_and_paste._can_paste_into_directory(owner, target_dir)


def _unique_preserving_order(paths):
    return copy_and_paste._unique_preserving_order(paths)


def _confirm_overwrite_existing_path(owner, target_path):
    return copy_and_paste._confirm_overwrite_existing_path(owner, target_path)


def _build_non_conflicting_path(target_path):
    return copy_and_paste._build_non_conflicting_path(target_path)


def _resolve_tree_selection_path(owner):
    return copy_and_paste._resolve_tree_selection_path(owner)


def _resolve_paste_target_directory(path):
    return copy_and_paste._resolve_paste_target_directory(path)


def save_list_view_state(owner):
    if not hasattr(owner, "list") or owner.list is None:
        return

    column_widths = [int(owner.list.GetColumnWidth(index)) for index in range(owner.list.GetColumnCount())]

    sort_column = getattr(owner, "list_sort_column", None)
    if not isinstance(sort_column, int) or not 0 <= sort_column < owner.list.GetColumnCount():
        sort_column = None

    sort_direction = int(getattr(owner, "list_sort_direction", 0) or 0)
    if sort_direction not in (-1, 1):
        sort_direction = 0

    update_settings(
        {
            "list_column_widths": column_widths,
            "list_sort_column": sort_column,
            "list_sort_direction": sort_direction,
        }
    )


def restore_list_view_state(owner, settings=None):
    if not hasattr(owner, "list") or owner.list is None:
        return

    if settings is None:
        settings = load_settings()

    column_widths = settings.get("list_column_widths")
    if isinstance(column_widths, list):
        for index, width in enumerate(column_widths[: owner.list.GetColumnCount()]):
            if isinstance(width, (int, float)) and int(width) > 16:
                owner.list.SetColumnWidth(index, int(width))

    sort_column = settings.get("list_sort_column")
    sort_direction = settings.get("list_sort_direction")

    if isinstance(sort_column, int) and 0 <= sort_column < owner.list.GetColumnCount():
        owner.list_sort_column = sort_column
    else:
        owner.list_sort_column = None

    if owner.list_sort_column is not None and int(sort_direction or 0) in (-1, 1):
        owner.list_sort_direction = int(sort_direction)
    else:
        owner.list_sort_direction = 0

    update_list_sort_header_icons(owner)


def build_list_panel(owner, parent_splitter):
    owner.list_host_panel = wx.Panel(parent_splitter)
    owner.list_toolbar = wx.BoxSizer(wx.HORIZONTAL)

    list_btn_icon_size = (16, 16)
    list_btn_size = (24, 24)
    owner.list_scan_btn = image_utils.create_bitmap_button2(
        owner.list_host_panel,
        owner.icon_manager,
        "scan",
        tr("scan"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_open_btn = image_utils.create_bitmap_button2(
        owner.list_host_panel,
        owner.icon_manager,
        "file_view",
        tr("context_open"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_rename_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_EDIT,
        tr("context_rename"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_new_folder_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_FOLDER,
        tr("context_new_folder"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_copy_btn = image_utils.create_bitmap_button2(
        owner.list_host_panel,
        owner.icon_manager,
        "copy",
        tr("context_copy"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_cut_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_CUT,
        tr("context_cut"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_paste_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_PASTE,
        tr("context_paste"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_delete_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_DELETE,
        tr("context_delete"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.filter_label = wx.StaticText(owner.list_host_panel, label=tr("filter_label"))
    owner.search_box = wx.TextCtrl(owner.list_host_panel, style=wx.TE_PROCESS_ENTER)
    owner.search_box.SetHint(tr("search_hint"))

    owner.list_toolbar.Add(owner.list_scan_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_open_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_rename_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_new_folder_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_copy_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_cut_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_paste_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_delete_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.filter_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    owner.list_toolbar.Add(owner.search_box, 0, wx.ALIGN_CENTER_VERTICAL)

    owner.list = wx.ListCtrl(owner.list_host_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
    owner.list.SetDropTarget(FileListDropTarget(owner))
    owner.list.InsertColumn(0, tr("name_column"), width=450)
    owner.list.InsertColumn(1, tr("type_column"), width=120)
    owner.list.InsertColumn(2, tr("size_column"), width=120)
    owner.list.InsertColumn(3, tr("modified_column"), width=180)
    image_utils.init_list_images(owner)

    list_host_sizer = wx.BoxSizer(wx.VERTICAL)
    list_host_sizer.Add(owner.list_toolbar, 0, wx.EXPAND | wx.ALL, 4)
    list_host_sizer.Add(owner.list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
    owner.list_host_panel.SetSizer(list_host_sizer)

    update_list_toolbar_buttons(owner)


def bind_list_events(owner):
    owner.list.Bind(wx.EVT_LIST_ITEM_SELECTED, owner.on_list_select)
    owner.list.Bind(wx.EVT_LIST_ITEM_DESELECTED, owner.on_list_deselect)
    owner.list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, owner.on_open_item)
    owner.list.Bind(wx.EVT_RIGHT_DOWN, owner.on_right_click)
    owner.list.Bind(wx.EVT_LIST_COL_CLICK, owner.on_list_column_click)
    owner.list.Bind(wx.EVT_LIST_BEGIN_DRAG, owner.on_list_begin_drag)

    owner.list_scan_btn.Bind(wx.EVT_BUTTON, owner.on_list_scan)
    owner.list_open_btn.Bind(wx.EVT_BUTTON, owner.on_list_open)
    owner.list_rename_btn.Bind(wx.EVT_BUTTON, owner.on_list_rename)
    owner.list_new_folder_btn.Bind(wx.EVT_BUTTON, owner.on_list_new_folder)
    owner.list_copy_btn.Bind(wx.EVT_BUTTON, owner.on_list_copy)
    owner.list_cut_btn.Bind(wx.EVT_BUTTON, owner.on_list_cut)
    owner.list_paste_btn.Bind(wx.EVT_BUTTON, owner.on_list_paste)
    owner.list_delete_btn.Bind(wx.EVT_BUTTON, owner.on_list_delete)


def _get_sort_header_image_index(owner, direction):
    list_images = getattr(owner, "list_images", None)
    icon_cache = getattr(owner, "list_icon_cache", None)
    if list_images is None or icon_cache is None:
        return -1

    cache_key = "__sort_up__" if direction > 0 else "__sort_down__"
    cached_index = icon_cache.get(cache_key)
    if cached_index is not None:
        return cached_index

    art_id = wx.ART_GO_UP if direction > 0 else wx.ART_GO_DOWN
    bitmap = wx.ArtProvider.GetBitmap(art_id, wx.ART_MENU, (16, 16))
    if bitmap is None or not bitmap.IsOk():
        return -1

    icon_cache[cache_key] = list_images.Add(bitmap)
    return icon_cache[cache_key]


def update_list_sort_header_icons(owner):
    sort_column = getattr(owner, "list_sort_column", None)
    sort_direction = int(getattr(owner, "list_sort_direction", 0) or 0)
    sort_image_index = (
        _get_sort_header_image_index(owner, sort_direction)
        if sort_column is not None and sort_direction in (-1, 1)
        else -1
    )

    for index in range(owner.list.GetColumnCount()):
        column = owner.list.GetColumn(index)
        column.SetMask(wx.LIST_MASK_TEXT | wx.LIST_MASK_IMAGE)
        if hasattr(column, "SetImage"):
            column.SetImage(-1)

        if index == sort_column and sort_image_index >= 0:
            if hasattr(column, "SetImage"):
                column.SetImage(sort_image_index)

        owner.list.SetColumn(index, column)


def update_list_toolbar_buttons(owner):
    if not hasattr(owner, "list") or owner.list is None:
        return

    selected_paths = get_selected_list_paths(owner)
    has_selection = bool(selected_paths)
    has_single_selection = len(selected_paths) == 1
    has_single_existing_item = has_single_selection and os.path.exists(selected_paths[0])
    current_folder = owner.path_box.GetValue()

    button = getattr(owner, "list_open_btn", None)
    if button is not None:
        button.Enable(has_single_existing_item)

    button = getattr(owner, "list_rename_btn", None)
    if button is not None:
        button.Enable(has_single_existing_item)

    button = getattr(owner, "list_new_folder_btn", None)
    if button is not None:
        button.Enable(os.path.isdir(current_folder))

    for button_name in ("list_copy_btn", "list_cut_btn", "list_delete_btn"):
        button = getattr(owner, button_name, None)
        if button is not None:
            button.Enable(has_selection)

    button = getattr(owner, "list_paste_btn", None)
    if button is not None:
        button.Enable(_can_paste_into_directory(owner, current_folder))


def refresh_list_item_size(owner, path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False

    current_folder = os.path.normpath(owner.path_box.GetValue())
    item_folder = os.path.normpath(os.path.dirname(path))
    if current_folder != item_folder:
        return False

    target_name = os.path.basename(path)
    try:
        size_text = f"{os.path.getsize(path)//1024} {tr('file_size_unit_kb')}"
    except Exception:
        size_text = ""

    for index in range(owner.list.GetItemCount()):
        if owner.list.GetItemText(index) == target_name:
            owner.list.SetItem(index, 2, size_text)
            return True

    return False


def select_list_item_by_path(owner, path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return False

    current_folder = os.path.normpath(owner.path_box.GetValue())
    item_folder = os.path.normpath(os.path.dirname(path))
    if current_folder != item_folder:
        return False

    target_name = os.path.basename(path)

    owner._restoring_list_selection = True
    try:
        for index in range(owner.list.GetItemCount()):
            owner.list.SetItemState(index, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)

        for index in range(owner.list.GetItemCount()):
            if owner.list.GetItemText(index) != target_name:
                continue

            owner.list.SetItemState(
                index,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
            )
            owner.list.EnsureVisible(index)
            update_list_toolbar_buttons(owner)
            return True
    finally:
        owner._restoring_list_selection = False

    update_list_toolbar_buttons(owner)
    return False


def on_list_select(owner, event):
    if getattr(owner, "_restoring_list_selection", False):
        update_list_toolbar_buttons(owner)
        return

    index = event.GetIndex()
    name = owner.list.GetItemText(index)
    path = os.path.join(owner.path_box.GetValue(), name)

    previous_path = owner.current_preview_path
    if not file_preview.confirm_preview_change(owner, path):
        wx.CallAfter(file_preview.restore_list_selection, owner, previous_path)
        wx.CallAfter(update_list_toolbar_buttons, owner)
        return

    file_preview.show_file_preview(owner, path)
    update_list_toolbar_buttons(owner)


def on_list_deselect(owner, _):
    update_list_toolbar_buttons(owner)


def on_right_click(owner, event):
    hit_index, _ = owner.list.HitTest(event.GetPosition())
    if hit_index != wx.NOT_FOUND:
        item_state = owner.list.GetItemState(hit_index, wx.LIST_STATE_SELECTED)
        if not item_state:
            owner._restoring_list_selection = True
            try:
                for index in range(owner.list.GetItemCount()):
                    owner.list.SetItemState(index, 0, wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED)
                owner.list.SetItemState(
                    hit_index,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                    wx.LIST_STATE_SELECTED | wx.LIST_STATE_FOCUSED,
                )
            finally:
                owner._restoring_list_selection = False

    menu = wx.Menu()

    scan_item = menu.Append(-1, tr("scan"))
    open_item = menu.Append(-1, tr("context_open"))
    rename_item = menu.Append(-1, tr("context_rename"))
    new_folder_item = menu.Append(-1, tr("context_new_folder"))
    menu.AppendSeparator()
    copy_item = menu.Append(-1, f"{tr('context_copy')}\tCtrl+C")
    cut_item = menu.Append(-1, f"{tr('context_cut')}\tCtrl+X")
    paste_item = menu.Append(-1, f"{tr('context_paste')}\tCtrl+V")
    delete_item = menu.Append(-1, f"{tr('context_delete')}\tCtrl+D")

    icon_manager = getattr(owner, "icon_manager", None)
    if icon_manager:
        icon_manager.set_menu_icon2(scan_item, "scan")
        icon_manager.set_menu_icon2(open_item, "file_view")
        icon_manager.set_menu_icon(rename_item, art_id=wx.ART_EDIT)
        icon_manager.set_menu_icon(new_folder_item, art_id=wx.ART_FOLDER)
        icon_manager.set_menu_icon2(copy_item, "copy")
        icon_manager.set_menu_icon(cut_item, art_id=wx.ART_CUT)
        icon_manager.set_menu_icon(paste_item, art_id=wx.ART_PASTE)
        icon_manager.set_menu_icon(delete_item, art_id=wx.ART_DELETE)

    selected_paths = get_selected_list_paths(owner)
    can_act_on_selection = bool(selected_paths)
    can_act_on_single_selection = len(selected_paths) == 1 and os.path.exists(selected_paths[0])
    can_create_in_current_folder = os.path.isdir(owner.path_box.GetValue())
    can_paste = _can_paste_into_directory(owner, owner.path_box.GetValue())

    scan_item.Enable(True)
    open_item.Enable(can_act_on_single_selection)
    rename_item.Enable(can_act_on_single_selection)
    new_folder_item.Enable(can_create_in_current_folder)
    copy_item.Enable(can_act_on_selection)
    cut_item.Enable(can_act_on_selection)
    paste_item.Enable(can_paste)
    delete_item.Enable(can_act_on_selection)

    owner.Bind(wx.EVT_MENU, owner.on_list_scan, scan_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_open, open_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_rename, rename_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_new_folder, new_folder_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_copy, copy_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_cut, cut_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_paste, paste_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_delete, delete_item)

    owner.list.PopupMenu(menu)
    menu.Destroy()


def get_selected_list_path(owner):
    selected_paths = get_selected_list_paths(owner)
    if not selected_paths:
        return None

    return selected_paths[0]


def on_list_begin_drag(owner, event):
    selected_paths = get_selected_list_paths(owner)
    file_paths = [path for path in selected_paths if path and os.path.exists(path)]
    if not file_paths:
        return

    file_data = wx.FileDataObject()
    for path in file_paths:
        file_data.AddFile(path)

    drag_source = wx.DropSource(owner.list)
    drag_source.SetData(file_data)
    drag_source.DoDragDrop(wx.Drag_AllowMove)


def get_selected_list_paths(owner):
    if not hasattr(owner, "list") or owner.list is None:
        return []

    current_folder = owner.path_box.GetValue()
    selected_paths = []
    index = owner.list.GetFirstSelected()
    while index != wx.NOT_FOUND:
        name = owner.list.GetItemText(index)
        selected_paths.append(os.path.join(current_folder, name))
        index = owner.list.GetNextSelected(index)

    return selected_paths


def _refresh_tree_node(owner, folder_path):
    if not isinstance(folder_path, str) or not folder_path:
        return
    if not hasattr(owner, "tree") or owner.tree is None:
        return
    if not hasattr(owner, "populate_tree_node"):
        return

    try:
        item = _find_tree_item_without_expanding(owner, folder_path)
        if item is not None and item.IsOk():
            owner.populate_tree_node(item, folder_path)
    except Exception:
        pass


def _find_tree_item_without_expanding(owner, target_path):
    normalized_target = os.path.normcase(os.path.normpath(target_path))

    root = owner.tree.GetRootItem()
    if not root.IsOk():
        return None

    stack = [root]
    while stack:
        item = stack.pop()
        item_path = owner.tree.GetItemData(item)
        if isinstance(item_path, str) and item_path:
            if os.path.normcase(os.path.normpath(item_path)) == normalized_target:
                return item

        child, cookie = owner.tree.GetFirstChild(item)
        while child.IsOk():
            stack.append(child)
            child, cookie = owner.tree.GetNextChild(item, cookie)

    return None


def _remove_tree_item_for_path(owner, path):
    if not hasattr(owner, "tree") or owner.tree is None:
        return

    item = _find_tree_item_without_expanding(owner, path)
    if item is None or not item.IsOk():
        return

    parent = owner.tree.GetItemParent(item)
    if parent.IsOk() and owner.tree.GetChildrenCount(parent) == 1:
        owner.tree.AppendItem(parent, tr("tree_expand_placeholder"))

    owner.tree.Delete(item)

    if getattr(owner, "tree", None) is not None:
        try:
            target_item = parent if parent.IsOk() else owner.tree.GetRootItem()
            if target_item is not None and target_item.IsOk():
                owner.tree.SelectItem(target_item)
        except Exception:
            pass


def _refresh_after_fs_change(owner, affected_dirs=None, preferred_preview_path=None):
    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
    normalized_current_folder = os.path.normpath(current_folder) if isinstance(current_folder, str) and current_folder else None

    selected_tree_path = None
    if hasattr(owner, "tree") and owner.tree is not None:
        try:
            selected_item = owner.tree.GetSelection()
        except Exception:
            selected_item = None
        if selected_item and selected_item.IsOk():
            item_path = owner.tree.GetItemData(selected_item)
            if isinstance(item_path, str) and item_path:
                selected_tree_path = os.path.normpath(item_path)

    if current_folder and os.path.isdir(current_folder):
        owner.load_folder(current_folder)
        _refresh_tree_node(owner, current_folder)

    if selected_tree_path and os.path.isdir(selected_tree_path):
        if normalized_current_folder is None or os.path.normcase(normalized_current_folder) != os.path.normcase(selected_tree_path):
            _refresh_tree_node(owner, selected_tree_path)

    if affected_dirs is not None:
        for folder in affected_dirs:
            if isinstance(folder, str) and folder and os.path.isdir(folder):
                if normalized_current_folder is None or os.path.normcase(normalized_current_folder) != os.path.normcase(os.path.normpath(folder)):
                    _refresh_tree_node(owner, folder)

    if preferred_preview_path and os.path.isfile(preferred_preview_path):
        file_preview.show_file_preview(owner, preferred_preview_path)
        select_list_item_by_path(owner, preferred_preview_path)
        return

    current_preview_path = getattr(owner, "current_preview_path", None)
    if current_preview_path and not os.path.exists(current_preview_path):
        file_preview.show_file_preview(owner, None)


def on_list_copy(owner, _):
    return copy_and_paste.on_list_copy(owner, _)


def on_list_cut(owner, _):
    return copy_and_paste.on_list_cut(owner, _)


def on_list_paste(owner, _):
    return paste_into_path(owner, owner.path_box.GetValue())


def on_list_scan(owner, _):
    if hasattr(owner, "on_scan_form"):
        owner.on_scan_form()


def open_path_or_file(owner, path):
    if not path:
        return False

    if os.path.isdir(path):
        if hasattr(owner, "open_path"):
            owner.open_path(path)
        return True

    if os.path.isfile(path):
        if is_office_file_open(path):
            return True
        try:
            os.startfile(path)
            return True
        except Exception as exc:
            wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
            return False

    return False


def on_list_open(owner, _, path=None):
    if path is None:
        selected_paths = get_selected_list_paths(owner)
        path = selected_paths[0] if len(selected_paths) == 1 else None

    open_path_or_file(owner, path)


def on_list_rename(owner, _):
    selected_paths = get_selected_list_paths(owner)
    path = selected_paths[0] if len(selected_paths) == 1 else None
    if not path:
        return

    current_name = os.path.basename(path)
    dialog = wx.TextEntryDialog(owner, tr("context_rename"), tr("context_rename"), value=current_name)
    result = dialog.ShowModal()
    new_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not new_name or new_name == current_name:
        return

    new_path = os.path.join(os.path.dirname(path), new_name)
    try:
        os.rename(path, new_path)
        _refresh_after_fs_change(owner, affected_dirs=[os.path.dirname(path)])
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def _resolve_new_folder_target_directory(owner, explicit_path=None):
    target_path = explicit_path
    if not target_path:
        target_path = getattr(owner.path_box, "GetValue", lambda: "")()

    if isinstance(target_path, str) and os.path.isfile(target_path):
        target_path = os.path.dirname(target_path)

    if isinstance(target_path, str) and os.path.isdir(target_path):
        return target_path

    return None


def _build_new_folder_name(target_dir, base_name):
    candidate = base_name
    index = 2
    while os.path.exists(os.path.join(target_dir, candidate)):
        candidate = f"{base_name} ({index})"
        index += 1
    return candidate


def create_new_folder(owner, target_path=None):
    target_dir = _resolve_new_folder_target_directory(owner, target_path)
    if not target_dir:
        return

    default_name = _build_new_folder_name(target_dir, tr("context_new_folder"))
    dialog = wx.TextEntryDialog(owner, tr("context_new_folder"), tr("context_new_folder"), value=default_name)
    result = dialog.ShowModal()
    folder_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not folder_name:
        return

    folder_path = os.path.join(target_dir, folder_name)
    try:
        os.makedirs(folder_path, exist_ok=False)
        _refresh_after_fs_change(owner, affected_dirs=[target_dir])
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_list_new_folder(owner, _):
    create_new_folder(owner)


def on_list_delete(owner, _):
    paths = get_selected_list_paths(owner)
    delete_paths(owner, paths)


def delete_paths(owner, paths):
    unique_paths = _unique_preserving_order(paths)
    unique_paths = [path for path in unique_paths if os.path.exists(path)]
    if not unique_paths:
        return

    if len(unique_paths) == 1:
        confirm_target = unique_paths[0]
    else:
        confirm_target = f"{len(unique_paths)} item(s)"

    dialog = wx.MessageDialog(
        owner,
        tr("confirm_delete", path=confirm_target),
        tr("context_delete"),
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    should_delete = dialog.ShowModal() == wx.ID_YES
    dialog.Destroy()

    if not should_delete:
        return

    errors = []
    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
    affected_dirs = [current_folder] if current_folder else []
    removed_current_preview = False

    try:
        for path in unique_paths:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    if is_pdf_file(path):
                        discard_pdf_changes(path)
                    os.remove(path)

                _remove_tree_item_for_path(owner, path)

                current_preview_path = getattr(owner, "current_preview_path", None)
                if current_preview_path and os.path.normcase(os.path.normpath(current_preview_path)) == os.path.normcase(os.path.normpath(path)):
                    removed_current_preview = True
            except Exception as exc:
                errors.append(f"{path}: {exc}")

        _refresh_after_fs_change(owner, affected_dirs=affected_dirs)
        if removed_current_preview:
            file_preview.show_file_preview(owner, None)
    except Exception as exc:
        errors.append(str(exc))

    if errors:
        wx.MessageBox("\n".join(errors), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def paste_into_path(owner, target_path):
    return copy_and_paste.paste_into_path(
        owner,
        target_path,
        refresh_callback=_refresh_after_fs_change,
        update_toolbar_callback=update_list_toolbar_buttons,
        confirm_overwrite_callback=_confirm_overwrite_existing_path,
        can_paste_into_directory_callback=_can_paste_into_directory,
        resolve_target_directory_callback=_resolve_paste_target_directory,
        get_clipboard_mode_callback=_get_clipboard_mode,
        get_clipboard_paths_callback=_get_clipboard_paths,
        unique_preserving_order_callback=_unique_preserving_order,
        build_non_conflicting_path_callback=_build_non_conflicting_path,
    )


def on_tree_copy(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    _set_clipboard(owner, [tree_path], CLIPBOARD_MODE_COPY)


def on_tree_cut(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    _set_clipboard(owner, [tree_path], CLIPBOARD_MODE_CUT)


def on_tree_paste(owner, path=None):
    target_path = path or _resolve_tree_selection_path(owner)
    paste_into_path(owner, target_path)


def on_tree_delete(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    delete_paths(owner, [tree_path])


def handle_file_ops_shortcut(owner, event):
    focus = wx.Window.FindFocus()
    if focus is None:
        return False

    list_has_focus = _is_window_or_descendant(focus, getattr(owner, "list", None))
    tree_has_focus = _is_window_or_descendant(focus, getattr(owner, "tree", None))
    if not list_has_focus and not tree_has_focus:
        return False

    key_code = event.GetKeyCode()
    if 97 <= key_code <= 122:
        key_code -= 32

    ctrl_pressed = bool(getattr(event, "ControlDown", lambda: False)())
    if key_code == wx.WXK_DELETE:
        if list_has_focus:
            on_list_delete(owner, None)
        else:
            on_tree_delete(owner)
        return True

    if not ctrl_pressed:
        return False

    if key_code == ord("C"):
        if list_has_focus:
            on_list_copy(owner, None)
        else:
            on_tree_copy(owner)
        return True

    if key_code == ord("X"):
        if list_has_focus:
            on_list_cut(owner, None)
        else:
            on_tree_cut(owner)
        return True

    if key_code == ord("V"):
        if list_has_focus:
            on_list_paste(owner, None)
        else:
            on_tree_paste(owner)
        return True

    if key_code == ord("D"):
        if list_has_focus:
            on_list_delete(owner, None)
        else:
            on_tree_delete(owner)
        return True

    return False


def _is_window_or_descendant(window, parent):
    if window is None or parent is None:
        return False

    current = window
    while current is not None:
        if current == parent:
            return True
        get_parent = getattr(current, "GetParent", None)
        if not callable(get_parent):
            break
        current = get_parent()
    return False


def on_open_item(owner, event):
    selected_path = get_selected_list_path(owner)
    if not selected_path:
        name = event.GetText()
        selected_path = os.path.join(owner.path_box.GetValue(), name)

    if not selected_path:
        return

    if os.path.isdir(selected_path):
        owner.open_path(selected_path)
        return

    owner.on_list_open(None, selected_path)


def on_list_column_click(owner, event):
    column = event.GetColumn()

    if owner.list_sort_column != column:
        owner.list_sort_column = column
        owner.list_sort_direction = 1
    elif owner.list_sort_direction == 1:
        owner.list_sort_direction = -1
    elif owner.list_sort_direction == -1:
        owner.list_sort_column = None
        owner.list_sort_direction = 0
    else:
        owner.list_sort_direction = 1

    update_list_sort_header_icons(owner)
    owner.load_folder(owner.path_box.GetValue())
