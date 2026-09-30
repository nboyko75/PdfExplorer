"""Create embedded browsers with writable data storage in installed builds."""

import os
import sys
import ctypes


_webview_loader = None


def _load_packaged_webview_loader():
    """Keep the dynamically loaded wxWidgets dependency alive for all views."""
    global _webview_loader
    if not getattr(sys, 'frozen', False) or _webview_loader is not None:
        return
    bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    loader_path = os.path.join(bundle_dir, 'WebView2Loader.dll')
    if not os.path.isfile(loader_path):
        raise RuntimeError('The application package is missing WebView2Loader.dll. '
                           'Rebuild or reinstall DocExplorer.')
    # MSIX DLL lookup differs from development. Load the exact bundled copy
    # before wxWidgets attempts LoadLibrary("WebView2Loader.dll").
    _webview_loader = ctypes.WinDLL(loader_path)


def create_webview(html2, parent, **kwargs):
    """Configure WebView2 before native creation (including async startup).

    Its default profile lives beside the executable, which is read-only inside
    an MSIX's WindowsApps directory. Use one per-user profile for all views.
    The environment override also works with wxPython versions that do not
    expose WebViewConfiguration.SetDataPath.
    """
    if sys.platform == "win32":
        _load_packaged_webview_loader()
        edge_backend = getattr(html2, 'WebViewBackendEdge', None)
        if not edge_backend or not html2.WebView.IsBackendAvailable(edge_backend):
            raise RuntimeError('Microsoft Edge WebView2 is unavailable. '
                               'Install or repair the Microsoft Edge WebView2 Runtime.')
        data_path = os.environ.get("WEBVIEW2_USER_DATA_FOLDER")
        if not data_path:
            base = os.environ.get("LOCALAPPDATA") or os.path.join(
                os.path.expanduser("~"), "AppData", "Local"
            )
            data_path = os.path.join(base, "DocExplorer", "WebView2")
        data_path = os.path.abspath(data_path)
        os.makedirs(data_path, exist_ok=True)
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = data_path
    return html2.WebView.New(parent, **kwargs)
