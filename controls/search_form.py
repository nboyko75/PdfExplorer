import fnmatch
import os
import re
import threading
import zipfile
from datetime import datetime
from xml.etree import ElementTree as ET

import wx

from common import date_utils as common_date_utils
from common.date_utils import (
    DatePickerCtrl,
    DatePickerEvent,
    DATE_PICKER_STYLE,
)
from common.search_match_utils import (
    _matches_date_filter,
    _matches_size_filter,
    _matches_text_query,
    _parse_date_value,
    _parse_size_kb,
)
from localization import tr
from controls.window_tools import load_settings, update_settings


def _show_date_picker_popup(parent_dialog, field_control, trigger_button=None, date_picker_name=None):
    if date_picker_name is None and isinstance(trigger_button, str):
        date_picker_name = trigger_button
        trigger_button = None
    return common_date_utils._show_date_picker_popup(
        parent_dialog,
        field_control,
        trigger_button,
        date_picker_name,
        wx_module=wx,
        picker_class=DatePickerCtrl,
        picker_event=DatePickerEvent,
    )


_COMMON_PARSE_DATE_VALUE = common_date_utils._parse_date_value
_COMMON_DATE_TO_WX_DATETIME = common_date_utils._date_to_wx_datetime


def _parse_date_value(value):
    return _COMMON_PARSE_DATE_VALUE(value)


def _date_to_wx_datetime(value):
    return _COMMON_DATE_TO_WX_DATETIME(value)


try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    import pythoncom
    import win32com.client as win32_client
except ImportError:  # pragma: no cover - optional runtime dependency
    pythoncom = None
    win32_client = None

_TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".csv",
    ".log",
    ".ini",
    ".cfg",
    ".json",
    ".xml",
    ".html",
    ".htm",
    ".sql",
    ".yaml",
    ".yml",
    ".toml",
    ".js",
    ".ts",
    ".py",
    ".java",
    ".cs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".php",
    ".rb",
    ".sh",
    ".ps1",
    ".bat",
}


def _split_file_mask(mask_value):
    if mask_value is None:
        return []
    tokens = []
    for chunk in re.split(r"[;,\s]+", str(mask_value).strip()):
        token = chunk.strip()
        if token:
            tokens.append(token)
    return tokens


def _normalize_file_mask(mask_value, include_word=False, include_excel=False):
    tokens = []
    for token in _split_file_mask(mask_value):
        lowered = token.lower()
        if lowered in {"*.doc?", "*.xls?"}:
            continue
        tokens.append(token)
    if include_word:
        tokens.append("*.doc?")
    if include_excel:
        tokens.append("*.xls?")
    return " ".join(tokens)


def _contains_file_mask_token(mask_value, token):
    token_name = (token or "").strip().lower()
    if not token_name:
        return False
    return any(chunk.lower() == token_name for chunk in _split_file_mask(mask_value))


def _safe_set_control_value(control, value, guard_name="_value_sync_guard"):
    if control is None:
        return
    if getattr(control, guard_name, False):
        return
    setattr(control, guard_name, True)
    try:
        control.SetValue(value)
    finally:
        setattr(control, guard_name, False)


def _sync_file_mask_related_checkboxes(file_mask_field, word_chk, excel_chk):
    if file_mask_field is None or word_chk is None or excel_chk is None:
        return
    mask_value = file_mask_field.GetValue() or ""
    _safe_set_control_value(word_chk, _contains_file_mask_token(mask_value, "*.doc?"), "_word_checkbox_sync_guard")
    _safe_set_control_value(excel_chk, _contains_file_mask_token(mask_value, "*.xls?"), "_excel_checkbox_sync_guard")


def _apply_file_mask_state(file_mask_field, word_chk, excel_chk):
    if file_mask_field is None:
        return
    if getattr(file_mask_field, "_value_sync_guard", False):
        return

    mask_value = file_mask_field.GetValue() or ""
    normalized = _normalize_file_mask(mask_value, word_chk.GetValue() if word_chk is not None else False, excel_chk.GetValue() if excel_chk is not None else False)
    if normalized == mask_value:
        _sync_file_mask_related_checkboxes(file_mask_field, word_chk, excel_chk)
        return

    _safe_set_control_value(file_mask_field, normalized, "_value_sync_guard")
    _sync_file_mask_related_checkboxes(file_mask_field, word_chk, excel_chk)


def _apply_date_filter_enabled(date_field, date_picker, enabled_chk, date_button=None):
    if date_field is None:
        return
    enabled = bool(enabled_chk.GetValue()) if enabled_chk is not None else True
    date_field.Enable(enabled)
    if date_picker is not None:
        date_picker.Enable(enabled)
    if date_button is not None:
        date_button.Enable(enabled)


