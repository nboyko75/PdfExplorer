import os
import ctypes
import subprocess
import tempfile
import time
from contextlib import ExitStack

import wx

try:
    import fitz
except ImportError:  # pragma: no cover - optional runtime dependency
    fitz = None

try:
    import win32api  # type: ignore[import-not-found]
    import win32con  # type: ignore[import-not-found]
    import win32gui  # type: ignore[import-not-found]
    import win32print  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    win32api = None
    win32con = None
    win32gui = None
    win32print = None

try:
    import pythoncom  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    pythoncom = None

try:
    import win32com.client as win32_client  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional runtime dependency
    win32_client = None

from file_operations.image_utils import IMAGE_EXTENSIONS
from localization import tr
from common.window_tools import load_settings, update_settings, save_control_geometry, restore_control_geometry
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


def _open_print_document(path):
    if os.path.splitext(path)[1].lower() == ".webp":
        # MuPDF does not open WebP directly; decode it losslessly with Pillow.
        from io import BytesIO
        from PIL import Image

        with Image.open(path) as image, BytesIO() as buffer:
            image.save(buffer, format="PNG", dpi=image.info.get("dpi", (96, 96)))
            return fitz.open(stream=buffer.getvalue(), filetype="png")
    return fitz.open(path)


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
        if fitz is not None:
            try:
                with _open_print_document(path) as image_doc:
                    return max(1, image_doc.page_count)
            except Exception:
                return 0
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
                raise ValueError(tr("print_page_out_of_range", page=page_number, count=page_count))
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
        if ext in pdf_utils.WORD_OFFICE_EXTENSIONS:
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

        if ext in pdf_utils.EXCEL_OFFICE_EXTENSIONS:
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


# Shell printing is asynchronous: the viewer may open the PDF after startfile
# returns, or even after DocExplorer exits. Never delete it on handoff/exit.
_PRINT_TEMP_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def _get_print_temp_directory():
    directory = os.path.join(tempfile.gettempdir(), "DocExplorer", "print_jobs")
    os.makedirs(directory, exist_ok=True)
    cutoff = time.time() - _PRINT_TEMP_MAX_AGE_SECONDS
    try:
        with os.scandir(directory) as entries:
            for entry in entries:
                if not (entry.name.startswith("pdfexplorer_print_") and entry.name.endswith(".pdf")):
                    continue
                try:
                    if (entry.is_file(follow_symlinks=False)
                            and entry.stat(follow_symlinks=False).st_mtime < cutoff):
                        os.remove(entry.path)
                except OSError:
                    # A viewer may still hold a file open; retry on a later print.
                    pass
    except OSError:
        pass
    return directory


def _create_print_subset(document_path, page_numbers=None):
    directory = _get_print_temp_directory()
    fd, temp_path = tempfile.mkstemp(prefix="pdfexplorer_print_", suffix=".pdf", dir=directory)
    os.close(fd)
    try:
        # Close every handle before launching an external viewer.
        with ExitStack() as stack:
            pdf_doc = stack.enter_context(_open_print_document(document_path))
            if not pdf_doc.is_pdf:
                # Direct conversion preserves image resolution and TIFF pages.
                pdf_doc = stack.enter_context(fitz.open(stream=pdf_doc.convert_to_pdf(), filetype="pdf"))
            subset_doc = stack.enter_context(fitz.open())
            pages = range(pdf_doc.page_count) if page_numbers is None else page_numbers
            for page_index in pages:
                subset_doc.insert_pdf(pdf_doc, from_page=page_index, to_page=page_index)
            subset_doc.save(temp_path)
    except Exception:
        # This incomplete file has never been handed to the viewer.
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
    return temp_path


def _get_printer_devmode(printer_handle):
    try:
        devmode = win32print.GetPrinter(printer_handle, 9).get("pDevMode")
    except Exception:
        devmode = None
    if devmode is None:
        devmode = win32print.GetPrinter(printer_handle, 2).get("pDevMode")
    return devmode


