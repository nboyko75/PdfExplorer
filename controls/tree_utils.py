import os
import wx

from common.system import is_hidden
from common.system import is_hidden
from localization import tr
from file_operations.pdf_utils import adjust_page_width, optimize_pdf, save_pdf
import file_operations.archive_helper as archive_helper
import file_operations.image_utils as image_utils
import controls.file_preview as file_preview
import controls.filelist as filelist


def bind_tree_events(owner):
    owner.tree.Bind(wx.EVT_TREE_ITEM_EXPANDING, owner.on_tree_expand)
    owner.tree.Bind(wx.EVT_TREE_SEL_CHANGING, owner.on_tree_select)
    owner.tree.Bind(wx.EVT_TREE_ITEM_ACTIVATED, owner.on_tree_activated)
    owner.tree.Bind(wx.EVT_CONTEXT_MENU, owner.on_tree_right_click)


def normalize_tree_path(path):
    if not isinstance(path, str):
        return path
    return os.path.normpath(path).replace("/", "\\")


def init_tree_images(owner):
    owner.tree_images = wx.ImageList(16, 16)
    owner.tree_icon_cache = {}

    root_bmp = wx.ArtProvider.GetBitmap(wx.ART_HARDDISK, wx.ART_OTHER, (16, 16))
    if not root_bmp.IsOk():
        root_bmp = wx.ArtProvider.GetBitmap(wx.ART_HARDDISK, wx.ART_TOOLBAR, (16, 16))

    folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
    if not folder_bmp.IsOk():
        folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, (16, 16))

    file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
    if not file_bmp.IsOk():
        file_bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (16, 16))

    owner.tree_icon_root = owner.tree_images.Add(root_bmp)
    owner.tree_icon_folder = owner.tree_images.Add(folder_bmp)
    owner.tree_icon_file = owner.tree_images.Add(file_bmp)
    owner.tree_icon_cache["__folder__"] = owner.tree_icon_folder
    owner.tree_icon_cache["__file__"] = owner.tree_icon_file

    owner.tree.AssignImageList(owner.tree_images)


def get_tree_icon_index(owner, path, is_dir, is_hidden_item=False):
    if is_dir:
        bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_OTHER, (16, 16))
        if not bmp.IsOk():
            bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_TOOLBAR, (16, 16))
        if is_hidden_item and bmp.IsOk():
            return owner.tree_images.Add(image_utils.Hidden_Image(bmp.ConvertToImage()).ConvertToBitmap())
        return owner.tree_icon_cache["__folder__"]

    ext = os.path.splitext(path)[1].lower()
    if not ext:
        bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_OTHER, (16, 16))
        if not bmp.IsOk():
            bmp = wx.ArtProvider.GetBitmap(wx.ART_NORMAL_FILE, wx.ART_TOOLBAR, (16, 16))
        if is_hidden_item and bmp.IsOk():
            return owner.tree_images.Add(image_utils.Hidden_Image(bmp.ConvertToImage()).ConvertToBitmap())
        return owner.tree_icon_cache["__file__"]

    cache_key = f"{ext}|hidden" if is_hidden_item else ext
    cached = owner.tree_icon_cache.get(cache_key)
    if cached is not None:
        return cached

    bmp = image_utils.create_extension_icon_bitmap(ext)
    if is_hidden_item:
        bmp = image_utils.Hidden_Image(bmp.ConvertToImage()).ConvertToBitmap()
    owner.tree_icon_cache[cache_key] = owner.tree_images.Add(bmp)
    return owner.tree_icon_cache[cache_key]


def refresh_tree_placeholders(owner):
    root = owner.tree.GetRootItem()
    if not root.IsOk():
        return

    owner.tree.SetItemText(root, tr("this_pc_root"))

    def visit(item):
        child, cookie = owner.tree.GetFirstChild(item)
        while child.IsOk():
            if owner.tree.GetItemData(child) is None:
                owner.tree.SetItemText(child, tr("tree_expand_placeholder"))
            visit(child)
            child, cookie = owner.tree.GetNextChild(item, cookie)

    visit(root)


def _should_populate_tree_node(owner, item, item_path):
    if not item or not item.IsOk():
        return False
    if not isinstance(item_path, str):
        return False

    normalized_path = normalize_tree_path(item_path)
    if not normalized_path or not os.path.isdir(normalized_path):
        return False

    child, _ = owner.tree.GetFirstChild(item)
    if not child.IsOk():
        return True

    if owner.tree.GetItemData(child) is None:
        return True

    return False


