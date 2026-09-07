import json

from common.dict_tools import OPTION_GROUP_TRANSLATION_KEYS
from localization import tr


def get_option_group_label(group_name):
    key = OPTION_GROUP_TRANSLATION_KEYS.get(group_name, "options_group_main")
    label = tr(key)
    return label if label != key else group_name.replace("_", " ").title()


def quality_label_to_value(label):
    mapping = {"low": 20, "medium": 35, "high": 55}
    normalized = str(label or "medium").strip().lower()
    if normalized in mapping:
        return mapping[normalized]
    for raw_name, value in mapping.items():
        if tr(f"options_quality_{raw_name}") == label:
            return value
    return mapping["medium"]


def quality_value_to_label(value):
    mapping = {20: "low", 35: "medium", 55: "high"}
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        numeric_value = 35
    return mapping.get(numeric_value, "medium")


def get_locale_value_label(code):
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


def normalize_setting_value(key, value, original_value):
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


_get_option_group_label = get_option_group_label
_quality_label_to_value = quality_label_to_value
_quality_value_to_label = quality_value_to_label
_get_locale_value_label = get_locale_value_label
_normalize_setting_value = normalize_setting_value
