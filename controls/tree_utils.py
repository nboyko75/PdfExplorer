import os
import wx

from localization import tr
from file_operations.pdf_utils import ajust_page_width, optimize_pdf, save_pdf
import file_operations.image_utils as image_utils


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


def get_tree_icon_index(owner, path, is_dir):
    if is_dir:
        return owner.tree_icon_cache["__folder__"]

    ext = os.path.splitext(path)[1].lower()
    if not ext:
        return owner.tree_icon_cache["__file__"]

    cached = owner.tree_icon_cache.get(ext)
    if cached is not None:
        return cached

    bmp = image_utils.create_extension_icon_bitmap(ext)
    owner.tree_icon_cache[ext] = owner.tree_images.Add(bmp)
    return owner.tree_icon_cache[ext]


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
                populate_tree_node(owner, child, item_path)
                owner.tree.Expand(child)
                found = find_tree_child_path(owner, child, normalized)
                if found:
                    return found
        child, cookie = owner.tree.GetNextChild(root, cookie)

    return None


def find_tree_child_path(owner, parent, normalized_path):
    populate_tree_node(owner, parent, owner.tree.GetItemData(parent))
    owner.tree.Expand(parent)
    child, cookie = owner.tree.GetFirstChild(parent)
    while child.IsOk():
        item_path = owner.tree.GetItemData(child)
        if item_path:
            item_normalized = os.path.normpath(item_path)
            if item_normalized == normalized_path:
                return child
            if normalized_path.startswith(item_normalized):
                populate_tree_node(owner, child, item_path)
                owner.tree.Expand(child)
                found = find_tree_child_path(owner, child, normalized_path)
                if found:
                    return found
        child, cookie = owner.tree.GetNextChild(parent, cookie)

    return None


def select_tree_item_by_path(owner, path):
    item = find_tree_item_by_path(owner, path)
    if item is None:
        return
    owner.tree.SelectItem(item)
    owner.tree.Expand(item)
    owner.tree.EnsureVisible(item)


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
        if not owner.show_hidden and (name.startswith(".") or name.startswith("$")):
            continue

        full_path = normalize_tree_path(os.path.join(path, name))
        child = owner.tree.AppendItem(item, name)
        owner.tree.SetItemData(child, full_path)

        if os.path.isdir(full_path):
            owner.tree.SetItemImage(child, owner.tree_icon_folder)
            owner.tree.AppendItem(child, tr("tree_expand_placeholder"))
        else:
            owner.tree.SetItemImage(child, get_tree_icon_index(owner, full_path, is_dir=False))


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
    path = normalize_tree_path(owner.tree.GetItemData(item))
    populate_tree_node(owner, item, path)


def on_tree_select(owner, event):
    item = event.GetItem()
    path = normalize_tree_path(owner.tree.GetItemData(item))

    if getattr(owner, "_syncing_tree_from_path", False):
        return

    if hasattr(owner, "confirm_preview_change") and not owner.confirm_preview_change(path):
        event.Veto()
        return

    owner.show_file_preview(path)

    if path and os.path.isdir(path):
        owner.open_path(path)


def on_tree_right_click(owner, event):
    path = _resolve_tree_context_path(owner, event)
    is_supported_target = _is_folder_or_single_pdf(path)

    menu = wx.Menu()
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

    owner.Bind(wx.EVT_MENU, handle_optimize_all, optimize_item)
    owner.Bind(wx.EVT_MENU, handle_adjust_all, adjust_item)

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
                ajust_page_width(file_path)
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


class _nullcontext:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False
