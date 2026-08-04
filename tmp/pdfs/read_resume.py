import os
import sys

import fitz


source, output_dir = sys.argv[1], sys.argv[2]
document = fitz.open(source)
print("PAGES", document.page_count)
for index, page in enumerate(document):
    print(f"\n===== PAGE {index + 1} =====\n")
    print(page.get_text("text"))
    pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    pixmap.save(os.path.join(output_dir, f"resume-page-{index + 1}.png"))
