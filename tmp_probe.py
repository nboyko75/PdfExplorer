import fitz, inspect, sys
print('python', sys.executable)
print('fitz', fitz.__version__)
doc = fitz.open()
page = doc.new_page()
pix = fitz.Pixmap(fitz.csRGB, 100, 100, b'\x00' * 30000, 0)
print('has jpg_quality', 'jpg_quality' in pix.tobytes.__code__.co_varnames if hasattr(pix.tobytes, '__code__') else 'n/a')
try:
    print('sig', inspect.signature(pix.tobytes))
except Exception as e:
    print('sig err', e)
for kwargs in ({'jpg_quality': 20}, {'quality': 20}, {'jpg_quality': 50}, {'quality': 50}):
    try:
        data = pix.tobytes('jpg', **kwargs)
        print(kwargs, 'ok', len(data))
    except Exception as e:
        print(kwargs, 'err', repr(e))
