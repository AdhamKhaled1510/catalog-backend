import io
from typing import List

import pandas as pd

from app.schemas import ProductItem


def parse_excel(file_bytes: bytes) -> List[ProductItem]:
    df = pd.read_excel(io.BytesIO(file_bytes))
    df.columns = df.columns.str.strip().str.lower()

    name_col = _find_column(df, ["name", "product name", "product", "item", "item name", "الاسم", "اسم المنتج"])
    price_col = _find_column(df, ["price", "unit price", "cost", "السعر", "سعر"])
    desc_col = _find_column(df, ["description", "desc", "details", "notes", "الوصف", "ملاحظات"])

    if not name_col:
        raise ValueError("Could not find a product name column in the Excel file")

    products = []
    for _, row in df.iterrows():
        name = str(row[name_col]).strip() if pd.notna(row[name_col]) else ""
        if not name:
            continue
        price = None
        if price_col and pd.notna(row[price_col]):
            try:
                price = float(row[price_col])
            except (ValueError, TypeError):
                price = None
        description = str(row[desc_col]).strip() if desc_col and pd.notna(row[desc_col]) else None
        products.append(ProductItem(name=name, price=price, description=description))

    return products


def generate_excel(products: List[ProductItem]) -> bytes:
    data = []
    for p in products:
        data.append({
            "Product Name": p.name,
            "Price": p.price if p.price is not None else "",
            "Description": p.description or "",
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Products")
    output.seek(0)
    return output.getvalue()


def _find_column(df, candidates: List[str]):
    for col in df.columns:
        if col.strip().lower() in candidates:
            return col
    return None
