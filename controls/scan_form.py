import os
import tempfile
from contextlib import nullcontext

import wx

try:
    import pythoncom
    import win32com.client as win32_client
except ImportError:  # pragma: no cover - optional runtime dependency
    pythoncom = None
    win32_client = None

try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    from PIL import Image, ImageOps
except ImportError:  # pragma: no cover - optional runtime dependency
    Image = None
    ImageOps = None

from localization import tr
from controls.window_tools import load_settings, update_settings, save_control_geometry, restore_control_geometry
import controls.file_preview as file_preview


def _create_nonexistent_temp_path(prefix, suffix):
    fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=suffix)
    os.close(fd)
    os.remove(temp_path)
    return temp_path


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
    open_after_scan_chk.SetValue(bool(settings.get("scan_open_after", False)))

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
    ok_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_TICK_MARK", wx.ART_INFORMATION), wx.ART_BUTTON, (16, 16))
    if ok_bmp.IsOk():
        scan_btn.SetBitmap(ok_bmp)
    cancel_bmp = wx.ArtProvider.GetBitmap(getattr(wx, "ART_CROSS_MARK", wx.ART_DELETE), wx.ART_BUTTON, (16, 16))
    if cancel_bmp.IsOk():
        cancel_btn.SetBitmap(cancel_bmp)
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

    restore_control_geometry(
        dialog,
        "scan_dialog",
        default_size=(520, 260),
        min_size=(260, 180),
        settings=settings,
    )

    result_code = dialog.ShowModal()
    save_control_geometry(dialog, "scan_dialog")

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
        "file_type_index": file_type_choice.GetSelection(),
        "multiple_pages": multiple_pages_chk.GetValue(),
        "output_path": output_path,
        "open_after": open_after_scan_chk.GetValue(),
    }
    dialog.Destroy()
    return scan_config


def _normalize_output_path(output_path, file_type_index):
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("scan_output_file_required")

    normalized_path = os.path.abspath(output_path.strip())
    root, ext = os.path.splitext(normalized_path)
    expected_ext = ".pdf" if file_type_index == 0 else ".jpg"
    if not ext:
        return root + expected_ext
    if ext.lower() != expected_ext:
        return root + expected_ext
    return normalized_path


def _build_nonconflicting_output_path(path):
    root, ext = os.path.splitext(path)
    index = 1
    while True:
        candidate = f"{root}({index}){ext}"
        if not os.path.exists(candidate):
            return candidate
        index += 1


def _resolve_output_path_before_save(owner, output_path, file_type_index):
    normalized_path = _normalize_output_path(output_path, file_type_index)
    if not os.path.exists(normalized_path):
        return normalized_path

    dialog = wx.MessageDialog(
        owner,
        tr("scan_overwrite_existing_prompt", path=normalized_path),
        tr("scan"),
        style=wx.YES_NO | wx.CANCEL | wx.ICON_WARNING,
    )
    dialog.SetYesNoCancelLabels(tr("confirm_yes"), tr("confirm_no"), tr("cancel_button"))
    try:
        result = dialog.ShowModal()
    finally:
        dialog.Destroy()

    if result == wx.ID_YES:
        return normalized_path
    if result == wx.ID_NO:
        return _build_nonconflicting_output_path(normalized_path)
    return None


def _should_show_scan_ui(scan_config, page_index):
    if not bool(scan_config.get("multiple_pages", False)):
        return True
    return page_index == 0


def _acquire_scanned_image_files(scan_config):
    if pythoncom is None or win32_client is None:
        raise RuntimeError("Windows WIA support is not available in this environment.")

    common_dialog = win32_client.Dispatch("WIA.CommonDialog")
    image_files = []
    page_index = 0

    while True:
        try:
            try:
                pythoncom.CoInitialize()
                show_ui = _should_show_scan_ui(scan_config, page_index)
                result = common_dialog.ShowAcquireImage(
                    0,
                    0,
                    0,
                    "{00000000-0000-0000-0000-000000000000}",
                    show_ui,
                    True,
                    False,
                )
            except Exception as exc:
                if "cancel" in str(exc).lower() or "user canceled" in str(exc).lower():
                    break
                raise RuntimeError(f"Unable to acquire image from scanner: {exc}") from exc
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

        if result is None:
            break

        acquired_items = []
        if hasattr(result, "Count"):
            try:
                acquired_items = [result[index] for index in range(int(result.Count))]
            except Exception:
                acquired_items = []
        elif hasattr(result, "Transfer"):
            acquired_items = [result]
        else:
            acquired_items = [result]

        for item in acquired_items:
            temp_path = None
            try:
                if hasattr(item, "FileName") and item.FileName:
                    candidate_path = os.path.abspath(str(item.FileName))
                    if os.path.isfile(candidate_path):
                        image_files.append(candidate_path)
                        continue

                temp_path = _create_nonexistent_temp_path(prefix="scan_", suffix=".jpg")

                if hasattr(item, "Transfer"):
                    transfer_result = item.Transfer()
                    if transfer_result is not None and hasattr(transfer_result, "FileName") and transfer_result.FileName:
                        image_path = os.path.abspath(str(transfer_result.FileName))
                        if os.path.isfile(image_path):
                            image_files.append(image_path)
                            continue
                    if hasattr(transfer_result, "SaveFile"):
                        transfer_result.SaveFile(temp_path)
                    elif hasattr(item, "SaveFile"):
                        item.SaveFile(temp_path)
                    else:
                        raise RuntimeError("Scanner returned an item that could not be saved to disk.")
                elif hasattr(item, "SaveFile"):
                    item.SaveFile(temp_path)
                else:
                    raise RuntimeError("Scanner returned an item that could not be saved to disk.")

                image_files.append(temp_path)
            except Exception as exc:
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                raise RuntimeError(f"Unable to save scanned image: {exc}") from exc

        page_index += 1
        if not bool(scan_config.get("multiple_pages", False)):
            break

    return image_files


