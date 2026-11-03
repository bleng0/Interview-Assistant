"""
AI Interview Assistant - Reports API

Endpoints for:
- Generating interview reports
- Downloading PDF reports
- Session summary reports

Author: AI Interview Assistant Team
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Response, Depends
from fastapi.responses import StreamingResponse
import io

from app.logging_config import get_logger
from app.services.auth_service import current_user_id
from app.services.report_generation_service import (
    generate_interview_report_data,
    generate_pdf_html,
    generate_pdf_bytes,
    save_report_to_database,
    get_user_reports
)
from app.services.dynamic_feedback_service import generate_consolidated_session_feedback
from app.services.supabase_db import get_user_attempts

logger = get_logger(__name__)

router = APIRouter(prefix="/reports", tags=["Reports"])


# ===========================================
# Report Generation Endpoints
# ===========================================

@router.post("/generate")
async def generate_report(
    user_id: str = Depends(current_user_id),
    session_id: Optional[str] = Query(default=None, description="Session ID for session report"),
    attempt_ids: Optional[str] = Query(default=None, description="Comma-separated attempt IDs"),
    report_type: str = Query(default="session", description="Type: session, custom, summary")
):
    """
    Generate an interview feedback report.
    
    Supports multiple report types:
    - session: Report for a complete interview session
    - custom: Report for selected attempts
    - summary: Overall performance summary
    
    Returns report data that can be:
    1. Displayed in UI
    2. Converted to PDF on client
    3. Downloaded as PDF (if server-side PDF generation available)
    """
    logger.info(f"Generating {report_type} report for user {user_id}")

    # A report can only be attached to the caller's own session
    if session_id:
        from app.services.supabase_db import get_session_by_id
        session = await get_session_by_id(session_id)
        if not session or session.get("user_id") != user_id:
            raise HTTPException(status_code=404, detail="Session not found")

    # Get attempts for the report
    if attempt_ids:
        # Get specific attempts
        ids = [int(id.strip()) for id in attempt_ids.split(",") if id.strip().isdigit()]
        all_attempts = await get_user_attempts(user_id, limit=100)
        attempts = [a for a in all_attempts if a.get("id") in ids]
    else:
        # Get recent attempts (or session-specific if session_id provided)
        attempts = await get_user_attempts(user_id, limit=10)
    
    if not attempts:
        raise HTTPException(
            status_code=404,
            detail="No attempts found for report generation"
        )
    
    # Build session data
    session_data = {
        "domain": attempts[0].get("domain", "General") if attempts else "General",
        "job_description": attempts[0].get("job_description", "") if attempts else "",
        "job_title": "",
        "session_id": session_id
    }
    
    # Generate consolidated feedback
    consolidated = await generate_consolidated_session_feedback(
        session_data=session_data,
        attempts=attempts,
        user_history=None  # Could fetch from dashboard stats
    )
    
    # Generate report data
    report_data = generate_interview_report_data(
        session_data=session_data,
        attempts=attempts,
        consolidated_feedback=consolidated,
        user_info=None  # Could fetch user profile
    )
    
    # Save report to database
    if user_id and session_id:
        await save_report_to_database(
            user_id=user_id,
            session_id=session_id,
            report_data=report_data
        )
    
    return {
        "success": True,
        "report": report_data,
        "pdf_available": True,  # Client can request PDF
        "generated_at": datetime.utcnow().isoformat()
    }


@router.get("/download/{report_id}")
async def download_report_pdf(
    report_id: str,
    user_id: str = Depends(current_user_id)
):
    """
    Download a report as PDF.
    
    Generates PDF from stored report data.
    Falls back to returning HTML if PDF generation fails.
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        result = supabase.table("interview_reports")\
            .select("*")\
            .eq("id", report_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        report = result.data
    except:
        report = None
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Parse report data
    report_data = report.get("report_data", {})
    if isinstance(report_data, str):
        import json
        report_data = json.loads(report_data)
    
    # Try to generate PDF
    pdf_bytes = await generate_pdf_bytes(report_data)
    
    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=interview_report_{report_id[:8]}.pdf"
            }
        )
    else:
        # Return HTML if PDF generation not available
        html = generate_pdf_html(report_data)
        return Response(
            content=html,
            media_type="text/html",
            headers={
                "Content-Disposition": f"attachment; filename=interview_report_{report_id[:8]}.html"
            }
        )


