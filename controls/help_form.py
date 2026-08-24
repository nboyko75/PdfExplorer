import wx

from localization import tr


def _build_manual_section_text(title, entries):
    lines = [title, "-"]
    for entry in entries:
        lines.append(f"• {entry}")
    return "\n".join(lines)


def show_app_manual_form(owner):
    dialog = wx.Dialog(owner, title=tr("menu_app_manual"), size=(720, 520))
    panel = wx.Panel(dialog)
    scroll = wx.ScrolledWindow(panel)
    scroll.SetScrollRate(12, 12)

    sections = [
        (
            tr("menu_file"),
            [
                "Open - open a selected file or folder.",
                "New folder - create a folder inside the current directory.",
                "Rename - rename the selected item.",
                "Copy / Cut / Paste / Delete - manage files and folders.",
                "Options - change application settings.",
                "Exit - close the application.",
            ],
        ),
        (
            tr("menu_navigation"),
            [
                "Back / Forward - move through the navigation history.",
                "Search in files - search the selected folder content.",
            ],
        ),
        (
            tr("menu_document"),
            [
                "Import from file / scanner - add pages into a PDF.",
                "Export pages - save selected PDF pages to a new file.",
                "Save / Cancel - keep or discard PDF changes.",
                "Zoom / Layout - switch page display modes.",
                "Rotate / Move / Remove page - edit the opened PDF.",
                "Optimize / Adjust page width - improve exported or displayed PDF output.",
            ],
        ),
        (
            tr("menu_help"),
            [
                "About - view application information.",
                "App manual - open this help guide.",
            ],
        ),
    ]

    body_sizer = wx.BoxSizer(wx.VERTICAL)
    for title, entries in sections:
        heading = wx.StaticText(scroll, label=title)
        heading.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        body = wx.StaticText(scroll, label=_build_manual_section_text(title, entries))
        body.Wrap(620)
        body_sizer.Add(heading, 0, wx.ALL | wx.EXPAND, 8)
        body_sizer.Add(body, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

    scroll.SetSizer(body_sizer)
    scroll.Layout()

    close_btn = wx.Button(panel, wx.ID_OK, tr("exit_button"))
    main_sizer = wx.BoxSizer(wx.VERTICAL)
    main_sizer.Add(scroll, 1, wx.EXPAND | wx.ALL, 12)
    main_sizer.Add(close_btn, 0, wx.ALIGN_CENTRE | wx.BOTTOM, 12)
    panel.SetSizer(main_sizer)
    dialog.CenterOnParent()
    dialog.ShowModal()
    dialog.Destroy()
