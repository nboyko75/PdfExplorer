import os

import image_utils
from localization import tr
from window_tools import update_settings


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

    for name in items:
        if not owner.show_hidden and (name.startswith(".") or name.startswith("$")):
            continue

        if filter_text and filter_text not in name.lower():
            continue

        full = os.path.join(path, name)

        if os.path.isdir(full):
            typ = tr("file_type_folder")
            size = ""
            image_index = image_utils.get_list_icon_index(owner, full, is_dir=True)
        else:
            typ = tr("file_type_file")
            try:
                size = f"{os.path.getsize(full)//1024} {tr('file_size_unit_kb')}"
            except Exception:
                size = ""
            image_index = image_utils.get_list_icon_index(owner, full, is_dir=False)

        item_index = owner.list.InsertItem(owner.list.GetItemCount(), name, image_index)
        owner.list.SetItem(item_index, 1, typ)
        owner.list.SetItem(item_index, 2, size)
