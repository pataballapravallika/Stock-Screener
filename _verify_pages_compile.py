import py_compile
import glob

print("Checking syntax and compilation of all app pages...\n")
files = glob.glob("pages/*.py") + ["app.py", "home.py"]
for page in files:
    try:
        py_compile.compile(page, doraise=True)
        print(f"  [OK] {page}")
    except Exception as e:
        print(f"  [FAIL] {page}: {e}")
