import ntpath
import os
import shutil

import wx

from file_operations.recycle_bin import RECYCLE_BIN_PATH, restore_recycle_bin_items, clear_recycle_bin

from common.system import move_to_recycle_bin

if not hasattr(wx, "DATADOBJECT_PREFERRED"):
    wx.DATADOBJECT_PREFERRED = 0

from controls import tree_utils
from controls import tree_utils
from localization import tr
from file_operations.pdf_utils import discard_pdf_changes, is_pdf_file
from file_operations.office_preview import is_office_file_open
import file_operations.copy_and_paste as copy_and_paste
import file_operations.image_utils as image_utils
import file_operations.archive_helper as archive_helper
import controls.file_preview as file_preview
import controls.drag_and_drop as drag_and_drop
import controls.print_form as print_form
from controls.window_tools import load_settings, update_settings

CLIPBOARD_MODE_COPY = copy_and_paste.CLIPBOARD_MODE_COPY
CLIPBOARD_MODE_CUT = copy_and_paste.CLIPBOARD_MODE_CUT

FileListDropTarget = drag_and_drop.FileListDropTarget

_set_clipboard = copy_and_paste._set_clipboard
_get_clipboard_paths = copy_and_paste._get_clipboard_paths
_get_clipboard_mode = copy_and_paste._get_clipboard_mode
_can_paste_into_directory = copy_and_paste._can_paste_into_directory
_unique_preserving_order = copy_and_paste._unique_preserving_order
_confirm_overwrite_existing_path = copy_and_paste._confirm_overwrite_existing_path
_resolve_tree_selection_path = copy_and_paste._resolve_tree_selection_path
_resolve_paste_target_directory = copy_and_paste._resolve_paste_target_directory
_build_non_conflicting_path = copy_and_paste._build_non_conflicting_path


