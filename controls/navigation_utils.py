import os

import file_operations.image_utils as image_utils
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
    return True


def go_back(owner, _):
    if owner.history_index > 0:
        owner.history_index -= 1
        owner.open_path(owner.history[owner.history_index], add_history=False)


def go_forward(owner, _):
    if owner.history_index < len(owner.history) - 1:
        owner.history_index += 1
        owner.open_path(owner.history[owner.history_index], add_history=False)


def load_folder(owner, path):
    owner.list.DeleteAllItems()

    try:
        items = os.listdir(path)
    except PermissionError:
        return

    filter_text = owner.search_box.GetValue().lower()
    row_data = []

    for original_index, name in enumerate(items):
        if not owner.show_hidden and (name.startswith(".") or name.startswith("$")):
            continue

        if filter_text and filter_text not in name.lower():
            continue

        full = os.path.join(path, name)

        if os.path.isdir(full):
            typ = tr("file_type_folder")
            size = ""
            size_kb = None
            is_dir = True
            image_index = image_utils.get_list_icon_index(owner, full, is_dir=True)
        else:
            typ = tr("file_type_file")
            try:
                size_kb = os.path.getsize(full) // 1024
                size = f"{size_kb} {tr('file_size_unit_kb')}"
            except Exception:
                size_kb = None
                size = ""
            is_dir = False
            image_index = image_utils.get_list_icon_index(owner, full, is_dir=False)

        row_data.append(
            {
                "original_index": original_index,
                "name": name,
                "name_ci": name.casefold(),
                "type": typ,
                "type_ci": typ.casefold(),
                "size": size,
                "size_kb": size_kb,
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

    if hasattr(owner, "update_list_sort_header_icons"):
        owner.update_list_sort_header_icons()
    if hasattr(owner, "update_list_toolbar_buttons"):
        owner.update_list_toolbar_buttons()
