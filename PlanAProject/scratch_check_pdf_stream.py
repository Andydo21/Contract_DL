import fitz
from pathlib import Path

pdf_path = "d:/Django_project/DensoFactoryHack2026/PlanAProject/media/documents/The_International_Standards_Organization_ISO___DENSO_Auto_Parts.pdf"
doc = fitz.open(pdf_path)
print(f"Total pages: {len(doc)}")
for pno in range(len(doc)):
    page = doc[pno]
    txt = page.get_text("text")
    if "water" in txt.lower() or "tight" in txt.lower() or "boot" in txt.lower():
        print(f"Page {pno+1} HAS text 'water/tight/boot' in raw page stream!")
    else:
        print(f"Page {pno+1} does NOT have 'water/tight/boot' in raw page stream.")