def find_tree_item_by_path(owner, path):
    normalized = os.path.normpath(path)
    root = owner.tree.GetRootItem()
    if not root.IsOk():
        return None

    child, cookie = owner.tree.GetFirstChild(root)
    while child.IsOk():
        item_path = owner.tree.GetItemData(child)
        if item_path:
            item_normalized = os.path.normpath(item_path)
            if item_normalized == normalized:
                return child
            if normalized.startswith(item_normalized):
                if _should_populate_tree_node(owner, child, item_path):
                    populate_tree_node(owner, child, item_path)
                owner.tree.Expand(child)
                found = find_tree_child_path(owner, child, normalized)
                if found:
                    return found
        child, cookie = owner.tree.GetNextChild(root, cookie)

    return None


def find_tree_child_path(owner, parent, normalized_path):
    parent_item_path = owner.tree.GetItemData(parent)
    if _should_populate_tree_node(owner, parent, parent_item_path):
        populate_tree_node(owner, parent, parent_item_path)
    owner.tree.Expand(parent)
    child, cookie = owner.tree.GetFirstChild(parent)
    while child.IsOk():
        item_path = owner.tree.GetItemData(child)
        if item_path:
            item_normalized = os.path.normpath(item_path)
            if item_normalized == normalized_path:
                return child
            if normalized_path.startswith(item_normalized):
                if _should_populate_tree_node(owner, child, item_path):
                    populate_tree_node(owner, child, item_path)
                owner.tree.Expand(child)
                found = find_tree_child_path(owner, child, normalized_path)
                if found:
                    return found
        child, cookie = owner.tree.GetNextChild(parent, cookie)

    return None


def select_tree_item_by_path(owner, path):
    normalized_path = normalize_tree_path(path)
    item = find_tree_item_by_path(owner, normalized_path)
    if item is None:
        return

    item_path = normalize_tree_path(owner.tree.GetItemData(item))
    path_box = getattr(owner, "path_box", None)
    if path_box is not None and hasattr(path_box, "SetValue"):
        if item_path and os.path.isdir(item_path):
            path_box.SetValue(item_path)
        elif item_path and os.path.isfile(item_path):
            path_box.SetValue(os.path.dirname(item_path))

    previous_syncing = getattr(owner, "_syncing_tree_from_path", False)
    owner._syncing_tree_from_path = True
    try:
        owner.tree.SelectItem(item)
        owner.tree.Expand(item)
        owner.tree.EnsureVisible(item)
    finally:
        if not previous_syncing:
            owner._syncing_tree_from_path = False


def populate_tree_node(owner, item, path):
    path = normalize_tree_path(path)
    if not path or not os.path.isdir(path):
        return

    owner.tree.DeleteChildren(item)

    try:
        entries = os.listdir(path)
    except (PermissionError, FileNotFoundError):
        return

    entries.sort(key=lambda name: (not os.path.isdir(os.path.join(path, name)), name.lower()))

    for name in entries:
        full_path = normalize_tree_path(os.path.join(path, name))

        if not owner.show_hidden and is_hidden(full_path):
            continue

        child = owner.tree.AppendItem(item, name)
        owner.tree.SetItemData(child, full_path)

        is_item_hidden = bool(is_hidden(full_path))
        if os.path.isdir(full_path):
            owner.tree.SetItemImage(child, get_tree_icon_index(owner, full_path, is_dir=True, is_hidden_item=is_item_hidden))
            owner.tree.AppendItem(child, tr("tree_expand_placeholder"))
        else:
            owner.tree.SetItemImage(child, get_tree_icon_index(owner, full_path, is_dir=False, is_hidden_item=is_item_hidden))


def refresh_tree_subtree(owner, item, path):
    if not item or not item.IsOk():
        return

    normalized_path = normalize_tree_path(path)
    if not normalized_path or not os.path.isdir(normalized_path):
        return

    populate_tree_node(owner, item, normalized_path)

    child, cookie = owner.tree.GetFirstChild(item)
    while child.IsOk():
        child_path = owner.tree.GetItemData(child)
        if isinstance(child_path, str) and os.path.isdir(normalize_tree_path(child_path)):
            refresh_tree_subtree(owner, child, child_path)
        child, cookie = owner.tree.GetNextChild(item, cookie)


