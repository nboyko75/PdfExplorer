import glob
import os
import re

translations = {
    'en': 'Scan',
    'uk': 'Сканувати',
    'ru': 'Сканировать',
    'de': 'Scannen',
    'fr': 'Numériser',
    'es': 'Escanear',
    'it': 'Scansiona',
    'ja': 'スキャン',
    'ko': 'スキャン',
    'pt_br': 'Escanear',
    'zh_cn': '扫描'
}

folders = [r'd:\Projects\PdfExplorer\localization', r'd:\Projects\PdfExplorer\distlocalization']

updated_count = 0

for folder in folders:
    files = glob.glob(os.path.join(folder, 'localization_*.py'))
    for filepath in files:
        # Get filename and locale code
        filename = os.path.basename(filepath)
        # e.g., localization_en.py -> en, or localization_pt_br.py -> pt_br
        match = re.search(r'localization_([a-z_]+)\.py', filename)
        if not match:
            continue
        locale = match.group(1)
        val = translations.get(locale)
        if not val:
            print(f"Warning: no translation for locale '{locale}' in {filename}")
            continue
        
        # Read file lines
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        new_lines = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if '"context_delete":' in line and '"scan":' not in line:
                # Find indentation from 'line'
                indent = re.match(r'^(\s*)', line).group(1)
                # Ensure context_delete has a trailing comma (it probably does, but let's check or just append ours with a comma)
                # The line with scan can be:
                newline = f'{indent}"scan": "{val}",\n'
                new_lines.append(newline)
                inserted = True
                
        if inserted:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            updated_count += 1
            print(f"Updated {filepath} with scan='{val}'")
        else:
            print(f"Could not or did not need to update {filepath} (maybe already has scan key or missing context_delete)")

print(f"Total files updated: {updated_count}")
