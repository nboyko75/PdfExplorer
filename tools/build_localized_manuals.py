"""Build offline HTML/PDF manuals from docs/translations (Python + reportlab + PyMuPDF)."""
import ast
import html
import json
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
LANGUAGES = {'en':'English','uk':'Українська','de':'Deutsch','fr':'Français','es':'Español','it':'Italiano','pt_br':'Português (Brasil)','ja':'日本語','ko':'한국어','zh_cn':'简体中文','ru':'Русский'}
KEYS = ['scan','context_open','context_open_with','context_rename','context_new_folder','context_refresh','print_button',
        'context_copy','context_cut','context_remove_to_recycle_bin','context_delete','context_add_to_archive',
        'context_extract_from_archive_here','context_extract_from_archive_into','menu_file_options','exit_button',
        'back_button','folder_up_button','favorite_add_menu_item','search_in_files_button','preview_import_from_file_button',
        'preview_import_from_scanner_button','preview_export_pages_button','preview_save_button','preview_cancel_button',
        'preview_zoom_in_button','preview_zoom_out_button','preview_show_1_page_wide','preview_rotate_button',
        'preview_rotate_all_right_button','preview_move_page_button','preview_remove_page_button','preview_adjust_page_width_button','preview_optimize_button']

def translations(path):
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Dict):
            value = ast.literal_eval(node.value)
            if 'app_title' in value:
                return value
    raise ValueError(path)

def ui_strings(code):
    result=translations(ROOT/'localization/__init__.py')
    result.update(translations(ROOT/'localization'/f'localization_{code}.py'))
    return result

def build_html(code, data, ui, template):
    esc=html.escape
    css=re.search(r'<style>(.*?)</style>',template,re.S).group(1)
    css+='\nnav select{width:100%;padding:8px;margin:12px 0} nav a{overflow-wrap:anywhere} .reading{padding:20px 24px;margin:16px 0;background:white;border-radius:8px} .reading p{margin:12px 0}.command{grid-template-columns:minmax(0,1fr) minmax(0,1.5fr);align-items:start}.command img{max-width:720px}.copy{min-width:0}.copy h3{overflow-wrap:anywhere}'
    options=''.join(f'<option value="index_{c}.html"'+(' selected' if c==code else '')+f'>{esc(n)}</option>' for c,n in LANGUAGES.items())
    groups=[('file-menu','menu_file',0,16),('navigation-menu','menu_navigation',16,20),('document-menu','menu_document',20,34)]
    nav=''.join(f'<li><a href="#{id}">{esc(ui[key])}</a></li>' for id,key,_,_ in groups)
    nav+=f'<li><a href="#contents">{esc(data["contents"])}</a></li>'
    nav+=''.join(f'<li><a href="#chapter-{i}">{i}. {esc(title)}</a></li>' for i,(title,_) in enumerate(data['sections'],1))
    title='DocExplorer — '+data['title']
    body=f'<h1>{esc(title)}</h1><div class="intro"><p>{esc(data["note"])}</p><p><a href="../DocExplorer_User_Manual_{code}.pdf">{esc(ui["help_manual_open_pdf_button"])}</a></p></div>'
    commands=re.findall(r'<section class="command" id="([^"]+)">.*?<img src="([^"]+)".*?</section>',template,re.S)
    assert len(commands)==len(data['help'])==len(KEYS)==34
    for id,key,start,end in groups:
        body+=f'<h2 id="{id}">{esc(ui[key])}</h2>'
        for i in range(start,end):
            command_id,img=commands[i];label=ui[KEYS[i]]
            if i in (7,8): label+=' / '+ui['context_paste']
            if i==16: label+=' / '+ui['forward_button']
            if i==27: label=' / '.join(ui[k] for k in ('preview_show_1_page_wide','preview_show_2_pages_wide','preview_show_1_page_tall'))
            body+=f'<section class="command" id="{command_id}"><div class="copy"><h3>{esc(label)}</h3><p>{esc(data["help"][i])}</p></div><img loading="lazy" src="{img}" alt="{esc(label)}"></section>'
    body+=f'<h2 id="contents">{esc(data["contents"])}</h2>'
    for i,(heading,paragraphs) in enumerate(data['sections'],1):
        body+=f'<section class="reading" id="chapter-{i}"><h3>{i}. {esc(heading)}</h3>'
        body+=''.join('<p>'+esc(p)+'</p>' for p in paragraphs.split('\\n'))+'</section>'
    lang={'zh_cn':'zh-CN','pt_br':'pt-BR'}.get(code,code)
    result=f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>{esc(title)}</title><style>{css}</style></head><body><nav><h1>DocExplorer</h1><label for="language">{esc(ui["settings_ui_locale"])}</label><select id="language" onchange="location.href=this.value+location.hash">{options}</select><ul>{nav}</ul></nav><main>{body}</main></body></html>'
    (DOCS/'help'/f'index_{code}.html').write_text(result,encoding='utf-8')
    if code=='en': (DOCS/'help/index.html').write_text(result,encoding='utf-8')