def _export_excel_active_sheet(document_path):
    """Capture the active sheet and its layout without changing the workbook."""
    if win32_client is None:
        raise RuntimeError(tr("print_error_unavailable"))
    fd, output = tempfile.mkstemp(prefix="pdfexplorer_print_", suffix=".pdf",
                                  dir=_get_print_temp_directory())
    os.close(fd)
    try:
        with ExitStack() as stack:
            # Use Windows' reference-counted initialization directly. pywin32
            # skips repeated initialization on its main thread, so pairing its
            # calls here could disconnect an existing workbook's COM objects.
            ole32 = ctypes.OleDLL("ole32")
            ole32.CoUninitialize.restype = None
            ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
            stack.callback(ole32.CoUninitialize)
            _, workbook = _get_running_print_office_document(
                document_path, "Excel.Application", "Workbooks")
            owned_workbook = workbook is None
            if workbook is None:
                workbook = stack.enter_context(office_preview.preview_document(
                    win32_client, None, "Excel", document_path))
            # Workbook.ActiveSheet also works when another workbook has focus.
            sheet = workbook.ActiveSheet
            if owned_workbook and not sheet.PageSetup.PrintArea:
                # Some Excel installations load the saved defined name without
                # applying it to PageSetup in a hidden automation session.
                for name in sheet.Names:
                    if name.Name.rsplit("!", 1)[-1].lower() == "print_area":
                        sheet.PageSetup.PrintArea = name.RefersToRange.Address
                        break
            layout = {"orientation": int(sheet.PageSetup.Orientation),
                      "paper_size": int(sheet.PageSetup.PaperSize)}
            # Omit page limits: export the complete active sheet, respecting its
            # print area. Positional arguments work with dynamic COM dispatch.
            sheet.ExportAsFixedFormat(0, output, 0, False, False)
        return output, layout
    except Exception:
        try:
            os.remove(output)
        except OSError:
            pass
        raise


def _create_mirrored_print_document(document_path, page_numbers=None):
    """Swap common horizontal margins on even pages in the requested print order.

    Fixed-layout documents have no margin settings. Estimate their margins from
    visible content, using common bounds for pages of the same size so short
    paragraphs do not receive different offsets. Render only for measurement;
    the output retains the original text, vectors and image resolution.
    """
    from PIL import Image, ImageChops

    if fitz is None:
        raise RuntimeError(tr("print_error_unavailable"))
    if office_preview.can_preview_office(document_path):
        page_count = office_preview.get_office_document_page_count(document_path)
        if page_count < 1:
            raise ValueError(tr("export_pdf_page_numbers_invalid"))
        document_path = office_preview.convert_office_to_preview_pdf(document_path, max_pages=page_count)

    # This intermediate file has not been handed to a viewer and can be removed.
    subset_path = _create_print_subset(document_path, page_numbers)
    output_path = None
    try:
        with fitz.open(subset_path) as source, fitz.open() as output:
            source.bake()  # Retain visible annotations and form values in print.
            bounds_by_size = {}
            sizes = []
            for page in source:
                rect = page.rect
                size = (rect.width, rect.height)
                sizes.append(size)
                # Cap the measurement bitmap for unusually large page formats.
                scale = min(2.0, 2000 / max(rect.width, rect.height))
                pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale),
                                         colorspace=fitz.csRGB, alpha=False)
                with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as bitmap:
                    with Image.new("RGB", bitmap.size, "white") as white:
                        with ImageChops.difference(bitmap, white) as ink:
                            bounds = ink.getbbox()
                if bounds is not None:
                    left = bounds[0] / scale
                    right = min(rect.width, bounds[2] / scale)
                    previous = bounds_by_size.get(size, (rect.width, 0))
                    bounds_by_size[size] = (min(previous[0], left), max(previous[1], right))

            for index, page in enumerate(source):
                width, height = sizes[index]
                bounds = bounds_by_size.get(sizes[index])
                offset = width - bounds[1] - bounds[0] if bounds and index % 2 else 0
                if abs(offset) < 0.01 or not page.get_contents():
                    output.insert_pdf(source, from_page=index, to_page=index)
                else:
                    target = output.new_page(width=width, height=height)
                    rotation = page.rotation
                    # Import the crop in unrotated coordinates, then reproduce
                    # its display rotation within the translated destination.
                    page.set_rotation(0)
                    try:
                        target.show_pdf_page(fitz.Rect(offset, 0, width + offset, height),
                                             source, index, rotate=-rotation)
                    finally:
                        page.set_rotation(rotation)

            fd, output_path = tempfile.mkstemp(prefix="pdfexplorer_print_", suffix=".pdf",
                                               dir=_get_print_temp_directory())
            os.close(fd)
            output.save(output_path)
        return output_path
    except Exception:
        if output_path is not None:
            try:
                os.remove(output_path)
            except OSError:
                pass
        raise
    finally:
        try:
            os.remove(subset_path)
        except OSError:
            pass