def _matches_file_mask(file_path, mask_value):
    if not mask_value:
        return True

    file_name = os.path.basename(file_path)
    for pattern in _split_file_mask(mask_value):
        if fnmatch.fnmatch(file_name.lower(), pattern.lower()):
            return True
    return False


def _iter_candidate_files(start_folder, include_child_folders, file_mask=""):
    if not isinstance(start_folder, str) or not os.path.isdir(start_folder):
        return []

    if not include_child_folders:
        files = []
        for name in sorted(os.listdir(start_folder)):
            full_path = os.path.join(start_folder, name)
            if os.path.isfile(full_path) and _matches_file_mask(full_path, file_mask):
                files.append(full_path)
        return files

    result = []
    for root, dir_names, file_names in os.walk(start_folder):
        dir_names.sort()
        for file_name in sorted(file_names):
            file_path = os.path.join(root, file_name)
            if os.path.isfile(file_path) and _matches_file_mask(file_path, file_mask):
                result.append(file_path)
    return result


def _read_text_file(path):
    tried_encodings = ["utf-8", "utf-8-sig", "utf-16", "cp1252", "latin-1"]
    for encoding in tried_encodings:
        try:
            with open(path, "r", encoding=encoding, errors="strict") as handle:
                return handle.read()
        except (UnicodeDecodeError, OSError, ValueError):
            continue
    try:
        with open(path, "rb") as handle:
            raw_data = handle.read()
        return raw_data.decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _collect_xml_text(node):
    text_parts = []
    for element in node.iter():
        if element.text and element.text.strip():
            text_parts.append(element.text.strip())
        if element.tail and element.tail.strip():
            text_parts.append(element.tail.strip())
    return " ".join(text_parts)


def _read_office_zip_text(path):
    try:
        with zipfile.ZipFile(path, "r") as archive:
            text_parts = []
            for name in archive.namelist():
                if not name.endswith(".xml"):
                    continue
                try:
                    xml_root = ET.fromstring(archive.read(name))
                except ET.ParseError:
                    continue
                xml_text = _collect_xml_text(xml_root)
                if xml_text:
                    text_parts.append(xml_text)
            return " ".join(text_parts)
    except (zipfile.BadZipFile, OSError):
        return ""


def _read_pdf_text(path):
    if fitz is None:
        return ""
    try:
        document = fitz.open(path)
        try:
            pages = []
            for page in document:
                page_text = page.get_text("text")
                if page_text:
                    pages.append(page_text)
            return "\n".join(pages)
        finally:
            document.close()
    except Exception:
        return ""


def _read_office_com_text(path):
    if pythoncom is None or win32_client is None:
        return ""
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    try:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

        try:
            if ext in {".doc", ".docx", ".docm"}:
                app = win32_client.Dispatch("Word.Application")
                app.Visible = False
                document = app.Documents.Open(path, ReadOnly=True)
                try:
                    return document.Content.Text or ""
                finally:
                    document.Close(False)
                    app.Quit()

            if ext in {".xls", ".xlsx", ".xlsm"}:
                app = win32_client.Dispatch("Excel.Application")
                app.Visible = False
                workbook = app.Workbooks.Open(path, ReadOnly=True)
                try:
                    data = []
                    for sheet in workbook.Sheets:
                        used_range = sheet.UsedRange
                        if used_range is not None:
                            values = used_range.Value
                            if isinstance(values, list):
                                for row in values:
                                    if row is None:
                                        continue
                                    flattened = []
                                    for value in row:
                                        if value is None:
                                            flattened.append("")
                                        else:
                                            flattened.append(str(value))
                                    data.append(" ".join(flattened))
                    return "\n".join(data)
                finally:
                    workbook.Close(False)
                    app.Quit()

            if ext in {".ppt", ".pptx", ".pptm"}:
                app = win32_client.Dispatch("PowerPoint.Application")
                presentation = app.Presentations.Open(path, WithWindow=False)
                try:
                    parts = []
                    for slide in presentation.Slides:
                        for shape in slide.Shapes:
                            try:
                                if hasattr(shape, "TextFrame") and shape.TextFrame is not None:
                                    parts.append(shape.TextFrame.TextRange.Text)
                            except Exception:
                                continue
                    return "\n".join(part for part in parts if part)
                finally:
                    presentation.Close()
                    app.Quit()
        except Exception:
            return ""
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return ""


def _extract_text_from_file(path):
    if not isinstance(path, str) or not os.path.isfile(path):
        return ""

    _, ext = os.path.splitext(path)
    ext = ext.lower()

    if ext == ".pdf":
        return _read_pdf_text(path)

    if ext in {".docx", ".xlsx", ".pptx", ".docm", ".xlsm", ".pptm"}:
        text = _read_office_zip_text(path)
        if text:
            return text
        return _read_office_com_text(path)

    if ext in {".doc", ".xls", ".ppt"}:
        return _read_office_com_text(path)

    if ext in _TEXT_EXTENSIONS:
        return _read_text_file(path)

    return ""


