import json
import os
import sys

import wx

from common.dict_tools import OPTION_FIELDS, OPTION_GROUP_ORDER, OPTION_GROUP_TRANSLATION_KEYS, PERSISTED_LAYOUT_KEYS
from localization import tr


def _get_project_root_dir():
    # In frozen builds (e.g. PyInstaller), persist settings next to the executable.
    if getattr(sys, "frozen", False):
        executable_path = os.path.abspath(getattr(sys, "executable", ""))
        executable_dir = os.path.dirname(executable_path)
        if executable_dir:
            return executable_dir

    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    if os.path.basename(current_dir) == "controls":
        return os.path.dirname(current_dir)
    return current_dir


def _get_settings_file_path():
    return os.path.join(_get_project_root_dir(), ".pdf_explorer_settings.json")


def load_settings():
    settings_file = _get_settings_file_path()
    try:
        if os.path.isfile(settings_file):
            with open(settings_file, "r", encoding="utf-8") as handle:
                return json.load(handle)
    except Exception:
        pass
    return {}


def save_settings(settings):
    settings_file = _get_settings_file_path()
    try:
        os.makedirs(os.path.dirname(settings_file), exist_ok=True)
        with open(settings_file, "w", encoding="utf-8") as handle:
            json.dump(settings, handle, ensure_ascii=False, indent=4)
    except Exception:
        pass


def update_settings(new_values):
    settings = load_settings()
    settings.update(new_values)
    save_settings(settings)


def get_configurable_settings_rows(settings):
    if not isinstance(settings, dict):
        return []

    rows = []
    for key, value in sorted(settings.items()):
        if key in PERSISTED_LAYOUT_KEYS:
            continue
        if key.endswith("_position") or key.endswith("_size"):
            continue
        if key.startswith("search_form_date_") or key.startswith("search_form_size_"):
            continue
        if key in {"search_form_folder", "search_form_file_mask"}:
            continue
        rows.append({"key": key, "value": value})
    return rows


def _format_setting_value(value):
    if isinstance(value, bool):
        return tr("options_value_true") if value else tr("options_value_false")
    if value is None:
        return tr("options_value_empty")
    if isinstance(value, (list, tuple, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    return str(value)


def _normalize_setting_value(key, value, original_value):
    if key == "ui_locale":
        normalized = str(value or "uk").strip().lower().replace("-", "_")
        if normalized == "ua":
            normalized = "uk"
        return normalized if normalized else "uk"
    if isinstance(original_value, bool):
        return bool(value)
    if isinstance(original_value, int):
        try:
            return int(value)
        except (TypeError, ValueError):
            return original_value
    if isinstance(original_value, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return original_value
    if isinstance(original_value, list):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else original_value
        except Exception:
            return original_value
    if isinstance(original_value, dict):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else original_value
        except Exception:
            return original_value
    return value


def _get_setting_label(key):
    translated = tr(f"settings_{key}")
    if translated.startswith("settings_"):
        return key.replace("_", " ").strip().title()
    return translated


def _get_option_group_label(group_name):
    key = OPTION_GROUP_TRANSLATION_KEYS.get(group_name, "options_group_main")
    label = tr(key)
    return label if label != key else group_name.replace("_", " ").title()


def _quality_label_to_value(label):
    mapping = {"low": 20, "medium": 35, "high": 55}
    normalized = str(label or "medium").strip().lower()
    if normalized in mapping:
        return mapping[normalized]
    for raw_name, value in mapping.items():
        if tr(f"options_quality_{raw_name}") == label:
            return value
    return mapping["medium"]


def _quality_value_to_label(value):
    mapping = {20: "low", 35: "medium", 55: "high"}
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        numeric_value = 35
    return mapping.get(numeric_value, "medium")


def _get_locale_value_label(code):
    code = str(code or "uk").strip().lower().replace("-", "_")
    if code == "ua":
        code = "uk"
    labels = {
        "en": tr("locale_name_english"),
        "uk": tr("locale_name_ukrainian"),
        "de": tr("locale_name_german"),
        "fr": tr("locale_name_french"),
        "es": tr("locale_name_spanish"),
        "it": tr("locale_name_italian"),
        "pt_br": tr("locale_name_portuguese_brazilian"),
        "ja": tr("locale_name_japanese"),
        "ko": tr("locale_name_korean"),
        "zh_cn": tr("locale_name_chinese_simplified"),
        "ru": tr("locale_name_russian"),
    }
    return labels.get(code, code.upper())


def show_options_form(owner):
    from controls.options_form import show_options_form as _show_options_form
    return _show_options_form(owner)


def save_window_geometry(frame):
    if frame.IsIconized():
        return

    position = frame.GetPosition()
    size = frame.GetSize()
    update_settings(
        {
            "window_position": [int(position.x), int(position.y)],
            "window_size": [int(size.x), int(size.y)],
        }
    )


def restore_window_geometry(frame, settings=None):
    if settings is None:
        settings = load_settings()

    position = settings.get("window_position")
    size = settings.get("window_size")

    if isinstance(size, list) and len(size) == 2:
        width, height = int(size[0]), int(size[1])
        if width > 100 and height > 100:
            frame.SetSize((width, height))

    if isinstance(position, list) and len(position) == 2:
        x, y = int(position[0]), int(position[1])
        frame.SetPosition((x, y))
