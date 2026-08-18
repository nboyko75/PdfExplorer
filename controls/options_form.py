import json

import wx

from common.dict_tools import OPTION_FIELDS, OPTION_GROUP_ORDER, OPTION_GROUP_TRANSLATION_KEYS
from localization import tr
from controls.window_tools import load_settings, update_settings


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


def _save_dialog_geometry(dialog):
    position = dialog.GetPosition()
    size = dialog.GetSize()
    update_settings({
        "options_form_position": [int(position.x), int(position.y)],
        "options_form_size": [int(size.x), int(size.y)],
    })


def _apply_dialog_geometry(dialog, settings):
    saved_position = settings.get("options_form_position")
    saved_size = settings.get("options_form_size")

    min_width, min_height = 550, 450
    default_width, default_height = 920, 620
    dialog.SetMinSize((min_width, min_height))
    dialog.SetSize((default_width, default_height))

    if isinstance(saved_size, list) and len(saved_size) == 2:
        width, height = int(saved_size[0]), int(saved_size[1])
        if width >= min_width and height >= min_height:
            dialog.SetSize((width, height))
    if isinstance(saved_position, list) and len(saved_position) == 2:
        x, y = int(saved_position[0]), int(saved_position[1])
        dialog.SetPosition((x, y))


def show_options_form(owner):
    settings = load_settings()
    group_fields = {}
    for field in OPTION_FIELDS:
        key = field["key"]
        value = settings.get(key, field.get("default"))
        if value is None:
            continue
        group_fields.setdefault(field["group"], []).append({**field, "value": value})

    if not group_fields:
        group_fields = {"main": [{"key": "ui_locale", "group": "main", "label_key": "settings_ui_locale", "kind": "locale_choice", "default": "uk", "value": settings.get("ui_locale", "uk")}]}

    dialog = wx.Dialog(owner, title=tr("options_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    _apply_dialog_geometry(dialog, settings)

    panel = wx.Panel(dialog)
    controls_by_key = {}
    root = wx.BoxSizer(wx.VERTICAL)
    notebook = wx.Notebook(panel)
    root.Add(notebook, 1, wx.EXPAND | wx.ALL, 12)

    def _on_dialog_close(event):
        _save_dialog_geometry(dialog)
        dialog.EndModal(wx.ID_CANCEL)

    dialog.Bind(wx.EVT_CLOSE, _on_dialog_close)

    for group_name in OPTION_GROUP_ORDER:
        fields = group_fields.get(group_name, [])
        if not fields:
            continue

        page = wx.Panel(notebook)
        page_sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        grid.AddGrowableCol(1, 1)

        for field in fields:
            key = field["key"]
            label = wx.StaticText(page, label=tr(field["label_key"]))
            label.Wrap(220)
            value = field.get("value")

            if key == "optimize_pdf_color_quality":
                choices = [tr("options_quality_low"), tr("options_quality_medium"), tr("options_quality_high")]
                current_key = _quality_value_to_label(value)
                combo = wx.ComboBox(page, value=tr(f"options_quality_{current_key}"), choices=choices, style=wx.CB_READONLY)
                controls_by_key[key] = combo
                grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(combo, 1, wx.EXPAND)
                continue

            if field["kind"] == "locale_choice":
                locale_code_by_label = {
                    tr("locale_name_english"): "en",
                    tr("locale_name_ukrainian"): "uk",
                    tr("locale_name_german"): "de",
                    tr("locale_name_french"): "fr",
                    tr("locale_name_spanish"): "es",
                    tr("locale_name_italian"): "it",
                    tr("locale_name_portuguese_brazilian"): "pt_br",
                    tr("locale_name_japanese"): "ja",
                    tr("locale_name_korean"): "ko",
                    tr("locale_name_chinese_simplified"): "zh_cn",
                    tr("locale_name_russian"): "ru",
                }
                choices = [
                    tr("locale_name_english"),
                    tr("locale_name_ukrainian"),
                    tr("locale_name_german"),
                    tr("locale_name_french"),
                    tr("locale_name_spanish"),
                    tr("locale_name_italian"),
                    tr("locale_name_portuguese_brazilian"),
                    tr("locale_name_japanese"),
                    tr("locale_name_korean"),
                    tr("locale_name_chinese_simplified"),
                    tr("locale_name_russian"),
                ]
                combo = wx.ComboBox(page, value=_get_locale_value_label(value), choices=choices, style=wx.CB_READONLY)
                controls_by_key[key] = combo
                grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(combo, 1, wx.EXPAND)
                continue

            if field["kind"] == "bool":
                chk = wx.CheckBox(page, label="")
                chk.SetValue(bool(value))
                controls_by_key[key] = chk
                grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(chk, 1, wx.ALIGN_LEFT)
                continue

            if field["kind"] == "choice":
                code_choices = list(field.get("choices") or [])
                text_choices = []
                for choice in code_choices:
                    if str(choice).lower() == "jpeg":
                        text_choices.append(tr("scan_output_type_jpeg"))
                    elif str(choice).lower() == "pdf":
                        text_choices.append(tr("scan_output_type_pdf"))
                    elif str(choice).lower() in {"ccitt_group3", "ccitt_group4", "png"}:
                        text_choices.append(str(choice).replace("_", " ").title())
                    else:
                        text_choices.append(str(choice))
                selection = str(value)
                if selection.isdigit():
                    selection_index = int(selection)
                    conversion = {0: tr("scan_output_type_pdf"), 1: tr("scan_output_type_jpeg")}
                    selection = conversion.get(selection_index, str(value))
                choice_ctrl = wx.Choice(page, choices=text_choices)
                try:
                    choice_ctrl.SetStringSelection(str(selection))
                except Exception:
                    try:
                        choice_ctrl.SetSelection(int(selection))
                    except Exception:
                        choice_ctrl.SetSelection(0)
                controls_by_key[key] = choice_ctrl
                grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                grid.Add(choice_ctrl, 1, wx.EXPAND)
                continue

            text = wx.TextCtrl(page, value=str(value), style=wx.TE_PROCESS_ENTER)
            controls_by_key[key] = text
            grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
            grid.Add(text, 1, wx.EXPAND)

        page_sizer.Add(grid, 1, wx.EXPAND | wx.ALL, 12)
        page.SetSizer(page_sizer)
        notebook.AddPage(page, _get_option_group_label(group_name))

    apply_btn = wx.Button(panel, wx.ID_OK, tr("options_apply_button"))
    cancel_btn = wx.Button(panel, wx.ID_CANCEL, tr("options_cancel_button"))
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(apply_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)
    root.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

    panel.SetSizer(root)
    panel.Layout()
    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizer(dialog_sizer)
    dialog.Layout()

    result = dialog.ShowModal()
    if result != wx.ID_OK:
        _save_dialog_geometry(dialog)
        dialog.Destroy()
        return

    changes = {}
    for key, control in controls_by_key.items():
        original_value = settings.get(key)
        if key == "ui_locale":
            selected_label = control.GetValue()
            locale_map = {
                tr("locale_name_english"): "en",
                tr("locale_name_ukrainian"): "uk",
                tr("locale_name_german"): "de",
                tr("locale_name_french"): "fr",
                tr("locale_name_spanish"): "es",
                tr("locale_name_italian"): "it",
                tr("locale_name_portuguese_brazilian"): "pt_br",
                tr("locale_name_japanese"): "ja",
                tr("locale_name_korean"): "ko",
                tr("locale_name_chinese_simplified"): "zh_cn",
                tr("locale_name_russian"): "ru",
            }
            normalized = locale_map.get(selected_label, selected_label)
            changes[key] = _normalize_setting_value(key, normalized, original_value)
        elif key == "optimize_pdf_color_quality":
            selected = control.GetStringSelection().strip()
            changes[key] = _quality_label_to_value(selected)
        elif isinstance(control, wx.CheckBox):
            changes[key] = bool(control.GetValue())
        elif isinstance(control, wx.Choice):
            selected = control.GetStringSelection()
            try:
                choice_def = next(item for item in OPTION_FIELDS if item["key"] == key)
            except StopIteration:
                choice_def = {"default": original_value}
            choice_values = choice_def.get("choices") or []
            if choice_values and isinstance(choice_values[0], int):
                mapping = {str(v): v for v in choice_values}
                value = mapping.get(str(selected), choice_values[0])
            else:
                normalized = str(selected).strip().lower().replace(" ", "_")
                if normalized == "jpeg":
                    value = "jpeg"
                elif normalized == "pdf":
                    value = "pdf"
                elif normalized == "ccitt_group3":
                    value = "ccitt_group3"
                elif normalized == "ccitt_group4":
                    value = "ccitt_group4"
                elif normalized == "png":
                    value = "png"
                else:
                    value = str(selected)
            changes[key] = value
        else:
            text_value = control.GetValue().strip()
            changes[key] = _normalize_setting_value(key, text_value, original_value)

    position = dialog.GetPosition()
    size = dialog.GetSize()
    saved_geometry = {
        "options_form_position": [int(position.x), int(position.y)],
        "options_form_size": [int(size.x), int(size.y)],
    }
    if changes:
        update_settings({**changes, **saved_geometry})
    else:
        update_settings(saved_geometry)

    if owner is not None:
        for key, value in changes.items():
            if hasattr(owner, key):
                setattr(owner, key, value)
        if "ui_locale" in changes and hasattr(owner, "current_locale"):
            locale_code = str(changes["ui_locale"]).strip().lower().replace("-", "_")
            if locale_code == "ua":
                locale_code = "uk"
            owner.current_locale = locale_code if locale_code in {"en", "uk", "de", "fr", "es", "it", "pt_br", "ja", "ko", "zh_cn", "ru"} else "uk"
            try:
                from localization import load_locale
                load_locale(owner.current_locale)
            except Exception:
                pass
            if hasattr(owner, "refresh_locale"):
                owner.refresh_locale()
        elif hasattr(owner, "refresh"):
            owner.refresh()

    dialog.Destroy()