def _collect_search_matches(
    query,
    folder,
    mode="text",
    include_child_folders=True,
    stop_event=None,
    on_status=None,
    file_mask="",
    case_sensitive=True,
    whole_word=False,
    date_mode=0,
    date_from=None,
    date_to=None,
    size_mode=0,
    size_from=None,
    size_to=None,
):
    if not isinstance(query, str):
        return []

    query = query.strip()
    if not query:
        return []

    normalized_mode = (mode or "text").lower()
    if normalized_mode == "regex":
        try:
            if whole_word:
                pattern = re.compile(rf"(?<!\w)(?:{query})(?!\w)", 0 if case_sensitive else re.IGNORECASE)
            else:
                pattern = re.compile(query, 0 if case_sensitive else re.IGNORECASE)
        except re.error as exc:
            raise ValueError(str(exc)) from exc
    else:
        pattern = None

    if not isinstance(folder, str) or not os.path.isdir(folder):
        return []

    matches = []
    for file_path in _iter_candidate_files(folder, include_child_folders, file_mask=file_mask):
        if stop_event is not None and stop_event.is_set():
            return matches

        if not os.path.isfile(file_path):
            continue

        if not _matches_date_filter(file_path, date_mode=date_mode, date_from=date_from, date_to=date_to):
            continue
        if not _matches_size_filter(file_path, size_mode=size_mode, size_from=size_from, size_to=size_to):
            continue

        if on_status is not None:
            try:
                on_status(folder, file_path)
            except Exception:
                pass

        content = _extract_text_from_file(file_path)
        if stop_event is not None and stop_event.is_set():
            return matches
        if not content:
            continue

        if pattern is not None:
            if pattern.search(content):
                matches.append(file_path)
        else:
            if _matches_text_query(content, query, case_sensitive=case_sensitive, whole_word=whole_word):
                matches.append(file_path)
    return matches


def search_files(
    query,
    folder,
    mode="text",
    include_child_folders=True,
    file_mask="",
    case_sensitive=False,
    whole_word=False,
    date_mode=0,
    date_from=None,
    date_to=None,
    size_mode=0,
    size_from=None,
    size_to=None,
):
    return _collect_search_matches(
        query,
        folder,
        mode=mode,
        include_child_folders=include_child_folders,
        file_mask=file_mask,
        case_sensitive=case_sensitive,
        whole_word=whole_word,
        date_mode=date_mode,
        date_from=date_from,
        date_to=date_to,
        size_mode=size_mode,
        size_from=size_from,
        size_to=size_to,
    )


def _get_stop_button_label(stopped=False):
    return tr("search_stop_button")


def _get_pause_button_label(paused=False):
    return _get_stop_button_label()


def _format_search_status(folder_name, file_name=None):
    if file_name:
        left = f"{tr('search_status_folder')}: {os.path.dirname(file_name) or folder_name}"
        right = f"{tr('search_status_file')}: {os.path.basename(file_name)}"
        return left, right

    left = f"{tr('search_status_folder')}: {folder_name}" if folder_name else ""
    return left, ""


def _load_search_history():
    settings = load_settings()
    values = settings.get("search_history", [])
    if not isinstance(values, list):
        return []
    history = []
    seen = set()
    for item in values:
        if not isinstance(item, str):
            continue
        cleaned = item.strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        history.append(cleaned)
        seen.add(key)
    return history[:30]


def _save_search_history(query_value):
    if not isinstance(query_value, str):
        return
    cleaned = query_value.strip()
    if not cleaned:
        return

    settings = load_settings()
    history = settings.get("search_history", [])
    if not isinstance(history, list):
        history = []

    normalized = []
    seen = set()
    for item in history:
        if not isinstance(item, str):
            continue
        candidate = item.strip()
        if not candidate:
            continue
        key = candidate.lower()
        if key in seen:
            continue
        normalized.append(candidate)
        seen.add(key)

    if cleaned.lower() in seen:
        normalized = [item for item in normalized if item.lower() != cleaned.lower()]
    normalized.insert(0, cleaned)
    trimmed = normalized[:30]
    update_settings({"search_history": trimmed})


