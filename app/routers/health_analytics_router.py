from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func
import logging
from datetime import datetime, timedelta

from ..db.session import get_session
from ..db.models.health.analysis import AnalysisHistory
from ..db.models.users.user import User
from ..schemas.analysis.analysis import HealthSummary
from ..services.auth import decode_jwt_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health & Analytics"])

oauth2_scheme = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(oauth2_scheme)) -> str:
    """
    Extract current user ID from JWT token.

    Note: User IDs in this project are UUID strings (not integers), so we
    return the raw `sub` claim without casting.
    """
    token = credentials.credentials
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
    return user_id


@router.get("/summary", response_model=HealthSummary)
def get_health_summary(current_user: str = Depends(get_current_user), session: Session = Depends(get_session)):
    try:
        total_analyses = session.exec(select(func.count(AnalysisHistory.id)).where(AnalysisHistory.user_id == current_user)).first() or 0
        last_analysis = session.exec(select(AnalysisHistory).where(AnalysisHistory.user_id == current_user).order_by(AnalysisHistory.created_at.desc())).first()
        last_analysis_date = last_analysis.created_at.strftime("%Y-%m-%d") if last_analysis else None
        health_score = 0
        if total_analyses > 0 and last_analysis:
            days_since_last = (datetime.utcnow() - last_analysis.created_at).days
            base_score = min(total_analyses * 10, 50)
            recency_score = 30 if days_since_last <= 30 else 20 if days_since_last <= 90 else 10 if days_since_last <= 180 else 0
            health_score = min(base_score + recency_score, 100)
        recommendations = []
        if total_analyses == 0:
            recommendations.append("Schedule your first dental checkup")
        elif last_analysis:
            days_since_last = (datetime.utcnow() - last_analysis.created_at).days
            if days_since_last > 180:
                recommendations.append("Schedule a dental checkup - it's been over 6 months")
            elif days_since_last > 90:
                recommendations.append("Consider scheduling a follow-up appointment")
        recommendations.extend(["Brush your teeth twice daily", "Floss regularly", "Limit sugary foods and drinks", "Visit your dentist for regular checkups"])
        next_checkup_date = (last_analysis.created_at + timedelta(days=180)).strftime("%Y-%m-%d") if last_analysis else None
        return HealthSummary(total_analyses=total_analyses, last_analysis_date=last_analysis_date, health_score=health_score, recommendations=recommendations, next_checkup_date=next_checkup_date)
    except Exception as e:
        logger.error(f"Error generating health summary for user {current_user}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to generate health summary")


