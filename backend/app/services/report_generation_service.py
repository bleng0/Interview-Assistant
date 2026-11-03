"""
AI Interview Assistant - PDF Report Generation Service

Generates professional interview feedback reports in PDF format.

Features:
- Executive summary
- Question-by-question breakdown
- Score visualizations
- Improvement recommendations
- STAR method analysis
- Skill progress charts

Author: AI Interview Assistant Team
"""

import asyncio
import html as html_lib
import io
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from app.logging_config import get_logger

logger = get_logger(__name__)


# ===========================================
# Report Data Structures
# ===========================================

@dataclass
class ReportSection:
    """A section in the PDF report."""
    title: str
    content: Any
    section_type: str  # text, table, chart, scores


@dataclass
class InterviewReport:
    """Complete interview report data."""
    title: str
    generated_at: datetime
    user_name: str
    domain: str
    job_title: Optional[str]
    
    # Summary
    overall_score: float
    total_questions: int
    session_duration: float
    
    # Scores
    content_score: float
    delivery_score: float
    communication_score: float
    voice_score: float
    confidence_score: float
    structure_score: float
    
    # Analysis
    strengths: List[str]
    improvements: List[str]
    
    # Per-question data
    questions: List[Dict[str, Any]]
    
    # Recommendations
    action_plan: List[Dict[str, str]]
    
    # Metadata
    session_id: Optional[str] = None


# ===========================================
# Report Generation Functions
# ===========================================

