from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Merchant
from app.schemas import MerchantOut

router = APIRouter(tags=["auth"])


@router.post("/auth/login")
async def login(phone: str, name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Merchant).where(Merchant.phone == phone))
    merchant = result.scalar_one_or_none()
    if not merchant:
        merchant = Merchant(name=name, phone=phone)
        db.add(merchant)
        await db.commit()
        await db.refresh(merchant)
    return {
        "merchant_id": merchant.id,
        "name": merchant.name,
        "phone": merchant.phone,
    }


@router.get("/merchants/{merchant_id}")
async def get_merchant(merchant_id: str, db: AsyncSession = Depends(get_db)):
    merchant = await db.get(Merchant, merchant_id)
    if not merchant:
        raise HTTPException(status_code=404, detail="Merchant not found")
    return {"id": merchant.id, "name": merchant.name, "phone": merchant.phone}
