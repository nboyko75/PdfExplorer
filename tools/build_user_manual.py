from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak, Table, TableStyle, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs"
IMG = OUT / "manual_images"
PDF = OUT / "DocExplorer_User_Manual.pdf"
OUT.mkdir(exist_ok=True)
IMG.mkdir(exist_ok=True)

FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
SMALL = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
BOLD = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
pdfmetrics.registerFont(TTFont("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("DejaVu-Oblique", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold", italic="DejaVu-Oblique")

def box(d, xy, text="", fill="#ffffff", outline="#9aa6b2", font=FONT, radius=5):
    d.rounded_rectangle(xy, radius, fill=fill, outline=outline, width=2)
    if text:
        d.text((xy[0] + 9, xy[1] + 7), text, fill="#273444", font=font)

def callout(d, n, x, y, label):
    d.ellipse((x, y, x + 30, y + 30), fill="#e05252")
    d.text((x + 9, y + 4), str(n), fill="white", font=BOLD)
    d.text((x + 38, y + 5), label, fill="#8b1f1f", font=SMALL)

def chrome(title):
    im = Image.new("RGB", (1400, 820), "#f5f7fa")
    d = ImageDraw.Draw(im)
    d.rectangle((0, 0, 1400, 42), fill="#1666b1")
    d.text((16, 9), title, fill="white", font=BOLD)
    return im, d

def main_screen():
    im, d = chrome("DocExplorer")
    d.rectangle((0, 42, 1400, 76), fill="#edf1f5")
    d.text((12, 49), "File     Navigation     Document     Help", fill="#202832", font=FONT)
    for i, symbol in enumerate(["<", ">", "?", "X"]): box(d, (12+i*43, 90, 48+i*43, 126), symbol)
    box(d, (190, 90, 1220, 126), "C:\\Users\\User\\Documents")
    d.text((1240, 97), "[ ] Hidden", fill="#273444", font=SMALL)
    box(d, (10, 145, 305, 508), "Folder tree", fill="#ffffff")
    for i,t in enumerate(["Desktop", "Documents", "Downloads", "Pictures", "Projects"]): d.text((35, 195+i*45), "▸  "+t, fill="#273444", font=FONT)
    box(d, (10, 520, 305, 805), "Favorites / shortcuts", fill="#ffffff")
    box(d, (318, 145, 865, 805), "File list", fill="#ffffff")
    d.rectangle((330, 190, 850, 225), fill="#e8eef4")
    d.text((340, 198), "Name                   Type       Size       Modified", fill="#273444", font=SMALL)
    for i,t in enumerate(["Report.pdf", "Budget.xlsx", "Notes.txt", "Images"]): d.text((345, 245+i*45), t, fill="#273444", font=FONT)
    box(d, (878, 145, 1390, 805), "Preview", fill="#ffffff")
    d.rectangle((995, 220, 1280, 655), fill="white", outline="#75808c", width=2)
    d.text((1030, 260), "Document preview", fill="#75808c", font=FONT)
    callout(d, 1, 45, 52, "Menus")
    callout(d, 2, 540, 87, "Address bar")
    callout(d, 3, 35, 150, "Navigation")
    callout(d, 4, 350, 150, "Files and filter")
    callout(d, 5, 900, 150, "Preview and PDF tools")
    p=IMG/"main_window.png"; im.save(p); return p

def search_screen():
    im,d=chrome("Search in files")
    box(d,(25,70,1370,785),fill="white")
    d.text((55,100),"Search folder",font=FONT,fill="#273444"); box(d,(210,88,870,130),"C:\\Documents")
    box(d,(885,88,990,130),"Browse..."); d.text((1010,100),"File mask",font=FONT,fill="#273444"); box(d,(1120,88,1320,130),"*.pdf *.doc?")
    d.text((210,150),"[x] Include child folders",font=SMALL,fill="#273444"); d.text((1130,150),"[x] Word    [ ] Excel",font=SMALL,fill="#273444")
    d.text((55,205),"[x] Search for file name",font=FONT,fill="#273444"); box(d,(300,192,1320,236),"invoice")
    d.text((55,260),"[x] Search in file content",font=FONT,fill="#273444"); box(d,(300,247,1320,291),"approved")
    d.text((300,310),"(•) Text   ( ) Regular expression    [ ] Case sensitive   [x] Whole word",font=SMALL,fill="#273444")
    d.text((55,355),"Date and size filters",font=BOLD,fill="#273444"); box(d,(55,390,1320,455),"Optional From / To filters",fill="#f6f8fb")
    box(d,(55,485,1320,680),"Results: name | size | modified | full path")
    box(d,(990,705,1085,752),"Search"); box(d,(1095,705,1190,752),"Stop"); box(d,(1200,705,1300,752),"Quit")
    callout(d,1,35,84,"Scope and masks"); callout(d,2,35,190,"Name/content criteria"); callout(d,3,35,380,"Optional filters"); callout(d,4,35,500,"Double-click a result to open")
    p=IMG/"search_window.png"; im.save(p); return p

def preview_screen():
    im,d=chrome("PDF preview and editing")
    box(d,(20,65,1380,795),fill="white")
    for i,t in enumerate(["Open","Save","Cancel","Zoom +","Zoom -","Layout","Rotate","Import","Export","Optimize"]): box(d,(40+i*126,90,150+i*126,132),t,font=SMALL)
    for i in range(3):
        x=100+i*420; d.rectangle((x,180,x+330,680),fill="#ffffff",outline="#65717c",width=2); d.text((x+135,700),f"Page {i+1}",fill="#273444",font=SMALL)
    d.rectangle((520,178,852,682),outline="#e05252",width=5)
    d.text((40,750),"Select a page, then rotate, move, remove, or export it. Save commits staged PDF changes.",fill="#273444",font=FONT)
    callout(d,1,40,140,"Document toolbar"); callout(d,2,870,180,"Selected page"); callout(d,3,40,735,"Unsaved-change workflow")
    p=IMG/"pdf_preview.png"; im.save(p); return p

def settings_screen():
    im,d=chrome("Options")
    box(d,(110,75,1290,750),fill="white")
    tabs=["Main","Preview","PDF optimization","PDF advanced","Scan"]
    for i,t in enumerate(tabs): box(d,(135+i*215,100,330+i*215,145),t,font=SMALL,fill="#eaf1f8" if i else "white")
    fields=[("Interface language","Ukrainian"),("Show hidden items","No"),("Preview enabled","Yes"),("MS Office preview","No"),("Pages initially loaded","10")]
    for i,(a,b) in enumerate(fields):
        y=190+i*75; d.text((180,y+8),a,fill="#273444",font=FONT); box(d,(590,y,1120,y+45),b)
    box(d,(995,680,1100,728),"Apply"); box(d,(1115,680,1220,728),"Cancel")
    callout(d,1,130,92,"Settings categories"); callout(d,2,150,180,"Values"); callout(d,3,820,675,"Apply saves changes")
    p=IMG/"options_window.png"; im.save(p); return p

def dialogs_screen():
    im,d=chrome("Scanning and printing")
    box(d,(45,80,680,760),"Scan documents",fill="white",font=BOLD); box(d,(720,80,1355,760),"Print",fill="white",font=BOLD)
    left=[("Output type","PDF"),("Multiple pages","Yes"),("Output file","C:\\Scans\\scan.pdf"),("Open after scan","Yes")]
    right=[("Printer","Office Printer"),("Copies","1"),("Range","Selected pages"),("Pages","1,3-5"),("File","Report.pdf")]
    for i,(a,b) in enumerate(left): d.text((80,160+i*90),a,fill="#273444",font=FONT); box(d,(265,145+i*90,620,192+i*90),b)
    for i,(a,b) in enumerate(right): d.text((755,160+i*80),a,fill="#273444",font=FONT); box(d,(930,145+i*80,1300,192+i*80),b)
    box(d,(445,680,535,725),"Scan"); box(d,(545,680,635,725),"Cancel"); box(d,(1040,680,1130,725),"Print"); box(d,(1140,680,1300,725),"Cancel")
    callout(d,1,70,115,"WIA scan output"); callout(d,2,745,115,"Printer and page range")
    p=IMG/"scan_print.png"; im.save(p); return p

IMAGES=[main_screen(),search_screen(),preview_screen(),settings_screen(),dialogs_screen()]

styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name="ManualTitle",parent=styles["Title"],fontName="DejaVu-Bold",fontSize=28,leading=34,textColor=colors.HexColor("#165f9e"),alignment=TA_CENTER,spaceAfter=18))
styles.add(ParagraphStyle(name="H1x",parent=styles["Heading1"],fontName="DejaVu-Bold",fontSize=20,leading=24,textColor=colors.HexColor("#165f9e"),spaceBefore=8,spaceAfter=10))
styles.add(ParagraphStyle(name="H2x",parent=styles["Heading2"],fontName="DejaVu-Bold",fontSize=14,leading=18,textColor=colors.HexColor("#234f73"),spaceBefore=8,spaceAfter=6))
styles.add(ParagraphStyle(name="Bodyx",parent=styles["BodyText"],fontName="DejaVu",fontSize=10.2,leading=14,spaceAfter=7))
styles.add(ParagraphStyle(name="Notex",parent=styles["BodyText"],fontName="DejaVu",fontSize=9.5,leading=13,leftIndent=8,rightIndent=8,borderColor=colors.HexColor("#aac8df"),borderWidth=1,borderPadding=7,backColor=colors.HexColor("#eef7fd"),spaceBefore=6,spaceAfter=10))