_is_archive_file = archive_helper._is_archive_file
_archive_selected_path = archive_helper._archive_selected_path
_extract_selected_archive_here = archive_helper._extract_selected_archive_here
_extract_selected_archive_into = archive_helper._extract_selected_archive_into


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
    owner.list_up_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_GO_UP,
        tr("folder_up_button"),
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
    owner.list_print_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_PRINT,
        tr("context_print"),
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
    owner.list_rename_btn = image_utils.create_bitmap_button(
        owner.list_host_panel,
        wx.ART_EDIT,
        tr("context_rename"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    owner.list_delete_btn = image_utils.create_bitmap_button2(
        owner.list_host_panel,
        owner.icon_manager,
        "recycle_bin",
        tr("context_remove_to_recycle_bin"),
        icon_size=list_btn_icon_size,
        button_size=list_btn_size,
    )
    # owner.list_delete_permanent_btn = image_utils.create_bitmap_button(
    #     owner.list_host_panel,
    #     wx.ART_DELETE,
    #     tr("context_delete"),
    #     icon_size=list_btn_icon_size,
    #     button_size=list_btn_size,
    # )
    owner.filter_label = wx.StaticText(owner.list_host_panel, label=tr("filter_label"))
    owner.search_box = wx.TextCtrl(owner.list_host_panel, style=wx.TE_PROCESS_ENTER)
    owner.search_box.SetHint(tr("search_hint"))

    owner.list_toolbar.Add(owner.list_scan_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_open_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_up_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_new_folder_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_print_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_copy_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_cut_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_paste_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_rename_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.list_delete_btn, 0, wx.RIGHT, 3)
    ## owner.list_toolbar.Add(owner.list_delete_permanent_btn, 0, wx.RIGHT, 3)
    owner.list_toolbar.Add(owner.filter_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    owner.list_toolbar.Add(owner.search_box, 0, wx.ALIGN_CENTER_VERTICAL)

    owner.list = wx.ListCtrl(owner.list_host_panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
    owner.list.SetDropTarget(drag_and_drop.FileListDropTarget(owner))
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
    owner.list_up_btn.Bind(wx.EVT_BUTTON, owner.on_folder_up)
    owner.list_new_folder_btn.Bind(wx.EVT_BUTTON, owner.on_list_new_folder)
    owner.list_print_btn.Bind(wx.EVT_BUTTON, owner.on_list_print)
    owner.list_copy_btn.Bind(wx.EVT_BUTTON, owner.on_list_copy)
    owner.list_cut_btn.Bind(wx.EVT_BUTTON, owner.on_list_cut)
    owner.list_paste_btn.Bind(wx.EVT_BUTTON, owner.on_list_paste)
    owner.list_delete_btn.Bind(wx.EVT_BUTTON, owner.on_list_delete)
    ## owner.list_delete_permanent_btn.Bind(wx.EVT_BUTTON, owner.on_list_delete_permanent)


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

    button = getattr(owner, "list_up_btn", None)
    if button is not None:
        parent_folder = ntpath.dirname(current_folder) if isinstance(current_folder, str) and current_folder else ""
        button.Enable(bool(current_folder and os.path.isdir(current_folder) and parent_folder and ntpath.normpath(parent_folder) != ntpath.normpath(current_folder)))

    button = getattr(owner, "list_new_folder_btn", None)
    if button is not None:
        button.Enable(os.path.isdir(current_folder))

    button = getattr(owner, "list_print_btn", None)
    if button is not None:
        button.Enable(has_single_existing_item)

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
    if not isinstance(path, str) or not (os.path.isfile(path) or os.path.isdir(path)):
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
    item_paths = getattr(owner, "_list_item_paths", {})
    path = item_paths.get(index)
    if not isinstance(path, str) or not path:
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


def _remove_restored_preview_tabs(owner, restored_paths):
    if not isinstance(restored_paths, (list, tuple)) or not restored_paths:
        return False

    preview_tabs = getattr(owner, "preview_tabs", None)
    if not isinstance(preview_tabs, list):
        return False

    selected_names = set()
    selected_norm_paths = set()
    for path in restored_paths:
        if not isinstance(path, str) or not path:
            continue
        selected_names.add(os.path.basename(path))
        selected_norm_paths.add(os.path.normcase(os.path.normpath(path)))

    remaining_tabs = []
    removed_any = False
    for tab in preview_tabs:
        if not isinstance(tab, dict):
            remaining_tabs.append(tab)
            continue

        tab_path = tab.get("path")
        if not isinstance(tab_path, str) or not tab_path:
            remaining_tabs.append(tab)
            continue

        tab_name = os.path.basename(tab_path)
        tab_norm = os.path.normcase(os.path.normpath(tab_path))
        if tab_norm in selected_norm_paths or tab_name in selected_names:
            removed_any = True
            continue

        remaining_tabs.append(tab)

    if not removed_any:
        return False

    owner.preview_tabs = remaining_tabs
    if not owner.preview_tabs:
        owner.preview_active_tab_index = None
    else:
        owner.preview_active_tab_index = max(0, min(getattr(owner, "preview_active_tab_index", 0) or 0, len(owner.preview_tabs) - 1))
        file_preview._normalize_preview_tabs(owner)
    file_preview._render_preview_tab_bar(owner)

    current_preview_path = getattr(owner, "current_preview_path", None)
    if isinstance(current_preview_path, str) and current_preview_path:
        current_norm = os.path.normcase(os.path.normpath(current_preview_path))
        if current_norm in selected_norm_paths or os.path.basename(current_preview_path) in selected_names:
            owner.current_preview_path = None
            file_preview.show_file_preview(owner, None)

    return True


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

    def handle_refresh(_):
        current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
        if hasattr(owner, "load_folder") and isinstance(current_folder, str) and current_folder:
            owner.load_folder(current_folder)
        try:
            import controls.tree_utils as tree_utils
            if hasattr(owner, "tree") and owner.tree is not None:
                tree_utils.refresh_tree_selection_and_filelist(owner)
        except Exception:
            pass

    def handle_restore(_):
        selected_paths = get_selected_list_paths(owner)
        if not selected_paths:
            return
        if not restore_recycle_bin_items(selected_paths):
            return

        _remove_restored_preview_tabs(owner, selected_paths)

        current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
        if hasattr(owner, "load_folder") and isinstance(current_folder, str) and current_folder:
            wx.CallLater(300, owner.load_folder, current_folder)

    menu = wx.Menu()
    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
    is_recycle_bin = isinstance(current_folder, str) and current_folder.lower() == RECYCLE_BIN_PATH.lower()
    icon_manager = image_utils.ensure_owner_icon_manager(owner)

    if is_recycle_bin:
        refresh_item = menu.Append(-1, f"{tr('context_refresh')}\tF5")
        restore_item = menu.Append(-1, tr("context_restore"))
        delete_permanent_item = menu.Append(-1, f"{tr('context_delete')}\tShift+Del")
        clear_all_item = menu.Append(-1, tr("context_clear_all"))

        if icon_manager:
            icon_manager.set_menu_icon(refresh_item, art_id=wx.ART_REDO)
            icon_manager.set_menu_icon(restore_item, art_id=wx.ART_UNDO)
            icon_manager.set_menu_icon(delete_permanent_item, art_id=wx.ART_DELETE)
            icon_manager.set_menu_icon(clear_all_item, art_id=wx.ART_DELETE)

        selected_paths = get_selected_list_paths(owner)
        valid_selected_paths = [path for path in selected_paths if isinstance(path, str) and path]
        has_items = bool(getattr(owner, "list", None) is not None and getattr(owner.list, "GetItemCount", lambda: 0)() > 0)

        refresh_item.Enable(True)
        restore_item.Enable(bool(valid_selected_paths))
        delete_permanent_item.Enable(bool(valid_selected_paths))
        clear_all_item.Enable(has_items)

        owner.Bind(wx.EVT_MENU, handle_refresh, refresh_item)
        owner.Bind(wx.EVT_MENU, handle_restore, restore_item)
        owner.Bind(wx.EVT_MENU, owner.on_list_delete_permanent, delete_permanent_item)
        owner.Bind(wx.EVT_MENU, owner.on_list_clear_recycle_bin, clear_all_item)
        owner.list.PopupMenu(menu)
        menu.Destroy()
        return

    scan_item = menu.Append(-1, tr("scan"))
    open_item = menu.Append(-1, tr("context_open"))
    folder_up_item = menu.Append(-1, tr("folder_up_button"))
    new_folder_item = menu.Append(-1, tr("context_new_folder"))
    refresh_item = menu.Append(-1, f"{tr('context_refresh')}\tF5")
    print_item = menu.Append(-1, f"{tr('context_print')}\tCtrl+P")
    menu.AppendSeparator()
    copy_item = menu.Append(-1, f"{tr('context_copy')}\tCtrl+C")
    cut_item = menu.Append(-1, f"{tr('context_cut')}\tCtrl+X")
    paste_item = menu.Append(-1, f"{tr('context_paste')}\tCtrl+V")
    rename_item = menu.Append(-1, tr("context_rename"))
    delete_item = menu.Append(-1, f"{tr('context_remove_to_recycle_bin')}\tCtrl+D")
    delete_permanent_item = menu.Append(-1, f"{tr('context_delete')}\tShift+Del")
    menu.AppendSeparator()

    add_to_archive_item = menu.Append(-1, tr("context_add_to_archive"))
    extract_from_archive_item = menu.Append(-1, tr("context_extract_from_archive_here"))
    extract_from_archive_into_item = menu.Append(-1, tr("context_extract_from_archive_into"))

    refresh_bmp = wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_MENU, (16, 16))
    if refresh_bmp.IsOk():
        refresh_item.SetBitmap(refresh_bmp)

    print_bmp = wx.ArtProvider.GetBitmap(wx.ART_PRINT, wx.ART_MENU, (16, 16))
    if print_bmp.IsOk():
        print_item.SetBitmap(print_bmp)

    if icon_manager:
        icon_manager.set_menu_icon2(scan_item, "scan")
        icon_manager.set_menu_icon2(open_item, "file_view")
        icon_manager.set_menu_icon(folder_up_item, art_id=wx.ART_GO_UP)
        icon_manager.set_menu_icon(rename_item, art_id=wx.ART_EDIT)
        icon_manager.set_menu_icon(new_folder_item, art_id=wx.ART_FOLDER)
        icon_manager.set_menu_icon(refresh_item, art_id=wx.ART_REDO)
        icon_manager.set_menu_icon(print_item, art_id=wx.ART_PRINT)
        icon_manager.set_menu_icon2(copy_item, "copy")
        icon_manager.set_menu_icon(cut_item, art_id=wx.ART_CUT)
        icon_manager.set_menu_icon(paste_item, art_id=wx.ART_PASTE)
        icon_manager.set_menu_icon2(delete_item, "recycle_bin")
        icon_manager.set_menu_icon(delete_permanent_item, art_id=wx.ART_DELETE)
        icon_manager.set_menu_icon2(add_to_archive_item, "add_to_archive")
        icon_manager.set_menu_icon2(extract_from_archive_item, "extract_from_archive")
        icon_manager.set_menu_icon2(extract_from_archive_into_item, "extract_from_archive")

    selected_paths = get_selected_list_paths(owner)
    valid_selected_paths = [path for path in selected_paths if isinstance(path, str) and os.path.exists(path)]
    can_act_on_selection = bool(valid_selected_paths)
    can_act_on_single_selection = len(valid_selected_paths) == 1
    can_create_in_current_folder = os.path.isdir(current_folder)
    can_go_up = bool(current_folder and os.path.isdir(current_folder) and os.path.dirname(current_folder))
    can_paste = _can_paste_into_directory(owner, current_folder)
    can_add_to_archive = bool(valid_selected_paths and all(not _is_archive_file(path) for path in valid_selected_paths))
    can_extract_from_archive = bool(len(valid_selected_paths) == 1 and _is_archive_file(valid_selected_paths[0]))

    scan_item.Enable(True)
    open_item.Enable(can_act_on_single_selection)
    folder_up_item.Enable(can_go_up)
    rename_item.Enable(can_act_on_single_selection)
    new_folder_item.Enable(can_create_in_current_folder)
    refresh_item.Enable(True)
    print_item.Enable(can_act_on_single_selection)
    copy_item.Enable(can_act_on_selection)
    cut_item.Enable(can_act_on_selection)
    paste_item.Enable(can_paste)
    delete_item.Enable(can_act_on_selection)
    delete_permanent_item.Enable(can_act_on_selection)
    add_to_archive_item.Enable(can_add_to_archive)
    extract_from_archive_item.Enable(can_extract_from_archive)
    extract_from_archive_into_item.Enable(can_extract_from_archive)

    owner.Bind(wx.EVT_MENU, owner.on_list_scan, scan_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_open, open_item)
    owner.Bind(wx.EVT_MENU, owner.on_folder_up, folder_up_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_rename, rename_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_new_folder, new_folder_item)
    owner.Bind(wx.EVT_MENU, handle_refresh, refresh_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_print, print_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_copy, copy_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_cut, cut_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_paste, paste_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_delete, delete_item)
    owner.Bind(wx.EVT_MENU, owner.on_list_delete_permanent, delete_permanent_item)
    owner.Bind(wx.EVT_MENU, lambda _event: _archive_selected_path(owner, valid_selected_paths), add_to_archive_item)
    owner.Bind(wx.EVT_MENU, lambda _event: _extract_selected_archive_here(owner, valid_selected_paths[0]) if valid_selected_paths else None, extract_from_archive_item)
    owner.Bind(wx.EVT_MENU, lambda _event: _extract_selected_archive_into(owner, valid_selected_paths[0]) if valid_selected_paths else None, extract_from_archive_into_item)

    owner.list.PopupMenu(menu)
    menu.Destroy()


def get_selected_list_path(owner):
    selected_paths = get_selected_list_paths(owner)
    if not selected_paths:
        return None

    return selected_paths[0]


def _build_drag_payload(file_paths):
    file_data = wx.FileDataObject()
    for path in file_paths:
        file_data.AddFile(path)

    payload_data = wx.TextDataObject()
    payload = drag_and_drop.INTERNAL_DRAG_MARKER + "\n" + "\n".join(file_paths)
    payload_data.SetText(payload)

    is_mocked_data_object = getattr(type(file_data), "__module__", "").startswith("unittest.mock") or getattr(type(wx.DataObjectComposite), "__module__", "").startswith("unittest.mock")
    if isinstance(file_data, wx.DataObject) or is_mocked_data_object:
        composite_data = wx.DataObjectComposite()
        if hasattr(wx, "DATADOBJECT_PREFERRED"):
            composite_data.Add(payload_data, wx.DATADOBJECT_PREFERRED)
        else:
            composite_data.Add(payload_data)
        composite_data.Add(file_data)
        return composite_data

    return payload_data


def on_list_begin_drag(owner, event):
    selected_paths = get_selected_list_paths(owner)
    file_paths = [path for path in selected_paths if path and os.path.exists(path)]
    if not file_paths:
        return

    drag_data = _build_drag_payload(file_paths)
    drag_source = wx.DropSource(owner.list)
    drag_source.SetData(drag_data)
    drag_source.DoDragDrop(wx.Drag_AllowMove)


def get_selected_list_paths(owner):
    if not hasattr(owner, "list") or owner.list is None:
        return []

    current_folder = owner.path_box.GetValue()
    item_paths = getattr(owner, "_list_item_paths", {})
    selected_paths = []
    index = owner.list.GetFirstSelected()
    while index != wx.NOT_FOUND:
        name = owner.list.GetItemText(index)
        item_path = item_paths.get(index)
        if isinstance(item_path, str) and item_path:
            selected_paths.append(item_path)
        else:
            selected_paths.append(os.path.join(current_folder, name))
        index = owner.list.GetNextSelected(index)

    return selected_paths


def _refresh_tree_node(owner, folder_path):
    if not isinstance(folder_path, str) or not folder_path:
        return
    if not hasattr(owner, "tree") or owner.tree is None:
        return

    try:
        item = _find_tree_item_without_expanding(owner, folder_path)
        if item is not None and item.IsOk():
            tree_utils.populate_tree_node(owner, item, folder_path)
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

        try:
            first_child = owner.tree.GetFirstChild(item)
            if not isinstance(first_child, tuple) or len(first_child) != 2:
                continue
            child, cookie = first_child
        except Exception:
            continue

        while child.IsOk():
            stack.append(child)
            try:
                next_child = owner.tree.GetNextChild(item, cookie)
                if not isinstance(next_child, tuple) or len(next_child) != 2:
                    break
                child, cookie = next_child
            except Exception:
                break

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

    if parent.IsOk():
        previous_syncing = getattr(owner, "_syncing_tree_from_path", False)
        owner._syncing_tree_from_path = True
        try:
            owner.tree.SelectItem(parent)
        except Exception:
            pass
        finally:
            owner._syncing_tree_from_path = previous_syncing


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

    is_virtual_shell_folder = isinstance(current_folder, str) and current_folder.lower().startswith("shell:")
    if current_folder and (os.path.isdir(current_folder) or is_virtual_shell_folder) and hasattr(owner, "load_folder"):
        owner.load_folder(current_folder)
        if os.path.isdir(current_folder):
            _refresh_tree_node(owner, current_folder)

    if selected_tree_path and os.path.isdir(selected_tree_path):
        if normalized_current_folder is None or os.path.normcase(normalized_current_folder) != os.path.normcase(selected_tree_path):
            _refresh_tree_node(owner, selected_tree_path)

    if affected_dirs is not None:
        for folder in affected_dirs:
            if not isinstance(folder, str) or not folder:
                continue
            is_virtual_folder = folder.lower().startswith("shell:")
            if os.path.isdir(folder) or is_virtual_folder:
                if normalized_current_folder is None or os.path.normcase(normalized_current_folder) != os.path.normcase(os.path.normpath(folder)):
                    _refresh_tree_node(owner, folder)

    file_preview._prune_deleted_preview_tabs(owner)

    if preferred_preview_path and (os.path.isfile(preferred_preview_path) or os.path.isdir(preferred_preview_path)):
        if os.path.isfile(preferred_preview_path):
            file_preview.show_file_preview(owner, preferred_preview_path)
        select_list_item_by_path(owner, preferred_preview_path)
        if os.path.isdir(preferred_preview_path) and hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(preferred_preview_path)
        return

    current_preview_path = getattr(owner, "current_preview_path", None)
    if current_preview_path and not os.path.exists(current_preview_path):
        file_preview.show_file_preview(owner, None)


def _prompt_rename_name(owner, current_name):
    dialog = wx.TextEntryDialog(owner, tr("context_rename"), tr("context_rename"), value=current_name)

    ok_button = dialog.FindWindow(wx.ID_OK)
    if ok_button:
        ok_button.SetLabel(tr("ok_button"))

    cancel_button = dialog.FindWindow(wx.ID_CANCEL)
    if cancel_button:
        cancel_button.SetLabel(tr("cancel_button"))

    dialog.Layout()
    result = dialog.ShowModal()
    new_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()
    return result, new_name


def _handle_rename_refresh(owner, old_path, new_path):
    _refresh_renamed_list_item(owner, old_path, new_path)
    _refresh_renamed_tree_item(owner, old_path, new_path)

    if hasattr(owner, "select_tree_item_by_path"):
        owner.select_tree_item_by_path(new_path)

    if hasattr(owner, "path_box") and hasattr(owner.path_box, "GetValue"):
        current_folder = owner.path_box.GetValue()
        if isinstance(current_folder, str) and os.path.normpath(os.path.dirname(new_path)) == os.path.normpath(current_folder):
            select_list_item_by_path(owner, new_path)

    current_preview_path = getattr(owner, "current_preview_path", None)
    if current_preview_path and os.path.normcase(os.path.normpath(current_preview_path)) == os.path.normcase(os.path.normpath(old_path)):
        owner.current_preview_path = new_path


def _refresh_renamed_list_item(owner, old_path, new_path):
    if not isinstance(old_path, str) or not isinstance(new_path, str):
        return False

    if not hasattr(owner, "list") or owner.list is None:
        return False

    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
    if not isinstance(current_folder, str):
        return False

    if os.path.normpath(os.path.dirname(old_path)) != os.path.normpath(current_folder):
        return False

    old_name = os.path.basename(old_path)
    new_name = os.path.basename(new_path)

    for index in range(owner.list.GetItemCount()):
        if owner.list.GetItemText(index) != old_name:
            continue
        owner.list.SetItem(index, 0, new_name)
        return True

    return False


def _refresh_renamed_tree_item(owner, old_path, new_path):
    if not isinstance(old_path, str) or not isinstance(new_path, str):
        return False

    if not hasattr(owner, "tree") or owner.tree is None:
        return False

    item = _find_tree_item_without_expanding(owner, old_path)
    if item is None or not item.IsOk():
        return False

    try:
        owner.tree.SetItemText(item, os.path.basename(new_path))
        owner.tree.SetItemData(item, new_path)
        return True
    except Exception:
        return False


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

    if isinstance(path, str) and not os.path.isfile(path):
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(path)

    open_path_or_file(owner, path)


def on_list_rename(owner, _):
    selected_paths = get_selected_list_paths(owner)
    path = selected_paths[0] if len(selected_paths) == 1 else None
    if not path:
        return

    current_name = os.path.basename(path)
    result, new_name = _prompt_rename_name(owner, current_name)
    if result != wx.ID_OK or not new_name or new_name == current_name:
        return

    new_path = os.path.join(os.path.dirname(path), new_name)
    try:
        os.rename(path, new_path)
        _handle_rename_refresh(owner, path, new_path)
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
    if hasattr(dialog, "SetOKCancelLabels"):
        dialog.SetOKCancelLabels(tr("ok_button"), tr("cancel_button"))
    result = dialog.ShowModal()
    folder_name = dialog.GetValue().strip() if result == wx.ID_OK else ""
    dialog.Destroy()

    if result != wx.ID_OK or not folder_name:
        return

    folder_path = os.path.join(target_dir, folder_name)
    try:
        os.makedirs(folder_path, exist_ok=False)
        affected_dirs = [target_dir]
        _refresh_after_fs_change(owner, affected_dirs=affected_dirs)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_folder_up(owner, _):
    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") and owner.path_box is not None else ""
    if not isinstance(current_folder, str) or not current_folder:
        return

    parent_folder = ntpath.dirname(current_folder)
    if not parent_folder:
        return

    if hasattr(owner, "select_tree_item_by_path"):
        owner.select_tree_item_by_path(parent_folder)
    if hasattr(owner, "open_path"):
        owner.open_path(parent_folder, add_history=True)


def on_list_new_folder(owner, _):
    create_new_folder(owner)


def on_list_print(owner, _):
    selected_paths = get_selected_list_paths(owner)
    path = selected_paths[0] if len(selected_paths) == 1 else getattr(owner, "current_preview_path", None)
    if not path:
        path = getattr(owner, "path_box", None)
        if hasattr(path, "GetValue"):
            path = path.GetValue()
    if not isinstance(path, str) or not os.path.exists(path):
        path = getattr(owner, "current_preview_path", None)
    if not path:
        wx.MessageBox(tr("print_no_selection"), tr("print_dialog_title"), style=wx.OK | wx.ICON_INFORMATION)
        return
    print_form.show_print_form(owner, path)


def on_list_delete(owner, _):
    paths = get_selected_list_paths(owner)
    delete_paths(owner, paths, permanent=False)


def on_list_delete_permanent(owner, _):
    paths = get_selected_list_paths(owner)
    delete_paths(owner, paths, permanent=True)


def on_list_clear_recycle_bin(owner, _):
    if owner is None:
        return

    if clear_recycle_bin():
        current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
        if hasattr(owner, "load_folder") and isinstance(current_folder, str) and current_folder:
            wx.CallAfter(owner.load_folder, current_folder)
        if hasattr(owner, "tree") and owner.tree is not None:
            try:
                import controls.tree_utils as tree_utils
                tree_utils.refresh_tree_selection_and_filelist(owner)
            except Exception:
                pass
        file_preview._prune_deleted_preview_tabs(owner)


def delete_paths(owner, paths, permanent=False):
    unique_paths = _unique_preserving_order(paths)
    unique_paths = [path for path in unique_paths if os.path.exists(path)]
    if not unique_paths:
        file_preview._prune_deleted_preview_tabs(owner)
        return

    action_title = tr("context_remove_to_recycle_bin") if not permanent else tr("context_delete")
    if len(unique_paths) == 1:
        action_target = os.path.basename(unique_paths[0])
    else:
        action_target = ", ".join(os.path.basename(path) for path in unique_paths)

    confirmation_dialog = wx.MessageDialog(
        owner,
        tr("confirm_delete", path=action_target),
        action_title,
        wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING,
    )
    confirmation_dialog.SetYesNoLabels(tr("confirm_yes"), tr("confirm_no"))
    confirmation_result = confirmation_dialog.ShowModal()
    confirmation_dialog.Destroy()
    if confirmation_result != wx.ID_YES:
        return

    errors = []
    current_folder = owner.path_box.GetValue() if hasattr(owner, "path_box") else ""
    affected_dirs = [current_folder] if current_folder else []
    removed_current_preview = False

    try:
        for path in unique_paths:
            try:
                if is_pdf_file(path):
                    discard_pdf_changes(path)

                if not permanent and move_to_recycle_bin([path]):
                    _remove_tree_item_for_path(owner, path)
                elif permanent:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    _remove_tree_item_for_path(owner, path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                    _remove_tree_item_for_path(owner, path)
                else:
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
        else:
            file_preview._prune_deleted_preview_tabs(owner)
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
    _set_clipboard(owner, [tree_path], copy_and_paste.CLIPBOARD_MODE_COPY)


def on_tree_cut(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    _set_clipboard(owner, [tree_path], copy_and_paste.CLIPBOARD_MODE_CUT)


def on_tree_paste(owner, path=None):
    target_path = path or _resolve_tree_selection_path(owner)
    paste_into_path(owner, target_path)


def on_tree_rename(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path:
        return

    current_name = os.path.basename(tree_path)
    result, new_name = _prompt_rename_name(owner, current_name)
    if result != wx.ID_OK or not new_name or new_name == current_name:
        return

    new_path = os.path.join(os.path.dirname(tree_path), new_name)
    try:
        os.rename(tree_path, new_path)
        _handle_rename_refresh(owner, tree_path, new_path)
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)


def on_tree_delete(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    delete_paths(owner, [tree_path], permanent=False)


def on_tree_delete_permanent(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    delete_paths(owner, [tree_path], permanent=True)


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
    shift_pressed = bool(getattr(event, "ShiftDown", lambda: False)())

    if key_code == wx.WXK_DELETE and shift_pressed:
        if list_has_focus:
            on_list_delete_permanent(owner, None)
        else:
            on_tree_delete_permanent(owner)
        return True

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

    if key_code == ord("P"):
        if list_has_focus:
            on_list_print(owner, None)
        else:
            tree_path = _resolve_tree_selection_path(owner)
            if isinstance(tree_path, str) and os.path.isfile(tree_path):
                import controls.print_form as print_form
                print_form.show_print_form(owner, tree_path)
                return True
        return True if list_has_focus else False

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