@router.post("/generate-pdf")
async def generate_pdf_from_data(
    user_id: str = Depends(current_user_id),
    attempt_ids: Optional[str] = Query(default=None, description="Comma-separated attempt IDs")
):
    """
    Generate PDF directly from attempt data.
    
    Use this when you want an immediate PDF without saving the report.
    """
    # Get attempts
    if attempt_ids:
        ids = [int(id.strip()) for id in attempt_ids.split(",") if id.strip().isdigit()]
        all_attempts = await get_user_attempts(user_id, limit=100)
        attempts = [a for a in all_attempts if a.get("id") in ids]
    else:
        attempts = await get_user_attempts(user_id, limit=10)
    
    if not attempts:
        raise HTTPException(status_code=404, detail="No attempts found")
    
    # Build session data
    session_data = {
        "domain": "General",
        "job_description": attempts[0].get("job_description", "") if attempts else ""
    }
    
    # Generate consolidated feedback
    consolidated = await generate_consolidated_session_feedback(
        session_data=session_data,
        attempts=attempts
    )
    
    # Generate report data
    report_data = generate_interview_report_data(
        session_data=session_data,
        attempts=attempts,
        consolidated_feedback=consolidated
    )
    
    # Generate PDF
    pdf_bytes = await generate_pdf_bytes(report_data)
    
    if pdf_bytes:
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=interview_report_{datetime.now().strftime('%Y%m%d')}.pdf"
            }
        )
    else:
        # Return HTML for client-side PDF generation
        html = generate_pdf_html(report_data)
        return {
            "pdf_available": False,
            "html": html,
            "message": "PDF library not available. Use html2pdf on client."
        }


# ===========================================
# Report History Endpoints
# ===========================================

@router.get("/list")
async def list_user_reports(
    user_id: str = Depends(current_user_id),
    limit: int = Query(default=10, ge=1, le=50)
):
    """
    List all reports for a user.
    
    Returns report metadata without full content.
    """
    reports = await get_user_reports(user_id, limit=limit)
    
    # Strip large fields for list view
    report_list = []
    for r in reports:
        report_list.append({
            "id": r.get("id"),
            "report_type": r.get("report_type"),
            "report_title": r.get("report_title"),
            "created_at": r.get("created_at"),
            "has_pdf": bool(r.get("pdf_file_url"))
        })
    
    return {
        "reports": report_list,
        "total": len(report_list)
    }


@router.get("/{report_id}")
async def get_report_details(
    report_id: str,
    user_id: str = Depends(current_user_id)
):
    """
    Get full report details.
    
    Returns complete report data including all feedback sections.
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        result = supabase.table("interview_reports")\
            .select("*")\
            .eq("id", report_id)\
            .eq("user_id", user_id)\
            .single()\
            .execute()
        
        report = result.data
    except:
        report = None
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    
    # Parse report data if string
    report_data = report.get("report_data", {})
    if isinstance(report_data, str):
        import json
        report_data = json.loads(report_data)
    
    return {
        "id": report.get("id"),
        "report_type": report.get("report_type"),
        "report_title": report.get("report_title"),
        "created_at": report.get("created_at"),
        "report_data": report_data,
        "pdf_available": bool(report.get("pdf_file_url")),
        "pdf_url": report.get("pdf_file_url")
    }


# ===========================================
# Quick Summary Endpoint
# ===========================================

@router.get("/summary/quick")
async def get_quick_summary(
    user_id: str = Depends(current_user_id),
    days: int = Query(default=7, ge=1, le=90)
):
    """
    Get a quick performance summary for dashboard display.
    
    Lightweight endpoint for showing key metrics.
    """
    from datetime import timedelta
    
    attempts = await get_user_attempts(user_id, limit=100)
    
    if not attempts:
        return {
            "has_data": False,
            "message": "Start practicing to see your summary!"
        }
    
    # Filter to period
    cutoff = datetime.utcnow() - timedelta(days=days)
    period_attempts = []
    
    for a in attempts:
        try:
            created_at = datetime.fromisoformat(str(a.get("created_at", "")).replace("Z", "+00:00"))
            if created_at >= cutoff:
                period_attempts.append(a)
        except:
            pass
    
    if not period_attempts:
        return {
            "has_data": False,
            "message": f"No practice sessions in the last {days} days"
        }
    
    # Calculate summary stats
    def safe_avg(field):
        values = [a.get(field, 0) or 0 for a in period_attempts]
        return round(sum(values) / len(values), 1) if values else 0
    
    # Find best and worst
    sorted_by_score = sorted(period_attempts, key=lambda x: x.get("final_score", 0) or 0, reverse=True)
    
    return {
        "has_data": True,
        "period_days": days,
        "attempts_count": len(period_attempts),
        "average_score": safe_avg("final_score"),
        "best_score": sorted_by_score[0].get("final_score", 0) if sorted_by_score else 0,
        "worst_score": sorted_by_score[-1].get("final_score", 0) if sorted_by_score else 0,
        "skill_averages": {
            "content": safe_avg("content_score"),
            "delivery": safe_avg("delivery_score"),
            "communication": safe_avg("communication_score"),
            "voice": safe_avg("voice_score"),
            "confidence": safe_avg("confidence_score"),
            "structure": safe_avg("structure_score")
        },
        "practice_streak": len(set(
            a.get("created_at", "")[:10] for a in period_attempts if a.get("created_at")
        ))
    }
