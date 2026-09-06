import os
import sys

import wx

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None

from localization import tr


MANUAL_RELATIVE_PATH = os.path.join("docs", "DocExplorer_User_Manual.pdf")


def _resource_path(relative_path):
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)


def _set_manual_page_bitmap(bitmap_control, pdf_page, available_width):
    page_width = max(1.0, float(pdf_page.rect.width))
    target_width = max(320, min(1400, int(available_width)))
    zoom = max(0.5, min(2.5, target_width / page_width))
    pixmap = pdf_page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    image = wx.Image(pixmap.width, pixmap.height)
    image.SetData(bytes(pixmap.samples))
    bitmap_control.SetBitmap(wx.Bitmap(image))
    bitmap_control.SetMinSize((pixmap.width, pixmap.height))


def show_app_manual_form(owner):
    manual_path = _resource_path(MANUAL_RELATIVE_PATH)
    if not os.path.isfile(manual_path):
        wx.MessageBox(f"Manual file was not found:\n{manual_path}", tr("menu_app_manual"), style=wx.OK | wx.ICON_ERROR)
        return

    dialog = wx.Dialog(owner, title=tr("menu_app_manual"), size=(1000, 760), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)
    toolbar = wx.BoxSizer(wx.HORIZONTAL)
    open_btn = wx.Button(panel, label=tr("help_manual_open_pdf_button"))
    close_btn = wx.Button(panel, wx.ID_CLOSE, tr("exit_button"))
    toolbar.Add(open_btn, 0, wx.RIGHT, 8)
    toolbar.AddStretchSpacer(1)
    toolbar.Add(close_btn, 0)

    scroll = wx.ScrolledWindow(panel, style=wx.VSCROLL | wx.HSCROLL)
    scroll.SetScrollRate(12, 12)
    pages_sizer = wx.BoxSizer(wx.VERTICAL)
    pdf_document = None

    if fitz is None:
        message = wx.StaticText(scroll, label="The embedded PDF renderer is unavailable. Select Open PDF to view the manual.")
        pages_sizer.Add(message, 0, wx.ALL, 16)
    else:
        try:
            pdf_document = fitz.open(manual_path)
            available_width = max(700, dialog.GetClientSize().width - 70)
            for page_index in range(pdf_document.page_count):
                page_bitmap = wx.StaticBitmap(scroll)
                _set_manual_page_bitmap(page_bitmap, pdf_document.load_page(page_index), available_width)
                pages_sizer.Add(page_bitmap, 0, wx.ALIGN_CENTER | wx.ALL, 8)
        except Exception as exc:
            if pdf_document is not None:
                pdf_document.close()
                pdf_document = None
            message = wx.StaticText(scroll, label=f"The manual could not be rendered inside DocExplorer.\n{exc}\n\nSelect Open PDF to view it.")
            pages_sizer.Add(message, 0, wx.ALL, 16)

    scroll.SetSizer(pages_sizer)
    scroll.FitInside()
    main_sizer = wx.BoxSizer(wx.VERTICAL)
    main_sizer.Add(scroll, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
    main_sizer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 10)
    panel.SetSizer(main_sizer)

    open_btn.Bind(wx.EVT_BUTTON, lambda _event: os.startfile(manual_path))
    close_btn.Bind(wx.EVT_BUTTON, lambda _event: dialog.EndModal(wx.ID_CLOSE))
    dialog.CenterOnParent()
    try:
        dialog.ShowModal()
    finally:
        if pdf_document is not None:
            pdf_document.close()
        dialog.Destroy()
