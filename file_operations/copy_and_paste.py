import os
import shutil

import wx

from localization import tr

from common.consts import CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT, _OVERWRITE_DECISION


def _reset_overwrite_decision():
    global _OVERWRITE_DECISION
    _OVERWRITE_DECISION = None


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


def _clipboard_sequence_number():
    """Identify clipboard replacements, including copying the same paths again."""
    if os.name == "nt":
        try:
            import ctypes
            return ctypes.windll.user32.GetClipboardSequenceNumber()
        except Exception:
            pass
    return None


def _read_native_clipboard():
    """Return (paths, mode); None means the clipboard is temporarily unavailable."""
    if os.name == "nt":
        try:
            import win32clipboard
        except ImportError:
            pass
        else:
            try:
                win32clipboard.OpenClipboard()
                try:
                    if not win32clipboard.IsClipboardFormatAvailable(15):  # CF_HDROP
                        return [], None
                    paths = list(win32clipboard.GetClipboardData(15))
                    effect_format = win32clipboard.RegisterClipboardFormat("Preferred DropEffect")
                    mode = CLIPBOARD_MODE_COPY
                    if win32clipboard.IsClipboardFormatAvailable(effect_format):
                        effect = win32clipboard.GetClipboardData(effect_format)
                        if isinstance(effect, bytes) and len(effect) >= 4:
                            effect = int.from_bytes(effect[:4], "little")
                            if effect & 2 and not effect & 1:
                                mode = CLIPBOARD_MODE_CUT
                    return [os.path.normpath(p) for p in paths if isinstance(p, str) and p], mode
                finally:
                    win32clipboard.CloseClipboard()
            except Exception:
                # wx also supports CF_HDROP; try it if the native read failed.
                pass

    clipboard = getattr(wx, "TheClipboard", None)
    if clipboard is None or not hasattr(clipboard, "Open"):
        return None
    try:
        if not clipboard.Open():
            return None
        try:
            data = wx.FileDataObject()
            if not clipboard.GetData(data):
                return [], None
            paths = [os.path.normpath(p) for p in data.GetFilenames() if isinstance(p, str) and p]
            return paths, CLIPBOARD_MODE_COPY if paths else None
        finally:
            clipboard.Close()
    except Exception:
        return None


def _read_native_clipboard_paths():
    snapshot = _read_native_clipboard()
    return snapshot[0] if snapshot is not None else []


def _sync_clipboard(owner):
    sequence = _clipboard_sequence_number()
    own_sequence = getattr(owner, "_file_clipboard_sequence", None)
    snapshot = _read_native_clipboard()
    if snapshot is None:
        # Never paste stale paths while another application owns the clipboard.
        return [], None
    paths, mode = snapshot
    own_paths = getattr(owner, "_file_clipboard_written_paths", None)
    if paths and paths == own_paths and (sequence is None or sequence == own_sequence):
        # Our wx payload contains filenames; retain the local Copy/Cut intent.
        mode = getattr(owner, "_file_clipboard_written_mode", mode)
    owner.file_clipboard_paths = paths
    owner.file_clipboard_mode = mode
    return paths, mode


def _write_native_clipboard(paths, mode):
    if mode not in (CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT):
        return False

    clipboard = getattr(wx, "TheClipboard", None)
    if clipboard is None or not hasattr(clipboard, "Open"):
        return False

    data = wx.FileDataObject()
    for path in paths:
        if isinstance(path, str) and path:
            data.AddFile(path)

    try:
        if not clipboard.Open():
            return False
        try:
            if not clipboard.SetData(data):
                return False
            clipboard.Flush()
            return True
        finally:
            try:
                clipboard.Close()
            except Exception:
                pass
    except Exception:
        return False