def _sync_query_history(query_field, current_text=None):
    if query_field is None:
        return
    if getattr(query_field, "_query_history_syncing", False):
        return

    text_value = (current_text if current_text is not None else query_field.GetValue())
    if text_value is None:
        text_value = ""
    text_value = str(text_value).strip()

    history = _load_search_history()
    filtered = [item for item in history if not text_value or text_value.lower() in item.lower()]

    current_value = ""
    try:
        current_value = query_field.GetValue()
    except Exception:
        current_value = ""
    current_value = "" if current_value is None else str(current_value)

    query_field._query_history_syncing = True
    try:
        query_field.SetItems(filtered[:30])
    finally:
        query_field._query_history_syncing = False

    if text_value:
        try:
            query_field.SetValue(text_value)
        except Exception:
            pass
    elif current_value:
        try:
            query_field.SetValue(current_value)
        except Exception:
            pass

    # Do not manually reopen the ComboBox dropdown here. The dropdown is already
    # owned by the user action that triggered this refresh, and re-entering Popup()
    # causes recursive EVT_COMBOBOX_DROPDOWN cycles. Updating the item list is
    # enough to refresh the history while the dropdown is open.
    _ = filtered


def _save_search_form_state(
    dialog,
    query_value,
    folder_value,
    file_mask_value,
    include_child_value,
    mode_index,
    word_value,
    excel_value,
    case_sensitive_value,
    whole_word_value,
    date_mode_value,
    date_from_value,
    date_to_value,
    date_from_enabled_value,
    date_to_enabled_value,
    size_mode_value,
    size_from_value,
    size_to_value,
):
    try:
        position = dialog.GetPosition()
        size = dialog.GetSize()
        update_settings(
            {
                "search_form_position": [int(position.x), int(position.y)],
                "search_form_size": [int(size.x), int(size.y)],
                "search_form_query": query_value,
                "search_form_folder": folder_value,
                "search_form_file_mask": file_mask_value,
                "search_form_include_child_folders": bool(include_child_value),
                "search_form_mode_index": int(mode_index),
                "search_form_word": bool(word_value),
                "search_form_excel": bool(excel_value),
                "search_form_case_sensitive": bool(case_sensitive_value),
                "search_form_whole_word": bool(whole_word_value),
                "search_form_date_mode": int(date_mode_value),
                "search_form_date_from": date_from_value,
                "search_form_date_to": date_to_value,
                "search_form_date_from_enabled": bool(date_from_enabled_value),
                "search_form_date_to_enabled": bool(date_to_enabled_value),
                "search_form_size_mode": int(size_mode_value),
                "search_form_size_from": size_from_value,
                "search_form_size_to": size_to_value,
            }
        )
    except Exception:
        pass


def _restore_search_form_state(settings):
    state = {}
    if isinstance(settings, dict):
        state = settings
    return {
        "query": state.get("search_form_query", ""),
        "folder": state.get("search_form_folder", ""),
        "file_mask": state.get("search_form_file_mask", ""),
        "include_child": bool(state.get("search_form_include_child_folders", True)),
        "mode_index": int(state.get("search_form_mode_index", 0) or 0),
        "word": bool(state.get("search_form_word", False)),
        "excel": bool(state.get("search_form_excel", False)),
        "case_sensitive": bool(state.get("search_form_case_sensitive", True)),
        "whole_word": bool(state.get("search_form_whole_word", False)),
        "date_mode": int(state.get("search_form_date_mode", 0) or 0),
        "date_from": state.get("search_form_date_from", ""),
        "date_to": state.get("search_form_date_to", ""),
        "date_from_enabled": bool(state.get("search_form_date_from_enabled", bool(state.get("search_form_date_from", "")))),
        "date_to_enabled": bool(state.get("search_form_date_to_enabled", bool(state.get("search_form_date_to", "")))),
        "size_mode": int(state.get("search_form_size_mode", 0) or 0),
        "size_from": state.get("search_form_size_from", ""),
        "size_to": state.get("search_form_size_to", ""),
        "position": state.get("search_form_position"),
        "size": state.get("search_form_size"),
    }


def _browse_for_folder(dialog, current_value):
    default_dir = current_value.strip() if current_value and os.path.isdir(current_value) else os.getcwd()
    chooser = wx.DirDialog(dialog, tr("search_select_folder_title"), defaultPath=default_dir)
    if chooser.ShowModal() == wx.ID_OK:
        return chooser.GetPath()
    return None


