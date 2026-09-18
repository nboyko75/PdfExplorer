"""HTML5 video preview using WebView2 and a private, range-aware local stream."""
import html
import mimetypes
import os
import re
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import wx
from localization import tr

try:
    import wx.html2 as wx_html2
except ImportError:
    wx_html2 = None

from common.consts import VIDEO_EXTENSIONS


def is_video_file(path):
    return isinstance(path, str) and os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def close_video_preview(owner):
    panel = getattr(owner, "video_preview_panel", None)
    if panel is not None:
        panel.close()


def _byte_range(header, size):
    """Return an inclusive single byte range, or raise ValueError for 416."""
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header or "")
    if not match or size <= 0:
        raise ValueError("Invalid range")
    first, last = match.groups()
    if not first:
        if not last or int(last) <= 0:
            raise ValueError("Invalid suffix")
        return max(0, size - int(last)), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or end < start:
        raise ValueError("Unsatisfiable range")
    return start, end


def _player_html(source, error_text):
    return ('''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body{margin:0;width:100%;height:100%;background:#181818;color:#eee;
font:14px system-ui}body{display:flex;flex-direction:column}
video{width:100%;flex:1;min-height:0;object-fit:contain}p{padding:12px}</style>
</head><body><video controls preload="metadata" playsinline src="'''
            + html.escape(source, quote=True) + '''"></video><p hidden>'''
            + html.escape(error_text) + '''</p><script>
const v=document.querySelector('video'),p=document.querySelector('p');
v.addEventListener('error',()=>{p.hidden=false;
if(v.error)p.textContent+=' (MediaError '+v.error.code+')';});
window.addEventListener('pagehide',()=>{v.pause();v.removeAttribute('src');v.load();});
</script></body></html>''').encode("utf-8")


class VideoStream:
    """Serve only the selected file, with byte ranges for seeking; never a folder."""
    def __init__(self, path, error_text):
        self.path = os.path.abspath(path)
        self.stop_event = threading.Event()
        self.token = "/" + secrets.token_urlsafe(24)
        self.mime = {".mp4": "video/mp4", ".m4v": "video/mp4",
                     ".webm": "video/webm", ".ogv": "video/ogg"}.get(
                         os.path.splitext(path)[1].lower(),
                         mimetypes.guess_type(path)[0] or "application/octet-stream")
        stream = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_HEAD(self):
                self._serve(False)

            def do_GET(self):
                self._serve(True)

            def _serve(self, send_body):
                if stream.stop_event.is_set():
                    self.send_error(410)
                    return
                if self.path == stream.token + "/":
                    body = _player_html(stream.token + "/video", error_text)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    if send_body:
                        try:
                            self.wfile.write(body)
                        except OSError:
                            pass
                    return
                if self.path != stream.token + "/video":
                    self.send_error(404)
                    return
                try:
                    source = open(stream.path, "rb")
                except OSError:
                    self.send_error(404)
                    return
                with source:
                    size = os.fstat(source.fileno()).st_size
                    start, end = 0, size - 1
                    partial = self.headers.get("Range")
                    if partial:
                        try:
                            start, end = _byte_range(partial, size)
                        except ValueError:
                            self.send_response(416)
                            self.send_header("Content-Range", "bytes */" + str(size))
                            self.send_header("Content-Length", "0")
                            self.end_headers()
                            return
                    self.send_response(206 if partial else 200)
                    self.send_header("Content-Type", stream.mime)
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(max(0, end - start + 1)))
                    self.send_header("Cache-Control", "no-store")
                    if partial:
                        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                    self.end_headers()
                    if not send_body:
                        return
                    source.seek(start)
                    remaining = end - start + 1
                    self.connection.settimeout(1)
                    try:
                        while remaining > 0 and not stream.stop_event.is_set():
                            chunk = source.read(min(64 * 1024, remaining))
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                    except OSError:
                        pass  # Normal when seeking or closing a preview.

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.server.server_port}{self.token}/"
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": 0.05}, daemon=True)
        self.thread.start()

    def close(self):
        if not self.stop_event.is_set():
            self.stop_event.set()
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=1)


class VideoPreviewPanel(wx.Panel):
    def __init__(self, parent):
        super().__init__(parent)
        self.browser = None
        self.stream = None
        self.status = wx.StaticText(self, label="")
        self.sizer = wx.BoxSizer(wx.VERTICAL)
        self.sizer.Add(self.status, 0, wx.EXPAND | wx.ALL, 8)
        self.SetSizer(self.sizer)
        self.SetMinSize((0, 0))
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

    def close(self):
        browser, self.browser = self.browser, None
        stream, self.stream = self.stream, None
        if browser is not None:
            self.sizer.Detach(browser)
            browser.Hide()
            try:
                browser.LoadURL("about:blank")
            except Exception:
                pass
            browser.Destroy()
        if stream is not None:
            stream.close()

    def load(self, path):
        self.close()
        self.status.SetLabel(tr("video_loading"))
        self.status.Show()
        try:
            if wx_html2 is None or not getattr(wx_html2, "WebViewBackendEdge", None):
                raise RuntimeError(tr("video_backend_unavailable"))
            self.browser = wx_html2.WebView.New(self, backend=wx_html2.WebViewBackendEdge)
            self.browser.SetMinSize((0, 0))
            self.sizer.Add(self.browser, 1, wx.EXPAND)
            self.browser.Bind(wx_html2.EVT_WEBVIEW_LOADED, self._on_loaded)
            self.browser.Bind(wx_html2.EVT_WEBVIEW_ERROR, self._on_error)
            self.stream = VideoStream(path, tr("video_load_failed"))
            self.browser.LoadURL(self.stream.url)
        except Exception as exc:
            self.close()
            self.status.SetLabel(tr("unable_preview_file", exc=exc))
        self.Layout()

    def _on_loaded(self, event):
        if event.GetEventObject() is self.browser and self.stream is not None:
            if event.GetURL() == self.stream.url:
                self.status.Hide()
                self.Layout()

    def _on_error(self, event):
        if event.GetEventObject() is self.browser and self.browser is not None:
            detail = event.GetString()
            self.close()
            self.status.SetLabel(tr("unable_preview_file", exc=detail))
            self.status.Show()
            self.Layout()

    def _on_destroy(self, event):
        if event.GetEventObject() is self:
            self.close()
        event.Skip()
