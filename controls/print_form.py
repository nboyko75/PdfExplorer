import os
import tempfile

import wx

try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    import win32api  # type: ignore[import-not-found]
    import win32con  # type: ignore[import-not-found]
    import win32print  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    win32api = None
    win32con = None
    win32print = None

try:
    import pythoncom  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    pythoncom = None

try:
    import win32com.client as win32_client  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    win32_client = None

from controls.file_preview import IMAGE_EXTENSIONS
from localization import tr
from controls.window_tools import load_settings, update_settings
import file_operations.office_preview as office_preview
import file_operations.pdf_utils as pdf_utils


def _get_printer_names():
    if win32print is None:
        return []

    try:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        printers = win32print.EnumPrinters(flags, None, 1)
    except Exception:
        return []

    names = []
    for item in printers:
        if not isinstance(item, (tuple, list)) or len(item) < 4:
            continue
        name = item[2]
        if isinstance(name, str) and name.strip():
            names.append(name.strip())

    unique_names = []
    seen = set()
    for name in names:
        if name not in seen:
            seen.add(name)
            unique_names.append(name)
    return unique_names


def _get_document_page_count(path):
    if not isinstance(path, str) or not path:
        return 0

    lower_path = path.lower()
    if lower_path.endswith(".pdf"):
        try:
            return max(1, int(pdf_utils.get_pdf_page_count(path)))
        except Exception:
            return 0

    if office_preview.can_preview_office(path):
        try:
            return max(1, int(office_preview.get_office_document_page_count(path)))
        except Exception:
            return 0

    if os.path.splitext(lower_path)[1] in IMAGE_EXTENSIONS:
        return 1

    return 1


def _parse_page_numbers_input(text, page_count):
    page_count = max(1, int(page_count or 1))
    tokens = [token.strip() for token in str(text).split(",") if token.strip()]
    if not tokens:
        raise ValueError(tr("export_pdf_page_numbers_invalid"))

    page_indices = []
    seen = set()
    for token in tokens:
        if "-" in token:
            parts = [part.strip() for part in token.split("-", 1)]
            if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            start_page = int(parts[0])
            end_page = int(parts[1])
            step = 1 if end_page >= start_page else -1
            page_numbers = range(start_page, end_page + step, step)
        else:
            if not token.isdigit():
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            page_numbers = [int(token)]

        for page_number in page_numbers:
            if not 1 <= page_number <= page_count:
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            page_index = page_number - 1
            if page_index in seen:
                continue
            seen.add(page_index)
            page_indices.append(page_index)

    if not page_indices:
        raise ValueError(tr("export_pdf_page_numbers_invalid"))
    return page_indices


def _build_office_page_range(page_numbers):
    if page_numbers is None:
        return ""

    raw_is_string = isinstance(page_numbers, str)
    if raw_is_string:
        raw_value = page_numbers.strip()
        if not raw_value:
            return ""
        values = []
        for chunk in [token.strip() for token in raw_value.split(",") if token.strip()]:
            if "-" in chunk:
                start_text, end_text = [part.strip() for part in chunk.split("-", 1)]
                if not start_text or not end_text or not start_text.isdigit() or not end_text.isdigit():
                    return ""
                start_page = int(start_text)
                end_page = int(end_text)
                if end_page < start_page:
                    return ""
                values.extend(range(start_page, end_page + 1))
            elif chunk.isdigit():
                values.append(int(chunk))
            else:
                return ""
        page_numbers = values
    elif isinstance(page_numbers, int):
        page_numbers = [page_numbers]

    normalized_pages = []
    for page in (page_numbers or []):
        try:
            page_value = int(page)
        except (TypeError, ValueError):
            continue
        if raw_is_string:
            if page_value < 1:
                continue
            normalized_pages.append(page_value)
        else:
            if page_value < 0:
                continue
            normalized_pages.append(page_value + 1)

    if not normalized_pages:
        return ""

    normalized_pages = sorted(set(normalized_pages))
    ranges = []
    start = prev = normalized_pages[0]
    for page in normalized_pages[1:]:
        if page == prev + 1:
            prev = page
            continue
        ranges.append(f"{start}-{prev}" if start != prev else str(start))
        start = prev = page
    ranges.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(ranges)


def _get_running_print_office_document(document_path, app_name, collection_name):
    if win32_client is None:
        return None, None

    try:
        app = win32_client.GetActiveObject(app_name)
    except Exception:
        return None, None

    collection = getattr(app, collection_name, None)
    if collection is None:
        return app, None

    target = os.path.normcase(os.path.normpath(os.path.abspath(document_path)))
    for item in collection:
        try:
            full_name = getattr(item, "FullName", None)
            if full_name and os.path.normcase(os.path.normpath(os.path.abspath(full_name))) == target:
                return app, item
        except Exception:
            continue

    return app, None


