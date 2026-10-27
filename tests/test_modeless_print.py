"""Exercise the live wx event loop and worker IPC without printing any pages."""
from contextlib import ExitStack
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import wx

from controls import print_form
from localization import tr


def click(dialog, button_id):
    dialog.ProcessWindowEvent(wx.CommandEvent(wx.EVT_BUTTON.typeId, button_id))


def simulated_worker(connection, request, translations):
    """Runs in a real child process with only the printer backend replaced."""
    def submit(**options):
        record = Path(options["record"])
        record.write_text("started")
        if options["duplex"]:
            confirmed = options["confirm_reload"]("Reload sheets")
            record.write_text("submitted" if confirmed else "cancelled")
        else:
            time.sleep(0.3)
            record.write_text("submitted")
        return "Printer"

    with patch.object(print_form, "_execute_print_request", side_effect=submit):
        print_form._print_worker(connection, request, translations)


class ModelessPrintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = wx.App.Get() or wx.App(False)

    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = str(Path(directory) / "selected.pdf")
        Path(self.path).touch()
        self.owner = wx.Frame(None)
        self.addCleanup(self.owner.Destroy)
        self.owner.list_host_panel = wx.Panel(self.owner)
        self.owner.list_selection_hint = wx.StaticText(self.owner.list_host_panel, label="")
        self.owner.list_selection_hint.Hide()
        self.stack.enter_context(patch.object(print_form, "_get_printer_names", return_value=["Printer"]))
        self.stack.enter_context(patch.object(print_form, "_get_printer_duplex", return_value=1))
        self.stack.enter_context(patch.object(print_form, "load_settings", return_value={}))
        self.stack.enter_context(patch.object(print_form, "update_settings"))
        self.stack.enter_context(patch.object(print_form, "_save_print_form_geometry"))
        self.stack.enter_context(patch.object(wx.Dialog, "ShowModal", side_effect=AssertionError("Modal UI")))
        self.stack.enter_context(patch.object(wx, "MessageBox", side_effect=AssertionError("Message box")))
        self.job = Mock()
        self.job.poll.return_value = []
        self.start_job = self.stack.enter_context(patch.object(print_form, "_PrintJob", return_value=self.job))
        self.dialog = print_form.show_print_form(self.owner, self.path)
        self.addCleanup(self.close_dialog)

    def close_dialog(self):
        from controls.filelist import hide_list_selection_hint
        hide_list_selection_hint(self.owner)
        if self.dialog:
            self.dialog.Close()
            self.pump_events()

    def pump_events(self):
        wx.CallLater(20, self.app.ExitMainLoop)
        self.app.MainLoop()

    def wait_until(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.pump_events()
        self.assertTrue(predicate())

    def has_status(self, text):
        return any(isinstance(child, wx.StaticText) and text in child.GetLabel()
                   for child in self.dialog.GetChildren()[0].GetChildren())

    def test_form_and_submission_leave_main_window_enabled_and_capture_original_file(self):
        self.assertFalse(self.dialog.IsModal())
        self.assertTrue(self.owner.IsEnabled())
        self.owner.current_preview_path = "another.pdf"
        click(self.dialog, wx.ID_OK)
        click(self.dialog, wx.ID_OK)  # Repeated commands must not submit twice.
        self.start_job.assert_called_once()
        self.assertEqual(self.start_job.call_args.args[0]["document_path"], self.path)
        self.assertFalse(self.dialog.FindWindow(wx.ID_OK).IsEnabled())
        self.assertTrue(self.owner.IsEnabled())
        received = []
        wx.CallAfter(received.append, "app remains responsive")
        self.wait_until(lambda: bool(received))

    def test_success_uses_three_second_list_hint_and_errors_stay_in_form(self):
        for kind, message in (("error", "Spooler failed"), ("done", "Printer")):
            click(self.dialog, wx.ID_OK)
            self.job.poll.return_value = [(kind, message)]
            expected = message if kind == "error" else tr("print_status_success", printer=message)
            if kind == "error":
                self.wait_until(lambda: self.has_status(expected))
                self.assertFalse(self.owner.list_selection_hint.IsShown())
            else:
                hint = self.owner.list_selection_hint
                self.wait_until(lambda: hint.IsShown() and hint.GetLabel() == expected)
                self.assertFalse(self.has_status(expected))
                self.assertEqual(self.owner._list_selection_hint_timer.GetInterval(), 3000)
                self.wait_until(lambda: not hint.IsShown(), timeout=5)
            self.assertTrue(self.dialog.FindWindow(wx.ID_OK).IsEnabled())
            self.assertTrue(self.owner.IsEnabled())
        self.assertEqual(self.start_job.call_count, 2)
        self.assertEqual(self.job.close.call_count, 2)

    def test_manual_reload_waits_for_explicit_ok_without_blocking_app(self):
        click(self.dialog, wx.ID_OK)
        self.job.poll.side_effect = [[("reload", "Reload the sheets")], []]
        self.wait_until(lambda: self.has_status("Reload the sheets"))
        self.job.resume.assert_not_called()
        self.assertTrue(self.owner.IsEnabled())
        self.assertEqual(self.dialog.FindWindow(wx.ID_OK).GetLabel(), tr("ok_button"))
        click(self.dialog, wx.ID_OK)
        self.job.resume.assert_called_once()
        self.assertFalse(self.dialog.FindWindow(wx.ID_OK).IsEnabled())

    def test_cancel_command_detaches_job_and_destroys_modeless_dialog(self):
        click(self.dialog, wx.ID_OK)
        click(self.dialog, wx.ID_CANCEL)  # Also the command generated by Escape.
        self.pump_events()
        self.assertFalse(self.dialog)
        self.job.close.assert_called_once()
        self.job.resume.assert_not_called()

    def test_owner_destruction_detaches_job(self):
        click(self.dialog, wx.ID_OK)
        self.dialog.Destroy()  # Child dialogs also receive this on owner shutdown.
        self.pump_events()
        self.job.close.assert_called_once()


class PrintWorkerTests(unittest.TestCase):
    def test_worker_relays_reload_and_completion_without_using_wx(self):
        connection = Mock()
        connection.recv.return_value = True

        def submit(**request):
            self.assertTrue(request["confirm_reload"]("Reload sheets"))
            return "Printer"

        with patch.object(print_form, "_execute_print_request", side_effect=submit), \
                patch.object(wx, "MessageBox") as modal:
            print_form._print_worker(connection, {}, {})
        self.assertEqual([call.args[0] for call in connection.send.call_args_list],
                         [("reload", "Reload sheets"), ("done", "Printer")])
        connection.close.assert_called_once()
        modal.assert_not_called()

    def test_closing_pipe_cancels_remaining_duplex_pass(self):
        connection = Mock()
        connection.recv.side_effect = EOFError

        def submit(**request):
            self.assertFalse(request["confirm_reload"]("Reload sheets"))

        with patch.object(print_form, "_execute_print_request", side_effect=submit):
            print_form._print_worker(connection, {}, {})

    def test_worker_reports_failure_and_closes_connection(self):
        connection = Mock()
        with patch.object(print_form, "_execute_print_request", side_effect=OSError("Printer offline")):
            print_form._print_worker(connection, {}, {})
        connection.send.assert_called_once_with(("error", "Printer offline"))
        connection.close.assert_called_once()

    def test_real_spawned_worker_returns_error_for_missing_file(self):
        # Fails before any printer API is used; verifies Windows spawn and IPC.
        with tempfile.TemporaryDirectory() as directory:
            missing = str(Path(directory) / "missing.pdf")
            job = print_form._PrintJob(dict(document_path=missing, selected_printer="Unused"))
            try:
                self.assertNotEqual(job.process.pid, os.getpid())
                deadline = time.monotonic() + 15
                messages = []
                while not messages and time.monotonic() < deadline:
                    messages.extend(job.poll())
                    time.sleep(0.01)
                self.assertEqual(messages, [("error", missing)])
            finally:
                job.close()

    def test_detaching_keeps_submission_running_but_cancels_pending_duplex(self):
        for duplex in (False, True):
            with self.subTest(duplex=duplex), tempfile.TemporaryDirectory() as directory:
                record = Path(directory) / "status.txt"
                with patch.object(print_form, "_print_worker", simulated_worker):
                    job = print_form._PrintJob(dict(record=str(record), duplex=duplex))
                try:
                    deadline = time.monotonic() + 15
                    while not record.exists() and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(record.exists())
                finally:
                    job.close()
                expected = "cancelled" if duplex else "submitted"
                while record.read_text() != expected and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertEqual(record.read_text(), expected)


if __name__ == "__main__":
    unittest.main()
