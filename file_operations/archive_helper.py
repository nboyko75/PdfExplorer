import os
import shutil
import subprocess
from contextlib import nullcontext
from zipfile import Path
from pathlib import Path as FilePath

import wx

from file_operations import copy_and_paste
from controls.window_tools import load_settings, update_settings
from localization import tr

_ARCHIVE_SUFFIXES = (".tar.gz", ".tar.bz2", ".tar.xz", ".tar.zst", ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".cab")


def _is_archive_file(path):
    if not isinstance(path, str):
        return False
    lower_path = os.path.normpath(path).lower()
    return any(lower_path.endswith(suffix) for suffix in _ARCHIVE_SUFFIXES)


def _build_archive_destination_path(path):
    if not isinstance(path, str) or not path:
        return ""
    normalized = os.path.normpath(path)
    if _is_archive_file(normalized):
        return normalized
    return f"{normalized}.zip"


def _run_command(command, cwd=None):
    run_kwargs = {
        "cwd": cwd,
        "capture_output": True,
        "text": True,
        "check": True,
    }

    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    try:
        return subprocess.run(command, **run_kwargs)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required command not found: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise RuntimeError(detail or f"Command failed: {' '.join(command)}") from exc


def _create_zip_archive(source_path, destination_path):
    if isinstance(source_path, (list, tuple)):
        source_paths = [path for path in source_path if isinstance(path, str) and os.path.exists(path)]
        if not source_paths:
            raise FileNotFoundError(str(source_path))

        destination_path = os.path.normpath(destination_path or _build_archive_destination_path(source_paths[0]))
        if any(os.path.abspath(destination_path) == os.path.abspath(path) for path in source_paths):
            raise ValueError("Archive destination must differ from the source path.")

        powershell = shutil.which("powershell")
        if powershell:
            escaped_paths = [path.replace('"', '""') for path in source_paths]
            quoted_paths = ", ".join(f'"{path}"' for path in escaped_paths)
            quoted_destination = destination_path.replace('"', '""')
            _run_command([
                powershell,
                "-NoProfile",
                "-Command",
                f'Compress-Archive -LiteralPath {quoted_paths} -DestinationPath "{quoted_destination}" -Force',
            ])
            return destination_path

        zip_executable = shutil.which("zip")
        if zip_executable:
            cwd = os.path.dirname(source_paths[0]) or os.getcwd()
            archive_name = os.path.basename(destination_path)
            arguments = [zip_executable, "-r", archive_name]
            for source in source_paths:
                arguments.append(os.path.basename(source))
            _run_command(arguments, cwd=cwd)
            return os.path.join(cwd, archive_name)

        raise RuntimeError("No system zip utility is available.")

    if not isinstance(source_path, str) or not os.path.exists(source_path):
        raise FileNotFoundError(source_path)

    destination_path = os.path.normpath(destination_path or _build_archive_destination_path(source_path))
    if os.path.exists(destination_path) and os.path.abspath(destination_path) == os.path.abspath(source_path):
        raise ValueError("Archive destination must differ from the source path.")

    powershell = shutil.which("powershell")
    if powershell:
        quoted_source = source_path.replace('"', '""')
        quoted_destination = destination_path.replace('"', '""')
        _run_command([
            powershell,
            "-NoProfile",
            "-Command",
            f'Compress-Archive -LiteralPath "{quoted_source}" -DestinationPath "{quoted_destination}" -Force',
        ])
        return destination_path

    zip_executable = shutil.which("zip")
    if zip_executable:
        source_dir = os.path.dirname(source_path) or os.getcwd()
        source_name = os.path.basename(source_path)
        archive_name = os.path.basename(destination_path)
        _run_command([zip_executable, "-r", archive_name, source_name], cwd=source_dir)
        return os.path.join(source_dir, archive_name)

    raise RuntimeError("No system zip utility is available.")


def _get_7z_executable():
    for executable_name in ("7z", "7za", "7zr"):
        candidate = shutil.which(executable_name)
        if candidate:
            return candidate
    return None