def _print_office_document_pages(document_path, printer_name, copies=1, page_numbers=None):
    if not isinstance(document_path, str) or not document_path or not os.path.exists(document_path):
        raise FileNotFoundError(document_path)

    if win32_client is None:
        raise RuntimeError(tr("print_error_unavailable"))

    if not page_numbers:
        return

    ext = os.path.splitext(document_path)[1].lower()
    if pythoncom is not None:
        try:
            pythoncom.CoInitialize()
        except Exception:
            pass

    try:
        if ext in {".doc", ".docx", ".docm"}:
            app = None
            document = None
            should_close_document = False
            should_quit_app = True
            try:
                try:
                    app, document = _get_running_print_office_document(document_path, "Word.Application", "Documents")
                except Exception:
                    app, document = None, None
                if app is None:
                    app = win32_client.DispatchEx("Word.Application")
                else:
                    should_quit_app = False
                app.Visible = False
                app.DisplayAlerts = 0
                if document is None:
                    document = app.Documents.Open(document_path, ReadOnly=True)
                    should_close_document = True
                try:
                    app.ActivePrinter = printer_name
                    doc_pages = _build_office_page_range(page_numbers)
                    # === COPILOT PROTECTED: BEGIN ===
                    range_type = 4  # wdPrintRangeOfPages 
                    document.PrintOut(
                        Background=False,
                        Append=False,
                        Range=range_type,
                        OutputFileName="",
                        From="",
                        To="",
                        Item=0, 
                        Copies=copies,
                        Pages=doc_pages
                    )
                    # === COPILOT PROTECTED: END ===
                finally:
                    if should_close_document and document is not None:
                        document.Close(False)
            finally:
                if app is not None and should_quit_app:
                    app.Quit()
            return

        if ext in {".xls", ".xlsx", ".xlsm"}:
            app = None
            workbook = None
            should_close_workbook = False
            should_quit_app = True
            try:
                try:
                    app, workbook = office_preview._get_running_office_document(document_path, "Excel.Application", "Workbooks")
                except Exception:
                    app, workbook = None, None
                if app is None:
                    app = win32_client.DispatchEx("Excel.Application")
                else:
                    should_quit_app = False
                app.Visible = False
                app.DisplayAlerts = False
                if workbook is None:
                    workbook = app.Workbooks.Open(document_path, ReadOnly=True)
                    should_close_workbook = True
                try:
                    app.ActivePrinter = printer_name
                    first_page = min(page_numbers) + 1
                    last_page = max(page_numbers) + 1
                    workbook.PrintOut(Copies=copies, From=first_page, To=last_page, Preview=False, ActivePrinter=printer_name)
                finally:
                    if should_close_workbook and workbook is not None:
                        workbook.Close(False)
            finally:
                if app is not None and should_quit_app:
                    app.Quit()
            return

        if ext in {".ppt", ".pptx", ".pptm"}:
            app = None
            presentation = None
            should_close_presentation = False
            should_quit_app = True
            try:
                try:
                    app, presentation = office_preview._get_running_office_document(document_path, "PowerPoint.Application", "Presentations")
                except Exception:
                    app, presentation = None, None
                if app is None:
                    app = win32_client.DispatchEx("PowerPoint.Application")
                else:
                    should_quit_app = False
                if presentation is None:
                    presentation = app.Presentations.Open(document_path, WithWindow=False)
                    should_close_presentation = True
                try:
                    app.ActivePrinter = printer_name
                    first_page = min(page_numbers) + 1
                    last_page = max(page_numbers) + 1
                    presentation.PrintOptions.Ranges.ClearAll()
                    presentation.PrintOptions.Ranges.Add(first_page, last_page)
                    presentation.PrintOptions.RangeType = 2
                    presentation.PrintOut()
                finally:
                    if should_close_presentation and presentation is not None:
                        presentation.Close()
            finally:
                if app is not None and should_quit_app:
                    app.Quit()
            return

        raise ValueError(tr("print_error_unavailable"))
    finally:
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass


