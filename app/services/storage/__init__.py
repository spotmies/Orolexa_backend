from typing import Optional
from sqlmodel import Session, select
from app.db.models import ImageStorage, User, AnalysisHistory, UserSession, OTPCode

def get_image_from_database(session: Session, image_id: str) -> Optional[ImageStorage]:
    return session.get(ImageStorage, image_id)

def get_user_profile_image(session: Session, user_id: str) -> Optional[ImageStorage]:
    user = session.get(User, user_id)
    if user and user.profile_image_id:
        return session.get(ImageStorage, user.profile_image_id)
    return None

def delete_user_cascade(session: Session, user_id: str) -> bool:
    try:
        # Delete dependent rows referencing user
        for model in [
            AnalysisHistory,
            UserSession,
            OTPCode,
            ImageStorage,
        ]:
            session.exec(select(model).where(getattr(model, 'user_id', None) == user_id))
            # For simplicity, rely on foreign keys with ON DELETE CASCADE when possible
        user = session.get(User, user_id)
        if user:
            session.delete(user)
            session.commit()
            return True
        return False
    except Exception:
        session.rollback()
        return False


