"""
AI Interview Assistant - History & Improvement API

Endpoints for:
- Viewing attempt history
- Tracking skill progress
- Improvement analytics
- Session management

Author: AI Interview Assistant Team
"""

from typing import List, Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Depends

from app.logging_config import get_logger
from app.services.auth_service import current_user_id
from app.services.supabase_db import (
    get_user_attempts,
    get_attempt_by_id,
    count_user_attempts,
    get_dashboard_stats
)

logger = get_logger(__name__)

router = APIRouter(prefix="/history", tags=["History & Progress"])


# ===========================================
# Attempt History Endpoints
# ===========================================

@router.get("/attempts")
async def get_attempts(
    user_id: str = Depends(current_user_id),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    question_id: Optional[int] = Query(default=None, description="Filter by question ID"),
    min_score: Optional[float] = Query(default=None, ge=0, le=100),
    max_score: Optional[float] = Query(default=None, ge=0, le=100),
    start_date: Optional[str] = Query(default=None, description="Filter from date (ISO format)"),
    end_date: Optional[str] = Query(default=None, description="Filter until date (ISO format)")
):
    """
    Get user's attempt history with optional filtering.
    
    Supports filtering by:
    - Question ID (for specific question history)
    - Score range (for finding good/bad attempts)
    - Date range (for period-specific analysis)
    
    Returns attempts ordered by newest first.
    """
    logger.info(f"Fetching attempts for user {user_id}, limit={limit}, offset={offset}")
    
    # Get base attempts
    attempts = await get_user_attempts(user_id, limit=limit + 20, offset=offset)  # Get extra for filtering
    
    # Apply filters
    if question_id is not None:
        attempts = [a for a in attempts if a.get("question_id") == question_id]
    
    if min_score is not None:
        attempts = [a for a in attempts if (a.get("final_score") or 0) >= min_score]
    
    if max_score is not None:
        attempts = [a for a in attempts if (a.get("final_score") or 0) <= max_score]
    
    if start_date:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            attempts = [
                a for a in attempts 
                if a.get("created_at") and datetime.fromisoformat(str(a["created_at"]).replace("Z", "+00:00")) >= start_dt
            ]
        except:
            pass
    
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            attempts = [
                a for a in attempts 
                if a.get("created_at") and datetime.fromisoformat(str(a["created_at"]).replace("Z", "+00:00")) <= end_dt
            ]
        except:
            pass
    
    # Limit after filtering
    attempts = attempts[:limit]
    
    # Get total count
    total = await count_user_attempts(user_id)
    
    return {
        "attempts": attempts,
        "total": total,
        "returned": len(attempts),
        "offset": offset,
        "limit": limit
    }


@router.get("/attempts/{attempt_id}")
async def get_single_attempt(
    attempt_id: int,
    user_id: str = Depends(current_user_id)
):
    """
    Get detailed information about a single attempt.

    Includes full transcript, all scores, and LLM feedback.
    Only the attempt's owner can read it (others get 404, so IDs can't be probed).
    """
    attempt = await get_attempt_by_id(attempt_id)

    if not attempt or attempt.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    return attempt


