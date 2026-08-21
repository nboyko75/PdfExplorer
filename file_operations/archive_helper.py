import os
import shutil
import subprocess
from contextlib import nullcontext

import wx

from localization import tr

_ARCHIVE_SUFFIXES = (
    ".tar.gz",
    ".tar.bz2",
    ".tar.xz",
    ".tar.zst",
    ".zip",
    ".rar",
    ".7z",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".cab",
)


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


def _extract_archive_file(archive_path, destination_dir):
    if not isinstance(archive_path, str) or not os.path.isfile(archive_path):
        raise FileNotFoundError(archive_path)

    destination_dir = os.path.normpath(destination_dir or os.path.dirname(archive_path))
    os.makedirs(destination_dir, exist_ok=True)

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


def _refresh_after_archive_change(owner, archive_path):
    if not isinstance(archive_path, str) or not archive_path:
        return

    archive_path = os.path.normpath(archive_path)
    archive_folder = os.path.dirname(archive_path)

    try:
        if hasattr(owner, "open_path"):
            owner.open_path(archive_folder)
        if hasattr(owner, "load_folder"):
            owner.load_folder(archive_folder)
        path_box = getattr(owner, "path_box", None)
        if path_box is not None and hasattr(path_box, "ChangeValue"):
            path_box.ChangeValue(archive_folder)
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


def _extract_selected_archive(owner, path):
    if not _is_archive_file(path):
        return False

    destination_dir = os.path.join(os.path.dirname(path), os.path.splitext(os.path.basename(path))[0])
    if os.path.exists(destination_dir):
        candidate = destination_dir
        index = 1
        while os.path.exists(candidate):
            candidate = f"{destination_dir} ({index})"
            index += 1
        destination_dir = candidate

    try:
        _extract_archive_file(path, destination_dir)
        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
        return False
