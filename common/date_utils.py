import locale, ctypes
from datetime import date, datetime

import wx
from localization import tr

LOCALE_NAME_USER_DEFAULT = None
LOCALE_SSHORTDATE = 0x0000001F

def get_windows_short_date_format():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    buffer = ctypes.create_unicode_buffer(256)

    result = kernel32.GetLocaleInfoEx(
        LOCALE_NAME_USER_DEFAULT,
        LOCALE_SSHORTDATE,
        buffer,
        len(buffer)
    )

    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())

    return buffer.value

def get_wx_short_date_format() -> str:
    windows_format = get_windows_short_date_format()

    replacements = {
        "yyyy": "%Y",
        "yy": "%y",
        "MM": "%m",
        "dd": "%d",
    }

    result = windows_format

    for old, new in replacements.items():
        result = result.replace(old, new)

    return result

DatePickerCtrl = None
DatePickerEvent = None

try:
    DatePickerCtrl = wx.DatePickerCtrl
    DatePickerEvent = wx.EVT_DATE_CHANGED
except AttributeError:  # pragma: no cover - wxPython compatibility fallback
    try:
        from wx import adv
        DatePickerCtrl = adv.DatePickerCtrl
        DatePickerEvent = adv.EVT_DATE_CHANGED
    except ImportError:  # pragma: no cover - fallback if no date picker is available
        DatePickerCtrl = None
        DatePickerEvent = None

# Some wxPython builds expose DatePickerCtrl and its flags in the wx.adv module.
# Build the style bitmask defensively so the form still works across versions.
DATE_PICKER_STYLE = 0
for source in (wx, getattr(wx, "adv", None)):
    if source is None:
        continue
    for style_name in ("DP_DROPDOWN", "DP_SHOWCENTURY", "DP_DEFAULT"):
        style_flag = getattr(source, style_name, None)
        if style_flag is not None:
            DATE_PICKER_STYLE |= style_flag


def _parse_date_value(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            try:
                return datetime.strptime(value, "%d.%m.%Y").date()
            except ValueError:
                return None
    return None


def _date_to_wx_datetime(value):
    parsed = _parse_date_value(value)
    if parsed is None:
        parsed = datetime.now().date()
    try:
        return wx.DateTime.FromDMY(parsed.day, parsed.month - 1, parsed.year)
    except AttributeError:
        try:
            return wx.DateTimeFromDMY(parsed.day, parsed.month - 1, parsed.year)
        except AttributeError:
            return None


def _fallback_system_date_format(parsed):
    if parsed is None:
        return ""
    frm = get_wx_short_date_format()
    return parsed.strftime(frm)


def _format_system_date(value):
    parsed = _parse_date_value(value)
    return _fallback_system_date_format(parsed)


def _show_date_picker_popup(
    parent_dialog,
    field_control,
    trigger_button=None,
    date_picker_name=None,
    wx_module=None,
    picker_class=None,
    picker_event=None,
):
    if wx_module is None:
        wx_module = wx
    if picker_class is None:
        picker_class = DatePickerCtrl
    if picker_event is None:
        picker_event = DatePickerEvent

    if picker_class is None:
        return

    popup = wx_module.Dialog(parent_dialog, title=tr("search_pick_date_tooltip"), style=wx_module.NO_BORDER | wx_module.FRAME_FLOAT_ON_PARENT)
    popup_panel = wx_module.Panel(popup)
    picker = picker_class(popup_panel, style=DATE_PICKER_STYLE)
    picker.SetToolTip(tr("search_pick_date_tooltip"))

    current_value = _date_to_wx_datetime(field_control.GetValue())
    if current_value is not None:
        picker.SetValue(current_value)
    else:
        picker.SetValue(wx_module.DateTime.Now())

    def apply_selection():
        selected = picker.GetValue()
        if not selected.IsValid():
            return False

        selected_iso = selected.FormatISODate()
        current_field_value = (field_control.GetValue() or "").strip()
        parsed_current = _parse_date_value(current_field_value)
        if parsed_current is not None and selected_iso == parsed_current.isoformat():
            return True

        field_control.SetValue(_format_system_date(selected_iso))
        return True

    def on_select(_date_event=None):
        apply_selection()

    if picker_event is not None:
        picker.Bind(picker_event, on_select)

    button_id = getattr(wx_module, "ID_ANY", 0)
    ok_button = wx_module.Button(popup_panel, button_id, "OK")
    cancel_button = wx_module.Button(popup_panel, button_id, "Cancel")

    def on_ok(_event=None):
        if apply_selection():
            try:
                popup.EndModal(wx_module.ID_OK)
            except Exception:
                pass

    def on_cancel(_event=None):
        try:
            popup.EndModal(wx_module.ID_CANCEL)
        except Exception:
            pass

    def on_key(event):
        key_code = event.GetKeyCode()
        return_keys = tuple(
            value for value in (getattr(wx_module, "WXK_RETURN", None), getattr(wx_module, "WXK_NUMPAD_ENTER", None))
            if value is not None
        )
        escape_key = getattr(wx_module, "WXK_ESCAPE", None)
        if key_code in return_keys:
            on_ok()
            return
        if escape_key is not None and key_code == escape_key:
            on_cancel()
            return
        event.Skip()

    if hasattr(wx_module, "EVT_BUTTON"):
        ok_button.Bind(wx_module.EVT_BUTTON, on_ok)
        cancel_button.Bind(wx_module.EVT_BUTTON, on_cancel)
    if hasattr(wx_module, "EVT_CHAR_HOOK"):
        popup.Bind(wx_module.EVT_CHAR_HOOK, on_key)

    button_row = wx_module.BoxSizer(wx_module.HORIZONTAL)
    button_row.AddStretchSpacer()
    button_row.Add(ok_button, 0, getattr(wx_module, "RIGHT", 0), 8)
    button_row.Add(cancel_button, 0)

    popup_sizer = wx_module.BoxSizer(wx_module.VERTICAL)
    popup_sizer.Add(picker, 0, getattr(wx_module, "ALL", 0) | getattr(wx_module, "ALIGN_CENTER", 0), 8)
    popup_sizer.Add(
        button_row,
        0,
        getattr(wx_module, "EXPAND", 0) | getattr(wx_module, "LEFT", 0) | getattr(wx_module, "RIGHT", 0) | getattr(wx_module, "BOTTOM", 0),
        8,
    )
    popup_panel.SetSizerAndFit(popup_sizer)
    popup.SetClientSize(popup_panel.GetSize())

    if trigger_button is not None:
        try:
            button_pos = trigger_button.GetScreenPosition()
            button_size = trigger_button.GetSize()
            popup.SetPosition((button_pos.x, button_pos.y + button_size.y))
        except Exception:
            popup.CenterOnParent()
    else:
        popup.CenterOnParent()

    popup.ShowModal()
    popup.Destroy()
