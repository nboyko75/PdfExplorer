# -*- mode: python ; coding: utf-8 -*-


from pathlib import Path

project_dir = Path('D:/Projects/PdfExplorer').resolve()
venv_site_packages = project_dir / '.venv' / 'Lib' / 'site-packages'

pymupdf_files = [
    str(venv_site_packages / 'pymupdf' / 'mupdfcpp64.dll'),
    str(venv_site_packages / 'pymupdf' / '_extra.pyd'),
    str(venv_site_packages / 'pymupdf' / '_mupdf.pyd'),
]

pymupdf_datas = []
for path in pymupdf_files:
    if Path(path).exists():
        pymupdf_datas.append((path, 'pymupdf'))

pymupdf_hiddenimports = [
    'pymupdf',
    'pymupdf.mupdf',
    'pymupdf.pymupdf',
    'pymupdf.utils',
    'pymupdf.table',
    'fitz',
]

a = Analysis(
    [str(project_dir / 'main.py')],
    pathex=[str(project_dir), str(venv_site_packages)],
    binaries=[],
    datas=[('images', 'images'), ('localization', 'localization')] + pymupdf_datas,
    hiddenimports=pymupdf_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DocExplorer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['D:\\Projects\\PdfExplorer\\images\\main.ico'],
)