def generate_interview_report_data(
    session_data: Dict[str, Any],
    attempts: List[Dict[str, Any]],
    consolidated_feedback: Dict[str, Any],
    user_info: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Generate complete report data structure for PDF generation.
    
    This creates a JSON structure that can be:
    1. Sent to frontend for client-side PDF generation
    2. Used by a PDF library on the backend
    3. Stored for later retrieval
    
    Args:
        session_data: Session configuration
        attempts: All attempts in the session
        consolidated_feedback: LLM-generated consolidated feedback
        user_info: Optional user profile data
    
    Returns:
        Dict with complete report data ready for PDF generation
    """
    logger.info(f"Generating report data for session with {len(attempts)} attempts")
    
    # Calculate aggregate scores
    def safe_avg(field):
        values = [a.get(field, 0) or 0 for a in attempts]
        return round(sum(values) / len(values), 1) if values else 0
    
    # Build question breakdown
    questions_data = []
    for i, attempt in enumerate(attempts, 1):
        llm_feedback = attempt.get("llm_feedback", {})
        if isinstance(llm_feedback, str):
            try:
                llm_feedback = json.loads(llm_feedback)
            except:
                llm_feedback = {}
        
        questions_data.append({
            "number": i,
            "question": attempt.get("question_text", f"Question {i}"),
            "transcript_excerpt": (attempt.get("transcript", "")[:200] + "...") if len(attempt.get("transcript", "")) > 200 else attempt.get("transcript", ""),
            "duration_seconds": attempt.get("duration_seconds", 0),
            "scores": {
                "content": attempt.get("content_score", 0),
                "delivery": attempt.get("delivery_score", 0),
                "communication": attempt.get("communication_score", 0),
                "voice": attempt.get("voice_score", 0),
                "confidence": attempt.get("confidence_score", 0),
                "structure": attempt.get("structure_score", 0),
                "final": attempt.get("final_score", 0),
            },
            "feedback_summary": llm_feedback.get("overall_assessment", ""),
            "strengths": llm_feedback.get("strengths", [])[:2],
            "improvements": llm_feedback.get("improvement_areas", [])[:2],
            "star_analysis": llm_feedback.get("star_method_breakdown", {}),
        })
    
    # Build report structure
    report = {
        "metadata": {
            "report_id": f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
            "generated_at": datetime.utcnow().isoformat(),
            "version": "2.0",
            "type": "interview_session"
        },
        
        "header": {
            "title": "Interview Practice Report",
            "subtitle": f"{session_data.get('domain', 'General')} Interview Session",
            "user_name": user_info.get("full_name", "Anonymous") if user_info else "Anonymous",
            "user_email": user_info.get("email", "") if user_info else "",
            "date": datetime.utcnow().strftime("%B %d, %Y"),
            "job_title": session_data.get("job_title", ""),
        },
        
        "executive_summary": {
            "overall_score": safe_avg("final_score"),
            "total_questions": len(attempts),
            "session_duration_minutes": round(sum(a.get("duration_seconds", 0) for a in attempts) / 60, 1),
            "assessment": consolidated_feedback.get("session_summary", "Session completed successfully."),
            "interview_readiness": consolidated_feedback.get("interview_readiness", {
                "score": safe_avg("final_score"),
                "assessment": "Needs Practice" if safe_avg("final_score") < 70 else "Ready",
                "reasoning": "Based on overall performance across all questions."
            })
        },
        
        "score_breakdown": {
            "content": {
                "score": safe_avg("content_score"),
                "label": "Content & Relevance",
                "description": "How well answers addressed the questions",
                "weight": "30%"
            },
            "delivery": {
                "score": safe_avg("delivery_score"),
                "label": "Delivery & Pace",
                "description": "Speaking rate, filler words, pauses",
                "weight": "15%"
            },
            "communication": {
                "score": safe_avg("communication_score"),
                "label": "Communication",
                "description": "Grammar, vocabulary, clarity",
                "weight": "15%"
            },
            "voice": {
                "score": safe_avg("voice_score"),
                "label": "Voice Quality",
                "description": "Pitch variation, energy, rhythm",
                "weight": "15%"
            },
            "confidence": {
                "score": safe_avg("confidence_score"),
                "label": "Confidence",
                "description": "Assertiveness and composure",
                "weight": "15%"
            },
            "structure": {
                "score": safe_avg("structure_score"),
                "label": "Answer Structure",
                "description": "STAR method, organization",
                "weight": "10%"
            }
        },
        
        "performance_profile": consolidated_feedback.get("performance_profile", {
            "strongest_skill": "Unable to determine",
            "weakest_skill": "Unable to determine",
            "consistency_rating": "Varies"
        }),
        
        "questions_analysis": questions_data,
        
        "strengths_summary": consolidated_feedback.get("top_strengths", [
            "Completed all questions",
            "Demonstrated willingness to practice"
        ]),
        
        "improvement_priorities": consolidated_feedback.get("priority_improvements", [
            {
                "area": "Overall Practice",
                "current_level": "Developing",
                "target_level": "Proficient",
                "action_plan": "Continue practicing regularly with focus on weak areas"
            }
        ]),
        
        "action_plan": {
            "immediate": [
                "Review this feedback report thoroughly",
                "Practice the weakest question again",
                "Focus on STAR method structure"
            ],
            "short_term": [
                "Complete 3 more practice sessions this week",
                "Work on identified weak areas",
                "Record yourself and review delivery"
            ],
            "ongoing": [
                "Regular practice (3-5 times per week)",
                "Track progress over time",
                "Expand to new question types"
            ]
        },
        
        "recommended_practice": consolidated_feedback.get("recommended_practice", [
            {
                "focus_area": "General Practice",
                "exercise": "Answer 5 behavioral questions using STAR method",
                "frequency": "Daily"
            }
        ]),
        
        "next_steps": consolidated_feedback.get("next_session_focus", "Continue practicing with varied question types"),
        
        "footer": {
            "disclaimer": "This report is generated by AI for practice purposes. Actual interview performance may vary.",
            "powered_by": "AI Interview Assistant",
            "support_link": "https://example.com/help"
        }
    }
    
    return report


def generate_pdf_html(report_data: Dict[str, Any]) -> str:
    """
    Generate HTML representation of the report for PDF conversion.
    
    This HTML can be converted to PDF using:
    - WeasyPrint (Python)
    - Puppeteer (Node.js)
    - Client-side libraries (jsPDF, html2pdf)
    
    Args:
        report_data: Complete report data dictionary
    
    Returns:
        HTML string ready for PDF conversion
    """
    
    # All text in the report can contain user- or LLM-provided content
    # (questions, transcripts, feedback), so escape it before building HTML.
    def esc(value: Any) -> str:
        return html_lib.escape(str(value), quote=True)
    
    def num(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
    
    # Score color helper
    def score_color(score: float) -> str:
        if score >= 80:
            return "#22c55e"  # Green
        elif score >= 60:
            return "#eab308"  # Yellow
        else:
            return "#ef4444"  # Red
    
    # Build questions HTML
    questions_html = ""
    for q in report_data.get("questions_analysis", []):
        star = q.get("star_analysis", {})
        star_html = ""
        for part in ["situation", "task", "action", "result"]:
            part_data = star.get(part, {})
            present = "✓" if part_data.get("present") else "✗"
            color = "#22c55e" if part_data.get("present") else "#ef4444"
            star_html += f'<span style="color: {color}; margin-right: 10px;">{part.capitalize()}: {present}</span>'
        
        questions_html += f"""
        <div class="question-card" style="margin-bottom: 20px; padding: 15px; border: 1px solid #e5e7eb; border-radius: 8px;">
            <h4 style="margin: 0 0 10px 0; color: #374151;">Question {esc(q.get('number', ''))}</h4>
            <p style="font-style: italic; color: #6b7280; margin-bottom: 10px;">"{esc(str(q.get('question', ''))[:100])}..."</p>
            
            <div style="display: flex; gap: 20px; margin-bottom: 10px;">
                <div>
                    <strong>Score:</strong> 
                    <span style="font-size: 18px; font-weight: bold; color: {score_color(num(q.get('scores', {}).get('final', 0)))};">
                        {num(q.get('scores', {}).get('final', 0)):g}/100
                    </span>
                </div>
                <div>
                    <strong>Duration:</strong> {round(num(q.get('duration_seconds', 0)))}s
                </div>
            </div>
            
            <div style="margin-bottom: 10px;">
                <strong>STAR Method:</strong> {star_html}
            </div>
            
            <p style="color: #374151;">{esc(str(q.get('feedback_summary', ''))[:200])}</p>
        </div>
        """
    
    # Build scores HTML
    scores = report_data.get("score_breakdown", {})
    scores_html = ""
    for key, data in scores.items():
        score = num(data.get("score", 0))
        scores_html += f"""
        <div style="margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                <span>{esc(data.get('label', key))}</span>
                <span style="font-weight: bold; color: {score_color(score)};">{score:g}/100</span>
            </div>
            <div style="background: #e5e7eb; height: 8px; border-radius: 4px;">
                <div style="background: {score_color(score)}; height: 100%; width: {max(0.0, min(score, 100.0)):g}%; border-radius: 4px;"></div>
            </div>
        </div>
        """
    
    # Build improvements HTML
    improvements_html = ""
    for imp in report_data.get("improvement_priorities", []):
        improvements_html += f"""
        <div style="margin-bottom: 15px; padding: 10px; background: #fef3c7; border-radius: 6px;">
            <strong>{esc(imp.get('area', 'Focus Area'))}</strong>
            <p style="margin: 5px 0;">{esc(imp.get('action_plan', ''))}</p>
        </div>
        """
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Interview Report</title>
    <style>
        @page {{
            size: A4;
            margin: 2cm;
        }}
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #1f2937;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid #3b82f6;
            padding-bottom: 20px;
            margin-bottom: 30px;
        }}
        .header h1 {{
            margin: 0;
            color: #1e40af;
        }}
        .header .subtitle {{
            color: #6b7280;
            font-size: 14px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            color: #1e40af;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 5px;
            margin-bottom: 15px;
        }}
        .overall-score {{
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #3b82f6, #8b5cf6);
            border-radius: 12px;
            color: white;
            margin-bottom: 30px;
        }}
        .overall-score .score {{
            font-size: 48px;
            font-weight: bold;
        }}
        .grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        .card {{
            padding: 15px;
            border: 1px solid #e5e7eb;
            border-radius: 8px;
        }}
        .strengths {{
            background: #d1fae5;
        }}
        .improvements {{
            background: #fef3c7;
        }}
        ul {{
            margin: 0;
            padding-left: 20px;
        }}
        li {{
            margin-bottom: 5px;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            text-align: center;
            font-size: 12px;
            color: #9ca3af;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{esc(report_data.get('header', {}).get('title', 'Interview Report'))}</h1>
        <p class="subtitle">{esc(report_data.get('header', {}).get('subtitle', ''))}</p>
        <p>Prepared for: <strong>{esc(report_data.get('header', {}).get('user_name', 'Anonymous'))}</strong></p>
        <p>Date: {esc(report_data.get('header', {}).get('date', datetime.now().strftime('%B %d, %Y')))}</p>
    </div>
    
    <div class="overall-score">
        <div class="score">{num(report_data.get('executive_summary', {}).get('overall_score', 0)):g}/100</div>
        <div>Overall Session Score</div>
        <div style="margin-top: 10px; font-size: 14px;">
            {esc(report_data.get('executive_summary', {}).get('total_questions', 0))} Questions • 
            {esc(report_data.get('executive_summary', {}).get('session_duration_minutes', 0))} Minutes
        </div>
    </div>
    
    <div class="section">
        <h2 class="section-title">Executive Summary</h2>
        <p>{esc(report_data.get('executive_summary', {}).get('assessment', ''))}</p>
        
        <div style="margin-top: 15px; padding: 15px; background: #f3f4f6; border-radius: 8px;">
            <strong>Interview Readiness: </strong>
            <span style="color: {score_color(num(report_data.get('executive_summary', {}).get('interview_readiness', {}).get('score', 0)))};">
                {esc(report_data.get('executive_summary', {}).get('interview_readiness', {}).get('assessment', 'Unknown'))}
            </span>
        </div>
    </div>
    
    <div class="section">
        <h2 class="section-title">Score Breakdown</h2>
        {scores_html}
    </div>
    
    <div class="section grid">
        <div class="card strengths">
            <h3 style="margin-top: 0; color: #047857;">Strengths</h3>
            <ul>
                {''.join(f'<li>{esc(s)}</li>' for s in report_data.get('strengths_summary', ['Good effort'])[:5])}
            </ul>
        </div>
        <div class="card improvements">
            <h3 style="margin-top: 0; color: #92400e;">Areas for Improvement</h3>
            {improvements_html or '<p>Keep practicing to identify specific areas</p>'}
        </div>
    </div>
    
    <div class="section">
        <h2 class="section-title">Question-by-Question Analysis</h2>
        {questions_html}
    </div>
    
    <div class="section">
        <h2 class="section-title">Action Plan</h2>
        <div class="grid">
            <div class="card">
                <h4 style="margin-top: 0;">Immediate Actions</h4>
                <ul>
                    {''.join(f'<li>{esc(a)}</li>' for a in report_data.get('action_plan', {}).get('immediate', []))}
                </ul>
            </div>
            <div class="card">
                <h4 style="margin-top: 0;">This Week</h4>
                <ul>
                    {''.join(f'<li>{esc(a)}</li>' for a in report_data.get('action_plan', {}).get('short_term', []))}
                </ul>
            </div>
        </div>
    </div>
    
    <div class="footer">
        <p>{esc(report_data.get('footer', {}).get('disclaimer', ''))}</p>
        <p>Generated by {esc(report_data.get('footer', {}).get('powered_by', 'AI Interview Assistant'))}</p>
    </div>
</body>
</html>
    """
    
    return html


async def generate_pdf_bytes(report_data: Dict[str, Any]) -> Optional[bytes]:
    """
    Generate actual PDF bytes from report data.
    
    Tries multiple PDF generation methods:
    1. WeasyPrint (if installed)
    2. ReportLab (if installed)
    3. Returns None (client-side generation needed)
    
    Args:
        report_data: Complete report data dictionary
    
    Returns:
        PDF as bytes, or None if no PDF library available
    """
    html = generate_pdf_html(report_data)
    
    # The report HTML is self-contained. Refuse every external resource so a
    # URL that slips into report text can't make the server fetch it (SSRF).
    def _block_url_fetch(url, *args, **kwargs):
        raise ValueError(f"External resource blocked in PDF: {url}")
    
    def _block_link_callback(uri, rel):
        return ""
    
    # Try WeasyPrint first
    try:
        from weasyprint import HTML
        pdf_bytes = await asyncio.to_thread(
            lambda: HTML(string=html, url_fetcher=_block_url_fetch).write_pdf()
        )
        logger.info("PDF generated with WeasyPrint")
        return pdf_bytes
    except ImportError:
        logger.debug("WeasyPrint not installed")
    except Exception as e:
        logger.warning(f"WeasyPrint failed: {e}")
    
    # Try xhtml2pdf as fallback
    try:
        from xhtml2pdf import pisa
        result = io.BytesIO()
        pisa_status = await asyncio.to_thread(
            pisa.CreatePDF, io.StringIO(html), dest=result, link_callback=_block_link_callback
        )
        if not pisa_status.err:
            logger.info("PDF generated with xhtml2pdf")
            return result.getvalue()
    except ImportError:
        logger.debug("xhtml2pdf not installed")
    except Exception as e:
        logger.warning(f"xhtml2pdf failed: {e}")
    
    logger.info("No PDF library available - client-side generation needed")
    return None


# ===========================================
# Report Storage and Retrieval
# ===========================================

async def save_report_to_database(
    user_id: str,
    session_id: str,
    report_data: Dict[str, Any],
    pdf_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Save generated report to database.
    
    Args:
        user_id: User ID
        session_id: Session ID
        report_data: Complete report data
        pdf_url: Optional URL to stored PDF file
    
    Returns:
        Created report record
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    data = {
        "user_id": user_id,
        "session_id": session_id,
        "report_type": "session",
        "report_title": report_data.get("header", {}).get("title", "Interview Report"),
        "report_data": json.dumps(report_data),
        "pdf_file_url": pdf_url,
        "status": "generated",
        "created_at": datetime.utcnow().isoformat()
    }
    
    try:
        result = supabase.table("interview_reports").insert(data).execute()
        return result.data[0] if result.data else data
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
        return {"error": str(e), **data}


async def get_user_reports(
    user_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get user's report history.
    """
    from app.models.supabase_client import get_supabase
    
    supabase = get_supabase()
    
    try:
        result = supabase.table("interview_reports")\
            .select("*")\
            .eq("user_id", user_id)\
            .order("created_at", desc=True)\
            .limit(limit)\
            .execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get reports: {e}")
        return []
