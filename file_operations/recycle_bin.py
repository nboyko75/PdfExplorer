import datetime
import os

import pythoncom
import win32com.client


RECYCLE_BIN_PATH = "shell:RecycleBinFolder"
CSIDL_BITBUCKET = 10


def is_virtual_shell_path(path):
    return isinstance(path, str) and path.lower().startswith("shell:")


def _convert_com_date(value):
    if value is None:
        return None

    if isinstance(value, datetime.datetime):
        return value

    try:
        return datetime.datetime.fromtimestamp(float(value))
    except (TypeError, ValueError, OSError):
        return None


def _normalize_path(path):
    if not isinstance(path, str) or not path:
        return ""
    return os.path.normcase(os.path.normpath(path))


def _match_recycle_bin_item(shell_item, target_path):
    normalized_target = _normalize_path(target_path)
    if not normalized_target:
        return False

    try:
        recycled_path = str(shell_item.Path or "")
        display_name = str(shell_item.Name or "")

        deleted_from = shell_item.ExtendedProperty(
            "System.Recycle.DeletedFrom"
        )
        deleted_from = str(deleted_from or "")

        original_path = (
            os.path.join(deleted_from, display_name)
            if deleted_from
            else ""
        )

        possible_paths = {
            _normalize_path(recycled_path),
            _normalize_path(original_path),
        }
        possible_paths.discard("")

        return normalized_target in possible_paths

    except Exception:
        return False


def restore_recycle_bin_items(paths):
    """Restore selected Recycle Bin items to their original locations."""
    if os.name != "nt":
        return False

    remaining_paths = {
        _normalize_path(path)
        for path in paths or []
        if isinstance(path, str) and path
    }
    remaining_paths.discard("")

    if not remaining_paths:
        return False

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        recycle_bin = shell.NameSpace(CSIDL_BITBUCKET)
        if recycle_bin is None:
            return False

        # Copy the collection because Restore modifies it.
        shell_items = list(recycle_bin.Items())
        restored_count = 0

        for shell_item in shell_items:
            try:
                recycled_path = _normalize_path(
                    str(shell_item.Path or "")
                )
            except Exception:
                continue

            if recycled_path not in remaining_paths:
                continue

            try:
                # "undelete" is the canonical Shell verb for Restore.
                shell_item.InvokeVerb("undelete")
                remaining_paths.remove(recycled_path)
                restored_count += 1
            except Exception:
                continue

        return restored_count > 0

    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def get_recycle_bin_items():
    """Return items currently displayed by the Windows Recycle Bin."""
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    try:
        shell = win32com.client.Dispatch("Shell.Application")
        recycle_bin = shell.NameSpace(CSIDL_BITBUCKET)
        if recycle_bin is None:
            return []

        result = []
        for shell_item in recycle_bin.Items():
            try:
                display_name = str(shell_item.Name or "")
                recycled_path = str(shell_item.Path or "")
                is_folder = bool(shell_item.IsFolder)

                deleted_from = shell_item.ExtendedProperty("System.Recycle.DeletedFrom")
                deleted_from = str(deleted_from or "")

                deleted_date = shell_item.ExtendedProperty("System.Recycle.DateDeleted")
                deleted_date = _convert_com_date(deleted_date)

                original_path = os.path.join(deleted_from, display_name) if deleted_from else display_name

                try:
                    size = int(shell_item.Size or 0)
                except (TypeError, ValueError):
                    size = 0

                result.append(
                    {
                        "name": display_name,
                        "original_path": original_path,
                        "recycled_path": recycled_path,
                        "deleted_from": deleted_from,
                        "deleted_date": deleted_date,
                        "size": size,
                        "is_dir": is_folder,
                    }
                )
            except Exception:
                continue

        return result
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
