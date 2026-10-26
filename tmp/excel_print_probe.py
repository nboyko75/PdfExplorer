from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import time

import fitz
from PIL import Image, ImageChops
import pythoncom
import win32com.client
import win32print

from controls import print_form


def ink_bounds(page):
    pix = page.get_pixmap(colorspace=fitz.csRGB, alpha=False)
    with Image.frombytes('RGB', (pix.width, pix.height), pix.samples) as bitmap:
        with Image.new('RGB', bitmap.size, 'white') as white:
            with ImageChops.difference(bitmap, white) as diff:
                return diff.getbbox()


pythoncom.CoInitialize()
try:
    with TemporaryDirectory(prefix='excel_print_', dir='tmp') as folder:
        root = Path(folder).resolve()
        source = root / 'active-sheet.xlsx'
        output = root / 'printed.pdf'
        app = win32com.client.DispatchEx('Excel.Application')
        book = None
        try:
            app.Visible = False
            app.DisplayAlerts = False
            book = app.Workbooks.Add()
            first = book.Worksheets(1)
            first.Name = 'First sheet'
            first.Range('A1').Value = 'FIRST SHEET ONLY'
            first.PageSetup.Orientation = 1
            second = book.Worksheets.Add(After=first)
            second.Name = 'Active report'
            second.Activate()
            second.Range('A1').Value = 'ACTIVE SHEET REPORT'
            second.Range('A2').Value = 'Saved scale and margins'
            second.Range('J50').Value = 'OUTSIDE PRINT AREA'
            second.Range('A1:D12').ColumnWidth = 20
            second.Range('A1:D12').Font.Size = 16
            setup = second.PageSetup
            setup.PrintArea = '$A$1:$D$12'
            setup.Orientation = 2
            setup.PaperSize = 9
            setup.LeftMargin = 72
            setup.RightMargin = 36
            setup.TopMargin = 54
            setup.BottomMargin = 36
            setup.Zoom = 75
            second.Activate()
            book.SaveAs(str(source), FileFormat=51)
            print('Sheets:', [(s.Name, s.Index, s.PageSetup.PrintArea) for s in book.Worksheets], flush=True)
            from zipfile import ZipFile
            from xml.etree import ElementTree as ET
            with ZipFile(source) as archive:
                xml = ET.fromstring(archive.read('xl/workbook.xml'))
                print('Stored sheets:', [s.attrib for s in xml.findall('.//{*}sheet')], flush=True)
                print('Stored names:', [(n.attrib, n.text) for n in xml.findall('.//{*}definedName')], flush=True)

            # Unsaved selection in an open workbook takes priority over saved tab.
            first.Activate()
            first.Range('A2').Value = 'UNSAVED LIVE CONTENT'
            with patch.object(print_form, '_get_print_temp_directory', return_value=str(root)), \
                    patch.object(print_form, '_get_running_print_office_document', return_value=(app, book)):
                live_pdf, live_layout = print_form._export_excel_active_sheet(str(source))
            with fitz.open(live_pdf) as doc:
                text = ''.join(page.get_text() for page in doc)
                assert 'FIRST SHEET ONLY' in text and 'UNSAVED LIVE CONTENT' in text, text
                assert 'ACTIVE SHEET REPORT' not in text, text
                assert doc[0].rect.height > doc[0].rect.width
            assert live_layout['orientation'] == 1
            assert book.ActiveSheet.Name == 'First sheet'
        finally:
            if book is not None:
                book.Close(False)
            app.Quit()

        # Closed workbook uses the saved active second sheet and page setup.
        with patch.object(print_form, '_get_print_temp_directory', return_value=str(root)):
            exported, layout = print_form._export_excel_active_sheet(str(source))
        with fitz.open(exported) as doc:
            assert doc.page_count == 1, [(tuple(p.rect), p.get_text()) for p in doc]
            text = doc[0].get_text()
            assert 'ACTIVE SHEET REPORT' in text, text
            assert 'FIRST SHEET ONLY' not in text and 'OUTSIDE PRINT AREA' not in text, text
            assert doc[0].rect.width > doc[0].rect.height
            source_size = tuple(doc[0].rect)
            source_bounds = ink_bounds(doc[0])
        assert layout == {'orientation': 2, 'paper_size': 9}, layout

        original_start = win32print.StartDoc
        default_printer = win32print.GetDefaultPrinter()
        def start_to_file(dc, info):
            return original_start(dc, (info[0], str(output), info[2], info[3]))
        with patch.object(print_form.win32print, 'StartDoc', side_effect=start_to_file):
            print_form._print_pdf_document(exported, 'Microsoft Print to PDF', page_setup=layout)
        for _ in range(50):
            if output.exists() and output.stat().st_size:
                break
            time.sleep(0.1)
        with fitz.open(output) as doc:
            assert doc.page_count == 1
            printed_size = tuple(doc[0].rect)
            printed_bounds = ink_bounds(doc[0])
        assert all(abs(a-b) < 2 for a, b in zip(source_size, printed_size)), (source_size, printed_size)
        assert all(abs(a-b) <= 3 for a, b in zip(source_bounds, printed_bounds)), (source_bounds, printed_bounds)
        assert win32print.GetDefaultPrinter() == default_printer
        print('PASS: live active sheet and unsaved content; saved second sheet; print area; landscape A4; margins and 75% scale preserved through Windows PDF printing.')
        print('Exported ink bounds:', source_bounds, 'Printed ink bounds:', printed_bounds)
finally:
    pythoncom.CoUninitialize()