def _extract_archive_file(archive_path, destination_dir):
    if not isinstance(archive_path, str) or not os.path.isfile(archive_path):
        raise FileNotFoundError(archive_path)

    destination_dir = os.path.normpath(destination_dir or os.path.dirname(archive_path))
    os.makedirs(destination_dir, exist_ok=True)

    was_busy = wx.IsBusy() if hasattr(wx, "IsBusy") else False
    cursor_started = False
    if not was_busy and hasattr(wx, "BeginBusyCursor"):
        wx.BeginBusyCursor()
        cursor_started = True

    try:
        if archive_path.lower().endswith(".7z"):
            seven_zip_executable = _get_7z_executable()
            if seven_zip_executable:
                _run_command([
                    seven_zip_executable,
                    "x",
                    "-y",
                    "-o" + destination_dir,
                    archive_path,
                ])
                return destination_dir

        powershell = shutil.which("powershell")
        if powershell:
            quoted_archive = archive_path.replace('"', '""')
            quoted_destination = destination_dir.replace('"', '""')
            _run_command([
                powershell,
                "-NoProfile",
                "-Command",
                f'Expand-Archive -LiteralPath "{quoted_archive}" -DestinationPath "{quoted_destination}" -Force',
            ])
            return destination_dir

        unzip_executable = shutil.which("unzip")
        if unzip_executable:
            _run_command([unzip_executable, "-o", archive_path, "-d", destination_dir])
            return destination_dir

        tar_executable = shutil.which("tar")
        if tar_executable and not archive_path.lower().endswith(".zip"):
            _run_command([tar_executable, "-xf", archive_path, "-C", destination_dir])
            return destination_dir

        raise RuntimeError("No system archive extraction tool is available.")
    finally:
        if cursor_started and hasattr(wx, "EndBusyCursor"):
            wx.EndBusyCursor()


def _refresh_after_archive_change(owner, archive_path):
    if not isinstance(archive_path, str) or not archive_path:
        return

    archive_path = os.path.normpath(archive_path)
    archive_folder = os.path.dirname(archive_path)

    path_box = getattr(owner, "path_box", None)
    if path_box is not None and hasattr(path_box, "ChangeValue"):
        try:
            path_box.ChangeValue(archive_folder)
        except Exception:
            pass

    path_box = getattr(owner, "path_box", None)
    has_path_box_get_value = path_box is not None and hasattr(path_box, "GetValue")

    try:
        if hasattr(owner, "open_path") and (path_box is None or has_path_box_get_value):
            owner.open_path(archive_folder)
    except Exception:
        pass

    try:
        if hasattr(owner, "load_folder"):
            owner.load_folder(archive_folder)
    except Exception:
        pass

    try:
        if hasattr(owner, "tree"):
            import controls.tree_utils as tree_utils
            parent_item = tree_utils.find_tree_item_by_path(owner, archive_folder)
            if parent_item is not None and hasattr(parent_item, "IsOk") and parent_item.IsOk():
                tree_utils.refresh_tree_subtree(owner, parent_item, archive_folder)
    except Exception:
        pass

    try:
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(archive_path)
    except Exception:
        pass

    try:
        if hasattr(owner, "select_list_item_by_path"):
            owner.select_list_item_by_path(archive_path)
    except Exception:
        pass


def _archive_selected_paths(owner, paths):
    selected_paths = [path for path in (paths or []) if isinstance(path, str) and os.path.exists(path) and not _is_archive_file(path)]
    if not selected_paths:
        return False

    base_dir = os.path.dirname(selected_paths[0]) or os.getcwd()
    default_name = _build_archive_destination_path(selected_paths[0])
    default_value = os.path.basename(default_name)
    if len(selected_paths) > 1:
        default_value = "archive.zip"

    dialog = wx.TextEntryDialog(
        owner,
        tr("context_add_to_archive"),
        tr("context_add_to_archive"),
        value=default_value,
    )
    if dialog.ShowModal() != wx.ID_OK:
        dialog.Destroy()
        return False

    archive_name = dialog.GetValue().strip()
    dialog.Destroy()
    if not archive_name:
        return False

    if not os.path.splitext(archive_name)[1]:
        archive_name = f"{archive_name}.zip"

    destination_path = os.path.normpath(os.path.join(base_dir, archive_name))
    if not destination_path.lower().endswith(".zip"):
        destination_path = f"{destination_path}.zip"

    if os.path.exists(destination_path):
        candidate = destination_path
        index = 1
        while os.path.exists(candidate):
            candidate = f"{destination_path[:-4]} ({index}).zip" if destination_path.lower().endswith(".zip") else f"{destination_path} ({index})"
            index += 1
        destination_path = candidate

    try:
        cursor_context = owner.busy_cursor() if owner is not None and hasattr(owner, "busy_cursor") else nullcontext()
        with cursor_context:
            created_archive = _create_zip_archive(selected_paths, destination_path)
        _refresh_after_archive_change(owner, created_archive)
        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        return False


