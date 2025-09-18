from typing import Optional
from sqlmodel import Session, select

from app.db.models import (
    ImageStorage,
    User,
    AnalysisHistory,
    UserSession,
    OTPCode,
)


def get_image_from_database(session: Session, image_id: str) -> Optional[ImageStorage]:
    """Fetch a stored image by its ID from the database."""
    try:
        return session.exec(select(ImageStorage).where(ImageStorage.id == image_id)).first()
    except Exception:
        return None


def get_user_profile_image(session: Session, user_id: str) -> Optional[ImageStorage]:
    """Fetch the latest profile image for a user from the database, if any."""
    try:
        # Heuristic: image_type == 'profile' when set; otherwise use latest by created_at
        img = session.exec(
            select(ImageStorage)
            .where(ImageStorage.user_id == user_id)
            .where((ImageStorage.image_type == 'profile'))
        ).first()
        if img:
            return img
        return session.exec(
            select(ImageStorage)
            .where(ImageStorage.user_id == user_id)
            .order_by(ImageStorage.created_at.desc())
        ).first()
    except Exception:
        return None


def delete_user_cascade(session: Session, user_id: str) -> bool:
    """Delete a user and associated records in a best-effort single transaction."""
    try:
        # Delete related records first to satisfy FK constraints
        for model, cond in [
            (ImageStorage, ImageStorage.user_id == user_id),
            (AnalysisHistory, AnalysisHistory.user_id == user_id),
            (UserSession, UserSession.user_id == user_id),
            (OTPCode, OTPCode.phone == (session.exec(select(User).where(User.id == user_id)).first().phone if session else None)),
        ]:
            try:
                items = session.exec(select(model).where(cond)).all()
                for item in items:
                    session.delete(item)
            except Exception:
                # Non-fatal; continue deleting other resources
                pass

        # Finally delete the user
        user = session.exec(select(User).where(User.id == user_id)).first()
        if user:
            session.delete(user)
        session.commit()
        return True
    except Exception:
        session.rollback()
        return False


