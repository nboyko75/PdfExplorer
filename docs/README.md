# DocExplorer documentation

The application selects `help/index_<locale>.html` and
`DocExplorer_User_Manual_<locale>.pdf` using its interface language.
The unsuffixed HTML and PDF files are English compatibility fallbacks.

Supported locales: en, uk, de, fr, es, it, pt_br, ja, ko, zh_cn, ru.
Each HTML guide contains all 34 original command demonstrations plus all 15
manual chapters. Each PDF contains the same 15 chapters. A language selector
also works when opening HTML directly in a browser. No network is required.

Translation source: `translations/<locale>.json`.
Command names come from the application's localization dictionaries.
Layout and animation references come from `help/template.html`.
The original illustrations and GIF animations are retained in English;
surrounding instructions, headings and alternative text are localized.
The original outdated Office conversion and Pause/Resume descriptions were
updated to match the supplied application's behavior.

To rebuild, install Python packages `reportlab` and `PyMuPDF`, then run:

```sh
python tools/build_localized_manuals.py
```

`python tools/build_user_manual.py` is an equivalent compatibility entry point.
Install DejaVu Sans regular/bold fonts. On Linux the default font folder is
`/usr/share/fonts/truetype/dejavu`. On Windows or other installations set
`DOCEXPLORER_MANUAL_FONT_DIR` to the directory containing `DejaVuSans.ttf` and
`DejaVuSans-Bold.ttf`. CJK font data comes from PyMuPDF and is embedded in PDFs.
The application itself does not need these build dependencies to open the
prebuilt documentation. `DocExplorer.spec` already includes the complete docs
folder in packaged applications.