def _archive_selected_path(owner, path):
    if isinstance(path, (list, tuple)):
        return _archive_selected_paths(owner, path)
    if not isinstance(path, str) or not os.path.exists(path):
        return False
    if _is_archive_file(path):
        return False

    return _archive_selected_paths(owner, [path])


def _default_extract_destination(path, current_folder=None):
    if not _is_archive_file(path):
        return ""

    base_folder = current_folder if isinstance(current_folder, str) and current_folder and os.path.isdir(current_folder) else os.path.dirname(path) or os.getcwd()
    archive_name = os.path.splitext(os.path.basename(path))[0]
    if not archive_name:
        archive_name = "archive"
    else:
        archive_name = FilePath(archive_name).stem  # Remove additional extensions like .tar, .gz, etc.
    return os.path.normpath(os.path.join(base_folder, archive_name))


def _save_archive_extract_form_geometry(dialog):
    position = dialog.GetPosition()
    size = dialog.GetSize()
    update_settings({
        "archive_extract_form_position": [int(position.x), int(position.y)],
        "archive_extract_form_size": [int(size.x), int(size.y)],
    })


def _apply_archive_extract_form_geometry(dialog, settings=None):
    if settings is None:
        settings = load_settings()

    saved_position = settings.get("archive_extract_form_position")
    saved_size = settings.get("archive_extract_form_size")

    min_width, min_height = 360, 150
    default_width, default_height = 480, 180
    dialog.SetMinSize((min_width, min_height))
    dialog.SetSize((default_width, default_height))

    if isinstance(saved_size, list) and len(saved_size) == 2:
        width, height = int(saved_size[0]), int(saved_size[1])
        if width >= min_width and height >= min_height:
            dialog.SetSize((width, height))

    if isinstance(saved_position, list) and len(saved_position) == 2:
        x, y = int(saved_position[0]), int(saved_position[1])
        dialog.SetPosition((x, y))