def show_search_form(owner):
    existing_dialog = getattr(owner, "_search_form_dialog", None)
    if existing_dialog is not None and existing_dialog and existing_dialog.IsShown():
        existing_dialog.Raise()
        return existing_dialog

    settings = load_settings()
    restored_state = _restore_search_form_state(settings)
    dialog = wx.Dialog(owner, title=tr("search_in_files_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    try:
        icon = wx.ArtProvider.GetIcon(wx.ART_FIND, client=wx.ART_TOOLBAR, size=(16, 16))
        if icon:
            dialog.SetIcon(icon)
    except Exception:
        pass
    owner._search_form_dialog = dialog
    panel = wx.Panel(dialog)

    # ---------- Top search controls ----------
    main = wx.BoxSizer(wx.VERTICAL)

    # Search text + file mask
    top_grid = wx.FlexGridSizer(rows=2, cols=4, hgap=10, vgap=7)
    top_grid.AddGrowableCol(1, 1)

    query_label = wx.StaticText(panel, label=tr("search_query_label"))
    query_label.SetMinSize((130, -1))
    query_field = wx.ComboBox(panel, value=restored_state["query"], choices=_load_search_history(), style=wx.CB_DROPDOWN | wx.TE_PROCESS_ENTER)
    query_field.SetMinSize((300, -1))

    file_mask_label = wx.StaticText(panel, label=tr("search_file_mask_label"))
    file_mask_label.SetMinSize((80, -1))
    file_mask_field = wx.TextCtrl(panel, value=restored_state["file_mask"], style=wx.TE_PROCESS_ENTER)
    file_mask_field.SetMinSize((120, -1))
    clear_mask_btn = wx.Button(panel, label="x")
    clear_mask_btn.SetToolTip(tr("search_clear_mask_tooltip"))
    clear_mask_btn.SetMinSize((28, -1))
    word_chk = wx.CheckBox(panel, label=tr("search_word_checkbox"))
    word_chk.SetValue(bool(restored_state["word"]))
    excel_chk = wx.CheckBox(panel, label=tr("search_excel_checkbox"))
    excel_chk.SetValue(bool(restored_state["excel"]))

    file_mask_row = wx.BoxSizer(wx.HORIZONTAL)
    file_mask_row.Add(file_mask_field, 1, wx.EXPAND | wx.RIGHT, 2)
    file_mask_row.Add(clear_mask_btn, 0, wx.EXPAND)

    top_grid.Add(query_label, 0, wx.ALIGN_CENTER_VERTICAL)
    top_grid.Add(query_field, 1, wx.EXPAND | wx.RIGHT, 10)
    top_grid.Add(file_mask_label, 0, wx.ALIGN_CENTER_VERTICAL)
    top_grid.Add(file_mask_row, 1, wx.EXPAND)

    folder_label = wx.StaticText(panel, label=tr("search_folder_label"))
    folder_field = wx.TextCtrl(panel, value=restored_state["folder"], style=wx.TE_PROCESS_ENTER)
    folder_field.SetMinSize((225, -1))
    folder_row = wx.BoxSizer(wx.HORIZONTAL)
    file_mask_box = wx.BoxSizer(wx.HORIZONTAL)
 
    browse_btn = wx.Button(panel, label=tr("search_browse_button"))
    browse_btn.SetMinSize((75, -1))

    folder_row.Add(folder_field, 1, wx.EXPAND | wx.RIGHT, 10)
    folder_row.Add(browse_btn, 0, wx.RIGHT, 10)
    file_mask_box.Add(word_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)
    file_mask_box.Add(excel_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 10)

    top_grid.Add(folder_label, 0, wx.ALIGN_CENTER_VERTICAL)
    top_grid.Add(folder_row, 1, wx.EXPAND)
    top_grid.Add((1, 1))
    top_grid.Add(file_mask_box, 0, wx.EXPAND)

    main.Add(top_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

    # Include child folders
    options = wx.BoxSizer(wx.HORIZONTAL)
    include_child_chk = wx.CheckBox(panel, label=tr("search_include_subfolders"))
    include_child_chk.SetValue(bool(restored_state["include_child"]))
    options.Add(include_child_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 155)
 
    main.Add(options, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

    # ---------- Search mode ----------
    mode_box = wx.StaticBoxSizer(wx.StaticBox(panel, label=""), wx.HORIZONTAL)
    text_radio = wx.RadioButton(panel, label=tr("search_mode_text"), style=wx.RB_GROUP)
    regex_radio = wx.RadioButton(panel, label=tr("search_mode_regex"))
    case_sensitive_chk = wx.CheckBox(panel, label=tr("search_case_sensitive_checkbox"))
    case_sensitive_chk.SetValue(bool(restored_state["case_sensitive"]))
    whole_word_chk = wx.CheckBox(panel, label=tr("search_whole_word_checkbox"))

    mode_box.Add(text_radio, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 18)
    mode_box.Add(regex_radio, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 18)
    mode_box.Add(case_sensitive_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 18)
    mode_box.Add(whole_word_chk, 0, wx.ALIGN_CENTER_VERTICAL)

    main.Add(mode_box, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

    # ---------- Filters ----------
    filters = wx.BoxSizer(wx.HORIZONTAL)

    # Date filter
    date_box = wx.StaticBoxSizer(wx.StaticBox(panel, label=tr("search_date_filter_label")), wx.HORIZONTAL)

    date_from_enable_chk = wx.CheckBox(panel, label="")
    date_from_enable_chk.SetValue(bool(restored_state.get("date_from_enabled", bool(restored_state.get("date_from", "")))))
    date_box.Add(date_from_enable_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    date_box.Add(wx.StaticText(panel, label=tr("search_date_from")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    date_from_field = wx.TextCtrl(panel, value=str(restored_state.get("date_from", "")), style=wx.TE_PROCESS_ENTER)
    date_from_field.SetMinSize((100, -1))
    date_from_picker = None
    date_from_btn = wx.Button(panel, label="📅")
    date_from_btn.SetToolTip(tr("search_pick_date_tooltip"))
    date_from_btn.SetMinSize((28, -1))

    def show_date_picker_for_from(_event=None):
        _show_date_picker_popup(dialog, date_from_field, date_from_btn, "from")

    date_from_row = wx.BoxSizer(wx.HORIZONTAL)
    date_from_row.Add(date_from_field, 1, wx.EXPAND | wx.RIGHT, 5)
    date_from_row.Add(date_from_btn, 0, wx.ALIGN_CENTER_VERTICAL)
    date_box.Add(date_from_row, 1, wx.EXPAND | wx.RIGHT, 10)

    date_to_enable_chk = wx.CheckBox(panel, label="")
    date_to_enable_chk.SetValue(bool(restored_state.get("date_to_enabled", bool(restored_state.get("date_to", "")))))
    date_box.Add(date_to_enable_chk, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    date_box.Add(wx.StaticText(panel, label=tr("search_date_to")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    date_to_field = wx.TextCtrl(panel, value=str(restored_state.get("date_to", "")), style=wx.TE_PROCESS_ENTER)
    date_to_field.SetMinSize((100, -1))
    date_to_picker = None
    date_to_btn = wx.Button(panel, label="📅")
    date_to_btn.SetToolTip(tr("search_pick_date_tooltip"))
    date_to_btn.SetMinSize((28, -1))

    def show_date_picker_for_to(_event=None):
        _show_date_picker_popup(dialog, date_to_field, date_to_btn, "to")

    date_to_row = wx.BoxSizer(wx.HORIZONTAL)
    date_to_row.Add(date_to_field, 1, wx.EXPAND | wx.RIGHT, 5)
    date_to_row.Add(date_to_btn, 0, wx.ALIGN_CENTER_VERTICAL)
    date_box.Add(date_to_row, 1, wx.EXPAND)

    date_from_btn.Bind(wx.EVT_BUTTON, show_date_picker_for_from)
    date_to_btn.Bind(wx.EVT_BUTTON, show_date_picker_for_to)

    _apply_date_filter_enabled(date_from_field, date_from_picker, date_from_enable_chk, date_from_btn)
    _apply_date_filter_enabled(date_to_field, date_to_picker, date_to_enable_chk, date_to_btn)

    filters.Add(date_box, 1, wx.EXPAND | wx.RIGHT, 10)

    # Size filter
    size_box = wx.StaticBoxSizer(wx.StaticBox(panel, label=tr("search_size_filter_label")), wx.HORIZONTAL)
    size_box.Add(wx.StaticText(panel, label=tr("search_size_from")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    size_from_field = wx.TextCtrl(panel, value=str(restored_state.get("size_from", "")), style=wx.TE_PROCESS_ENTER)
    size_from_field.SetMinSize((100, -1))
    size_box.Add(size_from_field, 0, wx.RIGHT, 10)

    size_box.Add(wx.StaticText(panel, label=tr("search_size_to")), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
    size_to_field = wx.TextCtrl(panel, value=str(restored_state.get("size_to", "")), style=wx.TE_PROCESS_ENTER)
    size_to_field.SetMinSize((100, -1))
    size_box.Add(size_to_field, 0)

    size_box_measure = wx.StaticText(panel, label="KB")
    size_box_measure.SetMinSize((15, -1))
    size_box.Add(size_box_measure, 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT | wx.RIGHT, 5)

    filters.Add(size_box, 1, wx.EXPAND)

    main.Add(filters, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)

    search_btn = wx.Button(panel, label=tr("search_button"))
    stop_btn = wx.Button(panel, label=tr("search_stop_button"))
    stop_btn.Enable(False)
    quit_btn = wx.Button(panel, label=tr("search_cancel_button"))

    result_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN | wx.LC_SINGLE_SEL)
    result_list.InsertColumn(0, tr("search_result_short_name"), width=220)
    result_list.InsertColumn(1, tr("search_result_full_name"), width=520)

    status_bar = wx.StatusBar(panel, style=wx.STB_DEFAULT_STYLE)
    status_bar.SetFieldsCount(2)
    status_bar.SetStatusWidths([-2, -1])
    status_bar.SetStatusText("", 0)
    status_bar.SetStatusText("", 1)

    button_row = wx.BoxSizer(wx.HORIZONTAL)
    button_row.AddStretchSpacer()
    button_row.Add(search_btn, 0, wx.RIGHT, 8)
    button_row.Add(stop_btn, 0, wx.RIGHT, 8)
    button_row.Add(quit_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(result_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 12)
    root_sizer.Add(status_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 2)

    main.Add(root_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 2)
    panel.SetSizer(main)

    default_path = getattr(owner, "path_box", None)
    restored_folder = str(restored_state.get("folder") or "").strip()
    folder_value = restored_folder
    if not folder_value and default_path is not None:
        current_path = default_path.GetValue().strip()
        if current_path and os.path.isdir(current_path):
            folder_value = current_path
    if not folder_value:
        folder_value = os.path.expanduser("~")
    folder_field.SetValue(folder_value)

    def sync_file_mask_field():
        _apply_file_mask_state(file_mask_field, word_chk, excel_chk)

    def clear_mask(_event=None):
        _safe_set_control_value(file_mask_field, "", "_value_sync_guard")
        _safe_set_control_value(word_chk, False, "_word_checkbox_sync_guard")
        _safe_set_control_value(excel_chk, False, "_excel_checkbox_sync_guard")
        _sync_file_mask_related_checkboxes(file_mask_field, word_chk, excel_chk)

    def set_status(folder_name, file_name=None):
        left_text, right_text = _format_search_status(folder_name, file_name)
        status_bar.SetStatusText(left_text, 0)
        status_bar.SetStatusText(right_text, 1)

    def save_geometry():
        _save_search_form_state(
            dialog,
            query_field.GetValue(),
            folder_field.GetValue(),
            file_mask_field.GetValue(),
            include_child_chk.GetValue(),
            regex_radio.GetValue(),
            word_chk.GetValue(),
            excel_chk.GetValue(),
            case_sensitive_chk.GetValue(),
            whole_word_chk.GetValue(),
            int(date_from_enable_chk.GetValue() or date_to_enable_chk.GetValue()),
            date_from_field.GetValue(),
            date_to_field.GetValue(),
            date_from_enable_chk.GetValue(),
            date_to_enable_chk.GetValue(),
            0,
            size_from_field.GetValue(),
            size_to_field.GetValue(),
        )

    def finish_search(matches):
        result_list.DeleteAllItems()
        for match_path in matches:
            index = result_list.InsertItem(result_list.GetItemCount(), os.path.basename(match_path))
            result_list.SetItem(index, 1, match_path)
        if matches:
            status_bar.SetStatusText(tr("search_finished_status"), 0)
            status_bar.SetStatusText(f"{len(matches)} {tr('search_results_count')}", 1)
        else:
            status_bar.SetStatusText(tr("search_finished_status"), 0)
            status_bar.SetStatusText(tr("search_no_results"), 1)

    search_state = {"running": False, "stopped": False, "thread": None, "stop_event": None}

    def reset_search_ui():
        search_state["running"] = False
        search_state["stopped"] = False
        search_state["thread"] = None
        search_state["stop_event"] = None
        stop_btn.Enable(False)
        search_btn.Enable(True)

    def stop_search(_event=None):
        if not search_state["running"]:
            return
        search_state["stopped"] = True
        stop_event = search_state.get("stop_event")
        if stop_event is not None:
            stop_event.set()
        stop_btn.Enable(False)
        status_bar.SetStatusText(tr("search_paused_status"), 0)
        status_bar.SetStatusText("", 1)

    def refresh_query_history(_event=None):
        return

    def run_search(_event=None):
        text_value = query_field.GetValue().strip()
        folder_value = folder_field.GetValue().strip()
        if not text_value:
            wx.MessageBox(tr("search_query_required"), tr("app_title"), style=wx.OK | wx.ICON_INFORMATION)
            return
        if not folder_value or not os.path.isdir(folder_value):
            wx.MessageBox(tr("search_no_folder"), tr("app_title"), style=wx.OK | wx.ICON_INFORMATION)
            return

        _save_search_history(text_value)
        _sync_query_history(query_field, text_value)

        if search_state["running"]:
            return

        stop_event = threading.Event()
        sync_file_mask_field()
        mask_value = file_mask_field.GetValue().strip()
        date_from_enabled = bool(date_from_enable_chk.GetValue())
        date_to_enabled = bool(date_to_enable_chk.GetValue())
        date_mode = 1 if ((date_from_enabled and date_from_field.GetValue().strip()) or (date_to_enabled and date_to_field.GetValue().strip())) else 0
        size_mode = 1 if (size_from_field.GetValue().strip() or size_to_field.GetValue().strip()) else 0

        search_state["running"] = True
        search_state["stopped"] = False
        search_state["stop_event"] = stop_event
        search_btn.Enable(False)
        stop_btn.Enable(True)
        set_status(folder_value, "")

        def worker():
            try:
                matches = _collect_search_matches(
                    text_value,
                    folder_value,
                    mode="regex" if regex_radio.GetValue() else "text",
                    include_child_folders=include_child_chk.GetValue(),
                    stop_event=stop_event,
                    on_status=lambda current_folder, file_name: wx.CallAfter(set_status, current_folder, file_name),
                    file_mask=mask_value,
                    case_sensitive=case_sensitive_chk.GetValue(),
                    whole_word=whole_word_chk.GetValue(),
                    date_mode=date_mode,
                    date_from=date_from_field.GetValue() if date_from_enabled else "",
                    date_to=date_to_field.GetValue() if date_to_enabled else "",
                    size_mode=size_mode,
                    size_from=size_from_field.GetValue(),
                    size_to=size_to_field.GetValue(),
                )
                if stop_event.is_set():
                    wx.CallAfter(stop_search)
                    return
                wx.CallAfter(finish_search, matches)
            except re.error:
                wx.CallAfter(wx.MessageBox, tr("search_invalid_regex", error=text_value), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
            except Exception as exc:
                wx.CallAfter(wx.MessageBox, str(exc), tr("app_title"), style=wx.OK | wx.ICON_ERROR)
            finally:
                wx.CallAfter(reset_search_ui)

        thread = threading.Thread(target=worker, daemon=False)
        search_state["thread"] = thread
        thread.start()

    def select_result(_event):
        selected_index = result_list.GetFirstSelected()
        if selected_index == wx.NOT_FOUND:
            return
        full_path = result_list.GetItemText(selected_index, 1)
        if not full_path:
            return
        parent_folder = os.path.dirname(full_path)

        if hasattr(owner, "path_box"):
            owner.path_box.SetValue(parent_folder)
        if hasattr(owner, "open_path"):
            owner.open_path(parent_folder, add_history=False)
        if hasattr(owner, "select_tree_item_by_path"):
            owner.select_tree_item_by_path(parent_folder)
        if hasattr(owner, "load_folder"):
            owner.load_folder(parent_folder)
        if hasattr(owner, "select_list_item_by_path"):
            owner.select_list_item_by_path(full_path)
        if hasattr(owner, "show_file_preview"):
            try:
                owner.show_file_preview(full_path)
            except Exception:
                pass

    clear_mask_btn.Bind(wx.EVT_BUTTON, clear_mask)
    file_mask_field.Bind(wx.EVT_TEXT, lambda _event: sync_file_mask_field())
    word_chk.Bind(wx.EVT_CHECKBOX, lambda _event: sync_file_mask_field())
    excel_chk.Bind(wx.EVT_CHECKBOX, lambda _event: sync_file_mask_field())
    date_from_enable_chk.Bind(wx.EVT_CHECKBOX, lambda _event: _apply_date_filter_enabled(date_from_field, date_from_picker, date_from_enable_chk, date_from_btn))
    date_to_enable_chk.Bind(wx.EVT_CHECKBOX, lambda _event: _apply_date_filter_enabled(date_to_field, date_to_picker, date_to_enable_chk, date_to_btn))
    browse_btn.Bind(wx.EVT_BUTTON, lambda _event: (lambda chosen: folder_field.SetValue(chosen) if chosen else None)( _browse_for_folder(dialog, folder_field.GetValue()) ))
    search_btn.Bind(wx.EVT_BUTTON, run_search)
    stop_btn.Bind(wx.EVT_BUTTON, stop_search)
    quit_btn.Bind(wx.EVT_BUTTON, lambda _event: dialog.Close())
    result_list.Bind(wx.EVT_LIST_ITEM_ACTIVATED, select_result)
    def on_close(_event=None):
        stop_event = search_state.get("stop_event")
        if stop_event is not None:
            stop_event.set()
        thread = search_state.get("thread")
        if thread is not None and thread.is_alive():
            thread.join()
        save_geometry()
        dialog.Destroy()
        setattr(owner, "_search_form_dialog", None)

    dialog.Bind(wx.EVT_CLOSE, on_close)

    position = restored_state.get("position")
    size = restored_state.get("size")
    if isinstance(position, list) and len(position) == 2:
        try:
            dialog.SetPosition((int(position[0]), int(position[1])))
        except Exception:
            pass
    if isinstance(size, list) and len(size) == 2:
        try:
            width, height = int(size[0]), int(size[1])
            if width > 150 and height > 180:
                dialog.SetSize((width, height))
        except Exception:
            pass
    else:
        dialog.SetSize((900, 500))

    dialog.Layout()
    dialog.CenterOnParent()
    dialog.Show()
    return dialog
