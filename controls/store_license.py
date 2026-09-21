"""Modal Store gate, with background queries and safe handling of edited PDFs."""
import queue
import threading
import time
from datetime import datetime, timezone
import wx
from common.store_license import License, package_family_name, query_license, store_uri
from localization import tr


class LicenseDialog(wx.Dialog):
    def __init__(self, parent=None, result=None):
        super().__init__(parent, title=tr('license_title'), style=wx.DEFAULT_DIALOG_STYLE)
        self.result = result
        self.pending = False
        self.answers = queue.Queue()
        self.message = wx.StaticText(self, label='')
        self.message.SetMinSize((460, 100))
        self.retry = wx.Button(self, label=tr('license_retry'))
        buy = wx.Button(self, label=tr('license_buy'))
        leave = wx.Button(self, wx.ID_CANCEL, label=tr('license_exit'))
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        for button in (self.retry, buy, leave):
            buttons.Add(button, 0, wx.ALL, 5)
        layout = wx.BoxSizer(wx.VERTICAL)
        layout.Add(self.message, 1, wx.ALL | wx.EXPAND, 15)
        layout.Add(buttons, 0, wx.ALL | wx.ALIGN_RIGHT, 10)
        self.SetSizerAndFit(layout)
        self.retry.Bind(wx.EVT_BUTTON, lambda event: self.check())
        buy.Bind(wx.EVT_BUTTON, self.open_store)
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.poll, self.timer)
        self.Bind(wx.EVT_WINDOW_DESTROY, self.on_destroy)
        self.timer.Start(100)
        self.CentreOnParent()
        if result is None:
            wx.CallAfter(self.check)
        else:
            self.display(result)

    def on_destroy(self, event):
        if event.GetEventObject() is self:
            self.timer.Stop()
        event.Skip()

    def display(self, result):
        key = 'license_error' if result.state == 'error' else 'license_expired'
        text = tr(key)
        if result.detail:
            text += '\n\n' + result.detail
        self.message.SetLabel(text)
        self.message.Wrap(460)
        self.GetSizer().Fit(self)

    def check(self):
        if self.pending:
            return
        self.pending = True
        self.started = time.monotonic()
        self.retry.Disable()
        self.message.SetLabel(tr('license_checking'))
        hwnd = self.GetHandle()
        answers = self.answers
        threading.Thread(target=lambda: answers.put(query_license(hwnd)), daemon=True).start()

    def poll(self, event):
        try:
            result = self.answers.get_nowait()
        except queue.Empty:
            if self.pending and time.monotonic() - self.started > 35:
                # Keep the worker single-flight until it returns. Exit remains available.
                self.message.SetLabel(tr('license_error'))
                self.message.Wrap(460)
            return
        self.pending = False
        self.retry.Enable()
        self.result = result
        if result.allowed:
            self.EndModal(wx.ID_OK)
        else:
            self.display(result)

    def open_store(self, event):
        try:
            if not wx.LaunchDefaultBrowser(store_uri()):
                raise RuntimeError(tr('license_store_failed'))
        except Exception as exc:
            wx.MessageBox(str(exc), tr('license_title'), wx.OK | wx.ICON_ERROR, self)


def startup_license():
    try:
        if package_family_name() is None:
            return License('unpackaged')
    except Exception:
        pass  # Unexpected identity errors must not bypass Store licensing.
    dialog = LicenseDialog()
    try:
        return dialog.result if dialog.ShowModal() == wx.ID_OK else None
    finally:
        dialog.Destroy()


class LicenseMonitor:
    def __init__(self, frame, license):
        self.frame = frame
        self.license = license
        self.answers = queue.Queue()
        self.pending = False
        self.stopped = False
        self.gating = False
        self.next_check = time.monotonic() + 300
        self.timer = wx.Timer(frame)
        frame.Bind(wx.EVT_TIMER, self.tick, self.timer)
        frame.Bind(wx.EVT_WINDOW_DESTROY, self.destroyed)
        self.timer.Start(1000)
        if license.state == 'trial':
            wx.CallAfter(wx.MessageBox,
                         tr('license_trial', days=license.days_left,
                            date=license.expires.astimezone().strftime('%Y-%m-%d %H:%M')),
                         tr('license_title'), wx.OK | wx.ICON_INFORMATION, frame)

    def destroyed(self, event):
        if event.GetEventObject() is self.frame:
            self.stopped = True
            self.timer.Stop()
        event.Skip()

    def tick(self, event):
        if self.stopped or self.gating:
            return
        try:
            result = self.answers.get_nowait()
        except queue.Empty:
            result = None
        if result is not None:
            self.pending = False
            self.next_check = time.monotonic() + 300
            if result.allowed:
                self.license = result
            else:
                self.gate(result)
                return
        expired = (self.license.state == 'trial' and
                   self.license.expires <= datetime.now(timezone.utc))
        if expired:
            self.gate(License('expired', self.license.expires))
            return
        if time.monotonic() >= self.next_check and not self.pending:
            self.pending = True
            hwnd = self.frame.GetHandle()
            answers = self.answers
            threading.Thread(target=lambda: answers.put(query_license(hwnd)), daemon=True).start()

    def gate(self, result):
        self.gating = True
        dialog = LicenseDialog(self.frame, result)
        try:
            accepted = dialog.ShowModal() == wx.ID_OK
            if accepted:
                self.license = dialog.result
                self.next_check = time.monotonic() + 300
        finally:
            dialog.Destroy()
        if not accepted:
            # Existing on_close allows saving pending edits, and may veto on error/cancel.
            self.frame.Close()
            if not self.stopped and self.frame:
                # Re-open the modal gate after a veto; do not force-destroy unsaved work.
                wx.CallAfter(self.reopen, result)
                return
        self.gating = False

    def reopen(self, result):
        if not self.stopped and self.frame and not self.frame.IsBeingDeleted():
            self.gate(result)