def _show_extract_archive_into_dialog(owner, default_path):
    default_dir = default_path if isinstance(default_path, str) and default_path else os.getcwd()

    app_instance = wx.App.GetInstance() if hasattr(wx, "App") else None
    if app_instance is None:
        dialog = wx.TextEntryDialog(
            owner,
            tr("archive_extract_folder_label"),
            tr("context_extract_from_archive_into"),
            value=default_dir,
        )
        try:
            if dialog.ShowModal() != wx.ID_OK:
                return None
            selected_path = dialog.GetValue().strip()
            return selected_path or None
        finally:
            dialog.Destroy()

    dialog = wx.Dialog(owner, title=tr("context_extract_from_archive_into"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    _apply_archive_extract_form_geometry(dialog)
    panel = wx.Panel(dialog)
    main_sizer = wx.BoxSizer(wx.VERTICAL)

    folder_label = wx.StaticText(panel, label=tr("archive_extract_folder_label"))
    path_field = wx.TextCtrl(panel, value=default_dir)
    browse_button = wx.Button(panel, label=tr("search_browse_button"))
    browse_button.SetMinSize((90, -1))

    input_sizer = wx.BoxSizer(wx.HORIZONTAL)
    input_sizer.Add(path_field, 1, wx.EXPAND | wx.RIGHT, 6)
    input_sizer.Add(browse_button, 0, wx.ALIGN_CENTER_VERTICAL, 6)

    buttons = wx.StdDialogButtonSizer()
    ok_button = wx.Button(panel, wx.ID_OK, tr("ok_button"))
    cancel_button = wx.Button(panel, wx.ID_CANCEL, tr("cancel_button"))
    buttons.AddButton(ok_button)
    buttons.AddButton(cancel_button)
    buttons.Realize()

    main_sizer.Add(folder_label, 0, wx.EXPAND | wx.LEFT | wx.BOTTOM, 12)
    main_sizer.Add(input_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    main_sizer.Add(buttons, 0, wx.EXPAND | wx.ALL, 12)
    panel.SetSizer(main_sizer)
    main_sizer.Fit(dialog)

    def browse_for_folder(_event):
        chooser = wx.DirDialog(dialog, tr("archive_extract_select_folder_title"), defaultPath=path_field.GetValue() or default_dir)
        try:
            if chooser.ShowModal() == wx.ID_OK:
                chosen_path = chooser.GetPath()
                if chosen_path:
                    path_field.SetValue(chosen_path)
        finally:
            chooser.Destroy()

    browse_button.Bind(wx.EVT_BUTTON, browse_for_folder)
    ok_button.SetDefault()

    try:
        result = dialog.ShowModal()
        if result != wx.ID_OK:
            return None

        selected_path = path_field.GetValue().strip()
        return selected_path or None
    finally:
        try:
            _save_archive_extract_form_geometry(dialog)
        except Exception:
            pass
        dialog.Destroy()


def _extract_selected_archive(owner, path):
    if not _is_archive_file(path):
        return False

    try:
        current_folder = getattr(getattr(owner, "path_box", None), "GetValue", lambda: "")()
        default_dir = _default_extract_destination(path, current_folder)
        destination_dir = default_dir or (os.path.dirname(path) or os.getcwd())
        if not destination_dir:
            return False

        if os.path.exists(destination_dir):
            overwrite_choice = copy_and_paste._confirm_overwrite_existing_path(owner, destination_dir)
            if overwrite_choice is None:
                return False
            if overwrite_choice is False:
                destination_dir = copy_and_paste._build_non_conflicting_path(destination_dir)

        refresh_folder = current_folder if isinstance(current_folder, str) and current_folder and os.path.isdir(current_folder) else os.path.dirname(destination_dir) or os.getcwd()
        _extract_archive_file(path, destination_dir)

        try:
            if hasattr(owner, "load_folder"):
                owner.load_folder(refresh_folder)
        except Exception:
            pass

        try:
            if hasattr(owner, "tree"):
                import controls.tree_utils as tree_utils
                item = tree_utils.find_tree_item_by_path(owner, refresh_folder)
                if item is not None and hasattr(item, "IsOk") and item.IsOk():
                    tree_utils.refresh_tree_subtree(owner, item, refresh_folder)
        except Exception:
            pass

        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        return False


def _extract_selected_archive_into(owner, path):
    if not _is_archive_file(path):
        return False

    try:
        current_folder = getattr(getattr(owner, "path_box", None), "GetValue", lambda: "")()
        default_dir = _default_extract_destination(path, current_folder)
        target_dir = _show_extract_archive_into_dialog(owner, default_dir)
        if not target_dir:
            return False

        target_dir = os.path.normpath(target_dir)
        if os.path.exists(target_dir):
            overwrite_choice = copy_and_paste._confirm_overwrite_existing_path(owner, target_dir)
            if overwrite_choice is None:
                return False
            if overwrite_choice is False:
                target_dir = copy_and_paste._build_non_conflicting_path(target_dir)

        parent_dir = os.path.dirname(target_dir) or os.getcwd()
        refresh_folder = current_folder if isinstance(current_folder, str) and current_folder and os.path.isdir(current_folder) else parent_dir
        os.makedirs(target_dir, exist_ok=True)
        _extract_archive_file(path, target_dir)

        try:
            if hasattr(owner, "load_folder"):
                owner.load_folder(refresh_folder)
        except Exception:
            pass

        try:
            if hasattr(owner, "tree"):
                import controls.tree_utils as tree_utils
                item = tree_utils.find_tree_item_by_path(owner, refresh_folder)
                if item is not None and hasattr(item, "IsOk") and item.IsOk():
                    tree_utils.refresh_tree_subtree(owner, item, refresh_folder)
        except Exception:
            pass

        try:
            if hasattr(owner, "select_list_item_by_path"):
                owner.select_list_item_by_path(target_dir)
        except Exception:
            pass

        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        return False
