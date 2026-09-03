import os
from datetime import datetime

import file_operations.image_utils as image_utils
from common.system import is_hidden
from localization import tr
from controls.window_tools import update_settings


def save_last_folder(owner):
    current_folder = owner.path_box.GetValue()
    if os.path.isdir(current_folder):
        update_settings({"last_folder": current_folder})


def open_path(owner, path, add_history=True):
    if not os.path.isdir(path):
        return False

    if hasattr(owner, "confirm_preview_change") and not owner.confirm_preview_change(path):
        return False

    if add_history:
        owner.history = owner.history[:owner.history_index + 1]
        owner.history.append(path)
        owner.history_index += 1

    owner.path_box.ChangeValue(path)
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
        owner.open_path(target_path, add_history=False)


def go_forward(owner, _):
    if owner.history_index < len(owner.history) - 1:
        target_path = owner.history[owner.history_index + 1]
        owner.history_index += 1
        owner.open_path(target_path, add_history=False)


def load_folder(owner, path):
    owner.list.DeleteAllItems()

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
            image_index = image_utils.get_list_icon_index(owner, full_path, is_dir=True, is_hidden_item=is_hidden_item)
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
            image_index = image_utils.get_list_icon_index(owner, full_path, is_dir=False, is_hidden_item=is_hidden_item)

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
        owner.list.SetItem(item_index, 1, row["type"])
        owner.list.SetItem(item_index, 2, row["size"])
        owner.list.SetItem(item_index, 3, row["modified"])

    if hasattr(owner, "update_list_sort_header_icons"):
        owner.update_list_sort_header_icons()
    if hasattr(owner, "update_list_toolbar_buttons"):
        owner.update_list_toolbar_buttons()
