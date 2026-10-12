import copy
from datetime import date, timedelta
import unittest
from unittest.mock import Mock, patch

import wx

from controls import store_review as review


class ReviewScheduleTests(unittest.TestCase):
    def test_first_launch_is_day_one_and_restarts_do_not_reset_it(self):
        first = date(2026, 10, 1)
        state, due = review.review_due(None, first)
        self.assertFalse(due)
        for day in range(12):
            with self.subTest(day=day + 1):
                updated, due = review.review_due(state, first + timedelta(days=day))
                self.assertEqual(updated["first_used"], "2026-10-01")
                self.assertEqual(due, day >= 6)

    def test_reminder_date_overrides_initial_due_date(self):
        state = {"first_used": "2026-10-01", "remind_on": "2026-10-10"}
        self.assertFalse(review.review_due(state, date(2026, 10, 9))[1])
        self.assertTrue(review.review_due(state, date(2026, 10, 10))[1])
        self.assertTrue(review.review_due(state, date(2026, 11, 1))[1])

    def test_dismissal_is_permanent_even_without_dates(self):
        self.assertFalse(review.review_due({"dismissed": True}, date(2030, 1, 1))[1])

    def test_invalid_state_starts_a_new_count(self):
        for state in (None, [], "invalid", {"first_used": "invalid"}, {"first_used": 123}):
            with self.subTest(state=state):
                updated, due = review.review_due(state, date(2026, 10, 1))
                self.assertFalse(due)
                self.assertEqual(updated["first_used"], "2026-10-01")

    def test_invalid_reminder_and_clock_rollback(self):
        state = {"first_used": "2026-10-01", "remind_on": "invalid"}
        self.assertTrue(review.review_due(state, date(2026, 10, 7))[1])
        self.assertFalse(review.review_due(state, date(2026, 9, 30))[1])


class ReviewPromptTests(unittest.TestCase):
    def setUp(self):
        self.settings = {"ui_locale": "en", review.SETTINGS_KEY: {"first_used": "2026-10-01"}}
        self.parent = Mock(_closing=False)
        self.parent.IsEnabled.return_value = True
        self.dialog = Mock()
        self.dialog.ShowModal.return_value = wx.ID_CANCEL
        for target, kwargs in (
            ("load_settings", {"side_effect": lambda: copy.deepcopy(self.settings)}),
            ("update_settings", {"side_effect": lambda values: self.settings.update(copy.deepcopy(values))}),
            ("date", {"wraps": date}),
        ):
            patcher = patch.object(review, target, **kwargs)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            if target == "date":
                mocked.today.return_value = date(2026, 10, 7)
        for target in ("wx.MessageDialog", "wx.MessageBox", "os.startfile"):
            patcher = patch("controls.store_review." + target)
            mocked = patcher.start()
            self.addCleanup(patcher.stop)
            setattr(self, target.split(".")[-1], mocked)
        self.MessageDialog.return_value = self.dialog

    def test_cancel_and_window_close_stop_future_prompts(self):
        review.check_store_review(self.parent)
        review.check_store_review(self.parent)
        self.assertTrue(self.settings[review.SETTINGS_KEY]["dismissed"])
        self.MessageDialog.assert_called_once()
        self.dialog.Destroy.assert_called_once()
        self.startfile.assert_not_called()

    def test_store_button_closes_dialog_and_disables_prompt(self):
        self.dialog.ShowModal.return_value = wx.ID_YES
        review.check_store_review(self.parent)
        self.startfile.assert_called_once_with("ms-windows-store://review/?ProductId=9ns0crbdgtv6")
        self.dialog.Destroy.assert_called_once()
        review.check_store_review(self.parent)
        self.MessageDialog.assert_called_once()

    def test_remind_later_survives_restart_without_resetting_first_use(self):
        self.dialog.ShowModal.return_value = wx.ID_NO
        review.check_store_review(self.parent)
        state = self.settings[review.SETTINGS_KEY]
        self.assertEqual(state["remind_on"], "2026-10-10")
        self.assertEqual(state["first_used"], "2026-10-01")
        self.assertEqual(self.settings["ui_locale"], "en")
        review.check_store_review(self.parent)
        self.MessageDialog.assert_called_once()
        self.startfile.assert_not_called()

    def test_store_failure_is_reported_and_choice_still_persists(self):
        self.dialog.ShowModal.return_value = wx.ID_YES
        self.startfile.side_effect = OSError("Store unavailable")
        review.check_store_review(self.parent)
        self.MessageBox.assert_called_once()
        self.assertTrue(self.settings[review.SETTINGS_KEY]["dismissed"])

    def test_closed_parent_does_not_prompt(self):
        self.parent._closing = True
        review.check_store_review(self.parent)
        self.MessageDialog.assert_not_called()

    def test_waits_for_startup_license_dialog(self):
        self.parent.IsEnabled.return_value = False
        with patch.object(wx, "CallLater") as later:
            review.check_store_review(self.parent)
        later.assert_called_once_with(1000, review.check_store_review, self.parent)
        self.MessageDialog.assert_not_called()


if __name__ == "__main__":
    unittest.main()
