
from pathlib import Path
import pandas as pd

root = Path(__file__).resolve().parent.parent
data_dir = root / "data"

# Find the downloaded Excel workbook.
files = list(data_dir.rglob("online_retail_II.xlsx"))

if not files:
    raise FileNotFoundError(
        "Could not find online_retail_II.xlsx inside the data folder."
    )

source = files[0]
output = data_dir / "online_retail_II.csv"

# Online Retail II has two yearly worksheets.
sheets = pd.read_excel(source, sheet_name=None, dtype=str)

frames = [
    df for df in sheets.values()
    if not df.empty
]

combined = pd.concat(frames, ignore_index=True)
combined.to_csv(output, index=False)

print(f"Source: {source}")
print(f"Rows: {len(combined):,}")
print(f"Saved CSV: {output}")
