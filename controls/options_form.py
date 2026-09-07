import json
import os
import subprocess
import sys

import wx

from common.dict_tools import OPTION_FIELDS, OPTION_GROUP_ORDER
from common.settings_utils import (
    get_option_group_label,
    quality_label_to_value,
    quality_value_to_label,
    get_locale_value_label,
    normalize_setting_value,
)
from common.window_tools import load_settings, update_settings, save_control_geometry, restore_control_geometry
from localization import tr


_get_option_group_label = get_option_group_label
_quality_label_to_value = quality_label_to_value
_quality_value_to_label = quality_value_to_label
_get_locale_value_label = get_locale_value_label
_normalize_setting_value = normalize_setting_value


def _save_dialog_geometry(dialog):
    save_control_geometry(dialog, "options_form")


def _apply_dialog_geometry(dialog, settings):
    restore_control_geometry(
        dialog,
        "options_form",
        default_size=(920, 620),
        min_size=(550, 450),
        settings=settings,
    )


class OptionsDialog(wx.Dialog):
    def __init__(self, owner):
        super().__init__(owner, title=tr("options_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.owner = owner
        self.settings = load_settings()
        self.group_fields = self._build_group_fields()
        self.controls_by_key = {}
        self._restore_geometry()
        self._build_ui()
        self.Bind(wx.EVT_CLOSE, self._on_dialog_close)

    def _build_group_fields(self):
        group_fields = {}
        for field in OPTION_FIELDS:
            key = field["key"]
            value = self.settings.get(key, field.get("default"))
            if value is None:
                continue
            group_fields.setdefault(field["group"], []).append({**field, "value": value})

        if not group_fields:
            group_fields = {"main": [{"key": "ui_locale", "group": "main", "label_key": "settings_ui_locale", "kind": "locale_choice", "default": "uk", "value": self.settings.get("ui_locale", "uk")}]}
        return group_fields

    def _restore_geometry(self):
        _apply_dialog_geometry(self, self.settings)

    def _build_ui(self):
        panel = wx.Panel(self)
        root = wx.BoxSizer(wx.VERTICAL)
        notebook = wx.Notebook(panel)
        root.Add(notebook, 1, wx.EXPAND | wx.ALL, 12)

        for group_name in OPTION_GROUP_ORDER:
            fields = self.group_fields.get(group_name, [])
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
                    self.controls_by_key[key] = combo
                    grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                    grid.Add(combo, 1, wx.EXPAND)
                    continue

                if field["kind"] == "locale_choice":
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
                    self.controls_by_key[key] = combo
                    grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                    grid.Add(combo, 1, wx.EXPAND)
                    continue

                if field["kind"] == "bool":
                    chk = wx.CheckBox(page, label="")
                    chk.SetValue(bool(value))
                    self.controls_by_key[key] = chk
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
                    self.controls_by_key[key] = choice_ctrl
                    grid.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)
                    grid.Add(choice_ctrl, 1, wx.EXPAND)
                    continue

                text = wx.TextCtrl(page, value=str(value), style=wx.TE_PROCESS_ENTER)
                self.controls_by_key[key] = text
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
        self.SetSizer(dialog_sizer)
        self.Layout()

    def _on_dialog_close(self, event):
        _save_dialog_geometry(self)
        self.EndModal(wx.ID_CANCEL)

    def _collect_changes(self):
        changes = {}
        for key, control in self.controls_by_key.items():
            original_value = self.settings.get(key)
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
        return changes

    def _apply_changes(self, changes):
        position = self.GetPosition()
        size = self.GetSize()
        saved_geometry = {
            "options_form_position": [int(position.x), int(position.y)],
            "options_form_size": [int(size.x), int(size.y)],
        }

        if self.owner is not None and "ui_locale" in changes and hasattr(self.owner, "current_locale"):
            old_locale = self.owner.current_locale
            locale_code = str(changes["ui_locale"]).strip().lower().replace("-", "_")
            if locale_code == "ua":
                locale_code = "uk"
            new_locale = locale_code if locale_code in {"en", "uk", "de", "fr", "es", "it", "pt_br", "ja", "ko", "zh_cn", "ru"} else "uk"

            try:
                from localization import load_locale
                confirmation_dialog = wx.MessageDialog(
                    self.owner,
                    tr("restart_required_message"),
                    tr("restart_required_title"),
                    style=wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION,
                )
                confirmation_dialog.SetYesNoLabels(tr("confirm_yes"), tr("confirm_no"))
                result = confirmation_dialog.ShowModal()
                confirmation_dialog.Destroy()

                if result == wx.ID_YES:
                    update_settings({**changes, **saved_geometry})
                    self.owner.current_locale = new_locale
                    load_locale(self.owner.current_locale)
                    if hasattr(self.owner, "refresh_locale"):
                        self.owner.refresh_locale()

                    try:
                        app_executable = sys.executable
                        restart_args = [app_executable, *sys.argv[1:]]
                        subprocess.Popen(restart_args, cwd=os.getcwd())
                        self.owner.Hide()
                        self.owner.Destroy()
                        if hasattr(wx, "GetApp") and wx.GetApp() is not None:
                            wx.GetApp().ExitMainLoop()
                        sys.exit(0)
                    except Exception:
                        pass
                else:
                    changes_without_locale = dict(changes)
                    changes_without_locale.pop("ui_locale", None)
                    update_settings({**changes_without_locale, **saved_geometry})
                    self.owner.current_locale = old_locale
                    load_locale(self.owner.current_locale)
                    if hasattr(self.owner, "refresh_locale"):
                        self.owner.refresh_locale()
            except Exception:
                pass
        else:
            if changes:
                update_settings({**changes, **saved_geometry})
            else:
                update_settings(saved_geometry)

            if self.owner is not None:
                for key, value in changes.items():
                    if hasattr(self.owner, key):
                        setattr(self.owner, key, value)
                if hasattr(self.owner, "refresh"):
                    self.owner.refresh()

    def show(self):
        result = self.ShowModal()
        if result != wx.ID_OK:
            _save_dialog_geometry(self)
            self.Destroy()
            return None

        changes = self._collect_changes()
        self._apply_changes(changes)
        self.Destroy()
        return changes


def show_options_form(owner):
    return OptionsDialog(owner).show()