def P(text, style="Bodyx"): return Paragraph(text, styles[style])
def bullets(items): return [P("• "+x) for x in items]
def pic(path, caption): return [KeepTogether([RLImage(str(path), width=178*mm, height=104*mm), Spacer(1,2*mm), P("<i>"+caption+"</i>")])]
def page_num(canvas,doc):
    canvas.saveState(); canvas.setFont("DejaVu",8); canvas.setFillColor(colors.grey); canvas.drawString(18*mm,10*mm,"DocExplorer User Manual"); canvas.drawRightString(192*mm,10*mm,f"Page {doc.page}"); canvas.restoreState()

story=[Spacer(1,35*mm),P("DocExplorer","ManualTitle"),P("User Manual", "ManualTitle"),Spacer(1,8*mm),P("File navigation, document preview, search, PDF editing, scanning and printing", "Bodyx"),Spacer(1,15*mm),RLImage(str(IMAGES[0]),width=165*mm,height=96*mm),Spacer(1,8*mm),P("Manual for the application version supplied on 6 September 2026. The interface images are annotated reconstructions based on the supplied source code; appearance can vary with Windows theme, display scaling and language.","Notex"),PageBreak()]

story += [P("Contents","H1x")]
contents=["1. About DocExplorer","2. Getting started","3. Main window","4. Navigating files and folders","5. Favorites and Windows shortcuts","6. Previewing documents","7. Editing PDF files","8. Searching in files","9. File operations and archives","10. Recycle Bin","11. Scanning","12. Printing","13. Options and language","14. Keyboard shortcuts","15. Troubleshooting and safety"]
story += bullets(contents)+[PageBreak()]