def _create_manual_duplex_passes(document_path, page_numbers=None, copies=1):
    """Pair consecutive pages in the requested print order, preserving copies."""
    if fitz is None:
        raise RuntimeError(tr("print_error_unavailable"))
    if office_preview.can_preview_office(document_path):
        # Explicitly export every page, regardless of the preview page limit.
        page_count = office_preview.get_office_document_page_count(document_path)
        if page_count < 1:
            raise ValueError(tr("export_pdf_page_numbers_invalid"))
        document_path = office_preview.convert_office_to_preview_pdf(document_path, max_pages=page_count)

    paths = []
    try:
        with ExitStack() as stack:
            source = stack.enter_context(_open_print_document(document_path))
            if not source.is_pdf:
                source = stack.enter_context(fitz.open(stream=source.convert_to_pdf(), filetype="pdf"))
            pages = list(range(source.page_count) if page_numbers is None else page_numbers)
            if not pages or any(page < 0 or page >= source.page_count for page in pages):
                raise ValueError(tr("export_pdf_page_numbers_invalid"))
            fronts = stack.enter_context(fitz.open())
            backs = stack.enter_context(fitz.open())
            for _ in range(max(1, int(copies))):
                for index in range(0, len(pages), 2):
                    front = pages[index]
                    fronts.insert_pdf(source, from_page=front, to_page=front)
                    if index + 1 < len(pages):
                        back = pages[index + 1]
                        backs.insert_pdf(source, from_page=back, to_page=back)
                    elif len(pages) > 1:
                        # Keep the last sheet and the next copy aligned.
                        rect = source[front].rect
                        backs.new_page(width=rect.width, height=rect.height)
            for document in (fronts, backs):
                if not document.page_count:
                    continue
                fd, path = tempfile.mkstemp(prefix="pdfexplorer_print_", suffix=".pdf",
                                            dir=_get_print_temp_directory())
                os.close(fd)
                paths.append(path)
                document.save(path)
        return paths[0], paths[1] if len(paths) > 1 else None
    except Exception:
        # No files have been handed to a viewer yet.
        for path in paths:
            try:
                os.remove(path)
            except OSError:
                pass
        raise


def _print_manual_duplex(document_path, printer_name, copies=1, page_numbers=None, duplex=2,
                         page_setup=None):
    if os.path.splitext(document_path)[1].lower() in pdf_utils.EXCEL_OFFICE_EXTENSIONS:
        document_path, page_setup = _export_excel_active_sheet(document_path)
    layout_options = {"page_setup": page_setup} if page_setup is not None else {}
    fronts, backs = _create_manual_duplex_passes(document_path, page_numbers, copies)
    # Keep both jobs simplex. Restoring automatic duplex immediately after a
    # shell handoff would race the asynchronous PDF viewer.
    _print_with_selected_printer(fronts, printer_name, copies=1, duplex=1, **layout_options)
    if backs is not None:
        instruction = tr("print_manual_reload_long" if duplex == 2 else "print_manual_reload_short")
        result = wx.MessageBox(
            tr("print_manual_reload", binding=instruction), tr("print_manual_title"),
            style=wx.OK | wx.CANCEL | wx.ICON_INFORMATION,
        )
        if result != wx.OK:
            return None
        _print_with_selected_printer(backs, printer_name, copies=1, duplex=1, **layout_options)
    return printer_name


def _get_printer_duplex(printer_name):
    if win32print is None or win32con is None:
        return 1
    try:
        handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = _get_printer_devmode(handle)
            if (devmode is not None and devmode.Fields & win32con.DM_DUPLEX
                    and devmode.Duplex in (1, 2, 3)):
                return devmode.Duplex
        finally:
            win32print.ClosePrinter(handle)
    except Exception:
        pass
    return 1