def refresh_tree_root(owner):
    tree = getattr(owner, "tree", None)
    if tree is None or not hasattr(tree, "GetRootItem"):
        return

    root = tree.GetRootItem()
    if not root.IsOk():
        return

    cursor_ctx = owner.busy_cursor() if hasattr(owner, "busy_cursor") else _nullcontext()
    with cursor_ctx:
        tree.DeleteChildren(root)

        for drive in get_drives():
            item = tree.AppendItem(root, drive)
            tree.SetItemData(item, normalize_tree_path(drive))
            tree.SetItemImage(item, getattr(owner, "tree_icon_folder", 0))
            tree.AppendItem(item, tr("tree_expand_placeholder"))

        tree.Expand(root)


def refresh_tree_selection(owner):
    tree = getattr(owner, "tree", None)
    if tree is None or not hasattr(tree, "GetSelection") or not hasattr(tree, "GetRootItem"):
        return

    selected_item = tree.GetSelection()
    if not selected_item or not selected_item.IsOk():
        selected_item = tree.GetRootItem()

    if selected_item and selected_item.IsOk() and selected_item == tree.GetRootItem():
        refresh_tree_root(owner)
        return

    if selected_item and selected_item.IsOk():
        selected_path = tree.GetItemData(selected_item)
        if isinstance(selected_path, str) and os.path.isdir(normalize_tree_path(selected_path)):
            refresh_tree_subtree(owner, selected_item, selected_path)


def refresh_tree_selection_and_filelist(owner):
    selected_item = owner.tree.GetSelection()
    if not selected_item or not selected_item.IsOk():
        selected_item = owner.tree.GetRootItem()

    if selected_item and selected_item.IsOk() and selected_item == owner.tree.GetRootItem():
        refresh_tree_root(owner)
        return

    current_folder = getattr(owner, "path_box", None)
    current_folder_path = None
    if current_folder is not None and hasattr(current_folder, "GetValue"):
        current_folder_path = normalize_tree_path(current_folder.GetValue())

    if selected_item and selected_item.IsOk():
        selected_path = owner.tree.GetItemData(selected_item)
        if isinstance(selected_path, str):
            normalized_selected_path = normalize_tree_path(selected_path)
            if os.path.isdir(normalized_selected_path):
                if current_folder_path and normalized_selected_path == current_folder_path:
                    owner.load_folder(normalized_selected_path)
                    refresh_tree_subtree(owner, selected_item, normalized_selected_path)
                    return
                refresh_tree_subtree(owner, selected_item, normalized_selected_path)
                return

    refresh_tree_selection(owner)


def init_tree(owner):
    root = owner.tree.AddRoot(tr("this_pc_root"))
    owner.tree.SetItemImage(root, owner.tree_icon_root)

    for drive in get_drives():
        item = owner.tree.AppendItem(root, drive)
        owner.tree.SetItemData(item, normalize_tree_path(drive))
        owner.tree.SetItemImage(item, owner.tree_icon_folder)
        owner.tree.AppendItem(item, tr("tree_expand_placeholder"))

    owner.tree.Expand(root)


def get_drives():
    return [f"{d}:\\" for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if os.path.exists(f"{d}:/")]


def on_tree_expand(owner, event):
    item = event.GetItem()
    item_path = owner.tree.GetItemData(item)
    if not _should_populate_tree_node(owner, item, item_path):
        return

    path = normalize_tree_path(item_path)
    populate_tree_node(owner, item, path)


def on_tree_select(owner, event):
    item = event.GetItem()
    path = normalize_tree_path(owner.tree.GetItemData(item))

    if getattr(owner, "_syncing_tree_from_path", False):
        return

    if hasattr(owner, "confirm_preview_change") and not owner.confirm_preview_change(path):
        event.Veto()
        return

    if not path:
        return

    if os.path.isfile(path):
        path_box = getattr(owner, "path_box", None)
        if path_box is not None and hasattr(path_box, "SetValue"):
            path_box.SetValue(os.path.dirname(path))
        if hasattr(owner, "show_file_preview"):
            owner.show_file_preview(path)
        else:
            file_preview.show_file_preview(owner, path)
        return

    if os.path.isdir(path):
        owner.open_path(path)