story += [P("1. About DocExplorer","H1x"),P("DocExplorer is a Windows desktop file explorer focused on finding, previewing and working with documents. It combines a folder tree, favorites and Windows shortcuts, a detailed file list, and a preview pane. PDF files can also be edited without leaving the application."),P("Core capabilities","H2x")]+bullets(["Browse folders and inspect file name, type, size and modification date.","Preview PDF, image, text, HTML and supported Microsoft Office files.","Search by file name and/or document content with masks, regular expressions, dates and sizes.","Stage PDF page changes, then save or cancel them as one session.","Copy, cut, paste, rename, delete, archive, extract, scan and print.","Use a localized interface; the supplied version includes eleven languages."])+[P("Platform note","Notex"),P("DocExplorer is intended for Windows. Office preview/printing requires compatible Microsoft Office components. Scanning uses Windows Image Acquisition (WIA). Archive extraction depends on the archive tools available on the PC."),PageBreak()]

story += [P("2. Getting started","H1x"),P("Start DocExplorer normally. The application restores its previous window size, splitter positions, current language, last folder, favorites and many dialog settings."),P("First steps","H2x")]+bullets(["Use the folder tree or type a folder path in the address bar and press Enter.","Select a file in the middle pane. If Preview is enabled and the type is supported, the right pane displays it.","Double-click a folder to enter it or a file to open it with its associated Windows application.","Drag the splitters to give more room to navigation, the file list or preview.","Open File > Options to choose language and preview/PDF settings."])+[P("Changes to PDF pages are staged in memory. Use Save to write them to disk or Cancel to discard them.","Notex"),PageBreak()]

story += [P("3. Main window","H1x")]+pic(IMAGES[0],"Figure 1. Main DocExplorer workspace and its major areas.")+[P("Toolbar and address bar","H2x")]+bullets(["Back and Forward move through navigation history.","Search opens the full Search in files dialog.","Exit closes the application after resolving unsaved PDF changes.","The address bar accepts a folder or file path.","Hidden controls whether hidden items are listed."])+[P("File list toolbar","H2x")]+bullets(["Scan, Open, Up, New folder, Print, Copy, Cut, Paste, Rename and Remove to Recycle Bin.","The Filter box narrows the currently displayed list; it is different from full content search.","Click a column heading to sort. Double-click an item to open it."])+[PageBreak()]

