import fitz, os, sys
print('python', sys.executable)
print('fitz', fitz.__version__)
print('fitz_file', fitz.__file__)
print('fitz_dir', os.path.dirname(fitz.__file__))
for name in sorted(os.listdir(os.path.dirname(fitz.__file__)))[:50]:
    print(name)