def _set_printer_duplex(printer_name, duplex):
    if win32print is None or win32con is None:
        raise RuntimeError(tr("print_parameters_error"))
    if duplex not in (win32con.DMDUP_SIMPLEX, win32con.DMDUP_VERTICAL, win32con.DMDUP_HORIZONTAL):
        raise ValueError(tr("print_duplex_unsupported"))
    handle = win32print.OpenPrinter(printer_name)
    try:
        devmode = _get_printer_devmode(handle)
        if devmode is None:
            raise RuntimeError(tr("print_parameters_error"))
        if not devmode.Fields & win32con.DM_DUPLEX:
            if duplex == win32con.DMDUP_SIMPLEX:
                return  # Simplex-only drivers need no duplex setting.
            raise ValueError(tr("print_duplex_unsupported"))
        devmode.Duplex = duplex
        devmode.Fields |= win32con.DM_DUPLEX
        result = win32print.DocumentProperties(
            0, handle, printer_name, devmode, devmode,
            win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER,
        )
        if result != win32con.IDOK:
            raise RuntimeError(tr("print_parameters_error"))
        if devmode.Duplex != duplex or not devmode.Fields & win32con.DM_DUPLEX:
            raise ValueError(tr("print_duplex_unsupported"))
        win32print.SetPrinter(handle, 9, {"pDevMode": devmode}, 0)
    finally:
        win32print.ClosePrinter(handle)


def _print_pdf_document(document_path, printer_name, copies=1, page_setup=None):
    """Render pages into a Windows print job without an external PDF viewer."""
    from PIL import Image, ImageWin

    if fitz is None or win32gui is None:
        raise RuntimeError(tr("print_error_unavailable"))

    with fitz.open(document_path) as document:
        handle = win32print.OpenPrinter(printer_name)
        try:
            devmode = _get_printer_devmode(handle)
            if devmode is None:
                raise RuntimeError(tr("print_parameters_error"))
            # Repeat pages ourselves so copies also work with simplex drivers.
            devmode.Copies = 1
            devmode.Fields |= win32con.DM_COPIES
            if page_setup is not None:
                devmode.Orientation = page_setup["orientation"]
                devmode.PaperSize = page_setup["paper_size"]
                # A saved custom paper length/width must not override Excel's size.
                devmode.Fields &= ~(win32con.DM_PAPERLENGTH | win32con.DM_PAPERWIDTH)
                devmode.Fields |= win32con.DM_ORIENTATION | win32con.DM_PAPERSIZE
                result = win32print.DocumentProperties(
                    0, handle, printer_name, devmode, devmode,
                    win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER,
                )
                if (result != win32con.IDOK or devmode.Orientation != page_setup["orientation"]
                        or devmode.PaperSize != page_setup["paper_size"]):
                    raise RuntimeError(tr("print_parameters_error"))
            dc = win32gui.CreateDC("WINSPOOL", printer_name, devmode)
        finally:
            win32print.ClosePrinter(handle)

        started = False
        try:
            width = win32print.GetDeviceCaps(dc, win32con.HORZRES)
            height = win32print.GetDeviceCaps(dc, win32con.VERTRES)
            dpi_x = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSX)
            dpi_y = win32print.GetDeviceCaps(dc, win32con.LOGPIXELSY)
            if min(width, height, dpi_x, dpi_y) <= 0:
                raise RuntimeError(tr("print_parameters_error"))
            win32print.StartDoc(dc, (os.path.basename(document_path), None, None, 0))
            started = True
            for _ in range(max(1, int(copies))):
                for page in document:
                    scale = min(1.0, width * 72 / (page.rect.width * dpi_x),
                                height * 72 / (page.rect.height * dpi_y))
                    target_width = max(1, round(page.rect.width * dpi_x / 72 * scale))
                    target_height = max(1, round(page.rect.height * dpi_y / 72 * scale))
                    left = (width - target_width) // 2
                    top = (height - target_height) // 2
                    if page_setup is not None:
                        # Excel has already applied margins and Zoom/FitToPages.
                        # Preserve its physical layout, including hardware offsets,
                        # instead of shrinking it a second time to the printable area.
                        target_width = max(1, round(page.rect.width * dpi_x / 72))
                        target_height = max(1, round(page.rect.height * dpi_y / 72))
                        left = -win32print.GetDeviceCaps(dc, win32con.PHYSICALOFFSETX)
                        top = -win32print.GetDeviceCaps(dc, win32con.PHYSICALOFFSETY)
                    # Bound raster memory while retaining print-quality detail.
                    render_scale = min(300 / 72, 4096 / max(page.rect.width, page.rect.height))
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale),
                                             colorspace=fitz.csRGB, alpha=False)
                    with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as bitmap:
                        win32print.StartPage(dc)
                        ImageWin.Dib(bitmap).draw(dc, (left, top, left + target_width, top + target_height))
                        win32print.EndPage(dc)
            win32print.EndDoc(dc)
            started = False
        except Exception:
            if started:
                try:
                    win32print.AbortDoc(dc)
                except Exception:
                    pass  # Preserve the original submission/rendering error.
            raise
        finally:
            win32gui.DeleteDC(dc)