def build_pdfs():
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Image
    import fitz
    import os
    fonts=Path(os.environ.get('DOCEXPLORER_MANUAL_FONT_DIR','/usr/share/fonts/truetype/dejavu'))
    pdfmetrics.registerFont(TTFont('Body',str(fonts/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('Heading',str(fonts/'DejaVuSans-Bold.ttf')))
    with tempfile.TemporaryDirectory() as tmp:
        cjk=Path(tmp)/'CJK.ttf';cjk.write_bytes(fitz.Font('cjk').buffer)
        pdfmetrics.registerFont(TTFont('CJK',str(cjk)))
        for code in LANGUAGES:
            data=json.loads((DOCS/'translations'/f'{code}.json').read_text(encoding='utf-8'))
            is_cjk=code in ('ja','ko','zh_cn');font='CJK' if is_cjk else 'Body';bold=font if is_cjk else 'Heading'
            body=ParagraphStyle('body',fontName=font,fontSize=10.5,leading=16,spaceAfter=10,wordWrap='CJK' if is_cjk else None)
            head=ParagraphStyle('head',fontName=bold,fontSize=21,leading=28,spaceAfter=20,textColor=colors.HexColor('#17365d'),wordWrap='CJK' if is_cjk else None)
            note=ParagraphStyle('note',parent=body,fontSize=9,leading=14,textColor=colors.HexColor('#536272'))
            def p(text,style=body):return Paragraph(html.escape(text),style)
            story=[Spacer(1,18*mm),p('DocExplorer',head),p(data['title'],head),p(LANGUAGES[code]),Spacer(1,8*mm),Image(str(DOCS/'manual_images/main_window.png'),width=170*mm,height=99.57*mm),Spacer(1,6*mm),p(data['note'],note),PageBreak(),p(data['contents'],head)]
            for i,(title,_) in enumerate(data['sections'],1):story.append(p(f'{i}. {title}'))
            pictures={3:'main_window.png',7:'pdf_preview.png',8:'search_window.png',11:'scan_print.png',13:'options_window.png'}
            for i,(heading,paragraphs) in enumerate(data['sections'],1):
                story.extend([PageBreak(),p(f'{i}. {heading}',head)])
                if i in pictures:story.extend([Image(str(DOCS/'manual_images'/pictures[i]),width=170*mm,height=99.57*mm),Spacer(1,5*mm)])
                story.extend(p(t) for t in paragraphs.split('\\n'))
            path=DOCS/f'DocExplorer_User_Manual_{code}.pdf'
            def footer(canvas,doc):
                canvas.setStrokeColor(colors.HexColor('#d8e0ea'));canvas.line(18*mm,17*mm,192*mm,17*mm)
                canvas.setFont(font,8);canvas.setFillColor(colors.HexColor('#536272'))
                canvas.drawString(18*mm,12*mm,'DocExplorer | '+LANGUAGES[code]);canvas.drawRightString(192*mm,12*mm,str(doc.page))
            doc=SimpleDocTemplate(str(path),pagesize=A4,leftMargin=20*mm,rightMargin=20*mm,topMargin=18*mm,bottomMargin=23*mm,title='DocExplorer — '+data['title'],author='DocExplorer')
            doc.build(story,onFirstPage=footer,onLaterPages=footer)
            if code=='en':(DOCS/'DocExplorer_User_Manual.pdf').write_bytes(path.read_bytes())
            print(code, 'PDF built')

def main():
    template=(DOCS/'help/template.html').read_text(encoding='utf-8')
    for code in LANGUAGES:
        data=json.loads((DOCS/'translations'/f'{code}.json').read_text(encoding='utf-8'))
        assert len(data['sections'])==15
        build_html(code,data,ui_strings(code),template)
    build_pdfs()

if __name__=='__main__':main()
