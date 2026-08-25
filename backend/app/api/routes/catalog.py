"""Product catalog.

Velora owns this data, which is why the gate can trust it. Agents browse it
to choose; they never get to describe what they chose.
"""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession
from app.models import Product
from app.schemas.api import ProductOut

router = APIRouter(prefix="/api/products", tags=["catalog"])


@router.get("", response_model=list[ProductOut])
def list_products(db: DbSession, category: str | None = None, merchant: str | None = None):
    query = select(Product).order_by(Product.price_paise.asc())
    if category:
        query = query.where(Product.category == category)
    if merchant:
        query = query.where(Product.merchant == merchant)
    return list(db.scalars(query))


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: str, db: DbSession):
    from fastapi import HTTPException

    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="No such product.")
    return product
