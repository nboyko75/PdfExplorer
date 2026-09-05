import os
from datetime import datetime

import file_operations.image_utils as image_utils
from common.system import is_hidden
from file_operations.recycle_bin import RECYCLE_BIN_PATH, get_recycle_bin_items, is_virtual_shell_path
from localization import tr
from controls.window_tools import update_settings


def save_last_folder(owner):
    current_folder = owner.path_box.GetValue()
    if os.path.isdir(current_folder):
        update_settings({"last_folder": current_folder})


def _path_is_directory_like(path):
    if not isinstance(path, str) or not path:
        return False
    if os.path.isdir(path):
        return True
    if is_virtual_shell_path(path):
        return path.lower() == RECYCLE_BIN_PATH.lower() or path.lower().startswith("shell:")
    normalized = os.path.normpath(path)
    return bool(normalized) and (os.path.isabs(path) or normalized.startswith("\\\\") or bool(__import__("re").match(r"^[A-Za-z]:[\\/]", path)))


def open_path(owner, path, add_history=True):
    if not _path_is_directory_like(path):
        return False

    if hasattr(owner, "confirm_preview_change") and not owner.confirm_preview_change(path):
        return False

    if add_history:
        history = getattr(owner, "history", [])
        history_index = getattr(owner, "history_index", -1)
        owner.history = history[:history_index + 1]
        owner.history.append(path)
        owner.history_index = len(owner.history) - 1

    if hasattr(owner, "path_box") and hasattr(owner.path_box, "ChangeValue"):
        owner.path_box.ChangeValue(path)
    if hasattr(owner, "load_folder"):
        owner.load_folder(path)

    if hasattr(owner, "select_tree_item_by_path"):
        previous_syncing = getattr(owner, "_syncing_tree_from_path", False)
        owner._syncing_tree_from_path = True
        try:
            owner.select_tree_item_by_path(path)
        finally:
            owner._syncing_tree_from_path = previous_syncing

    return True


def go_back(owner, _):
    if owner.history_index > 0:
        target_path = owner.history[owner.history_index - 1]
        owner.history_index -= 1
        if hasattr(owner, "open_path"):
            owner.open_path(target_path, add_history=False)
            return
        if hasattr(owner, "path_box") and hasattr(owner.path_box, "ChangeValue"):
            owner.path_box.ChangeValue(target_path)
        if hasattr(owner, "load_folder"):
            owner.load_folder(target_path)
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(target_path)


def go_forward(owner, _):
    if owner.history_index < len(owner.history) - 1:
        target_path = owner.history[owner.history_index + 1]
        owner.history_index += 1
        if hasattr(owner, "open_path"):
            owner.open_path(target_path, add_history=False)
            return
        if hasattr(owner, "path_box") and hasattr(owner.path_box, "ChangeValue"):
            owner.path_box.ChangeValue(target_path)
        if hasattr(owner, "load_folder"):
            owner.load_folder(target_path)
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(target_path)


def open_recycle_bin(owner, add_history=True):
    return open_path(owner, RECYCLE_BIN_PATH, add_history=add_history)


