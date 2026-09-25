import glob
import os
import pdfplumber
import pandas as pd

# Path to the folder containing your PDF files
pdf_folder = "./data"
output_csv = "combined_pdf_data.csv"

all_data = []

# Loop through every PDF file in the specified directory
for file_path in glob.glob(os.path.join(pdf_folder, "*.pdf")):
    filename = os.path.basename(file_path)

    with pdfplumber.open(file_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            # Option A: Extract structured tables if present
            tables = page.extract_tables()
            for table in tables:
                for row in table:
                    all_data.append(
                        {
                            "Source_File": filename,
                            "Page": page_num,
                            "Content_Type": "Table Row",
                            "Data": " | ".join(
                                [str(cell) if cell else "" for cell in row]
                            ),
                        }
                    )

            # Option B: Extract full page text if no tables are found
            if not tables:
                text = page.extract_text()
                if text:
                    all_data.append(
                        {
                            "Source_File": filename,
                            "Page": page_num,
                            "Content_Type": "Text",
                            "Data": text.replace("\n", " "),
                        }
                    )

# Convert the gathered data into a DataFrame and export to CSV
df = pd.DataFrame(all_data)
df.to_csv(output_csv, index=False, encoding="utf-8")

print(
    f"Successfully processed {len(glob.glob(os.path.join(pdf_folder, '*.pdf')))} files into '{output_csv}'."
)