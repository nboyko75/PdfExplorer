"""Ask for a Store review on day seven, once per application launch."""
from datetime import date, timedelta
import os

import wx

from common.window_tools import load_settings, update_settings
from localization import tr


REVIEW_URI = "ms-windows-store://review/?ProductId=9ns0crbdgtv6"
FIRST_PROMPT_DAY = 7
REMINDER_DAYS = 3
SETTINGS_KEY = "store_review"


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def review_due(state, today):
    """Return the repaired state and whether today's launch should prompt.

    The first launch is day one; missed days do not postpone the prompt.
    Older installations start counting when they first run this feature.
    """
    state = dict(state) if isinstance(state, dict) else {}
    if state.get("dismissed") is True:
        return state, False
    first_used = _parse_date(state.get("first_used"))
    if first_used is None:
        first_used = today
        state["first_used"] = today.isoformat()
    remind_on = _parse_date(state.get("remind_on"))
    due = (today - first_used).days >= FIRST_PROMPT_DAY - 1
    return state, due and (remind_on is None or today >= remind_on)


def check_store_review(parent):
    """Run after the main window appears; choices persist across restarts."""
    if not parent or getattr(parent, "_closing", False):
        return
    # Startup trial/license dialogs run a nested event loop. Wait until they close.
    if not parent.IsEnabled():
        wx.CallLater(1000, check_store_review, parent)
        return
    saved_state = load_settings().get(SETTINGS_KEY)
    state, due = review_due(saved_state, date.today())
    if state != saved_state:
        update_settings({SETTINGS_KEY: state})
    if not due:
        return

    dialog = wx.MessageDialog(
        parent, tr("review_message", days=REMINDER_DAYS), tr("review_title"),
        wx.YES_NO | wx.CANCEL | wx.ICON_INFORMATION | wx.NO_DEFAULT,
    )
    dialog.SetYesNoCancelLabels(
        tr("review_store"), tr("review_later"), tr("options_cancel_button"),
    )
    try:
        choice = dialog.ShowModal()
    finally:
        dialog.Destroy()

    if choice == wx.ID_NO:
        state["remind_on"] = (date.today() + timedelta(days=REMINDER_DAYS)).isoformat()
    else:
        # Closing the dialog with X or Escape has the same meaning as Cancel.
        state["dismissed"] = True
    update_settings({SETTINGS_KEY: state})

    if choice == wx.ID_YES:
        try:
            os.startfile(REVIEW_URI)
        except OSError:
            wx.MessageBox(tr("license_store_failed"), tr("review_title"),
                          wx.OK | wx.ICON_ERROR, parent)