@router.get("/attempts/question/{question_id}")
async def get_question_history(
    question_id: int,
    user_id: str = Depends(current_user_id),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    Get all attempts for a specific question.
    
    Useful for:
    - Seeing improvement on a particular question
    - Comparing different approaches
    - Understanding recurring issues
    """
    attempts = await get_user_attempts(user_id, limit=100)
    
    # Filter to specific question
    question_attempts = [
        a for a in attempts 
        if a.get("question_id") == question_id
    ][:limit]
    
    # Calculate stats
    if question_attempts:
        scores = [a.get("final_score", 0) or 0 for a in question_attempts]
        stats = {
            "total_attempts": len(question_attempts),
            "best_score": max(scores),
            "latest_score": scores[0] if scores else 0,
            "average_score": round(sum(scores) / len(scores), 1),
            "improvement": round(scores[0] - scores[-1], 1) if len(scores) > 1 else 0
        }
    else:
        stats = {
            "total_attempts": 0,
            "best_score": 0,
            "latest_score": 0,
            "average_score": 0,
            "improvement": 0
        }
    
    return {
        "question_id": question_id,
        "attempts": question_attempts,
        "stats": stats
    }


# ===========================================
# Skill Progress Endpoints
# ===========================================

@router.get("/skills/progress")
async def get_skill_progress(
    user_id: str = Depends(current_user_id)
):
    """
    Get skill-wise progress data for a user.
    
    Returns:
    - Current score per skill
    - Trend (improving/stable/declining)
    - Historical data points for charts
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        result = supabase.table("skill_progress")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        skills = result.data or []
        
        # Calculate overall improvement
        if skills:
            avg_current = sum(s.get("current_score", 0) for s in skills) / len(skills)
            avg_previous = sum(s.get("previous_score", 0) for s in skills) / len(skills)
            overall_trend = "improving" if avg_current > avg_previous else "stable" if avg_current == avg_previous else "declining"
        else:
            avg_current = 0
            avg_previous = 0
            overall_trend = "new_user"
        
        return {
            "skills": skills,
            "summary": {
                "average_current_score": round(avg_current, 1),
                "average_previous_score": round(avg_previous, 1),
                "overall_trend": overall_trend,
                "skills_tracked": len(skills)
            }
        }
    except Exception as e:
        logger.error(f"Failed to get skill progress: {e}")
        return {
            "skills": [],
            "summary": {
                "average_current_score": 0,
                "overall_trend": "unknown",
                "error": str(e)
            }
        }


@router.get("/skills/{skill_name}/history")
async def get_skill_history(
    skill_name: str,
    user_id: str = Depends(current_user_id),
    days: int = Query(default=30, ge=7, le=365)
):
    """
    Get historical data for a specific skill.
    
    Returns data points for charting skill progress over time.
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        result = supabase.table("skill_progress")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("skill_name", skill_name)\
            .single()\
            .execute()
        
        skill = result.data
        
        if not skill:
            return {
                "skill_name": skill_name,
                "history": [],
                "current_score": 0,
                "trend": "no_data"
            }
        
        # Parse score history
        score_history = skill.get("score_history", [])
        if isinstance(score_history, str):
            import json
            score_history = json.loads(score_history)
        
        # Filter to requested days
        cutoff = datetime.utcnow() - timedelta(days=days)
        filtered_history = [
            h for h in score_history
            if datetime.fromisoformat(h.get("date", "").replace("Z", "+00:00")) >= cutoff
        ] if score_history else []
        
        return {
            "skill_name": skill_name,
            "current_score": skill.get("current_score", 0),
            "best_score": skill.get("best_score", 0),
            "trend": skill.get("trend", "stable"),
            "trend_percentage": skill.get("trend_percentage", 0),
            "attempts_count": skill.get("attempts_count", 0),
            "history": filtered_history
        }
    except Exception as e:
        logger.error(f"Failed to get skill history: {e}")
        return {
            "skill_name": skill_name,
            "history": [],
            "error": str(e)
        }


# ===========================================
# Improvement Analytics Endpoints
# ===========================================

@router.get("/improvement")
async def get_improvement_analytics(
    user_id: str = Depends(current_user_id),
    period_days: int = Query(default=30, ge=7, le=365)
):
    """
    Get comprehensive improvement analytics.
    
    Includes:
    - Overall improvement percentage
    - Skill-wise trends
    - Practice consistency
    - Milestones achieved
    """
    from app.services.intelligent_question_engine import (
        analyze_user_performance,
        get_improvement_recommendations,
        calculate_improvement_delta
    )
    
    # Get attempts for analysis
    attempts = await get_user_attempts(user_id, limit=100)
    
    if not attempts:
        return {
            "status": "new_user",
            "message": "Start practicing to see your improvement!",
            "total_attempts": 0
        }
    
    # Analyze performance
    profile = await analyze_user_performance(user_id, attempts)
    
    # Get recommendations
    recommendations = get_improvement_recommendations(profile)
    
    # Split attempts for comparison
    cutoff = datetime.utcnow() - timedelta(days=period_days // 2)
    recent = []
    older = []
    
    for a in attempts:
        try:
            created_at = datetime.fromisoformat(str(a.get("created_at", "")).replace("Z", "+00:00"))
            if created_at >= cutoff:
                recent.append(a)
            else:
                older.append(a)
        except:
            recent.append(a)
    
    # Calculate improvement delta
    delta = calculate_improvement_delta(older, recent) if older and recent else {}
    
    # Calculate practice consistency
    practice_dates = set()
    for a in attempts:
        try:
            dt = datetime.fromisoformat(str(a.get("created_at", "")).replace("Z", "+00:00"))
            practice_dates.add(dt.date())
        except:
            pass
    
    consistency = {
        "total_practice_days": len(practice_dates),
        "period_days": period_days,
        "consistency_percentage": round(len(practice_dates) / period_days * 100, 1) if period_days > 0 else 0
    }
    
    return {
        "user_id": user_id,
        "period_days": period_days,
        "profile": profile.to_dict(),
        "improvement_delta": delta,
        "recommendations": recommendations,
        "consistency": consistency,
        "total_attempts": len(attempts)
    }


@router.get("/improvement/insights")
async def get_improvement_insights(
    user_id: str = Depends(current_user_id)
):
    """
    Get AI-generated improvement insights.
    
    Uses LLM to analyze patterns and provide personalized advice.
    """
    from app.services.dynamic_feedback_service import generate_improvement_insights
    
    # Get skill progress
    from app.models.supabase_client import get_supabase
    supabase = get_supabase()
    
    try:
        skill_result = supabase.table("skill_progress")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        
        skills = skill_result.data or []
    except:
        skills = []
    
    # Get recent attempts
    attempts = await get_user_attempts(user_id, limit=20)
    
    # Calculate historical averages
    if attempts:
        historical = {
            "content": sum(a.get("content_score", 0) or 0 for a in attempts) / len(attempts),
            "delivery": sum(a.get("delivery_score", 0) or 0 for a in attempts) / len(attempts),
            "communication": sum(a.get("communication_score", 0) or 0 for a in attempts) / len(attempts),
            "final": sum(a.get("final_score", 0) or 0 for a in attempts) / len(attempts),
        }
    else:
        historical = {}
    
    # Generate insights
    insights = await generate_improvement_insights(
        skill_progress=skills,
        recent_attempts=attempts,
        historical_averages=historical
    )
    
    return {
        "user_id": user_id,
        "insights": insights,
        "generated_at": datetime.utcnow().isoformat()
    }


# ===========================================
# Dashboard Stats Endpoint
# ===========================================

@router.get("/dashboard")
async def get_dashboard_data(
    user_id: str = Depends(current_user_id)
):
    """
    Get comprehensive dashboard data for a user.
    
    Combines:
    - Overall stats
    - Recent activity
    - Skill overview
    - Improvement highlights
    """
    # Get base stats
    stats = await get_dashboard_stats(user_id)
    
    # Get recent attempts
    recent_attempts = await get_user_attempts(user_id, limit=5)
    
    # Get skill progress
    from app.models.supabase_client import get_supabase
    supabase = get_supabase()
    
    try:
        skill_result = supabase.table("skill_progress")\
            .select("*")\
            .eq("user_id", user_id)\
            .execute()
        skills = skill_result.data or []
    except:
        skills = []
    
    # Format skills for dashboard
    skill_summary = [
        {
            "name": s.get("skill_name", ""),
            "score": s.get("current_score", 0),
            "trend": s.get("trend", "stable"),
            "trend_value": s.get("trend_percentage", 0)
        }
        for s in skills
    ]
    
    # Calculate streaks and milestones
    attempts = await get_user_attempts(user_id, limit=100)
    
    milestones = []
    if len(attempts) >= 10:
        milestones.append({"title": "10 Attempts", "achieved": True})
    if len(attempts) >= 50:
        milestones.append({"title": "50 Attempts", "achieved": True})
    if any(a.get("final_score", 0) >= 90 for a in attempts):
        milestones.append({"title": "First 90+ Score", "achieved": True})
    
    return {
        "user_id": user_id,
        "stats": stats,
        "recent_attempts": recent_attempts,
        "skill_summary": skill_summary,
        "milestones": milestones,
        "last_updated": datetime.utcnow().isoformat()
    }