def on_tree_activated(owner, event):
    item = event.GetItem()
    if not item or not item.IsOk():
        return

    path = normalize_tree_path(owner.tree.GetItemData(item))
    is_tree_folder = bool(path) and not os.path.isfile(path)
    if is_tree_folder:
        if owner.tree.IsExpanded(item):
            owner.tree.Collapse(item)
        else:
            owner.tree.Expand(item)
        if hasattr(owner, "open_path"):
            owner.open_path(path)
        return

    filelist.open_path_or_file(owner, path)


def on_tree_right_click(owner, event):
    selected_item = owner.tree.GetSelection()
    if event is not None:
        try:
            pos = event.GetPosition()
            if pos != wx.DefaultPosition:
                client_pos = owner.tree.ScreenToClient(pos)
                item, _ = owner.tree.HitTest(client_pos)
                if item and item.IsOk():
                    owner.tree.SelectItem(item)
                    selected_item = item
        except Exception:
            pass

    path = _resolve_tree_context_path(owner, event)
    is_supported_target = _is_folder_or_single_pdf(path)
    can_act_on_selection = bool(path and os.path.exists(path))
    create_target = _resolve_tree_new_folder_target(owner, path)
    is_root_node = selected_item and selected_item.IsOk() and selected_item == owner.tree.GetRootItem()
    can_create_new_folder = create_target is not None and not is_root_node
    paste_target = path if path else getattr(owner.path_box, "GetValue", lambda: "")()
    can_paste = filelist._can_paste_into_directory(owner, filelist._resolve_paste_target_directory(paste_target))
    icon_manager = getattr(owner, "icon_manager", None)

    menu = wx.Menu()
    open_item = menu.Append(-1, tr("context_open"))
    folder_up_item = menu.Insert(2, -1, tr("folder_up_button"))
    new_folder_item = menu.Append(-1, tr("context_new_folder"))
    refresh_item = menu.Append(-1, f"{tr('context_refresh')}\tF5")
    print_item = menu.Append(-1, f"{tr('context_print')}\tCtrl+P")
    menu.AppendSeparator()

    copy_item = menu.Append(-1, f"{tr('context_copy')}\tCtrl+C")
    cut_item = menu.Append(-1, f"{tr('context_cut')}\tCtrl+X")
    paste_item = menu.Append(-1, f"{tr('context_paste')}\tCtrl+V")
    rename_item = menu.Append(-1, tr("context_rename"))
    delete_item = menu.Append(-1, f"{tr('context_delete')}\tCtrl+D")
    menu.AppendSeparator()

    add_to_archive_item = menu.Append(-1, tr("context_add_to_archive"))
    extract_from_archive_item = menu.Append(-1, tr("context_extract_from_archive"))

    open_item.Enable(can_act_on_selection)
    folder_up_item.Enable(bool(path and os.path.isdir(path) and os.path.dirname(path)))
    new_folder_item.Enable(can_create_new_folder)
    refresh_item.Enable(True)
    print_item.Enable(bool(path and os.path.isfile(path)))
    copy_item.Enable(can_act_on_selection)
    cut_item.Enable(can_act_on_selection)
    paste_item.Enable(can_paste)
    rename_item.Enable(can_act_on_selection)
    delete_item.Enable(can_act_on_selection)
    add_to_archive_item.Enable(bool(path and os.path.exists(path) and not archive_helper._is_archive_file(path)))
    extract_from_archive_item.Enable(bool(path and archive_helper._is_archive_file(path)))

    folder_up_bmp = wx.ArtProvider.GetBitmap(wx.ART_GO_UP, wx.ART_MENU, (16, 16))
    if folder_up_bmp.IsOk():
        folder_up_item.SetBitmap(folder_up_bmp)

    new_folder_bmp = wx.ArtProvider.GetBitmap(wx.ART_FOLDER, wx.ART_MENU, (16, 16))
    if new_folder_bmp.IsOk():
        new_folder_item.SetBitmap(new_folder_bmp)

    refresh_bmp = wx.ArtProvider.GetBitmap(wx.ART_REDO, wx.ART_MENU, (16, 16))
    if refresh_bmp.IsOk():
        refresh_item.SetBitmap(refresh_bmp)

    print_bmp = wx.ArtProvider.GetBitmap(wx.ART_PRINT, wx.ART_MENU, (16, 16))
    if print_bmp.IsOk():
        print_item.SetBitmap(print_bmp)

    if icon_manager:
        icon_manager.set_menu_icon2(open_item, "file_view")
        icon_manager.set_menu_icon2(copy_item, "copy")
        icon_manager.set_menu_icon2(add_to_archive_item, "add_to_archive")
        icon_manager.set_menu_icon2(extract_from_archive_item, "extract_from_archive")

    cut_bmp = wx.ArtProvider.GetBitmap(wx.ART_CUT, wx.ART_MENU, (16, 16))
    if cut_bmp.IsOk():
        cut_item.SetBitmap(cut_bmp)

    paste_bmp = wx.ArtProvider.GetBitmap(wx.ART_PASTE, wx.ART_MENU, (16, 16))
    if paste_bmp.IsOk():
        paste_item.SetBitmap(paste_bmp)

    rename_bmp = wx.ArtProvider.GetBitmap(wx.ART_EDIT, wx.ART_MENU, (16, 16))
    if rename_bmp.IsOk():
        rename_item.SetBitmap(rename_bmp)

    delete_bmp = wx.ArtProvider.GetBitmap(wx.ART_DELETE, wx.ART_MENU, (16, 16))
    if delete_bmp.IsOk():
        delete_item.SetBitmap(delete_bmp)
    menu.AppendSeparator()

    optimize_item = menu.Append(-1, tr("tree_optimize_all_pdf"))
    optimize_bmp = wx.ArtProvider.GetBitmap(wx.ART_TICK_MARK, wx.ART_MENU, (16, 16))
    if optimize_bmp.IsOk():
        optimize_item.SetBitmap(optimize_bmp)

    adjust_item = menu.Append(-1, tr("tree_adjust_page_width_all_pdf"))
    adjust_bmp = wx.ArtProvider.GetBitmap(wx.ART_REPORT_VIEW, wx.ART_MENU, (16, 16))
    if adjust_bmp.IsOk():
        adjust_item.SetBitmap(adjust_bmp)

    optimize_item.Enable(is_supported_target)
    adjust_item.Enable(is_supported_target)

    def handle_optimize_all(_):
        optimize_all_pdf_in_path(owner, path)

    def handle_adjust_all(_):
        adjust_page_width_all_pdf_in_path(owner, path)

    def handle_open(_):
        filelist.open_path_or_file(owner, path)

    def handle_new_folder(_):
        filelist.create_new_folder(owner, create_target)

    def handle_go_up(_):
        target_path = path or getattr(owner.path_box, "GetValue", lambda: "")()
        if not isinstance(target_path, str) or not target_path:
            return
        parent_path = os.path.dirname(target_path)
        if not parent_path or not os.path.isdir(parent_path):
            return
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(parent_path)
        if hasattr(owner, "open_path"):
            owner.open_path(parent_path, add_history=True)

    def handle_refresh(_):
        refresh_tree_selection_and_filelist(owner)

    def handle_print(_):
        if path and os.path.isfile(path):
            import controls.print_form as print_form
            print_form.show_print_form(owner, path)

    def handle_copy(_):
        filelist.on_tree_copy(owner, path)

    def handle_cut(_):
        filelist.on_tree_cut(owner, path)

    def handle_paste(_):
        filelist.on_tree_paste(owner, path)

    def handle_rename(_):
        filelist.on_tree_rename(owner, path)

    def handle_delete(_):
        filelist.on_tree_delete(owner, path)

    def handle_add_to_archive(_):
        archive_helper._archive_selected_path(owner, path)

    def handle_extract_from_archive(_):
        archive_helper._extract_selected_archive(owner, path)

    owner.Bind(wx.EVT_MENU, handle_optimize_all, optimize_item)
    owner.Bind(wx.EVT_MENU, handle_adjust_all, adjust_item)
    owner.Bind(wx.EVT_MENU, handle_open, open_item)
    owner.Bind(wx.EVT_MENU, handle_go_up, folder_up_item)
    owner.Bind(wx.EVT_MENU, handle_new_folder, new_folder_item)
    owner.Bind(wx.EVT_MENU, handle_refresh, refresh_item)
    owner.Bind(wx.EVT_MENU, handle_print, print_item)
    owner.Bind(wx.EVT_MENU, handle_copy, copy_item)
    owner.Bind(wx.EVT_MENU, handle_cut, cut_item)
    owner.Bind(wx.EVT_MENU, handle_paste, paste_item)
    owner.Bind(wx.EVT_MENU, handle_rename, rename_item)
    owner.Bind(wx.EVT_MENU, handle_delete, delete_item)
    owner.Bind(wx.EVT_MENU, handle_add_to_archive, add_to_archive_item)
    owner.Bind(wx.EVT_MENU, handle_extract_from_archive, extract_from_archive_item)

    popup_window = owner.tree
    if event is not None:
        try:
            obj = event.GetEventObject()
            if isinstance(obj, wx.Window):
                popup_window = obj
        except Exception:
            pass

    popup_window.PopupMenu(menu)
    menu.Destroy()