def _set_clipboard(owner, paths, mode, update_toolbar_callback=None):
    if mode not in (CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT):
        return

    owner.file_clipboard_paths = [os.path.normpath(path) for path in paths]
    owner.file_clipboard_mode = mode
    if _write_native_clipboard(owner.file_clipboard_paths, mode):
        owner._file_clipboard_sequence = _clipboard_sequence_number()
        owner._file_clipboard_written_paths = list(owner.file_clipboard_paths)
        owner._file_clipboard_written_mode = mode

    if update_toolbar_callback is not None:
        if getattr(update_toolbar_callback, "__self__", None) is not None:
            update_toolbar_callback()
        else:
            update_toolbar_callback(owner)
    else:
        fallback = getattr(owner, "update_list_toolbar_buttons", None)
        if callable(fallback):
            if getattr(fallback, "__self__", None) is not None:
                fallback()
            else:
                fallback(owner)


def _get_clipboard_paths(owner):
    return _sync_clipboard(owner)[0]


def _get_clipboard_mode(owner):
    return _sync_clipboard(owner)[1]


def _can_paste_into_directory(owner, target_dir):
    if not isinstance(target_dir, str) or not target_dir or not os.path.isdir(target_dir):
        return False
    paths, mode = _sync_clipboard(owner)
    return bool(paths and mode)


def _confirm_overwrite_existing_path(owner, target_path):
    global _OVERWRITE_DECISION

    if not isinstance(target_path, str) or not target_path:
        return False

    if _OVERWRITE_DECISION is True:
        return True
    if _OVERWRITE_DECISION is False:
        return False

    yes_to_all_id = getattr(wx, "ID_YES_TO_ALL", wx.ID_YES + 1000)
    no_to_all_id = getattr(wx, "ID_NO_TO_ALL", wx.ID_NO + 1000)

    dialog = wx.Dialog(owner, title=tr("context_paste"))
    message = wx.StaticText(dialog, label=tr("scan_overwrite_existing_prompt", path=target_path))
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)

    buttons = [
        (wx.ID_YES, tr("confirm_yes")),
        (yes_to_all_id, tr("confirm_yes_to_all")),
        (wx.ID_NO, tr("confirm_no")),
        (no_to_all_id, tr("confirm_no_to_all")),
        (wx.ID_CANCEL, tr("cancel_button")),
    ]

    for button_id, label in buttons:
        button = wx.Button(dialog, button_id, label)
        button.Bind(wx.EVT_BUTTON, lambda event, result=button_id: dialog.EndModal(result))
        button_sizer.Add(button, 0, wx.LEFT | wx.RIGHT, 5)

    content_sizer = wx.BoxSizer(wx.VERTICAL)
    content_sizer.Add(message, 0, wx.ALL | wx.EXPAND, 12)
    content_sizer.Add(button_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 8)
    dialog.SetSizerAndFit(content_sizer)
    dialog.CentreOnParent()

    try:
        result = dialog.ShowModal()
    finally:
        dialog.Destroy()

    if result == wx.ID_YES:
        return True
    if result == wx.ID_NO:
        return False
    if result == yes_to_all_id:
        _OVERWRITE_DECISION = True
        return True
    if result == no_to_all_id:
        _OVERWRITE_DECISION = False
        return False
    if result == wx.ID_CANCEL:
        _OVERWRITE_DECISION = None
        return None
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
    _reset_overwrite_decision()
    try:
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

        if get_clipboard_mode_callback is _get_clipboard_mode and get_clipboard_paths_callback is _get_clipboard_paths:
            clipboard_paths, clipboard_mode = _sync_clipboard(owner)
        else:
            clipboard_mode = get_clipboard_mode_callback(owner)
            clipboard_paths = get_clipboard_paths_callback(owner)
        source_paths = unique_preserving_order_callback(clipboard_paths)
        if clipboard_mode not in (CLIPBOARD_MODE_COPY, CLIPBOARD_MODE_CUT) or not source_paths:
            return
        errors = []
        affected_dirs = [target_dir]
        moved_preview_target = None
        pending_cut_paths = []
        operation_aborted = False

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
                    operation_aborted = True
                    break
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

        if refresh_callback is not None and not operation_aborted:
            refresh_callback(owner, affected_dirs=affected_dirs, preferred_preview_path=moved_preview_target)
        if update_toolbar_callback is not None:
            update_toolbar_callback(owner)

        if errors:
            wx.MessageBox("\n".join(errors), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
    finally:
        _reset_overwrite_decision()
