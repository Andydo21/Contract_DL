import os
import glob

files = glob.glob('C:\\Users\\Windows 10\\.gemini\\antigravity\\brain\\1294386f-646f-4f1e-9610-fe3171273009\\*.png')
files.sort(key=os.path.getmtime, reverse=True)

for f in files[:10]:
    print(f"{f}: {os.path.getmtime(f)}")