def _print_with_selected_printer(document_path, printer_name, copies=1, page_numbers=None):
    if not isinstance(document_path, str) or not document_path or not os.path.exists(document_path):
        raise FileNotFoundError(document_path)

    if win32print is None or win32api is None:
        raise RuntimeError(tr("print_error_unavailable"))

    selected_printer = str(printer_name or "").strip()
    if not selected_printer:
        raise ValueError(tr("print_no_printer"))

    if page_numbers and office_preview.can_preview_office(document_path):
        _print_office_document_pages(document_path, selected_printer, copies=copies, page_numbers=page_numbers)
        return selected_printer

    print_target = document_path
    if page_numbers:
        if fitz is None:
            raise ValueError(tr("print_error_unavailable"))

        pdf_doc = fitz.open(document_path)
        temp_fd, temp_path = tempfile.mkstemp(prefix="pdfexplorer_print_", suffix=".pdf")
        os.close(temp_fd)
        try:
            subset_doc = fitz.open()
            for page_index in page_numbers:
                subset_doc.insert_pdf(pdf_doc, from_page=page_index, to_page=page_index)
            subset_doc.save(temp_path)
            subset_doc.close()
            print_target = temp_path
        finally:
            pdf_doc.close()

    original_default = win32print.GetDefaultPrinter()
    try:
        win32print.SetDefaultPrinter(selected_printer)
        if copies > 1:
            current_printer = win32print.OpenPrinter(selected_printer)
            try:
                devmode = win32print.GetPrinter(current_printer, 2)[3]
                if devmode is not None:
                    devmode.Copies = int(copies)
                    win32print.SetPrinter(current_printer, 2, devmode, 0)
            finally:
                win32print.ClosePrinter(current_printer)
        os.startfile(print_target, "print")
    finally:
        try:
            win32print.SetDefaultPrinter(original_default)
        except Exception:
            pass

        if print_target != document_path:
            try:
                os.remove(print_target)
            except Exception:
                pass

    return selected_printer


def _show_printer_properties(printer_name):
    if win32print is None or win32con is None:
        return False

    selected_printer = str(printer_name or "").strip()
    if not selected_printer:
        return False

    try:
        printer_handle = win32print.OpenPrinter(selected_printer)
    except Exception:
        return False

    try:
        try:
            printer_info = win32print.GetPrinter(printer_handle, 2)
            devmode = printer_info[3] if isinstance(printer_info, (tuple, list)) and len(printer_info) > 3 else None
        except Exception:
            devmode = None

        if devmode is None:
            win32print.DocumentProperties(
                0,
                printer_handle,
                selected_printer,
                None,
                None,
                win32con.DM_IN_PROMPT,
            )
            return True

        win32print.DocumentProperties(
            0,
            printer_handle,
            selected_printer,
            devmode,
            devmode,
            win32con.DM_IN_PROMPT | win32con.DM_OUT_BUFFER,
        )
        return True
    except Exception:
        return False
    finally:
        try:
            win32print.ClosePrinter(printer_handle)
        except Exception:
            pass


def _save_print_form_geometry(dialog):
    position = dialog.GetPosition()
    size = dialog.GetSize()
    update_settings({
        "print_form_position": [int(position.x), int(position.y)],
        "print_form_size": [int(size.x), int(size.y)],
    })


def _apply_print_form_geometry(dialog, settings=None):
    if settings is None:
        settings = load_settings()

    saved_position = settings.get("print_form_position")
    saved_size = settings.get("print_form_size")

    min_width, min_height = 320, 200
    default_width, default_height = 420, 220
    dialog.SetMinSize((min_width, min_height))
    dialog.SetSize((default_width, default_height))

    if isinstance(saved_size, list) and len(saved_size) == 2:
        width, height = int(saved_size[0]), int(saved_size[1])
        if width >= min_width and height >= min_height:
            dialog.SetSize((width, height))

    if isinstance(saved_position, list) and len(saved_position) == 2:
        x, y = int(saved_position[0]), int(saved_position[1])
        dialog.SetPosition((x, y))


