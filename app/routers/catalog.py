from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Merchant, Catalog, Product
from app.schemas import CatalogCreate, CatalogOut, ProductOut, TextPasteRequest, ProductItem
from app.services.ai_service import extract_products_from_text
from app.services.excel_service import parse_excel, generate_excel

router = APIRouter(tags=["catalogs"])


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

    products_result = await db.execute(
        select(Product).where(Product.catalog_id == catalog_id)
    )
    products = products_result.scalars().all()

    return CatalogOut(
        id=catalog.id,
        title=catalog.title,
        description=catalog.description,
        merchant_id=catalog.merchant_id,
        is_public=catalog.is_public,
        products=[ProductOut.from_orm(p) for p in products],
    )


@router.get("/catalogs/{catalog_id}/download")
async def download_catalog(catalog_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Product).where(Product.catalog_id == catalog_id)
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



