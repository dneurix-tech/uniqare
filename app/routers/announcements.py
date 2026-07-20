from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Announcement
from app.schemas import (
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
)
from app.security import require_admin


router = APIRouter(
    prefix="/announcements",
    tags=["Announcements"],
)


@router.get(
    "/",
    response_model=list[AnnouncementResponse],
)
def get_active_announcements(
    db: Session = Depends(get_db),
):
    announcements = (
        db.query(Announcement)
        .filter(Announcement.is_active == True)
        .order_by(Announcement.id.desc())
        .all()
    )

    return announcements


@router.get(
    "/admin/all",
    response_model=list[AnnouncementResponse],
)
def get_all_announcements(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    announcements = (
        db.query(Announcement)
        .order_by(Announcement.id.desc())
        .all()
    )

    return announcements


@router.post(
    "/",
    response_model=AnnouncementResponse,
)
def create_announcement(
    announcement_data: AnnouncementCreate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    content = announcement_data.content.strip()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Announcement content is required",
        )

    new_announcement = Announcement(
        content=content,
        is_active=announcement_data.is_active,
    )

    db.add(new_announcement)
    db.commit()
    db.refresh(new_announcement)

    return new_announcement


@router.patch(
    "/{announcement_id}",
    response_model=AnnouncementResponse,
)
def update_announcement(
    announcement_id: int,
    announcement_data: AnnouncementUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    announcement = (
        db.query(Announcement)
        .filter(Announcement.id == announcement_id)
        .first()
    )

    if not announcement:
        raise HTTPException(
            status_code=404,
            detail="Announcement not found",
        )

    if announcement_data.content is not None:
        content = announcement_data.content.strip()

        if not content:
            raise HTTPException(
                status_code=400,
                detail="Announcement content cannot be empty",
            )

        announcement.content = content

    if announcement_data.is_active is not None:
        announcement.is_active = announcement_data.is_active

    db.commit()
    db.refresh(announcement)

    return announcement


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    announcement = (
        db.query(Announcement)
        .filter(Announcement.id == announcement_id)
        .first()
    )

    if not announcement:
        raise HTTPException(
            status_code=404,
            detail="Announcement not found",
        )

    db.delete(announcement)
    db.commit()

    return {
        "message": "Announcement deleted successfully",
    }