story += [P("4. Navigating files and folders","H1x"),P("The left tree represents folder hierarchy. Expand a node with its arrow, select a folder to load it, and use Up to move to its parent. The address bar and history buttons provide alternative navigation."),P("Common actions","H2x")]+bullets(["Open: opens the selected file or folder.","Refresh (F5): reloads the current folder and refreshes relevant tree nodes.","New folder: creates a uniquely named folder in the current location.","Rename: changes the selected item name.","Drag and drop: move or copy supported items between navigation and file panes.","Show hidden: displays hidden files with a visually dimmed icon."])+[P("The File and right-click menus enable only actions valid for the current selection.","Notex"),P("5. Favorites and Windows shortcuts","H1x"),P("Favorites provide a personal list of often-used folders. Add or remove the current folder from the Navigation menu or context menus. Use the arrow controls or drag rows to change their order."),P("The shortcuts section can show Desktop, Documents, Downloads, Pictures, Music, Videos and Recycle Bin. Use its toggle button to show or hide the section. Right-click the shortcuts list to choose which entries are visible."),P("Activating Recycle Bin displays deleted items in the file list; use Restore, Delete permanently or Clear all from its context menu."),PageBreak()]

story += [P("6. Previewing documents","H1x"),P("Select a file to preview it in the right pane. The Preview checkbox enables general previews; the MS Office checkbox separately controls Office conversion previews."),P("Supported preview families","H2x")]+bullets(["PDF documents with page thumbnails and layouts.","Common raster images, with zoom and rotation.","Text and source files, with long previews truncated for responsiveness.","HTML content in the embedded web view when available.","Word, Excel and PowerPoint via an Office-to-PDF preview conversion when Office preview is enabled."])+[P("Use pin/unpin on preview tabs when you want to preserve a document while browsing. Close tabs that are no longer needed. Large files may initially show only the configured number of pages; choose Load all to render the remainder."),P("Office applications may briefly create or activate a document window during conversion, depending on the installed Office version.","Notex"),PageBreak()]

story += [P("7. Editing PDF files","H1x")]+pic(IMAGES[2],"Figure 2. PDF page selection and editing tools.")+[P("Editing workflow","H2x")]+bullets(["Select a PDF and then select the page to work with.","Rotate the selected page left or right, or rotate all pages.","Move page asks for a destination position.","Remove page removes the selected page from the staged document.","Import from file inserts pages from another PDF; Import from scanner adds scanned pages.","Export pages writes chosen pages to a separate PDF.","Adjust page width normalizes scanned page widths.","Optimize recompresses embedded page images according to Options.","Save commits all staged changes. Save as creates another PDF. Cancel restores the on-disk state."])+[P("Optimization can reduce image quality. Set DPI and color/monochrome compression carefully in File > Options, and keep an original copy of important documents.","Notex"),PageBreak()]

story += [P("8. Searching in files","H1x")]+pic(IMAGES[1],"Figure 3. Search dialog with scope, criteria, filters and results.")+[P("How criteria combine","H2x")]+bullets(["Search folder defines the root. Include child folders searches recursively.","File mask accepts patterns separated by spaces, commas or semicolons, for example *.pdf *.txt.","Word and Excel toggle convenient *.doc? and *.xls? mask tokens.","File name and file content can be enabled independently. When both are enabled, a file must satisfy both.","Text mode performs normal matching; Regular expression mode uses a Python-compatible regular expression.","Case sensitive and Whole word further restrict matching.","Date and size From/To fields are optional boundaries."])+[P("Select Search to start. Pause/Resume temporarily stops work; Stop ends it. Double-click a result to open it. The dialog remembers its history, size, position and column widths."),P("Content extraction supports text/source files, PDF text and modern Office documents. Scanned PDFs without OCR text cannot be found by their visible words.","Notex"),PageBreak()]

