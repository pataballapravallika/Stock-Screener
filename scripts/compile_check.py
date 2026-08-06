import py_compile
import pathlib

fails = []
for p in pathlib.Path('..').resolve().joinpath('Stock_Screener').rglob('*.py'):
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception as e:
        print('FAILED', p)
        print(e)
        fails.append(p)
print('DONE', len(fails))
