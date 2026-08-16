import os
import subprocess
import sys

project_dir = r'd:\Projects\PdfExplorer'
venv_python = os.path.join(project_dir, '.venv', 'Scripts', 'python.exe')
if not os.path.exists(venv_python):
    raise SystemExit(f'Virtual environment Python not found: {venv_python}')

cmd = [venv_python, '-m', 'pip', 'install', '--upgrade', 'pyinstaller']
print('Running:', ' '.join(cmd))
result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
print(result.stdout)
print(result.stderr)
if result.returncode != 0:
    raise SystemExit(result.returncode)

cmd = [venv_python, '-m', 'PyInstaller', os.path.join(project_dir, 'DocExplorer.spec')]
print('Running:', ' '.join(cmd))
result = subprocess.run(cmd, cwd=project_dir, capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
print(result.stdout)
print(result.stderr)
if result.returncode != 0:
    raise SystemExit(result.returncode)
