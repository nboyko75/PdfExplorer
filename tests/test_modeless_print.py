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

REAL_PRINT_JOB = print_form._PrintJob


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


def simulated_foreground_worker(connection, request, translations):
    """A driver window that outlives the worker's completion message."""
    app = wx.App(False)
    frame = wx.Frame(None, title="Simulated print driver")
    frame.Show()
    frame.Raise()
    connection.recv()  # The test grants this process foreground permission.
    try:
        print_form.win32gui.SetForegroundWindow(frame.GetHandle())
    except Exception:
        if print_form.win32gui.GetForegroundWindow() != frame.GetHandle():
            raise
    app.Yield()
    with patch.object(print_form, "_execute_print_request", return_value="Printer"):
        print_form._print_worker(connection, request, translations)
    Path(request["record"]).touch()
    time.sleep(0.4)  # Native teardown happens after sending done and closing IPC.
    frame.Destroy()
    app.Yield()


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

    def reopen_from_file_list(self):
        self.close_dialog()
        self.owner.list = wx.ListCtrl(self.owner.list_host_panel, style=wx.LC_REPORT)
        self.owner.list.InsertColumn(0, "File")
        self.owner.list.InsertItem(0, "selected.pdf")
        self.owner.list.InsertItem(1, "another.pdf")
        self.owner.list.Select(0)
        self.owner.list.Focus(0)
        self.owner.Show()
        self.owner.list.SetFocus()
        self.wait_until(lambda: wx.Window.FindFocus() == self.owner.list)
        self.dialog = print_form.show_print_form(self.owner, self.path)
        self.dialog.FindWindow(wx.ID_CANCEL).SetFocus()
        self.wait_until(lambda: wx.Window.FindFocus() == self.dialog.FindWindow(wx.ID_CANCEL))

    def test_success_and_close_restore_file_focus_and_selection(self):
        self.reopen_from_file_list()
        click(self.dialog, wx.ID_OK)
        self.job.poll.return_value = [("done", "Printer")]
        self.wait_until(lambda: not self.dialog)
        self.wait_until(lambda: wx.Window.FindFocus() == self.owner.list)
        self.assertEqual(self.owner.list.GetFirstSelected(), 0)
        self.assertEqual(self.owner.list.GetFocusedItem(), 0)

        self.dialog = print_form.show_print_form(self.owner, self.path)
        self.dialog.FindWindow(wx.ID_CANCEL).SetFocus()
        click(self.dialog, wx.ID_CANCEL)
        self.wait_until(lambda: not self.dialog)
        self.wait_until(lambda: wx.Window.FindFocus() == self.owner.list)
        self.assertEqual(self.owner.list.GetFirstSelected(), 0)

    def test_completion_focuses_file_list_and_preserves_changed_selection(self):
        self.reopen_from_file_list()
        click(self.dialog, wx.ID_OK)
        self.owner.list.Select(0, False)
        self.owner.list.Select(1)
        self.owner.list.Focus(1)
        other_control = wx.TextCtrl(self.owner.list_host_panel, pos=(0, 150))
        other_control.SetFocus()
        self.wait_until(lambda: wx.Window.FindFocus() == other_control)
        self.job.poll.return_value = [("done", "Printer")]
        self.wait_until(lambda: not self.dialog)
        self.wait_until(lambda: wx.Window.FindFocus() == self.owner.list)
        self.assertEqual(self.owner.list.GetFirstSelected(), 1)
        self.assertEqual(self.owner.list.GetFocusedItem(), 1)

    def test_closing_form_opened_from_another_control_focuses_file_list(self):
        self.reopen_from_file_list()
        self.close_dialog()
        other_control = wx.Button(self.owner.list_host_panel, label="Print", pos=(0, 150))
        other_control.SetFocus()
        self.wait_until(lambda: wx.Window.FindFocus() == other_control)
        self.dialog = print_form.show_print_form(self.owner, self.path)
        self.dialog.FindWindow(wx.ID_CANCEL).SetFocus()
        click(self.dialog, wx.ID_CANCEL)
        self.wait_until(lambda: not self.dialog)
        self.wait_until(lambda: wx.Window.FindFocus() == self.owner.list)
        self.assertEqual(self.owner.list.GetFirstSelected(), 0)

    def test_repeated_prints_restore_focus_after_native_dialog_destruction(self):
        self.reopen_from_file_list()
        set_focus = self.owner.list.SetFocus
        dialog_alive_when_focused = []

        def record_focus():
            dialog_alive_when_focused.append(bool(self.dialog))
            set_focus()

        with patch.object(self.owner.list, "SetFocus", side_effect=record_focus):
            for cycle in range(6):
                with self.subTest(cycle=cycle):
                    if cycle:
                        self.dialog = print_form.show_print_form(self.owner, self.path)
                    self.dialog.FindWindow(wx.ID_CANCEL).SetFocus()
                    self.job.poll.return_value = []
                    if cycle % 2:
                        prompt = self.open_reload_window()
                        click(prompt, wx.ID_OK)
                    else:
                        click(self.dialog, wx.ID_OK)
                    self.job.poll.return_value = [("done", "Printer")]
                    self.wait_until(lambda: not self.dialog)
                    # Keep processing after destruction: an immediate focus
                    # assertion can miss the later native focus restoration.
                    self.pump_events()
                    self.assertEqual(wx.Window.FindFocus(), self.owner.list)
                    self.assertEqual(self.owner.list.GetFirstSelected(), 0)
                    self.assertEqual(self.owner.list.GetFocusedItem(), 0)
        self.assertEqual(dialog_alive_when_focused, [False] * 6)

    def test_foreground_returns_after_driver_process_teardown(self):
        self.reopen_from_file_list()
        jobs = []
        record = Path(self.path).with_suffix(".ready")

        def start(request):
            job = REAL_PRINT_JOB(dict(request, record=str(record)))
            jobs.append(job)
            print_form.ctypes.windll.user32.AllowSetForegroundWindow(job.process.pid)
            job.connection.send(True)
            return job

        self.start_job.side_effect = start
        with patch.object(print_form, "_print_worker", simulated_foreground_worker):
            for cycle in range(3):
                with self.subTest(cycle=cycle):
                    if cycle:
                        record.unlink()
                        self.dialog = print_form.show_print_form(self.owner, self.path)
                    click(self.dialog, wx.ID_OK)
                    self.wait_until(lambda: record.exists(), timeout=15)
                    self.wait_until(lambda: jobs[-1].finished)
                    self.assertTrue(jobs[-1].process.is_alive())
                    self.assertTrue(self.dialog)
                    self.wait_until(lambda: not self.dialog, timeout=15)
                    self.wait_until(lambda: self.owner.IsActive())
                    # Include another event-loop pass after worker destruction.
                    wx.CallLater(250, self.app.ExitMainLoop)
                    self.app.MainLoop()
                    self.assertEqual(print_form.win32gui.GetForegroundWindow(), self.owner.GetHandle())
                    self.assertEqual(wx.Window.FindFocus(), self.owner.list)
                    self.assertEqual(self.owner.list.GetFirstSelected(), 0)

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

    def test_batch_form_lists_and_captures_original_selection(self):
        self.close_dialog()
        second = str(Path(self.path).with_name("second.pdf"))
        Path(second).touch()
        selected = [self.path, second]
        self.dialog = print_form.show_print_form(self.owner, selected)
        files = next(child for child in self.dialog.GetChildren()[0].GetChildren()
                     if isinstance(child, wx.ListBox))
        self.assertEqual(files.GetStrings(), selected)
        self.assertTrue(self.has_status(tr("print_files_label", count=2)))
        selected.clear()
        self.owner.current_preview_path = "unrelated.pdf"
        click(self.dialog, wx.ID_OK)
        self.start_job.assert_called_once()
        self.assertEqual(self.start_job.call_args.args[0]["document_path"], [self.path, second])
        self.assertTrue(self.owner.IsEnabled())

    def test_success_uses_three_second_list_hint_and_errors_stay_in_form(self):
        for kind, message in (("error", "Spooler failed"), ("done", "Printer")):
            click(self.dialog, wx.ID_OK)
            self.job.poll.return_value = [(kind, message)]
            expected = message if kind == "error" else tr("print_status_success", printer=message)
            if kind == "error":
                self.wait_until(lambda: self.has_status(expected))
                self.assertFalse(self.owner.list_selection_hint.IsShown())
                self.assertTrue(self.dialog.FindWindow(wx.ID_OK).IsEnabled())
            else:
                hint = self.owner.list_selection_hint
                self.wait_until(lambda: hint.IsShown() and hint.GetLabel() == expected)
                self.wait_until(lambda: not self.dialog)
                self.assertEqual(self.owner._list_selection_hint_timer.GetInterval(), 3000)
                self.wait_until(lambda: not hint.IsShown(), timeout=5)
            self.assertTrue(self.owner.IsEnabled())
        self.assertEqual(self.start_job.call_count, 2)
        self.assertEqual(self.job.close.call_count, 2)

    def open_reload_window(self):
        click(self.dialog, wx.ID_OK)
        self.job.poll.return_value = [("reload", "Reload the sheets")]
        self.wait_until(lambda: any(isinstance(child, wx.Dialog)
                                   for child in self.dialog.GetChildren()))
        self.job.poll.return_value = []
        return next(child for child in self.dialog.GetChildren() if isinstance(child, wx.Dialog))

    def test_manual_reload_message_window_resumes_only_after_ok(self):
        prompt = self.open_reload_window()
        self.assertFalse(prompt.IsModal())
        self.assertTrue(prompt.IsShown())
        self.assertEqual(prompt.GetTitle(), tr("print_manual_title"))
        self.assertTrue(any(isinstance(child, wx.StaticText) and child.GetLabel() == "Reload the sheets"
                            for child in prompt.GetChildren()))
        self.assertTrue(self.owner.IsEnabled())
        self.assertTrue(self.dialog.IsEnabled())
        received = []
        wx.CallAfter(received.append, "app remains responsive")
        self.wait_until(lambda: bool(received))
        self.job.resume.assert_not_called()
        click(prompt, wx.ID_OK)
        self.wait_until(lambda: not prompt)
        self.job.resume.assert_called_once()
        self.assertTrue(self.owner.IsEnabled())
        self.assertFalse(self.dialog.FindWindow(wx.ID_OK).IsEnabled())
        self.job.poll.return_value = [("done", "Printer")]
        self.wait_until(lambda: not self.dialog)
        self.job.close.assert_called_once()

    def test_cancelling_reload_message_closes_form_without_printing_backs(self):
        prompt = self.open_reload_window()
        click(prompt, wx.ID_CANCEL)
        self.wait_until(lambda: not self.dialog and not prompt)
        self.job.resume.assert_not_called()
        self.job.close.assert_called_once()
        self.assertFalse(self.owner.list_selection_hint.IsShown())

    def test_closing_reload_window_cancels_remaining_printing(self):
        prompt = self.open_reload_window()
        prompt.Close()
        self.wait_until(lambda: not self.dialog and not prompt)
        self.job.resume.assert_not_called()
        self.job.close.assert_called_once()

    def test_closing_print_form_also_closes_reload_window(self):
        prompt = self.open_reload_window()
        self.dialog.Close()
        self.wait_until(lambda: not self.dialog and not prompt)
        self.job.resume.assert_not_called()
        self.job.close.assert_called_once()

    def test_worker_error_closes_reload_window_and_allows_retry(self):
        prompt = self.open_reload_window()
        self.job.poll.return_value = [("error", "Printer offline")]
        self.wait_until(lambda: not prompt)
        self.assertTrue(self.has_status("Printer offline"))
        self.assertTrue(self.dialog.FindWindow(wx.ID_OK).IsEnabled())
        self.job.resume.assert_not_called()

    def test_cancel_command_detaches_job_and_destroys_modeless_dialog(self):
        click(self.dialog, wx.ID_OK)
        click(self.dialog, wx.ID_CANCEL)  # Also the command generated by Escape.
        self.pump_events()
        self.assertFalse(self.dialog)
        self.job.close.assert_called_once()
        self.job.resume.assert_not_called()

    def test_owner_destruction_detaches_job(self):
        prompt = self.open_reload_window()
        self.dialog.Destroy()  # Child dialogs also receive this on owner shutdown.
        self.pump_events()
        self.assertFalse(prompt)
        self.job.close.assert_called_once()


class PrintWorkerTests(unittest.TestCase):
    def test_completion_waits_for_worker_exit_without_blocking_reload(self):
        for terminal in (("done", "Printer"), ("error", "Spooler failed")):
            with self.subTest(terminal=terminal):
                job = print_form._PrintJob.__new__(print_form._PrintJob)
                job.connection = Mock()
                job.connection.poll.return_value = True
                job.connection.recv.side_effect = [("reload", "Reload sheets"), terminal]
                job.process = Mock()
                job.process.is_alive.return_value = True
                job.finished = False
                job._terminal_message = None
                self.assertEqual(job.poll(), [("reload", "Reload sheets")])
                self.assertEqual(job.poll(), [])
                job.process.is_alive.return_value = False
                self.assertEqual(job.poll(), [terminal])
                self.assertEqual(job.poll(), [])
                job.process.join.assert_not_called()

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