def _save_scanned_pages(image_files, output_path, file_type_index):
    if not image_files:
        raise RuntimeError("No scanned images were acquired.")

    output_path = _normalize_output_path(output_path, file_type_index)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    if file_type_index == 0:
        if fitz is None:
            raise RuntimeError("PyMuPDF is not installed. PDF output is unavailable.")

        doc = fitz.open()
        try:
            for image_file in image_files:
                temp_handle = tempfile.NamedTemporaryFile(prefix="scan_page_", suffix=".jpg", delete=False)
                temp_handle.close()
                temp_path = temp_handle.name
                try:
                    if Image is not None and ImageOps is not None:
                        with Image.open(image_file) as image:
                            image = ImageOps.exif_transpose(image)
                            if image.mode not in {"RGB", "L"}:
                                image = image.convert("RGB")
                            image.save(temp_path, format="JPEG", quality=95)
                            image_width, image_height = image.width, image.height
                    else:
                        # Fallback for environments without Pillow.
                        wx_image = wx.Image(image_file, wx.BITMAP_TYPE_ANY)
                        if not wx_image.IsOk():
                            raise RuntimeError(f"Unable to load scanned image: {image_file}")
                        if not wx_image.SaveFile(temp_path, wx.BITMAP_TYPE_JPEG):
                            raise RuntimeError(f"Unable to convert scanned image to JPEG: {image_file}")
                        image_width, image_height = wx_image.GetWidth(), wx_image.GetHeight()

                    page = doc.new_page(width=max(1, image_width), height=max(1, image_height))
                    page.insert_image(page.rect, filename=temp_path, keep_proportion=True)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            doc.save(output_path, garbage=4, deflate=True, clean=True)
            return output_path
        finally:
            doc.close()

    if Image is not None and ImageOps is not None:
        with Image.open(image_files[0]) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(output_path, format="JPEG", quality=95)
    else:
        wx_image = wx.Image(image_files[0], wx.BITMAP_TYPE_ANY)
        if not wx_image.IsOk():
            raise RuntimeError(f"Unable to load scanned image: {image_files[0]}")
        if not wx_image.SaveFile(output_path, wx.BITMAP_TYPE_JPEG):
            raise RuntimeError(f"Unable to save JPEG output: {output_path}")

    return output_path


def _refresh_after_scan(owner, output_path):
    if owner is None:
        return

    current_folder = getattr(owner, "path_box", None)
    if current_folder is not None:
        try:
            current_folder_value = current_folder.GetValue()
        except Exception:
            current_folder_value = ""
        if current_folder_value and os.path.isdir(current_folder_value):
            owner.load_folder(current_folder_value)

    if output_path and os.path.isfile(output_path):
        if hasattr(owner, "current_preview_path"):
            owner.current_preview_path = output_path
        try:
            file_preview.show_file_preview(owner, output_path)
        except Exception:
            pass


def on_scan_form(owner):
    scan_config = _show_scan_dialog(owner)
    if scan_config is None:
        return

    output_path = scan_config["output_path"]
    output_name = os.path.splitext(os.path.basename(output_path))[0]
    update_settings(
        {
            "scan_file_type_index": scan_config["file_type_index"],
            "scan_multiple_pages": scan_config["multiple_pages"],
            "scan_output_name": output_name,
            "scan_open_after": scan_config["open_after"],
        }
    )

    try:
        cursor_context = owner.busy_cursor() if hasattr(owner, "busy_cursor") else nullcontext()
        with cursor_context:
            image_files = _acquire_scanned_image_files(scan_config)
            if not image_files:
                return
            output_path = _resolve_output_path_before_save(owner, output_path, scan_config["file_type_index"])
            if output_path is None:
                return
            output_path = _save_scanned_pages(image_files, output_path, scan_config["file_type_index"])
            _refresh_after_scan(owner, output_path)
            if scan_config.get("open_after", False):
                try:
                    os.startfile(output_path)
                except Exception:
                    pass
            wx.MessageBox(
                tr("scan_saved_message", output_path=output_path),
                tr("scan"),
                style=wx.OK | wx.ICON_INFORMATION,
            )
    except Exception as exc:
        wx.MessageBox(str(exc), tr("scan"), style=wx.OK | wx.ICON_ERROR)
