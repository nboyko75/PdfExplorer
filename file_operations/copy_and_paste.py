import os
import shutil

import wx

from localization import tr

CLIPBOARD_MODE_COPY = "copy"
CLIPBOARD_MODE_CUT = "cut"


def _unique_preserving_order(paths):
    unique_paths = []
    seen = set()
    for path in paths:
        normalized = os.path.normcase(os.path.normpath(path))
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_paths.append(path)
    return unique_paths


def _set_clipboard(owner, paths, mode, update_toolbar_callback=None):
    if mode not in (CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT):
        return

    owner.file_clipboard_paths = [os.path.normpath(path) for path in paths]
    owner.file_clipboard_mode = mode

    if update_toolbar_callback is not None:
        update_toolbar_callback(owner)
    else:
        fallback = getattr(owner, "update_list_toolbar_buttons", None)
        if callable(fallback):
            fallback(owner)


def _get_clipboard_paths(owner):
    paths = getattr(owner, "file_clipboard_paths", None)
    if not isinstance(paths, list):
        return []
    return [path for path in paths if isinstance(path, str) and path]


def _get_clipboard_mode(owner):
    mode = getattr(owner, "file_clipboard_mode", None)
    if mode in (CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT):
        return mode
    return None


def _can_paste_into_directory(owner, target_dir):
    return bool(os.path.isdir(target_dir) and _get_clipboard_mode(owner) and _get_clipboard_paths(owner))


def _confirm_overwrite_existing_path(owner, target_path):
    if not isinstance(target_path, str) or not target_path:
        return False

    dialog = wx.MessageDialog(
        owner,
        tr("scan_overwrite_existing_prompt", path=target_path),
        tr("context_paste"),
        style=wx.YES_NO | wx.CANCEL | wx.ICON_WARNING,
    )
    try:
        result = dialog.ShowModal()
    finally:
        dialog.Destroy()

    if result == wx.ID_YES:
        return True
    if result == wx.ID_NO:
        return False
    return None


def _build_non_conflicting_path(target_path):
    if not os.path.exists(target_path):
        return target_path

    directory = os.path.dirname(target_path)
    base_name = os.path.basename(target_path)
    name, ext = os.path.splitext(base_name)

    for suffix in [" - Copy"] + [f" - Copy ({index})" for index in range(2, 1000)]:
        candidate = os.path.join(directory, f"{name}{suffix}{ext}")
        if not os.path.exists(candidate):
            return candidate

    raise FileExistsError(base_name)


def _resolve_tree_selection_path(owner):
    if not hasattr(owner, "tree") or owner.tree is None:
        return None

    selected_item = owner.tree.GetSelection()
    if selected_item and selected_item.IsOk():
        item_path = owner.tree.GetItemData(selected_item)
        if isinstance(item_path, str) and item_path:
            return os.path.normpath(item_path)

    if hasattr(owner, "path_box"):
        value = owner.path_box.GetValue()
        if isinstance(value, str) and value:
            return os.path.normpath(value)
    return None


def _resolve_paste_target_directory(path):
    if not isinstance(path, str) or not path:
        return None
    normalized = os.path.normpath(path)
    if os.path.isdir(normalized):
        return normalized
    if os.path.isfile(normalized):
        return os.path.dirname(normalized)
    return None


def _get_refresh_callback(owner):
    callback = getattr(owner, "_refresh_after_fs_change", None)
    if callable(callback):
        return callback

    try:
        from controls import filelist as filelist_module
    except Exception:
        return None

    callback = getattr(filelist_module, "_refresh_after_fs_change", None)
    return callback if callable(callback) else None


def _get_update_toolbar_callback(owner):
    callback = getattr(owner, "update_list_toolbar_buttons", None)
    if callable(callback):
        return callback

    try:
        from controls import filelist as filelist_module
    except Exception:
        return None

    callback = getattr(filelist_module, "update_list_toolbar_buttons", None)
    return callback if callable(callback) else None


def on_list_copy(owner, _):
    try:
        from controls.filelist import get_selected_list_paths
    except Exception:
        return

    paths = get_selected_list_paths(owner)
    if not paths:
        return
    _set_clipboard(owner, _unique_preserving_order(paths), CLIPBOARD_MODE_COPY, _get_update_toolbar_callback(owner))


def on_list_cut(owner, _):
    try:
        from controls.filelist import get_selected_list_paths
    except Exception:
        return

    paths = get_selected_list_paths(owner)
    if not paths:
        return
    _set_clipboard(owner, _unique_preserving_order(paths), CLIPBOARD_MODE_CUT, _get_update_toolbar_callback(owner))


def on_list_paste(owner, _):
    try:
        from controls.filelist import get_selected_list_paths
    except Exception:
        return
    paste_into_path(owner, owner.path_box.GetValue(), _get_refresh_callback(owner), _get_update_toolbar_callback(owner))


