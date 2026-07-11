import os

import wx

from localization import tr
from controls.window_tools import load_settings, update_settings


def _get_scan_dialog_initial_dir(owner):
    candidate = str(owner.search_box.GetValue()).strip()
    if candidate:
        normalized_candidate = os.path.abspath(candidate)
        if os.path.isdir(normalized_candidate):
            return normalized_candidate

        parent_dir = os.path.dirname(normalized_candidate)
        if parent_dir and os.path.isdir(parent_dir):
            return parent_dir

    current_path = getattr(owner, "current_preview_path", None)
    if isinstance(current_path, str) and current_path:
        preview_dir = os.path.dirname(os.path.abspath(current_path))
        if preview_dir and os.path.isdir(preview_dir):
            return preview_dir

    return os.getcwd()


def _show_scan_dialog(owner):
    settings = load_settings()

    dialog = wx.Dialog(owner, title=tr("scan_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    scanner_label = wx.StaticText(panel, label=tr("scan_scanner_label"))
    scanner_choices = [tr("scan_default_scanner")]
    scanner_choice = wx.Choice(panel, choices=scanner_choices)
    scanner_choice.SetSelection(0)

    source_label = wx.StaticText(panel, label=tr("scan_source_label"))
    source_choices = [tr("scan_source_flatbed"), tr("scan_source_adf_simplex"), tr("scan_source_adf_duplex")]
    source_choice = wx.Choice(panel, choices=source_choices)
    source_choice.SetSelection(int(settings.get("scan_source_index", 0)) if str(settings.get("scan_source_index", "0")).isdigit() else 0)

    mode_label = wx.StaticText(panel, label=tr("scan_color_mode_label"))
    mode_choices = [tr("scan_color_mode_color"), tr("scan_color_mode_grayscale"), tr("scan_color_mode_black_white")]
    mode_choice = wx.Choice(panel, choices=mode_choices)
    mode_choice.SetSelection(int(settings.get("scan_color_mode_index", 0)) if str(settings.get("scan_color_mode_index", "0")).isdigit() else 0)

    dpi_label = wx.StaticText(panel, label=tr("scan_dpi_label"))
    dpi_choices = ["150", "200", "300", "600"]
    dpi_choice = wx.Choice(panel, choices=dpi_choices)
    dpi_choice.SetSelection(int(settings.get("scan_dpi_index", 2)) if str(settings.get("scan_dpi_index", "2")).isdigit() else 2)

    page_size_label = wx.StaticText(panel, label=tr("scan_page_size_label"))
    page_size_choices = [tr("scan_page_size_auto"), tr("scan_page_size_a4"), tr("scan_page_size_letter"), tr("scan_page_size_legal")]
    page_size_choice = wx.Choice(panel, choices=page_size_choices)
    page_size_choice.SetSelection(int(settings.get("scan_page_size_index", 0)) if str(settings.get("scan_page_size_index", "0")).isdigit() else 0)

    file_type_label = wx.StaticText(panel, label=tr("scan_output_type_label"))
    file_type_choices = [tr("scan_output_type_pdf"), tr("scan_output_type_jpeg")]
    file_type_choice = wx.Choice(panel, choices=file_type_choices)
    file_type_choice.SetSelection(int(settings.get("scan_file_type_index", 0)) if str(settings.get("scan_file_type_index", "0")).isdigit() else 0)

    multiple_pages_chk = wx.CheckBox(panel, label=tr("scan_multiple_pages_label"))
    multiple_pages_chk.SetValue(bool(settings.get("scan_multiple_pages", True)))

    output_label = wx.StaticText(panel, label=tr("scan_output_file_label"))
    default_dir = _get_scan_dialog_initial_dir(owner)
    default_ext = ".pdf" if file_type_choice.GetSelection() == 0 else ".jpg"
    default_name = str(settings.get("scan_output_name", "scan_result"))
    output_text = wx.TextCtrl(panel, value=os.path.join(default_dir, f"{default_name}{default_ext}"))
    browse_btn = wx.Button(panel, label=tr("scan_browse_button"))

    open_after_scan_chk = wx.CheckBox(panel, label=tr("scan_open_after_label"))
    open_after_scan_chk.SetValue(bool(settings.get("scan_open_after", True)))

    def update_output_extension(_):
        current_value = output_text.GetValue().strip()
        root, _ = os.path.splitext(current_value)
        ext = ".pdf" if file_type_choice.GetSelection() == 0 else ".jpg"
        if root:
            output_text.SetValue(root + ext)

    def browse_output(_):
        current_value = output_text.GetValue().strip()
        current_dir = os.path.dirname(current_value) if current_value else default_dir
        if not current_dir or not os.path.isdir(current_dir):
            current_dir = default_dir
        current_file = os.path.basename(current_value) if current_value else (f"{default_name}{'.pdf' if file_type_choice.GetSelection() == 0 else '.jpg'}")
        wildcard = "PDF files (*.pdf)|*.pdf" if file_type_choice.GetSelection() == 0 else "JPEG files (*.jpg)|*.jpg"
        file_dialog = wx.FileDialog(
            dialog,
            tr("scan_select_output_file_title"),
            defaultDir=current_dir,
            defaultFile=current_file,
            wildcard=wildcard,
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )
        if file_dialog.ShowModal() == wx.ID_OK:
            output_text.SetValue(file_dialog.GetPath())
        file_dialog.Destroy()

    file_type_choice.Bind(wx.EVT_CHOICE, update_output_extension)
    browse_btn.Bind(wx.EVT_BUTTON, browse_output)

    fields = wx.FlexGridSizer(cols=2, hgap=8, vgap=8)
    fields.Add(scanner_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(scanner_choice, 1, wx.EXPAND)
    fields.Add(source_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(source_choice, 1, wx.EXPAND)
    fields.Add(mode_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(mode_choice, 1, wx.EXPAND)
    fields.Add(dpi_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(dpi_choice, 1, wx.EXPAND)
    fields.Add(page_size_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(page_size_choice, 1, wx.EXPAND)
    fields.Add(file_type_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(file_type_choice, 1, wx.EXPAND)
    fields.Add(multiple_pages_chk, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add((1, 1), 1, wx.EXPAND)
    fields.Add(output_label, 0, wx.ALIGN_CENTER_VERTICAL)

    output_row = wx.BoxSizer(wx.HORIZONTAL)
    output_row.Add(output_text, 1, wx.RIGHT, 8)
    output_row.Add(browse_btn, 0)
    fields.Add(output_row, 1, wx.EXPAND)
    fields.AddGrowableCol(1, 1)

    scan_btn = wx.Button(panel, wx.ID_OK, tr("scan_button"))
    cancel_btn = wx.Button(panel, wx.ID_CANCEL, tr("scan_cancel_button"))
    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(scan_btn, 0, wx.RIGHT, 8)
    button_sizer.Add(cancel_btn, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(fields, 1, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(open_after_scan_chk, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizerAndFit(dialog_sizer)

    saved_size = settings.get("scan_dialog_size")
    if isinstance(saved_size, list) and len(saved_size) == 2:
        width, height = int(saved_size[0]), int(saved_size[1])
        if width > 100 and height > 100:
            dialog.SetSize((width, height))

    result_code = dialog.ShowModal()
    dialog_size = dialog.GetSize()
    update_settings({"scan_dialog_size": [int(dialog_size.x), int(dialog_size.y)]})

    if result_code != wx.ID_OK:
        dialog.Destroy()
        return None

    output_path = output_text.GetValue().strip()
    if not output_path:
        dialog.Destroy()
        wx.MessageBox(tr("scan_output_file_required"), tr("scan"), style=wx.OK | wx.ICON_INFORMATION)
        return None

    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir and not os.path.isdir(output_dir):
        dialog.Destroy()
        wx.MessageBox(tr("scan_output_folder_not_exists"), tr("scan"), style=wx.OK | wx.ICON_INFORMATION)
        return None

    scan_config = {
        "scanner_index": scanner_choice.GetSelection(),
        "source_index": source_choice.GetSelection(),
        "color_mode_index": mode_choice.GetSelection(),
        "dpi_index": dpi_choice.GetSelection(),
        "page_size_index": page_size_choice.GetSelection(),
        "file_type_index": file_type_choice.GetSelection(),
        "multiple_pages": multiple_pages_chk.GetValue(),
        "output_path": output_path,
        "open_after": open_after_scan_chk.GetValue(),
    }
    dialog.Destroy()
    return scan_config


def on_scan_form(owner):
    scan_config = _show_scan_dialog(owner)
    if scan_config is None:
        return

    output_path = scan_config["output_path"]
    output_name = os.path.splitext(os.path.basename(output_path))[0]
    update_settings(
        {
            "scan_source_index": scan_config["source_index"],
            "scan_color_mode_index": scan_config["color_mode_index"],
            "scan_dpi_index": scan_config["dpi_index"],
            "scan_page_size_index": scan_config["page_size_index"],
            "scan_file_type_index": scan_config["file_type_index"],
            "scan_multiple_pages": scan_config["multiple_pages"],
            "scan_output_name": output_name,
            "scan_open_after": scan_config["open_after"],
        }
    )

    wx.MessageBox(
        tr("scan_not_available_message"),
        tr("scan"),
        style=wx.OK | wx.ICON_INFORMATION,
    )