def optimize_all_pdf_in_path(owner, path):
    base_path = normalize_tree_path(path)
    if not _is_folder_or_single_pdf(base_path):
        wx.MessageBox(tr("tree_no_folder_or_pdf_selected"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    optimized_count = 0
    failed_count = 0

    cursor_ctx = owner.busy_cursor() if hasattr(owner, "busy_cursor") else _nullcontext()
    with cursor_ctx:
        for file_path in _iter_pdf_targets(base_path):
            try:
                optimize_pdf(file_path)
                save_pdf(file_path)
                if hasattr(owner, "refresh_list_item_size"):
                    owner.refresh_list_item_size(file_path)
                optimized_count += 1
            except Exception:
                failed_count += 1

    wx.MessageBox(
        tr("tree_optimize_all_done", optimized_count=optimized_count, failed_count=failed_count),
        tr("tree_optimize_all_pdf"),
        wx.OK | wx.ICON_INFORMATION,
    )


def adjust_page_width_all_pdf_in_path(owner, path):
    base_path = normalize_tree_path(path)
    if not _is_folder_or_single_pdf(base_path):
        wx.MessageBox(tr("tree_no_folder_or_pdf_selected"), tr("app_title"), wx.OK | wx.ICON_INFORMATION)
        return

    adjusted_count = 0
    failed_count = 0

    cursor_ctx = owner.busy_cursor() if hasattr(owner, "busy_cursor") else _nullcontext()
    with cursor_ctx:
        for file_path in _iter_pdf_targets(base_path):
            try:
                adjust_page_width(file_path)
                save_pdf(file_path)
                if hasattr(owner, "refresh_list_item_size"):
                    owner.refresh_list_item_size(file_path)
                adjusted_count += 1
            except Exception:
                failed_count += 1

    wx.MessageBox(
        tr("tree_adjust_page_width_all_done", adjusted_count=adjusted_count, failed_count=failed_count),
        tr("tree_adjust_page_width_all_pdf"),
        wx.OK | wx.ICON_INFORMATION,
    )


def _is_pdf_file_path(path):
    return isinstance(path, str) and path.lower().endswith(".pdf") and os.path.isfile(path)


def _is_folder_or_single_pdf(path):
    return isinstance(path, str) and (os.path.isdir(path) or _is_pdf_file_path(path))


def _iter_pdf_targets(path):
    if _is_pdf_file_path(path):
        yield path
        return

    if not os.path.isdir(path):
        return

    for root, _, filenames in os.walk(path):
        for filename in filenames:
            if filename.lower().endswith(".pdf"):
                yield os.path.join(root, filename)


def _resolve_tree_context_path(owner, event):
    selected_item = owner.tree.GetSelection()

    if event is not None:
        try:
            pos = event.GetPosition()
            if pos != wx.DefaultPosition:
                client_pos = owner.tree.ScreenToClient(pos)
                item, _ = owner.tree.HitTest(client_pos)
                if item and item.IsOk():
                    owner.tree.SelectItem(item)
                    selected_item = item
        except Exception:
            pass

    if selected_item and selected_item.IsOk():
        return normalize_tree_path(owner.tree.GetItemData(selected_item))

    current_folder = getattr(owner, "path_box", None)
    if current_folder is not None:
        return normalize_tree_path(current_folder.GetValue())
    return None


def _resolve_tree_new_folder_target(owner, path):
    if isinstance(path, str) and os.path.isdir(path):
        return path

    current_folder = getattr(owner, "path_box", None)
    if current_folder is not None:
        value = current_folder.GetValue()
        if isinstance(value, str) and os.path.isdir(value):
            return value

    if isinstance(path, str) and os.path.isfile(path):
        parent_dir = os.path.dirname(path)
        if os.path.isdir(parent_dir):
            return parent_dir

    return None


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
