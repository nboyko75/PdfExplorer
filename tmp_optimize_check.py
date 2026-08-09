import os
import shutil
import tempfile
import sys

sys.path.insert(0, r'd:\Projects\PdfExplorer')
import file_operations.pdf_utils as pdf_utils

src = r'D:\Temp\2235Т5_Renault Trafic_АШ-98.pdf'
tmpdir = tempfile.mkdtemp(prefix='pdfopt-', dir='d:/Temp')
tmpfile = os.path.join(tmpdir, 'out.pdf')
shutil.copy2(src, tmpfile)
print('fitz', pdf_utils.fitz.__version__ if pdf_utils.fitz else None)
print('before', os.path.getsize(tmpfile))
pdf_utils.load_settings = lambda: {}
pdf_utils.optimize_pdf(tmpfile)
pdf_utils.save_pdf(tmpfile)
print('after', os.path.getsize(tmpfile))
shutil.rmtree(tmpdir)