story += [P("9. File operations and archives","H1x"),P("Select one or more items in the file list before using Copy, Cut, Remove to Recycle Bin, Delete permanently or Add to archive. Paste operates in the current folder. Standard Windows shortcuts include Ctrl+C, Ctrl+X and Ctrl+V."),P("Archives","H2x")]+bullets(["Add to archive packages the selected files/folders.","Extract from archive here writes contents into the current directory.","Extract from archive into creates or selects a destination directory.","Available formats depend on the installed helper and application configuration."])+[P("Permanent deletion bypasses Recycle Bin and cannot be restored by DocExplorer. Verify the selection and path before confirming.","Notex"),P("10. Recycle Bin","H1x"),P("Open Recycle Bin from Windows shortcuts. Deleted entries appear in the file list with original metadata when Windows supplies it. Right-click an item and choose Restore to return it to its original folder. Delete permanently removes selected entries. Clear all empties the entire Recycle Bin."),P("If the original folder no longer exists or Windows denies access, restoration can fail. Recreate the folder or run with suitable permissions, then retry."),PageBreak()]

story += [P("11. Scanning","H1x"),P("Choose File > Scan or the scanner button. DocExplorer uses the Windows WIA acquisition dialog for the scanner-specific source, color and resolution settings.")]+pic(IMAGES[4],"Figure 4. Scan output options (left) and print options (right).")+bullets(["Choose PDF for a multipage document or JPEG for an image.","Enable Multiple pages to continue acquiring pages into one PDF.","Choose an output filename and whether to open it after scanning.","If the target exists, overwrite it, create a numbered copy, or cancel."])+[P("A WIA-compatible scanner and installed Windows driver are required.","Notex"),P("12. Printing","H1x"),P("Select a file and press Ctrl+P or choose File > Print. Select a printer, number of copies and All pages or Selected pages. Page expressions accept values such as 1,3-5. Printer Parameters opens the Windows printer properties dialog."),P("Selected-page printing is implemented for supported PDF and Microsoft Office documents. Exact printable margins and scaling remain controlled by the printer driver and document application."),PageBreak()]

story += [P("13. Options and language","H1x")]+pic(IMAGES[3],"Figure 5. Options are organized into category tabs.")+[P("Options include the interface language, preview limits and behavior, PDF optimization quality/DPI, advanced monochrome and color encoding, and scan defaults. Select Apply to save values. Some interface labels update immediately; restart if a Windows-integrated component retains its prior language."),P("DocExplorer includes English, Ukrainian, German, French, Spanish, Italian, Brazilian Portuguese, Japanese, Korean, Simplified Chinese and Russian interface resources."),P("14. Keyboard shortcuts","H1x")]
keys=[["Shortcut","Action"],["F1","Open this manual"],["F5","Refresh"],["Ctrl+P","Print selected/current document"],["Ctrl+C / Ctrl+X / Ctrl+V","Copy / Cut / Paste"],["Ctrl+D","Move selected items to Recycle Bin"],["Shift+Delete","Delete selected items permanently"],["Enter / double-click","Open or activate selected item"],["Ctrl+Z","Undo a supported staged PDF operation"]]
t=Table(keys,colWidths=[48*mm,120*mm],repeatRows=1); t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#165f9e")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONTNAME",(0,0),(-1,0),"DejaVu-Bold"),("FONTNAME",(0,1),(-1,-1),"DejaVu"),("FONTSIZE",(0,0),(-1,-1),9.5),("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#a9b8c5")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f4f7f9")]),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)])); story += [t,PageBreak()]

story += [P("15. Troubleshooting and safety","H1x"),P("Preview is blank","H2x")]+bullets(["Confirm Preview is checked.","For Word/Excel/PowerPoint, enable MS Office preview and confirm Microsoft Office is installed.","Wait for conversion of a large file, then reselect it.","Open the file externally to verify it is not damaged or locked."])+[P("Search finds no content","H2x")]+bullets(["Check the folder, file mask and Include child folders.","If both name and content are checked, remember that both must match.","Remove date/size limits and test again.","Scanned images require OCR text before content search can find words."])+[P("Icons or Recycle Bin differ in the packaged EXE","H2x")]+bullets(["Build with the supplied DocExplorer.spec so images, localization and this manual are included.","Windows shell metadata can vary by account, language and permissions.","Refresh after external file operations."])+[P("Safe document handling","H2x")]+bullets(["Keep backups before optimization, permanent deletion or extensive PDF edits.","Use Save as to preserve an original PDF.","Close documents in other programs if DocExplorer reports a sharing or access error.","Do not interrupt the application while it is writing a PDF or extracting an archive."])+[Spacer(1,10*mm),P("End of manual","H1x")]

doc=SimpleDocTemplate(str(PDF),pagesize=A4,rightMargin=16*mm,leftMargin=16*mm,topMargin=16*mm,bottomMargin=16*mm,title="DocExplorer User Manual",author="DocExplorer")
doc.build(story,onFirstPage=page_num,onLaterPages=page_num)
print(PDF)
