"""Owned, read-only Office documents used by preview exporters.

Only DispatchEx-created applications are closed here. Never pass a user's
running Office instance to this helper.
"""
from contextlib import contextmanager
import gc
import logging
import os

logger = logging.getLogger(__name__)


def _close_quietly(obj, method, *args):
    if obj is not None:
        try:
            getattr(obj, method)(*args)
        except Exception:
            logger.debug("Office cleanup failed: %s", method, exc_info=True)


@contextmanager
def preview_document(client, com, kind, source_path, *, hide_excel_window=False):
    """Close the document/application and balance COM even if export fails."""
    app = document = None
    initialized = False
    try:
        if com is not None:
            com.CoInitialize()
            initialized = True
        app = client.DispatchEx(kind + ".Application")
        if kind == "Word":
            app.Visible = False
            app.DisplayAlerts = 0
            app.ScreenUpdating = False
            document = app.Documents.Open(
                FileName=os.path.abspath(source_path),
                ConfirmConversions=False,
                ReadOnly=True,
                AddToRecentFiles=False,
                Visible=False,
                OpenAndRepair=False,
            )
        elif kind == "Excel":
            app.Visible = False
            app.DisplayAlerts = False
            app.ScreenUpdating = False
            app.EnableEvents = False
            app.AskToUpdateLinks = False
            document = app.Workbooks.Open(
                Filename=os.path.abspath(source_path),
                UpdateLinks=0,
                ReadOnly=True,
                IgnoreReadOnlyRecommended=True,
                AddToMru=False,
                Notify=False,
            )
            if hide_excel_window:
                try:
                    document.Windows(1).Visible = False
                except Exception:
                    logger.debug("Cannot hide Excel window", exc_info=True)
        elif kind == "PowerPoint":
            document = app.Presentations.Open(
                os.path.abspath(source_path), ReadOnly=True, WithWindow=False
            )
        else:
            raise ValueError("Unsupported Office application: " + kind)
        yield document
    finally:
        close_args = () if kind == "PowerPoint" else (False,)
        _close_quietly(document, "Close", *close_args)
        _close_quietly(app, "Quit")
        document = app = None
        gc.collect()
        if initialized:
            com.CoUninitialize()