def show_print_form(owner, document_path=None):
    if document_path is None:
        document_path = getattr(owner, "current_preview_path", None)

    if not document_path or not os.path.exists(document_path):
        wx.MessageBox(tr("print_no_selection"), tr("print_dialog_title"), style=wx.OK | wx.ICON_INFORMATION)
        return False

    printer_names = _get_printer_names()
    if not printer_names:
        wx.MessageBox(tr("print_no_printer"), tr("print_dialog_title"), style=wx.OK | wx.ICON_WARNING)
        return False

    default_printer = win32print.GetDefaultPrinter() if win32print is not None else printer_names[0]
    if default_printer not in printer_names:
        default_printer = printer_names[0]

    settings = load_settings()
    dialog = wx.Dialog(owner, title=tr("print_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    service_label = wx.StaticText(panel, label=tr("print_universal_print_label"))
    service_value = wx.StaticText(panel, label="Microsoft Universal Print")
    printer_label = wx.StaticText(panel, label=tr("print_printer_label"))
    printer_choice = wx.Choice(panel, choices=printer_names)
    printer_choice.SetStringSelection(default_printer)

    copies_label = wx.StaticText(panel, label=tr("print_copies_label"))
    copies_spin = wx.SpinCtrl(panel, value="1", min=1, max=99)

    range_label = wx.StaticText(panel, label=tr("print_range_label"))
    range_choice = wx.Choice(panel, choices=[tr("print_range_all"), tr("print_range_selection")])
    range_choice.SetSelection(0)

    pages_label = wx.StaticText(panel, label=tr("print_range_selection"))
    pages_text = wx.TextCtrl(panel)
    pages_text.SetHint("1,3-5")
    pages_text.SetToolTip("Examples: 1, 3-5, 1,3-5")
    pages_label.Hide()
    pages_text.Hide()

    file_label = wx.StaticText(panel, label=tr("print_file_label"))
    file_value = wx.StaticText(panel, label=os.path.basename(document_path))

    def update_page_range_visibility(_event=None):
        is_selected_pages = range_choice.GetStringSelection() == tr("print_range_selection")
        pages_label.Show(is_selected_pages)
        pages_text.Show(is_selected_pages)
        if not is_selected_pages:
            pages_text.SetValue("")
        panel.Layout()
        dialog.Layout()

    range_choice.Bind(wx.EVT_CHOICE, update_page_range_visibility)
    update_page_range_visibility()

    button_ok = wx.Button(panel, wx.ID_OK, tr("print_button"))
    button_parameters = wx.Button(panel, wx.ID_ANY, tr("print_parameters_button"))
    button_cancel = wx.Button(panel, wx.ID_CANCEL, tr("print_cancel_button"))

    def on_printer_parameters(_event=None):
        selected_printer = printer_names[printer_choice.GetSelection()] if printer_choice.GetSelection() >= 0 else default_printer
        _show_printer_properties(selected_printer)

    button_parameters.Bind(wx.EVT_BUTTON, on_printer_parameters)

    fields = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
    fields.AddGrowableCol(1, 1)
    fields.Add(service_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(service_value, 1, wx.EXPAND)
    fields.Add(printer_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(printer_choice, 1, wx.EXPAND)
    fields.Add(copies_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(copies_spin, 1, wx.EXPAND)
    fields.Add(range_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(range_choice, 1, wx.EXPAND)
    fields.Add(pages_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(pages_text, 1, wx.EXPAND)
    fields.Add(file_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(file_value, 1, wx.EXPAND)

    button_sizer = wx.BoxSizer(wx.HORIZONTAL)
    button_sizer.AddStretchSpacer()
    button_sizer.Add(button_parameters, 0, wx.RIGHT, 8)
    button_sizer.Add(button_ok, 0, wx.RIGHT, 8)
    button_sizer.Add(button_cancel, 0)

    root_sizer = wx.BoxSizer(wx.VERTICAL)
    root_sizer.Add(fields, 1, wx.EXPAND | wx.ALL, 12)
    root_sizer.Add(button_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)
    panel.SetSizer(root_sizer)

    dialog.SetClientSize((420, 320))
    _apply_print_form_geometry(dialog, settings)

    try:
        result = dialog.ShowModal()
    finally:
        _save_print_form_geometry(dialog)
        dialog.Destroy()

    if result != wx.ID_OK:
        return False

    selected_printer = printer_names[printer_choice.GetSelection()] if printer_choice.GetSelection() >= 0 else default_printer
    copies = max(1, int(copies_spin.GetValue()))
    selected_page_numbers = None
    if range_choice.GetStringSelection() == tr("print_range_selection"):
        page_text = pages_text.GetValue().strip()
        if not page_text:
            wx.MessageBox(tr("export_pdf_page_numbers_invalid"), tr("print_error_title"), style=wx.OK | wx.ICON_ERROR)
            return False
        try:
            selected_page_numbers = _parse_page_numbers_input(page_text, _get_document_page_count(document_path))
        except Exception as exc:
            wx.MessageBox(str(exc), tr("print_error_title"), style=wx.OK | wx.ICON_ERROR)
            return False
    try:
        printer_name = _print_with_selected_printer(document_path, selected_printer, copies=copies, page_numbers=selected_page_numbers)
        wx.MessageBox(tr("print_status_success", printer=printer_name), tr("print_dialog_title"), style=wx.OK | wx.ICON_INFORMATION)
        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("print_error_title"), style=wx.OK | wx.ICON_ERROR)
        return False