def load_folder(owner, path):
    owner.list.DeleteAllItems()
    owner._list_item_paths = {}

    if is_virtual_shell_path(path):
        if path.lower() == RECYCLE_BIN_PATH.lower():
            items = get_recycle_bin_items()
        else:
            items = []

        filter_text = owner.search_box.GetValue().lower()
        row_data = []

        for original_index, item in enumerate(items):
            name = str(item.get("name") or "")
            if not name:
                continue
            if filter_text and filter_text not in name.lower():
                continue

            is_dir = bool(item.get("is_dir"))
            size_value = item.get("size")
            try:
                size_kb = int(size_value or 0) // 1024
            except (TypeError, ValueError):
                size_kb = None
            size = f"{size_kb} {tr('file_size_unit_kb')}" if size_kb is not None else ""

            deleted_date = item.get("deleted_date")
            modified = deleted_date.strftime("%Y-%m-%d %H:%M:%S") if isinstance(deleted_date, datetime) else ""
            modified_ts = deleted_date.timestamp() if isinstance(deleted_date, datetime) else None
            original_path = item.get("original_path") or item.get("recycled_path") or name

            row_data.append(
                {
                    "original_index": original_index,
                    "name": name,
                    "name_ci": name.casefold(),
                    "type": tr("file_type_folder") if is_dir else tr("file_type_file"),
                    "type_ci": (tr("file_type_folder") if is_dir else tr("file_type_file")).casefold(),
                    "size": size,
                    "size_kb": size_kb,
                    "modified": modified,
                    "modified_ts": modified_ts,
                    "is_dir": is_dir,
                    "image_index": image_utils.get_list_icon_index(owner, original_path or name, is_dir, is_hidden_item=False),
                    "full_path": original_path,
                }
            )

        sort_column = getattr(owner, "list_sort_column", None)
        sort_direction = int(getattr(owner, "list_sort_direction", 0) or 0)

        def _row_sort_key(row):
            if sort_column == 0:
                return (row["name_ci"], row["original_index"])
            if sort_column == 1:
                return (row["type_ci"], row["name_ci"], row["original_index"])
            if sort_column == 2:
                return (
                    row["size_kb"] is None,
                    row["size_kb"] if row["size_kb"] is not None else -1,
                    row["name_ci"],
                    row["original_index"],
                )
            if sort_column == 3:
                return (
                    row["modified_ts"] is None,
                    row["modified_ts"] if row["modified_ts"] is not None else -1,
                    row["name_ci"],
                    row["original_index"],
                )
            return row["original_index"]

        folders = [row for row in row_data if row["is_dir"]]
        files = [row for row in row_data if not row["is_dir"]]

        if sort_column is not None and sort_direction in (-1, 1):
            reverse = sort_direction < 0
            folders = sorted(folders, key=_row_sort_key, reverse=reverse)
            files = sorted(files, key=_row_sort_key, reverse=reverse)

        row_data = folders + files

        for row in row_data:
            item_index = owner.list.InsertItem(owner.list.GetItemCount(), row["name"], row["image_index"])
            owner._list_item_paths[item_index] = row["full_path"]
            owner.list.SetItem(item_index, 1, row["type"])
            owner.list.SetItem(item_index, 2, row["size"])
            owner.list.SetItem(item_index, 3, row["modified"])

        if hasattr(owner, "update_list_sort_header_icons"):
            owner.update_list_sort_header_icons()
        if hasattr(owner, "update_list_toolbar_buttons"):
            owner.update_list_toolbar_buttons()
        return

    try:
        items = os.listdir(path)
    except PermissionError:
        return

    filter_text = owner.search_box.GetValue().lower()
    row_data = []

    for original_index, name in enumerate(items):
        full_path = os.path.join(path, name)

        if not owner.show_hidden and is_hidden(full_path):
            continue

        if filter_text and filter_text not in name.lower():
            continue

        is_hidden_item = bool(is_hidden(full_path))

        if os.path.isdir(full_path):
            typ = tr("file_type_folder")
            size = ""
            size_kb = None
            is_dir = True
            image_index = image_utils.get_file_list_shell_icon_index(owner, full_path, is_hidden_item=is_hidden_item)
        else:
            extension = os.path.splitext(name)[1].lower().lstrip(".")
            typ = extension if extension else tr("file_type_file")
            try:
                size_kb = os.path.getsize(full_path) // 1024
                size = f"{size_kb} {tr('file_size_unit_kb')}"
            except Exception:
                size_kb = None
                size = ""
            is_dir = False
            image_index = image_utils.get_file_list_shell_icon_index(owner, full_path, is_hidden_item=is_hidden_item)

        try:
            modified_ts = os.path.getmtime(full_path)
            modified = datetime.fromtimestamp(modified_ts).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            modified_ts = None
            modified = ""

        row_data.append(
            {
                "original_index": original_index,
                "name": name,
                "name_ci": name.casefold(),
                "type": typ,
                "type_ci": typ.casefold(),
                "size": size,
                "size_kb": size_kb,
                "modified": modified,
                "modified_ts": modified_ts,
                "is_dir": is_dir,
                "image_index": image_index,
                "full_path": full_path,
            }
        )

    sort_column = getattr(owner, "list_sort_column", None)
    sort_direction = int(getattr(owner, "list_sort_direction", 0) or 0)

    def _row_sort_key(row):
        if sort_column == 0:
            return (row["name_ci"], row["original_index"])
        if sort_column == 1:
            return (row["type_ci"], row["name_ci"], row["original_index"])
        if sort_column == 2:
            return (
                row["size_kb"] is None,
                row["size_kb"] if row["size_kb"] is not None else -1,
                row["name_ci"],
                row["original_index"],
            )
        if sort_column == 3:
            return (
                row["modified_ts"] is None,
                row["modified_ts"] if row["modified_ts"] is not None else -1,
                row["name_ci"],
                row["original_index"],
            )
        return row["original_index"]

    folders = [row for row in row_data if row["is_dir"]]
    files = [row for row in row_data if not row["is_dir"]]

    if sort_column is not None and sort_direction in (-1, 1):
        reverse = sort_direction < 0
        folders = sorted(folders, key=_row_sort_key, reverse=reverse)
        files = sorted(files, key=_row_sort_key, reverse=reverse)

    row_data = folders + files

    for row in row_data:
        item_index = owner.list.InsertItem(owner.list.GetItemCount(), row["name"], row["image_index"])
        owner._list_item_paths[item_index] = row["full_path"]
        owner.list.SetItem(item_index, 1, row["type"])
        owner.list.SetItem(item_index, 2, row["size"])
        owner.list.SetItem(item_index, 3, row["modified"])

    if hasattr(owner, "update_list_sort_header_icons"):
        owner.update_list_sort_header_icons()
    if hasattr(owner, "update_list_toolbar_buttons"):
        owner.update_list_toolbar_buttons()