def on_tree_copy(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    _set_clipboard(owner, [tree_path], CLIPBOARD_MODE_COPY, _get_update_toolbar_callback(owner))


def on_tree_cut(owner, path=None):
    tree_path = path or _resolve_tree_selection_path(owner)
    if not tree_path or not os.path.exists(tree_path):
        return
    _set_clipboard(owner, [tree_path], CLIPBOARD_MODE_CUT, _get_update_toolbar_callback(owner))


def on_tree_paste(owner, path=None):
    target_path = path or _resolve_tree_selection_path(owner)
    paste_into_path(owner, target_path, _get_refresh_callback(owner), _get_update_toolbar_callback(owner))


def paste_into_path(
    owner,
    target_path,
    refresh_callback=None,
    update_toolbar_callback=None,
    confirm_overwrite_callback=None,
    can_paste_into_directory_callback=None,
    resolve_target_directory_callback=None,
    get_clipboard_mode_callback=None,
    get_clipboard_paths_callback=None,
    unique_preserving_order_callback=None,
    build_non_conflicting_path_callback=None,
):
    if refresh_callback is None:
        refresh_callback = _get_refresh_callback(owner)
    if update_toolbar_callback is None:
        update_toolbar_callback = _get_update_toolbar_callback(owner)
    if confirm_overwrite_callback is None:
        confirm_overwrite_callback = _confirm_overwrite_existing_path
    if can_paste_into_directory_callback is None:
        can_paste_into_directory_callback = _can_paste_into_directory
    if resolve_target_directory_callback is None:
        resolve_target_directory_callback = _resolve_paste_target_directory
    if get_clipboard_mode_callback is None:
        get_clipboard_mode_callback = _get_clipboard_mode
    if get_clipboard_paths_callback is None:
        get_clipboard_paths_callback = _get_clipboard_paths
    if unique_preserving_order_callback is None:
        unique_preserving_order_callback = _unique_preserving_order
    if build_non_conflicting_path_callback is None:
        build_non_conflicting_path_callback = _build_non_conflicting_path

    target_dir = resolve_target_directory_callback(target_path)
    if not can_paste_into_directory_callback(owner, target_dir):
        return

    clipboard_mode = get_clipboard_mode_callback(owner)
    source_paths = unique_preserving_order_callback(get_clipboard_paths_callback(owner))
    errors = []
    affected_dirs = [target_dir]
    moved_preview_target = None
    pending_cut_paths = []

    if clipboard_mode == CLIPBOARD_MODE_CUT:
        for source_path in source_paths:
            normalized_source = os.path.normpath(source_path)
            if os.path.exists(normalized_source):
                source_dir = os.path.dirname(normalized_source)
                if source_dir and os.path.isdir(source_dir):
                    affected_dirs.append(source_dir)

    affected_dirs = unique_preserving_order_callback(affected_dirs)

    for source_path in source_paths:
        normalized_source = os.path.normpath(source_path)
        if not os.path.exists(normalized_source):
            continue

        source_name = os.path.basename(normalized_source.rstrip("\\/"))
        destination_path = os.path.join(target_dir, source_name)
        overwrite_target = False

        if os.path.normcase(os.path.normpath(destination_path)) == os.path.normcase(normalized_source):
            continue

        if os.path.exists(destination_path):
            overwrite_choice = confirm_overwrite_callback(owner, destination_path)
            if overwrite_choice is None:
                continue
            if overwrite_choice is False:
                destination_path = build_non_conflicting_path_callback(destination_path)
            else:
                overwrite_target = True

        try:
            if clipboard_mode == CLIPBOARD_MODE_COPY:
                if os.path.isdir(normalized_source):
                    if overwrite_target and os.path.exists(destination_path):
                        shutil.rmtree(destination_path)
                    shutil.copytree(normalized_source, destination_path)
                else:
                    if overwrite_target and os.path.exists(destination_path):
                        os.remove(destination_path)
                    shutil.copy2(normalized_source, destination_path)
            else:
                if overwrite_target and os.path.exists(destination_path):
                    if os.path.isdir(destination_path):
                        shutil.rmtree(destination_path)
                    else:
                        os.remove(destination_path)
                shutil.move(normalized_source, destination_path)

            current_preview_path = getattr(owner, "current_preview_path", None)
            if clipboard_mode == CLIPBOARD_MODE_CUT and current_preview_path:
                if os.path.normcase(os.path.normpath(current_preview_path)) == os.path.normcase(normalized_source):
                    moved_preview_target = destination_path
        except Exception as exc:
            errors.append(f"{normalized_source}: {exc}")
            if clipboard_mode == CLIPBOARD_MODE_CUT:
                pending_cut_paths.append(normalized_source)

    if clipboard_mode == CLIPBOARD_MODE_CUT:
        owner.file_clipboard_paths = pending_cut_paths
        owner.file_clipboard_mode = CLIPBOARD_MODE_CUT if pending_cut_paths else None

    if refresh_callback is not None:
        refresh_callback(owner, affected_dirs=affected_dirs, preferred_preview_path=moved_preview_target)
    if update_toolbar_callback is not None:
        update_toolbar_callback(owner)

    if errors:
        wx.MessageBox("\n".join(errors), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