def _print_with_selected_printer(document_path, printer_name, copies=1, page_numbers=None, duplex=None,
                                 page_setup=None):
    if not isinstance(document_path, str) or not document_path or not os.path.exists(document_path):
        raise FileNotFoundError(document_path)

    if win32print is None or win32api is None:
        raise RuntimeError(tr("print_error_unavailable"))

    selected_printer = str(printer_name or "").strip()
    if not selected_printer:
        raise ValueError(tr("print_no_printer"))

    if duplex is not None:
        _set_printer_duplex(selected_printer, duplex)

    if os.path.splitext(document_path)[1].lower() in pdf_utils.EXCEL_OFFICE_EXTENSIONS:
        document_path, page_setup = _export_excel_active_sheet(document_path)
    elif office_preview.can_preview_office(document_path):
        page_count = office_preview.get_office_document_page_count(document_path)
        if page_count < 1:
            raise ValueError(tr("export_pdf_page_numbers_invalid"))
        # Use the same complete export as manual duplex, avoiding Office's
        # application-specific ActivePrinter names and asynchronous shell verbs.
        document_path = office_preview.convert_office_to_preview_pdf(document_path, max_pages=page_count)

    print_target = document_path
    if page_numbers is not None or os.path.splitext(document_path)[1].lower() in IMAGE_EXTENSIONS:
        if fitz is None:
            raise ValueError(tr("print_error_unavailable"))

        print_target = _create_print_subset(document_path, page_numbers)

    if os.path.splitext(print_target)[1].lower() == ".pdf":
        layout_options = {"page_setup": page_setup} if page_setup is not None else {}
        _print_pdf_document(print_target, selected_printer, copies=copies, **layout_options)
    else:
        if copies > 1 or duplex is not None:
            current_printer = win32print.OpenPrinter(selected_printer)
            try:
                devmode = _get_printer_devmode(current_printer)
                if devmode is not None:
                    devmode.Copies = int(copies)
                    devmode.Fields |= win32con.DM_COPIES
                    win32print.SetPrinter(current_printer, 9, {"pDevMode": devmode}, 0)
            finally:
                win32print.ClosePrinter(current_printer)
        # Pass the printer explicitly; changing the default around an asynchronous
        # shell launch races the receiving application.
        win32api.ShellExecute(0, "printto", print_target,
                              subprocess.list2cmdline([selected_printer]), ".", 0)

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
        devmode = _get_printer_devmode(printer_handle)
        if devmode is None:
            return False

        result = win32print.DocumentProperties(
            0,
            printer_handle,
            selected_printer,
            devmode,
            devmode,
            win32con.DM_IN_PROMPT | win32con.DM_IN_BUFFER | win32con.DM_OUT_BUFFER,
        )
        if result == win32con.IDCANCEL:
            return True
        if result != win32con.IDOK:
            return False

        # Shell/Office printing reads Windows preferences. Persist the complete
        # driver DEVMODE for this user, including driver-specific parameters.
        win32print.SetPrinter(printer_handle, 9, {"pDevMode": devmode}, 0)
        return True
    except Exception:
        return False
    finally:
        try:
            win32print.ClosePrinter(printer_handle)
        except Exception:
            pass


def _save_print_form_geometry(dialog):
    save_control_geometry(dialog, "print_form")


