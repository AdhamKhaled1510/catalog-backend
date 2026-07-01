import base64
import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Merchant, Catalog, Product
from app.schemas import CatalogCreate, CatalogOut, ProductOut, TextPasteRequest, ProductItem
from app.services.ai_service import extract_products_from_text
from app.services.excel_service import parse_excel, generate_excel

router = APIRouter(tags=["catalogs"])


@router.get("/merchants/{merchant_id}/catalogs")
async def get_merchant_catalogs(merchant_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Catalog).where(Catalog.merchant_id == merchant_id)
    )
    catalogs = result.scalars().all()
    return [{"id": c.id, "title": c.title, "product_count": len(c.products)} for c in catalogs]


@router.post("/catalogs/create", response_model=CatalogOut)
async def create_catalog(data: CatalogCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.phone == data.merchant_phone))
    merchant = result.scalar_one_or_none()

    if not merchant:
        merchant = Merchant(name=data.merchant_name, phone=data.merchant_phone)
        db.add(merchant)
        await db.flush()

    catalog = Catalog(title=data.catalog_title, merchant_id=merchant.id)
    db.add(catalog)
    await db.commit()
    await db.refresh(catalog)

    return CatalogOut(
        id=catalog.id,
        title=catalog.title,
        description=catalog.description,
        merchant_id=catalog.merchant_id,
        merchant_phone=merchant.phone,
        is_public=catalog.is_public,
        products=[],
    )


@router.post("/catalogs/{catalog_id}/paste")
async def paste_text(catalog_id: str, data: TextPasteRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found")

    products_data = await extract_products_from_text(data.text)

    for item in products_data:
        product = Product(
            catalog_id=catalog_id,
            name=item.name,
            price=item.price,
            description=item.description,
        )
        db.add(product)

    await db.commit()
    return {"message": f"Added {len(products_data)} products", "count": len(products_data)}


@router.post("/catalogs/{catalog_id}/upload-excel")
async def upload_excel(catalog_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Catalog).where(Catalog.id == catalog_id))
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found")

    contents = await file.read()
    products_data = parse_excel(contents)

    for item in products_data:
        product = Product(
            catalog_id=catalog_id,
            name=item.name,
            price=item.price,
            description=item.description,
        )
        db.add(product)

    await db.commit()
    return {"message": f"Added {len(products_data)} products", "count": len(products_data)}


@router.get("/catalogs/{catalog_id}", response_model=CatalogOut)
async def get_catalog(catalog_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Catalog).where(Catalog.id == catalog_id)
    )
    catalog = result.scalar_one_or_none()
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found")

    merchant = await db.get(Merchant, catalog.merchant_id)
    products_result = await db.execute(
        select(Product).where(Product.catalog_id == catalog_id).order_by(Product.sort_order, Product.id)
    )
    products = products_result.scalars().all()

    return CatalogOut(
        id=catalog.id,
        title=catalog.title,
        description=catalog.description,
        merchant_id=catalog.merchant_id,
        merchant_phone=merchant.phone if merchant else None,
        is_public=catalog.is_public,
        products=[ProductOut.model_validate(p) for p in products],
    )


@router.get("/catalogs/{catalog_id}/download")
async def download_catalog(catalog_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.catalog_id == catalog_id).order_by(Product.sort_order, Product.id)
    )
    products = result.scalars().all()

    items = [
        ProductItem(name=p.name, price=p.price, description=p.description)
        for p in products
    ]
    excel_bytes = generate_excel(items)

    from fastapi.responses import Response
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=catalog_{catalog_id}.xlsx"},
    )


@router.post("/upload-image")
async def upload_product_image(file: UploadFile = File(...)):
    contents = await file.read()
    ext = file.filename.split(".")[-1] if file.filename else "png"
    b64 = base64.b64encode(contents).decode()
    return {"image_url": f"data:image/{ext};base64,{b64}"}
