from pydantic import BaseModel
from typing import Optional, List


class ProductOut(BaseModel):
    id: str
    catalog_id: str
    name: str
    price: Optional[float] = None
    description: Optional[str] = None
    image_url: Optional[str] = None

    class Config:
        from_attributes = True


class CatalogOut(BaseModel):
    id: str
    title: str
    description: Optional[str] = None
    merchant_id: str
    is_public: bool
    products: List[ProductOut] = []

    class Config:
        from_attributes = True


class MerchantOut(BaseModel):
    id: str
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    catalogs: List[CatalogOut] = []

    class Config:
        from_attributes = True


class CatalogCreate(BaseModel):
    merchant_name: str
    merchant_phone: Optional[str] = None
    catalog_title: str = "My Catalog"


class TextPasteRequest(BaseModel):
    merchant_id: str
    catalog_id: str
    text: str


class ProductItem(BaseModel):
    name: str
    price: Optional[float] = None
    description: Optional[str] = None
