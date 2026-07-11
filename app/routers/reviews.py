from typing import Optional

import cloudinary.uploader
import app.cloudinary_config

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Review

router = APIRouter(prefix="/reviews", tags=["Reviews"])


def review_to_dict(review: Review):
    return {
        "id": review.id,
        "customer_name": review.customer_name,
        "description": review.description,
        "image_url": review.image_url,
        "rating": review.rating,
        "is_active": review.is_active,
        "created_at": review.created_at,
    }


def upload_review_image(image: UploadFile):
    if not image:
        return None

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Only image files are allowed"
        )

    try:
        upload_result = cloudinary.uploader.upload(
            image.file,
            folder="uniqare/reviews",
            resource_type="image"
        )

        return upload_result.get("secure_url")

    except Exception as error:
        print("Cloudinary review upload error:", error)
        raise HTTPException(
            status_code=500,
            detail="Failed to upload review image"
        )


@router.get("/")
def get_public_reviews(db: Session = Depends(get_db)):
    reviews = (
        db.query(Review)
        .filter(Review.is_active == True)
        .order_by(desc(Review.created_at))
        .all()
    )

    return [review_to_dict(review) for review in reviews]


@router.get("/admin/all")
def get_admin_reviews(db: Session = Depends(get_db)):
    reviews = db.query(Review).order_by(desc(Review.created_at)).all()

    return [review_to_dict(review) for review in reviews]


@router.post("/")
def create_review(
    customer_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    rating: int = Form(5),
    is_active: bool = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    cleaned_description = description.strip() if description else None
    cleaned_customer_name = customer_name.strip() if customer_name else None

    image_url = None

    if image and image.filename:
        image_url = upload_review_image(image)

    if not cleaned_description and not image_url:
        raise HTTPException(
            status_code=400,
            detail="Review must have description or image"
        )

    if rating < 1 or rating > 5:
        raise HTTPException(
            status_code=400,
            detail="Rating must be between 1 and 5"
        )

    new_review = Review(
        customer_name=cleaned_customer_name,
        description=cleaned_description,
        image_url=image_url,
        rating=rating,
        is_active=is_active,
    )

    db.add(new_review)
    db.commit()
    db.refresh(new_review)

    return review_to_dict(new_review)


@router.patch("/{review_id}")
def update_review(
    review_id: int,
    customer_name: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    rating: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    review = db.query(Review).filter(Review.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    if customer_name is not None:
        review.customer_name = customer_name.strip() or None

    if description is not None:
        review.description = description.strip() or None

    if rating is not None:
        if rating < 1 or rating > 5:
            raise HTTPException(
                status_code=400,
                detail="Rating must be between 1 and 5"
            )

        review.rating = rating

    if is_active is not None:
        review.is_active = is_active

    if image and image.filename:
        review.image_url = upload_review_image(image)

    if not review.description and not review.image_url:
        raise HTTPException(
            status_code=400,
            detail="Review must have description or image"
        )

    db.commit()
    db.refresh(review)

    return review_to_dict(review)


@router.delete("/{review_id}")
def delete_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    db.delete(review)
    db.commit()

    return {"message": "Review deleted successfully"}