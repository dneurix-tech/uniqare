from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
import cloudinary.uploader

from app.database import get_db
from app.models import Product
from app.schemas import ProductResponse
from app.cloudinary_config import cloudinary


router = APIRouter(
    prefix="/products",
    tags=["Products"]
)


def upload_image_to_cloudinary(image: UploadFile):
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    try:
        upload_result = cloudinary.uploader.upload(
            image.file,
            folder="uniqare/products",
            resource_type="image"
        )

        image_url = upload_result.get("secure_url")

        if not image_url:
            raise HTTPException(
                status_code=500,
                detail="Cloudinary did not return image URL"
            )

        return image_url

    except HTTPException:
        raise

    except Exception as e:
        print("Cloudinary upload error:", repr(e))
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {str(e)}"
        )


@router.post("/", response_model=ProductResponse)
def create_product(
    name: str = Form(...),
    description: Optional[str] = Form(None),
    price: float = Form(...),
    category: Optional[str] = Form(None),
    stock: int = Form(0),
    is_active: bool = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    image_url = None

    if image:
        image_url = upload_image_to_cloudinary(image)

    if stock <= 0:
        stock = 0
        is_active = False

    new_product = Product(
        name=name,
        description=description,
        price=price,
        image_url=image_url,
        category=category,
        stock=stock,
        is_active=is_active
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


@router.get("/", response_model=list[ProductResponse])
def get_products(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.is_active == True).all()
    return products


@router.get("/{product_id}", response_model=ProductResponse)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@router.patch("/{product_id}", response_model=ProductResponse)
def update_product(
    product_id: int,
    name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    category: Optional[str] = Form(None),
    stock: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if name is not None:
        product.name = name

    if description is not None:
        product.description = description

    if price is not None:
        product.price = price

    if category is not None:
        product.category = category

    if stock is not None:
        product.stock = stock

    if is_active is not None:
        product.is_active = is_active

    if image:
        image_url = upload_image_to_cloudinary(image)
        product.image_url = image_url

    if product.stock <= 0:
        product.stock = 0
        product.is_active = False
    else:
        if is_active is None:
            product.is_active = True

    db.commit()
    db.refresh(product)

    return product


@router.delete("/{product_id}")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return {"message": "Product deleted successfully"}