def _apply_print_form_geometry(dialog, settings=None):
    restore_control_geometry(
        dialog,
        "print_form",
        default_size=(540, 380),
        min_size=(420, 340),
        settings=settings,
    )


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

    settings = load_settings()
    saved_duplex = settings.get("print_form_duplex_modes", {})
    duplex_modes = dict(saved_duplex) if isinstance(saved_duplex, dict) else {}
    default_printer = settings.get("print_form_printer")
    if default_printer not in printer_names:
        try:
            default_printer = win32print.GetDefaultPrinter() if win32print is not None else printer_names[0]
        except Exception:
            default_printer = printer_names[0]
    if default_printer not in printer_names:
        default_printer = printer_names[0]

    dialog = wx.Dialog(owner, title=tr("print_dialog_title"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
    panel = wx.Panel(dialog)

    service_label = wx.StaticText(panel, label=tr("print_universal_print_label"))
    service_value = wx.StaticText(panel, label="Microsoft Universal Print")
    printer_label = wx.StaticText(panel, label=tr("print_printer_label"))
    printer_choice = wx.Choice(panel, choices=printer_names)
    printer_choice.SetStringSelection(default_printer)

    copies_label = wx.StaticText(panel, label=tr("print_copies_label"))
    try:
        saved_copies = max(1, min(99, int(settings.get("print_form_copies", 1))))
    except (TypeError, ValueError, OverflowError):
        saved_copies = 1
    copies_spin = wx.SpinCtrl(panel, value=str(saved_copies), min=1, max=99)

    duplex_label = wx.StaticText(panel, label=tr("print_duplex_label"))
    # Manual duplex is saved separately from the driver's simplex job setting.
    duplex_choice = wx.Choice(panel, choices=[
        tr("print_duplex_simplex"), tr("print_duplex_long_edge"), tr("print_duplex_short_edge"),
    ])

    multiple_pages_label = wx.StaticText(panel, label=tr("print_multiple_pages_label"))
    multiple_pages_choice = wx.Choice(panel, choices=[
        tr("print_multiple_pages_usual"), tr("print_multiple_pages_mirrored"),
    ])
    multiple_pages_choice.SetSelection(
        1 if settings.get("print_form_multiple_pages") == "mirrored_margins" else 0
    )

    def update_multiple_pages_enabled():
        enabled = duplex_choice.GetSelection() in (1, 2)
        multiple_pages_label.Enable(enabled)
        multiple_pages_choice.Enable(enabled)

    def refresh_duplex(_event=None):
        selected_printer = printer_choice.GetStringSelection() or default_printer
        mode = duplex_modes.get(selected_printer)
        if mode not in (1, 2, 3):
            mode = _get_printer_duplex(selected_printer)
        duplex_choice.SetSelection(mode - 1)
        update_multiple_pages_enabled()

    def on_duplex_changed(_event=None):
        selected_printer = printer_choice.GetStringSelection() or default_printer
        duplex_modes[selected_printer] = duplex_choice.GetSelection() + 1
        update_multiple_pages_enabled()
        update_settings({"print_form_duplex_modes": duplex_modes})

    printer_choice.Bind(wx.EVT_CHOICE, refresh_duplex)
    duplex_choice.Bind(wx.EVT_CHOICE, on_duplex_changed)
    refresh_duplex()

    range_label = wx.StaticText(panel, label=tr("print_range_label"))
    range_choice = wx.Choice(panel, choices=[tr("print_range_all"), tr("print_range_selection")])
    range_choice.SetSelection(1 if settings.get("print_form_page_range") == "selection" else 0)

    pages_label = wx.StaticText(panel, label=tr("print_range_selection"))
    saved_pages = settings.get("print_form_page_numbers", "")
    pages_text = wx.TextCtrl(panel, value=saved_pages if isinstance(saved_pages, str) else "")
    pages_text.SetHint("1,3-5")
    pages_text.SetToolTip("Examples: 1, 3-5, 1,3-5")
    pages_label.Hide()
    pages_text.Hide()

    file_label = wx.StaticText(panel, label=tr("print_file_label"))
    file_value = wx.StaticText(panel, label=os.path.basename(document_path))

    def update_page_range_visibility(_event=None):
        is_selected_pages = range_choice.GetSelection() == 1
        pages_label.Show(is_selected_pages)
        pages_text.Show(is_selected_pages)
        panel.Layout()
        dialog.Layout()

    range_choice.Bind(wx.EVT_CHOICE, update_page_range_visibility)
    update_page_range_visibility()

    button_ok = wx.Button(panel, wx.ID_OK, tr("print_button"))
    button_ok.SetDefault()
    button_parameters = wx.Button(panel, wx.ID_ANY, tr("print_parameters_button"))
    button_cancel = wx.Button(panel, wx.ID_CANCEL, tr("print_cancel_button"))

    def on_printer_parameters(_event=None):
        selected_printer = printer_names[printer_choice.GetSelection()] if printer_choice.GetSelection() >= 0 else default_printer
        if not _show_printer_properties(selected_printer):
            wx.MessageBox(tr("print_parameters_error"), tr("print_error_title"), style=wx.OK | wx.ICON_ERROR)
        refresh_duplex()

    button_parameters.Bind(wx.EVT_BUTTON, on_printer_parameters)

    fields = wx.FlexGridSizer(cols=2, hgap=10, vgap=10)
    fields.AddGrowableCol(1, 1)
    fields.Add(service_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(service_value, 1, wx.EXPAND)
    fields.Add(printer_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(printer_choice, 1, wx.EXPAND)
    fields.Add(copies_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(copies_spin, 1, wx.EXPAND)
    fields.Add(duplex_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(duplex_choice, 1, wx.EXPAND)
    fields.Add(multiple_pages_label, 0, wx.ALIGN_CENTER_VERTICAL)
    fields.Add(multiple_pages_choice, 1, wx.EXPAND)
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

    dialog_sizer = wx.BoxSizer(wx.VERTICAL)
    dialog_sizer.Add(panel, 1, wx.EXPAND)
    dialog.SetSizer(dialog_sizer)
    _apply_print_form_geometry(dialog, settings)
    # Include the optional page-range row when calculating the minimum size.
    pages_label.Show()
    pages_text.Show()
    dialog.SetMinSize(dialog.GetBestSize())
    update_page_range_visibility()

    try:
        result = dialog.ShowModal()
        selected_printer = printer_choice.GetStringSelection() or default_printer
        copies = max(1, int(copies_spin.GetValue()))
        duplex = duplex_choice.GetSelection() + 1
        duplex_modes[selected_printer] = duplex
        mirrored_margins = multiple_pages_choice.GetSelection() == 1
        is_selected_pages = range_choice.GetSelection() == 1
        page_text = pages_text.GetValue().strip()
        update_settings({
            "print_form_printer": selected_printer,
            "print_form_copies": copies,
            "print_form_duplex_modes": duplex_modes,
            "print_form_multiple_pages": (
                "mirrored_margins" if mirrored_margins else "usual"
            ),
            "print_form_page_range": "selection" if is_selected_pages else "all",
            "print_form_page_numbers": page_text,
        })
    finally:
        _save_print_form_geometry(dialog)
        dialog.Destroy()

    if result != wx.ID_OK:
        return False

    try:
        layout_options = {}
        if os.path.splitext(document_path)[1].lower() in pdf_utils.EXCEL_OFFICE_EXTENSIONS:
            document_path, page_setup = _export_excel_active_sheet(document_path)
            layout_options["page_setup"] = page_setup
        selected_page_numbers = None
        if is_selected_pages:
            selected_page_numbers = _parse_page_numbers_input(page_text, _get_document_page_count(document_path))
        if mirrored_margins and duplex in (2, 3):
            document_path = _create_mirrored_print_document(document_path, selected_page_numbers)
            selected_page_numbers = None  # Selection and parity are already applied.
        if duplex in (2, 3):
            printer_name = _print_manual_duplex(document_path, selected_printer, copies=copies,
                                               page_numbers=selected_page_numbers, duplex=duplex, **layout_options)
            if printer_name is None:
                return False
        else:
            printer_name = _print_with_selected_printer(document_path, selected_printer, copies=copies,
                                                       page_numbers=selected_page_numbers, duplex=1, **layout_options)
        wx.MessageBox(tr("print_status_success", printer=printer_name), tr("print_dialog_title"), style=wx.OK | wx.ICON_INFORMATION)
        return True
    except Exception as exc:
        wx.MessageBox(str(exc), tr("print_error_title"), style=wx.OK | wx.ICON_ERROR)
        return False
