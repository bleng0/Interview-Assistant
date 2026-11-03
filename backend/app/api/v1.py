"""
AI Interview Feedback MVP - API v1 Endpoints

This module defines all the REST API endpoints for the core interview functionality.
It handles request validation, orchestrates service calls, and returns responses.

===========================================
ENDPOINT SUMMARY
===========================================

Health & Status:
    GET  /health              - API health check
    GET  /llm/status          - LLM connection status
    GET  /llm/keys/health     - Multi-key rotation system health status

Questions:
    GET  /questions           - List all interview questions
    GET  /questions/random    - Get random questions by domain
    POST /questions/smart     - Get intelligent, personalized questions
    POST /questions/analyze-jd - Analyze job description
    POST /questions/validate_custom - Validate custom question format

Resume:
    POST /upload_resume       - Upload and analyze resume
    POST /analyze_resume_for_domain - Domain-specific resume analysis

Interview:
    POST /upload_audio        - Upload audio and get feedback
    POST /submit_answer       - Submit answer for analysis

Data:
    GET  /domains             - List available interview domains
    GET  /attempts            - Get user's attempt history

===========================================
Author: AI Interview Assistant Team
===========================================
"""

import os
import uuid
import json
import random
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Query

from app.config import (
    UPLOAD_DIR, 
    ALLOWED_RESUME_EXTENSIONS, 
    ALLOWED_AUDIO_EXTENSIONS,
    MAX_RESUME_SIZE,
    MAX_AUDIO_SIZE
)
from app.models.schemas import (
    HealthResponse,
    Question,
    QuestionsResponse,
    ResumeAnalysisResponse,
    AudioFeedbackResponse,
    MLScores
)
from app.services.resume_service import extract_text_from_resume, compare_resume_with_jd
from app.services.audio_service import get_audio_duration, convert_audio_if_needed
from app.services.transcript_service import transcribe_audio
from app.services.ml_engine import score_answer, score_resume, score_answer_by_keywords
from app.services.storage_service import upload_resume_file, upload_resume_bytes, upload_audio_file
from app.logging_config import get_logger
from app.services.auth_service import require_auth, require_admin, ensure_same_user

logger = get_logger(__name__)

# Note: Test artifact functionality removed - use production mode only

from app.services.llm_bridge import generate_answer_feedback, generate_resume_feedback, get_llm_working_status
from app.services.supabase_db import save_resume_analysis
from app.services.question_service import (
    get_questions_for_interview, 
    analyze_job_description,
    parse_questions_from_json,
    parse_questions_from_csv,
    get_all_questions,
    get_question_by_id
)
from app.services.intelligent_question_engine import (
    select_questions_intelligently,
    analyze_user_performance
)


# ===========================================
# Create API Router
# ===========================================

router = APIRouter()


# ===========================================
# Helper Functions
# ===========================================

def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return os.path.splitext(filename)[1].lower()


def generate_unique_filename(original_filename: str) -> str:
    """Generate a unique filename to prevent collisions."""
    ext = get_file_extension(original_filename)
    unique_id = uuid.uuid4().hex[:8]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{timestamp}_{unique_id}{ext}"


def load_questions() -> List[dict]:
    """
    Load interview questions from the JSON data file.
    
    This function reads the centralized questions data file which contains:
    - Question ID and text
    - Ideal answer (reference for content scoring)
    - Category (behavioral, technical, situational, etc.)
    - Keywords for keyword-based scoring (if applicable)
    
    Returns:
        List[dict]: List of question objects with full structure:
            [{
                "id": int,
                "question": str,
                "ideal_answer": str,
                "category": str,
                "keywords": List[str] (optional)
            }, ...]
    
    Raises:
        Returns default fallback questions if file not found (graceful degradation)
    """
    questions_path = os.path.join(
        os.path.dirname(__file__), 
        "..", 
        "data", 
        "questions.json"
    )
    
    try:
        logger.debug(f"Loading questions from {questions_path}")
        with open(questions_path, "r", encoding="utf-8") as f:
            questions = json.load(f)
            logger.info(f"✓ Loaded {len(questions)} questions from file")
            return questions
    except FileNotFoundError:
        logger.warning(f"Questions file not found at {questions_path}, using fallback questions")
        # Return default questions if file not found
        return [
            {
                "id": 1,
                "question": "Tell me about yourself.",
                "ideal_answer": "I am a professional with experience in..."
            }
        ]


# ===========================================
# Health Check Endpoint
# ===========================================

@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    
    Returns the health status of the API, useful for monitoring
    and load balancer health checks.
    
    Returns:
        HealthResponse: Status object indicating API health
    """
    logger.debug("Health check requested")
    return HealthResponse(
        status="healthy",
        timestamp=datetime.now().isoformat(),
        version="1.0.0"
    )


@router.get("/stats/public")
async def get_public_stats():
    """
    Get public platform statistics for the landing page.
    
    Returns real-time counts from the database:
    - Total registered users
    - Total interview sessions
    - Total questions in the pool
    - Total attempts made
    
    This endpoint is unauthenticated and cached for performance.
    """
    from app.models.supabase_client import get_supabase
    
    try:
        supabase = get_supabase()
        
        # Get total users count
        users_result = supabase.table("users").select("id", count="exact").execute()
        total_users = users_result.count if users_result.count else 0
        
        # Get total sessions count
        sessions_result = supabase.table("interview_sessions").select("id", count="exact").execute()
        total_sessions = sessions_result.count if sessions_result.count else 0
        
        # Get total questions count
        questions_result = supabase.table("questions").select("id", count="exact").execute()
        total_questions = questions_result.count if questions_result.count else 0
        
        # Get total attempts count
        attempts_result = supabase.table("attempts").select("id", count="exact").execute()
        total_attempts = attempts_result.count if attempts_result.count else 0
        
        return {
            "total_users": total_users,
            "total_sessions": total_sessions,
            "total_questions": total_questions,
            "total_attempts": total_attempts,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error fetching public stats: {e}")
        # Return fallback values if database is unavailable
        return {
            "total_users": 0,
            "total_sessions": 0,
            "total_questions": 25,
            "total_attempts": 0,
            "timestamp": datetime.now().isoformat(),
            "fallback": True
        }



@router.get("/llm/status")
async def get_llm_status():
    """
    Get LLM (Gemini) working status.
    
    Returns whether the LLM API is configured and working properly.
    Frontend should check this to show appropriate error messages.
    
    Returns:
        dict: LLM status including is_working, last_error, provider
    """
    # Report the status recorded by real LLM calls. This public endpoint never
    # makes an LLM call itself, so it can't be used to burn API quota.
    status = get_llm_working_status()
    
    return {
        "is_working": status.get("is_working"),
        "last_error": "LLM request failed" if status.get("last_error") else None,
        "provider": status.get("provider"),
        "last_check": status.get("last_check")
    }


@router.get("/llm/keys/health", dependencies=[Depends(require_admin)])
async def get_keys_health():
    """
    Get health status of all configured Gemini API keys.
    
    Returns detailed information about the key rotation system:
    - Number of keys configured
    - Health status of each key
    - Quota exhaustion and cooldown status
    - Usage statistics
    - Next rotation info
    
    This endpoint is useful for monitoring and debugging the multi-key rotation system.
    
    Returns:
        dict: Complete health status of all keys and rotation system
    """
    from app.services.key_manager import get_key_manager
    
    try:
        key_manager = get_key_manager()
        health_info = key_manager.check_all_keys_health()
        
        return {
            "success": True,
            "rotation_enabled": True,
            **health_info,
            "checked_at": datetime.now().isoformat()
        }
    
    except RuntimeError as e:
        if "not initialized" in str(e):
            # Single key mode
            from app.config import settings
            return {
                "success": True,
                "rotation_enabled": False,
                "message": "Single key mode - rotation not enabled",
                "configured_keys": 1 if settings.llm_api_key else 0,
                "tip": "Add LLM_API_KEY_2, LLM_API_KEY_3, etc. to .env to enable rotation",
                "checked_at": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=500, detail=str(e))


# ===========================================
# Questions Endpoint
# ===========================================

@router.get("/questions", response_model=QuestionsResponse)
async def get_questions():
    """
    Get all available interview questions.
    
    Returns the list of interview questions that users can practice with.
    Questions are loaded from the questions.json data file.
    
    Returns:
        QuestionsResponse: List of questions with IDs and ideal answers
    """
    questions_data = load_questions()
    questions = [
        Question(
            id=q["id"],
            question=q["question"],
            ideal_answer=q["ideal_answer"],
            category=q.get("category", "General")
        )
        for q in questions_data
    ]
    return QuestionsResponse(questions=questions, total=len(questions))


@router.get("/domains")
async def get_domains():
    """
    Get all available interview domains.
    
    Returns:
        dict: List of available domains for interview practice
    """
    domains = [
        {"id": "management", "name": "Management", "description": "Leadership, strategy, team management"},
        {"id": "software_engineering", "name": "Software Engineering", "description": "Coding, algorithms, system design"},
        {"id": "finance", "name": "Finance", "description": "Financial analysis, markets, risk management"},
        {"id": "teaching", "name": "Teaching", "description": "Pedagogy, classroom management, curriculum"},
        {"id": "sales", "name": "Sales", "description": "Prospecting, negotiation, account management"}
    ]
    return {"domains": domains, "total": len(domains)}


@router.get("/questions/random")
async def get_random_questions(
    domain: str,
    behavioral_count: int = 5,
    technical_count: int = 5
):
    """
    Get randomized interview questions.
    
    Returns a mix of behavioral questions (common to all domains)
    and technical questions specific to the selected domain.
    
    Args:
        domain: The technical domain (Management, Software Engineering, etc.)
        behavioral_count: Number of behavioral questions (default 5)
        technical_count: Number of technical questions (default 5)
    
    Returns:
        dict: Randomized questions for the interview session
    """
    questions_data = load_questions()
    
    # Map domain ID to domain name
    domain_map = {
        "management": "Management",
        "software_engineering": "Software Engineering",
        "finance": "Finance",
        "teaching": "Teaching",
        "sales": "Sales"
    }
    
    domain_name = domain_map.get(domain.lower().replace(" ", "_"), domain)
    
    # Get behavioral questions
    behavioral = [q for q in questions_data if q.get("domain") == "Behavioral"]
    
    # Get technical questions for the selected domain
    technical = [q for q in questions_data if q.get("domain") == domain_name]
    
    # Randomize and select
    selected_behavioral = random.sample(behavioral, min(behavioral_count, len(behavioral)))
    selected_technical = random.sample(technical, min(technical_count, len(technical)))
    
    # Combine and shuffle
    all_selected = selected_behavioral + selected_technical
    random.shuffle(all_selected)
    
    # Convert to response format
    questions = [
        Question(
            id=q["id"],
            question=q["question"],
            ideal_answer=q["ideal_answer"],
            category=q.get("category", "General")
        )
        for q in all_selected
    ]
    
    return {
        "questions": questions,
        "total": len(questions),
        "domain": domain_name,
        "behavioral_count": len(selected_behavioral),
        "technical_count": len(selected_technical)
    }


# ===========================================
# Intelligent Question Selection Endpoint
# ===========================================

@router.post("/questions/smart")
async def get_smart_questions(
    job_description: str = Form(..., description="Job description text"),
    num_questions: int = Form(default=10, ge=5, le=20, description="Number of questions"),
    resume_text: Optional[str] = Form(default=None, description="Resume text for better matching"),
    previous_question_ids: Optional[str] = Form(default=None, description="Comma-separated IDs of previously asked questions"),
    user_id: Optional[str] = Form(default=None, description="Deprecated: the logged-in user is used"),
    user: dict = Depends(require_auth)
):
    """
    Get intelligently selected interview questions based on job description.
    
    This endpoint uses a sophisticated algorithm from intelligent_question_engine that:
    1. Analyzes user's performance history to identify weak areas (40% weight)
    2. Scores questions by domain relevance (25% weight)
    3. Matches JD keywords to questions (20% weight)  
    4. Applies difficulty progression - easy → medium → hard (15% weight)
    5. Balances across categories while prioritizing improvement areas
    6. Orders questions for optimal interview flow
    7. Avoids repetition with intelligent fallback
    
    Args:
        job_description: The full job description text
        num_questions: Number of questions to return (5-20)
        resume_text: Optional resume text for skill gap analysis
        previous_question_ids: Comma-separated list of question IDs to exclude
        user_id: Optional user ID for personalized selection based on history
    
    Returns:
        dict: Selected questions with metadata about the selection
    """
    from app.models.supabase_client import get_supabase
    
    user_id = ensure_same_user(user_id, user)
    
    # Analyze JD to detect domain and extract keywords
    jd_analysis = analyze_job_description(job_description)
    domain = jd_analysis.domain
    jd_keywords = jd_analysis.keywords[:20] if jd_analysis.keywords else []
    
    # Fetch all available questions from database
    all_questions = await get_all_questions()
    
    # Convert to dict format for the engine
    questions_data = [
        {
            "id": q.id,
            "question": q.question,
            "ideal_answer": q.ideal_answer,
            "category": q.category,
            "domain": q.domain,
            "difficulty": q.difficulty,
            "keywords": q.keywords,
            "time_limit_seconds": q.time_limit_seconds
        }
        for q in all_questions
    ]
    
    # Fetch user's attempt history for personalization
    user_attempts = []
    if user_id:
        try:
            supabase = get_supabase()
            attempts_response = supabase.table("attempts")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(100)\
                .execute()
            user_attempts = attempts_response.data or []
            logger.info(f"Fetched {len(user_attempts)} attempts for user {user_id} for personalized selection")
        except Exception as e:
            logger.warning(f"Could not fetch user history for personalization: {e}")
    
    # Use the intelligent selection algorithm
    selection_result = await select_questions_intelligently(
        all_questions=questions_data,
        user_id=user_id,
        user_attempts=user_attempts,
        jd_text=job_description,
        jd_keywords=jd_keywords,
        target_domain=domain,
        num_questions=num_questions,
        allow_repeats=False,
        randomization_factor=0.15  # Slight randomization to avoid staleness
    )
    
    # Convert to response format
    questions_response = [q.to_dict() for q in selection_result.questions]
    
    return {
        "questions": questions_response,
        "total": len(questions_response),
        "total_time_seconds": selection_result.total_time_seconds,
        "total_time_formatted": f"{selection_result.total_time_seconds // 60} min {selection_result.total_time_seconds % 60} sec",
        "category_distribution": selection_result.category_distribution,
        "difficulty_distribution": selection_result.difficulty_distribution,
        "domain_focus": selection_result.domain_focus,
        "user_weak_areas_targeted": selection_result.user_weak_areas_targeted,
        "jd_keywords_used": selection_result.jd_keywords_used[:10],
        "selection_algorithm": "intelligent_question_engine_v2",
        "jd_analysis": {
            "keywords": jd_analysis.keywords[:10],
            "skills": jd_analysis.skills[:10],
            "domain": jd_analysis.domain,
            "seniority": jd_analysis.seniority,
            "is_management": jd_analysis.is_management
        }
    }


@router.post("/questions/analyze-jd")
async def analyze_job_description_endpoint(
    job_description: str = Form(..., description="Job description text")
):
    """
    Analyze a job description without selecting questions.
    
    Returns extracted information about the JD including:
    - Keywords and skills detected
    - Detected domain (software, finance, etc.)
    - Seniority level
    - Whether it's a management role
    
    Useful for previewing what the selection algorithm sees.
    """
    analysis = analyze_job_description(job_description)
    
    if not analysis.is_valid:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid job description: {analysis.validation_reason}"
        )
    
    return {
        "keywords": analysis.keywords,
        "skills": analysis.skills,
        "domain": analysis.domain,
        "seniority": analysis.seniority,
        "is_management": analysis.is_management,
        "is_valid": True
    }


# ===========================================
# Domain-Specific Resume Analysis Endpoint
# ===========================================

@router.post("/analyze_resume_for_domain")
async def analyze_resume_for_domain(
    domain: str = Form(..., description="Selected interview domain"),
    job_description: str = Form(..., description="Job description text"),
    resume: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    user_id: Optional[str] = Form(None, description="Deprecated: the logged-in user is used"),
    user: dict = Depends(require_auth)
):
    """
    Analyze a resume against a job description for a specific domain.
    
    This endpoint is called after domain selection but before questions.
    It analyzes how well the resume matches the job description and
    provides feedback tailored to the selected domain.
    
    Args:
        domain: The selected interview domain (e.g., "software_engineering")
        job_description: The job description text the user is applying for
        resume: The resume file (PDF or DOCX format)
        user_id: Optional user ID for storage and database linking
    
    Returns:
        dict: Analysis results including:
            - skill_match_pct: Percentage of skills matched
            - missing_skills: Skills in JD but not in resume
            - matched_skills: Skills found in both
            - domain_fit: How well the resume fits the domain
            - feedback: Tips for improvement
    """
    import asyncio
    
    user_id = ensure_same_user(user_id, user)
    
    # Validate file extension
    ext = get_file_extension(resume.filename)
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}"
        )
    
    # Read file content
    content = await resume.read()
    file_size = len(content)
    
    # Validate file size
    if file_size > MAX_RESUME_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_RESUME_SIZE // (1024*1024)}MB"
        )
    
    # Save file temporarily for text extraction
    filename = generate_unique_filename(resume.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    # Upload to Supabase Storage
    file_url = None
    try:
        _, file_url = await upload_resume_bytes(content, resume.filename, user_id)
        logger.info(f"Resume uploaded to storage: {file_url}")
    except Exception as e:
        logger.warning(f"Storage upload failed (non-blocking): {e}")
    
    try:
        # Extract text from resume
        resume_text = extract_text_from_resume(filepath)
        
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract sufficient text from resume. Please check the file."
            )
        
        # Run ML and LLM tasks concurrently for speed
        async def run_ml_tasks():
            ml_result = compare_resume_with_jd(resume_text, job_description)
            resume_score = score_resume(resume_text, job_description)
            return ml_result, resume_score
        
        async def run_domain_check():
            domain_skills = get_domain_skills(domain)
            domain_matched = [skill for skill in domain_skills if skill.lower() in resume_text.lower()]
            domain_fit = (len(domain_matched) / len(domain_skills)) * 100 if domain_skills else 50
            return domain_matched, domain_fit
        
        # Execute ML tasks (these are CPU-bound but quick)
        ml_result, resume_score = await run_ml_tasks()
        domain_matched, domain_fit = await run_domain_check()
        
        # Generate LLM feedback (this is the slow part)
        llm_feedback = generate_resume_feedback(
            resume_text=resume_text,
            jd_text=job_description,
            ml_scores=ml_result
        )

        # Check for invalid resume (validity_score < 50)
        validity_score = llm_feedback.get("validity_score", 100)
        if validity_score < 50:
            logger.warning(f"Resume flagged as invalid (score {validity_score})")
            return {
                "domain": domain,
                "skill_match_pct": 0,
                "missing_skills": ml_result["missing_skills"],
                "matched_skills": [],
                "domain_skills_matched": [],
                "domain_fit": 0,
                "resume_score": 0,
                "similarity_score": 0,
                "feedback": {
                    "summary": llm_feedback.get("summary", "Resume appears to be invalid or too short."),
                    "strengths": [],
                    "gaps": ["File content does not resemble a valid professional resume"],
                    "tips": ["Please upload a proper resume PDF or DOCX file"],
                    "priority_skills": [],
                    "experience_feedback": "N/A",
                    "formatting_feedback": "N/A",
                    "validity_score": validity_score,
                    "is_valid_resume": False
                }
            }
        
        # Save to database (async, non-blocking)
        try:
            await save_resume_analysis(
                user_id=user_id,
                file_name=resume.filename,
                file_url=file_url or "",
                file_size_bytes=file_size,
                resume_text=resume_text,
                job_description=job_description,
                domain=domain,
                skill_match_pct=ml_result["skill_match_pct"],
                similarity_score=ml_result.get("similarity_score", 0.0),
                matched_skills=ml_result.get("matched_skills", []),
                missing_skills=ml_result.get("missing_skills", []),
                feedback=llm_feedback
            )
        except Exception as e:
            logger.warning(f"DB save failed (non-blocking): {e}")
        
        return {
            "domain": domain,
            "skill_match_pct": ml_result["skill_match_pct"],
            "missing_skills": ml_result["missing_skills"],
            "matched_skills": ml_result.get("matched_skills", []),
            "domain_skills_matched": domain_matched,
            "domain_fit": round(domain_fit, 1),
            "resume_score": resume_score["overall_score"],
            "similarity_score": ml_result.get("similarity_score", 0.0),
            "feedback": llm_feedback
        }
    
    finally:
        # Clean up temporary file
        if os.path.exists(filepath):
            os.remove(filepath)


def get_domain_skills(domain: str) -> List[str]:
    """Get key skills for a specific domain."""
    domain_skills_map = {
        "management": ["leadership", "strategy", "team", "project", "budget", "planning", "communication", "delegation"],
        "software_engineering": ["python", "javascript", "api", "database", "testing", "git", "agile", "debugging", "code"],
        "finance": ["analysis", "excel", "modeling", "forecasting", "budget", "investment", "risk", "accounting"],
        "teaching": ["curriculum", "lesson", "assessment", "classroom", "student", "education", "learning", "pedagogy"],
        "sales": ["negotiation", "prospecting", "closing", "crm", "pipeline", "revenue", "client", "quota"]
    }
    return domain_skills_map.get(domain.lower().replace(" ", "_"), [])


# ===========================================
# Resume Upload Endpoint
# ===========================================

@router.post("/upload_resume", response_model=ResumeAnalysisResponse)
async def upload_resume(
    resume: UploadFile = File(..., description="Resume file (PDF or DOCX)"),
    job_description: str = Form(..., description="Job description text"),
    user: dict = Depends(require_auth)
):
    """
    Upload a resume and analyze it against a job description.
    
    This endpoint:
    1. Validates the uploaded resume file
    2. Extracts text from the resume (PDF/DOCX)
    3. Compares skills with the job description using ML
    4. Generates feedback using LLM
    
    Args:
        resume: The resume file (PDF or DOCX format)
        job_description: The job description to compare against
    
    Returns:
        ResumeAnalysisResponse: Analysis results including:
            - skill_match_pct: Percentage of skills matched
            - missing_skills: Skills in JD but not in resume
            - resume_score: Overall resume relevance score
            - feedback: LLM-generated feedback and tips
    
    Raises:
        HTTPException: If file type is invalid or processing fails
    """
    # Validate file extension
    ext = get_file_extension(resume.filename)
    if ext not in ALLOWED_RESUME_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_RESUME_EXTENSIONS)}"
        )
    
    # Read file content
    content = await resume.read()
    
    # Validate file size
    if len(content) > MAX_RESUME_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_RESUME_SIZE // (1024*1024)}MB"
        )
    
    # Save file temporarily
    filename = generate_unique_filename(resume.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.write(content)
    
    try:
        # Extract text from resume
        resume_text = extract_text_from_resume(filepath)
        
        if not resume_text or len(resume_text.strip()) < 50:
            raise HTTPException(
                status_code=400,
                detail="Could not extract sufficient text from resume. Please check the file."
            )
        
        # Compare resume with job description using ML
        ml_result = compare_resume_with_jd(resume_text, job_description)
        
        # Score the resume
        resume_score = score_resume(resume_text, job_description)
        
        # Generate LLM feedback
        llm_feedback = generate_resume_feedback(
            resume_text=resume_text,
            jd_text=job_description,
            ml_scores=ml_result
        )

        # Store resume in Supabase Storage permanently if possible
        try:
            # Re-read file content from UploadFile for storage
            await resume.seek(0)
            await upload_resume_file(resume)
            logger.info(f"Resume {resume.filename} stored to permanent storage")
        except Exception as e:
            logger.warning(f"Failed to store resume permanently: {e}")
        
        return ResumeAnalysisResponse(
            skill_match_pct=ml_result["skill_match_pct"],
            missing_skills=ml_result["missing_skills"],
            matched_skills=ml_result.get("matched_skills", []),
            resume_score=resume_score["overall_score"],
            similarity_score=ml_result.get("similarity_score", 0.0),
            feedback=llm_feedback
        )
    
    finally:
        # Clean up temporary file
        if os.path.exists(filepath):
            os.remove(filepath)


# ===========================================
# Audio Upload Endpoint
# ===========================================

@router.post("/upload_audio", response_model=AudioFeedbackResponse)
async def upload_audio(
    audio: UploadFile = File(..., description="Audio recording of answer"),
    question_id: int = Form(..., description="ID of the question being answered"),
    user_id: Optional[str] = Form(default=None, description="Deprecated: the logged-in user is used"),
    user: dict = Depends(require_auth)
):
    """
    Upload an audio answer and get detailed feedback.
    
    Uses Supabase REST API - no database connection string needed!
    
    This endpoint:
    1. Validates the uploaded audio file
    2. Converts audio to WAV if necessary
    3. Transcribes the audio using the configured provider
    4. Calculates ML scores (content, delivery, communication)
    5. Generates LLM feedback with tips and example answer
    6. Saves the attempt to Supabase (unless in test mode)
    
    Args:
        audio: The audio file (WAV, MP3, M4A, WebM, OGG)
        question_id: The ID of the question being answered
        user_id: Optional user ID for authenticated users
    
    Returns:
        AudioFeedbackResponse: Feedback including:
            - transcript: The transcribed text
            - scores: ML scores for content, delivery, communication, voice, confidence, structure
            - feedback: LLM-generated tips and example answer
    
    Raises:
        HTTPException: If file type is invalid, question not found, or processing fails
    """
    user_id = ensure_same_user(user_id, user)
    logger.info(f"Audio upload initiated: question_id={question_id}, user_id={user_id}, filename={audio.filename}")
    
    # Validate file extension
    ext = get_file_extension(audio.filename)
    if ext not in ALLOWED_AUDIO_EXTENSIONS:
        logger.warning(f"Invalid audio format attempted: {ext}")
        raise HTTPException(
            status_code=400,
            detail=f"Invalid audio format. Allowed: {', '.join(ALLOWED_AUDIO_EXTENSIONS)}"
        )
    
    # Load question from database first, then fallback to local file
    question = None
    db_question = get_question_by_id(question_id)
    if db_question:
        question = {
            "id": db_question.id,
            "question": db_question.question,
            "ideal_answer": db_question.ideal_answer,
            "keywords": db_question.keywords,
            "category": db_question.category,
            "domain": db_question.domain
        }
        logger.debug(f"Found question in database: id={question_id}")
    else:
        # Fallback to local file for backwards compatibility
        questions = load_questions()
        question = next((q for q in questions if q["id"] == question_id), None)
        if question:
            logger.debug(f"Found question in local file: id={question_id}")
    
    if not question:
        logger.warning(f"Question not found: question_id={question_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Question with ID {question_id} not found"
        )
    
    # Read file content
    content = await audio.read()
    
    # Validate file size
    if len(content) > MAX_AUDIO_SIZE:
        logger.warning(f"Audio file too large: {len(content)} bytes (max: {MAX_AUDIO_SIZE})")
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {MAX_AUDIO_SIZE // (1024*1024)}MB"
        )
    
    logger.debug(f"Audio file received: {len(content)} bytes")
    
    # Save file temporarily
    filename = generate_unique_filename(audio.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    with open(filepath, "wb") as f:
        f.write(content)
    logger.debug(f"Temporary audio file saved: {filepath}")
    
    try:
        # Convert audio if needed (to WAV for processing)
        logger.debug("Converting audio format if necessary")
        processed_path = convert_audio_if_needed(filepath)
        
        # Get audio duration
        duration_seconds = get_audio_duration(processed_path)
        logger.info(f"Audio duration: {duration_seconds:.2f} seconds")
        
        # Transcribe the audio
        logger.info("Transcribing audio...")
        transcript = transcribe_audio(processed_path)
        
        if not transcript or len(transcript.strip()) < 5:
            logger.warning(f"Transcription failed or too short: {len(transcript or '')} chars")
            raise HTTPException(
                status_code=400,
                detail="Could not transcribe audio. Please ensure clear speech and try again."
            )
        
        logger.info(f"Transcription successful: {len(transcript)} characters")
        logger.debug(f"Transcript: {transcript[:100]}...")
        
        # Get keywords from question (if available)
        keywords = question.get("keywords", [])
        
        # Calculate ML scores using keyword-based scoring (0-10 scale)
        if keywords:
            logger.debug(f"Calculating keyword-based scores with {len(keywords)} keywords")
            ml_scores = score_answer_by_keywords(
                transcript=transcript,
                keywords=keywords,
                duration_seconds=duration_seconds,
                ideal_answer=question["ideal_answer"]
            )
        else:
            # Fallback to semantic similarity scoring (already 0-100)
            logger.debug("Calculating semantic similarity scores")
            ml_scores_raw = score_answer(
                transcript=transcript,
                duration_seconds=duration_seconds,
                ideal_answer=question["ideal_answer"],
                audio_path=processed_path  # Pass audio path for voice analysis
            )
            # 6-score system - include all new scores
            ml_scores = {
                "content": ml_scores_raw["content"],
                "delivery": ml_scores_raw["delivery"],
                "communication": ml_scores_raw["communication"],
                "voice": ml_scores_raw.get("voice", 70.0),
                "confidence": ml_scores_raw.get("confidence", 70.0),
                "structure": ml_scores_raw.get("structure", 70.0),
                "final": ml_scores_raw["final"],
                "wpm": ml_scores_raw["wpm"],
                "filler_count": ml_scores_raw["filler_count"],
                "grammar_errors": ml_scores_raw["grammar_errors"],
                "relevance": ml_scores_raw["relevance"],
                "keywords_found": [],
                "keywords_missing": [],
                "keyword_match_pct": 0.0,
                "filler_details": ml_scores_raw.get("filler_details", []),
                "grammar_details": ml_scores_raw.get("grammar_details", []),
                "wpm_feedback": ml_scores_raw.get("wpm_feedback", ""),
                "voice_feedback": ml_scores_raw.get("voice_feedback", []),
                "structure_feedback": ml_scores_raw.get("structure_feedback", []),
                "confidence_feedback": ml_scores_raw.get("confidence_feedback", [])
            }
        
        logger.info(f"ML scores calculated: content={ml_scores['content']:.1f}, delivery={ml_scores['delivery']:.1f}, communication={ml_scores['communication']:.1f}, final={ml_scores['final']:.1f}")
        
        # Generate LLM feedback
        logger.info("Generating LLM feedback...")
        llm_feedback = generate_answer_feedback(
            question=question["question"],
            transcript=transcript,
            ideal_answer=question["ideal_answer"],
            ml_scores=ml_scores
        )
        logger.debug(f"LLM feedback generated: {len(llm_feedback.get('tips', []))} tips")
        
        # Always persist attempt to database
        attempt_id = 0
        try:
            from app.services.supabase_db import create_attempt
            result = await create_attempt(
                user_id=user_id,
                question_id=question_id,
                transcript=transcript,
                duration_seconds=duration_seconds,
                scores={
                    "content": ml_scores["content"],
                    "delivery": ml_scores["delivery"],
                    "communication": ml_scores["communication"],
                    "voice": ml_scores.get("voice", 70.0),
                    "confidence": ml_scores.get("confidence", 70.0),
                    "structure": ml_scores.get("structure", 70.0),
                    "final": ml_scores["final"],
                    **ml_scores  # Include all ML scores
                },
                llm_feedback=llm_feedback,
                question_text=question["question"],
                ideal_answer=question.get("ideal_answer", "")
            )
            attempt_id = result.get("id", 0)
            logger.info(f"✓ Attempt saved to Supabase with ID {attempt_id}")
        except Exception as e:
            logger.error(f"Could not save to Supabase: {e}. Continuing without persistence.")
        
        # Note: Transcript is now stored in the database attempts table, no local file needed
        
        logger.info(f"✓ Audio processing complete. Returning feedback to client (attempt_id={attempt_id})")
        return AudioFeedbackResponse(
            attempt_id=attempt_id,
            question_id=question_id,
            question_text=question["question"],
            transcript=transcript,
            duration_seconds=duration_seconds,
            scores=MLScores(
                content=ml_scores["content"],
                delivery=ml_scores["delivery"],
                communication=ml_scores["communication"],
                voice=ml_scores.get("voice", 70.0),
                confidence=ml_scores.get("confidence", 70.0),
                structure=ml_scores.get("structure", 70.0),
                final=ml_scores["final"],
                wpm=ml_scores["wpm"],
                filler_count=ml_scores["filler_count"],
                grammar_errors=ml_scores["grammar_errors"],
                relevance=ml_scores["relevance"]
            ),
            feedback=llm_feedback,
            keywords_found=ml_scores.get("keywords_found", []),
            keywords_missing=ml_scores.get("keywords_missing", [])
        )
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Audio processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )
    
    finally:
        # Clean up temporary files
        logger.debug("Cleaning up temporary audio files")
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                logger.debug(f"Removed temporary file: {filepath}")
            except Exception as e:
                logger.debug(f"Could not remove temporary file {filepath}: {e}")
        if processed_path != filepath and os.path.exists(processed_path):
            try:
                os.remove(processed_path)
                logger.debug(f"Removed processed file: {processed_path}")
            except Exception as e:
                logger.debug(f"Could not remove processed file {processed_path}: {e}")

# Note: Dashboard and History endpoints moved to dashboard.py and history.py routers


# ===========================================
# Submit Answer with Transcript (Web Speech API)
# ===========================================


from pydantic import BaseModel

class AnswerSubmission(BaseModel):
    """Request body for submitting an answer with transcript."""
    question_id: int
    transcript: str
    duration_seconds: float = 0
    job_description: Optional[str] = None  # Job description for contextual scoring
    user_id: str  # Required: User's UUID
    session_id: str  # Required: Session UUID
    question_order: int = 1  # Position in session (1-10)
    domain: Optional[str] = "general"  # Question domain
    difficulty: Optional[str] = "medium"  # Question difficulty


@router.post("/submit_answer", response_model=AudioFeedbackResponse)
async def submit_answer(
    submission: AnswerSubmission,
    user: dict = Depends(require_auth)
):
    """
    Submit an answer with transcript from browser speech recognition.
    
    Uses Supabase REST API - no database connection string needed!
    
    This endpoint accepts a transcript directly from the Web Speech API,
    bypassing audio file processing for faster and more reliable transcription.
    Best used for testing mode where AI-powered transcription is not critical.
    
    Args:
        submission: The answer submission with transcript
    
    Returns:
        AudioFeedbackResponse: Feedback including:
            - transcript: The submitted transcript
            - scores: ML scores for content, delivery, communication, voice, confidence, structure
            - feedback: LLM-generated tips and example answer
    """
    submission.user_id = ensure_same_user(submission.user_id, user)
    
    # Answers can only be added to the caller's own session
    from app.services.supabase_db import get_session_by_id
    session = await get_session_by_id(submission.session_id)
    if not session or session.get("user_id") != submission.user_id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    logger.info(f"Answer submission: question_id={submission.question_id}, transcript_len={len(submission.transcript)}")
    
    # Load question from database first, then fallback to local file
    question = None
    db_question = get_question_by_id(submission.question_id)
    if db_question:
        question = {
            "id": db_question.id,
            "question": db_question.question,
            "ideal_answer": db_question.ideal_answer,
            "keywords": db_question.keywords,
            "category": db_question.category,
            "domain": db_question.domain
        }
        logger.debug(f"Found question in database: id={submission.question_id}")
    else:
        # Fallback to local file for backwards compatibility
        questions = load_questions()
        question = next((q for q in questions if q["id"] == submission.question_id), None)
        if question:
            logger.debug(f"Found question in local file: id={submission.question_id}")
    
    if not question:
        logger.warning(f"Question not found: question_id={submission.question_id}")
        raise HTTPException(
            status_code=404,
            detail=f"Question with ID {submission.question_id} not found"
        )
    
    transcript = submission.transcript.strip()
    
    if not transcript or len(transcript) < 5:
        logger.warning(f"Transcript too short: {len(transcript)} characters")
        raise HTTPException(
            status_code=400,
            detail="Transcript too short. Please provide a longer answer."
        )
    
    logger.debug(f"Transcript received: {len(transcript)} characters")
    
    duration_seconds = submission.duration_seconds or 30.0  # Default if not provided
    logger.debug(f"Duration: {duration_seconds} seconds")
    
    # Get keywords from question (if available)
    keywords = question.get("keywords", [])
    
    # Calculate ML scores using keyword-based scoring (0-10 scale)
    try:
        if keywords:
            logger.debug(f"Calculating keyword-based scores with {len(keywords)} keywords")
            ml_scores = score_answer_by_keywords(
                transcript=transcript,
                keywords=keywords,
                duration_seconds=duration_seconds,
                ideal_answer=question["ideal_answer"]
            )
        else:
            # Fallback to semantic similarity scoring
            logger.debug("Calculating semantic similarity scores")
            ml_scores_raw = score_answer(
                transcript=transcript,
                duration_seconds=duration_seconds,
                ideal_answer=question["ideal_answer"]
            )
            ml_scores = {
                "content": ml_scores_raw["content"],
                "delivery": ml_scores_raw["delivery"],
                "communication": ml_scores_raw["communication"],
                "final": ml_scores_raw["final"],
                "wpm": ml_scores_raw["wpm"],
                "filler_count": ml_scores_raw["filler_count"],
                "grammar_errors": ml_scores_raw["grammar_errors"],
                "relevance": ml_scores_raw["relevance"],
                "keywords_found": [],
                "keywords_missing": [],
                "keyword_match_pct": 0.0,
                "filler_details": ml_scores_raw.get("filler_details", []),
                "grammar_details": ml_scores_raw.get("grammar_details", []),
                "wpm_feedback": ml_scores_raw.get("wpm_feedback", "")
            }
        
        logger.info(f"ML scores calculated: content={ml_scores['content']:.1f}, delivery={ml_scores['delivery']:.1f}, communication={ml_scores['communication']:.1f}, final={ml_scores['final']:.1f}")
        
        # Generate LLM feedback
        logger.info("Generating LLM feedback...")
        llm_feedback = generate_answer_feedback(
            question=question["question"],
            transcript=transcript,
            ideal_answer=question["ideal_answer"],
            ml_scores=ml_scores,
            job_description=submission.job_description
        )
        logger.debug(f"LLM feedback generated: {len(llm_feedback.get('tips', []))} tips")
        
        # Always persist attempt to database
        attempt_id = 0
        try:
            from app.services.supabase_db import create_attempt
            result = await create_attempt(
                user_id=submission.user_id,
                session_id=submission.session_id,
                question_id=submission.question_id,
                question_order=submission.question_order,
                transcript=transcript,
                duration_seconds=duration_seconds,
                scores=ml_scores,
                question_text=question["question"],
                ideal_answer=question.get("ideal_answer", ""),
                llm_feedback=llm_feedback,
                domain=submission.domain or question.get("domain", "general"),
                difficulty=submission.difficulty or question.get("difficulty", "medium")
            )
            attempt_id = result.get("id", 0)
            logger.info(f"✓ Answer saved to Supabase with ID {attempt_id}, session: {submission.session_id}")
        except Exception as e:
            logger.error(f"Could not save to Supabase: {e}. Continuing without persistence.")
        
        # Note: Transcript is now stored in the database attempts table, no local file needed
        
        logger.info(f"✓ Successfully processed answer for question {submission.question_id} (final score: {ml_scores['final']:.1f})")
        
        return AudioFeedbackResponse(
            attempt_id=attempt_id,
            question_id=submission.question_id,
            question_text=question["question"],
            transcript=transcript,
            duration_seconds=duration_seconds,
            scores=MLScores(
                content=ml_scores["content"],
                delivery=ml_scores["delivery"],
                communication=ml_scores["communication"],
                final=ml_scores["final"],
                wpm=ml_scores["wpm"],
                filler_count=ml_scores["filler_count"],
                grammar_errors=ml_scores["grammar_errors"],
                relevance=ml_scores["relevance"]
            ),
            feedback=llm_feedback,
            keywords_found=ml_scores.get("keywords_found", []),
            keywords_missing=ml_scores.get("keywords_missing", [])
        )
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"Answer submission failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )

@router.post("/upload_attempt_audio")
async def upload_attempt_audio(
    audio: UploadFile = File(...),
    user_id: str = Form(...),
    session_id: str = Form(...),
    question_order: int = Form(...),
    attempt_id: int = Form(...),
    user: dict = Depends(require_auth)
):
    """
    Upload audio for a specific attempt in the background.
    
    This is called after submit_answer has already created the attempt record.
    """
    from app.services.storage_service import upload_audio_file
    from app.services.supabase_db import update_attempt_audio_url, get_attempt_by_id
    
    user_id = ensure_same_user(user_id, user)
    attempt = await get_attempt_by_id(attempt_id)
    if not attempt or attempt.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    logger.info(f"Background audio upload for attempt {attempt_id}, session {session_id}")
    
    try:
        # Upload to Supabase Storage using existing service
        # Note: we use attempt_id as question_id for naming uniqueness if needed
        file_path, public_url = await upload_audio_file(
            audio, 
            user_id=user_id, 
            question_id=attempt_id
        )
        
        # Update database with the URL
        success = await update_attempt_audio_url(attempt_id, public_url)
        
        if not success:
            logger.warning(f"Failed to update database with audio URL for attempt {attempt_id}")
            return {"status": "partial_success", "message": "Uploaded but DB update failed", "url": public_url}
            
        return {"status": "success", "url": public_url}
        
    except Exception as e:
        logger.error(f"Failed to upload background audio for attempt {attempt_id}: {e}")
        # We don't raise HTTPException here because this is a background call 
        # that shouldn't break the UI if it fails
        return {"status": "error", "message": str(e)}


# ===========================================
# Custom Questions Endpoint
# ===========================================

@router.post("/questions/validate_custom")
async def validate_custom_questions(
    file: UploadFile = File(..., description="JSON or CSV file containing questions"),
    user: dict = Depends(require_auth)
):
    """
    Validate and parse a custom questions file for a single session.
    
    Does NOT save to the global question pool.
    Returns the parsed questions to the frontend to be used in the current session state.
    """
    ext = get_file_extension(file.filename)
    if ext not in [".json", ".csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload .json or .csv"
        )
    
    content = await file.read()
    content_str = content.decode("utf-8")
    
    try:
        questions = []
        if ext == ".json":
            questions = parse_questions_from_json(content_str)
        else:
            questions = parse_questions_from_csv(content_str)
            
        return {
            "success": True,
            "count": len(questions),
            "questions": [q.to_dict() for q in questions]
        }
    except Exception as e:
        logger.error(f"Failed to parse custom questions: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}"
        )


@router.post("/questions/upload_custom")
async def upload_custom_questions_to_db(
    file: UploadFile = File(..., description="JSON or CSV file containing questions"),
    user_id: Optional[str] = Form(default=None, description="Deprecated: the logged-in user is recorded"),
    user: dict = Depends(require_auth)
):
    """
    Upload custom questions to the database permanently.
    
    Unlike validate_custom_questions which only parses for session use,
    this endpoint saves questions to the global question pool.
    
    Each question will be marked with:
    - is_custom: TRUE
    - uploaded_by: user_id
    
    Expected JSON format:
    [
        {
            "question": "Your question text",
            "ideal_answer": "Expected answer",
            "keywords": ["keyword1", "keyword2"],
            "category": "behavioral|technical|situational|general",
            "domain": "software_engineering|management|finance|teaching|sales|general",
            "difficulty": "easy|medium|hard"
        }
    ]
    """
    from app.models.supabase_client import get_supabase
    
    user_id = ensure_same_user(user_id, user)
    
    ext = get_file_extension(file.filename)
    if ext not in [".json", ".csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload .json or .csv"
        )
    
    content = await file.read()
    content_str = content.decode("utf-8")
    
    try:
        # Parse questions from file
        questions = []
        if ext == ".json":
            questions = parse_questions_from_json(content_str)
        else:
            questions = parse_questions_from_csv(content_str)
        
        if not questions:
            raise HTTPException(status_code=400, detail="No valid questions found in file")
        
        # Prepare records for bulk insert
        supabase = get_supabase()
        insert_records = []
        
        for q in questions:
            record = {
                "question": q.question,
                "ideal_answer": q.ideal_answer,
                "keywords": q.keywords or [],
                "category": q.category or "behavioral",
                "domain": q.domain or "general",
                "difficulty": q.difficulty or "medium",
                "time_limit_seconds": getattr(q, 'time_limit_seconds', 120),
                "is_custom": True,
                "uploaded_by": user_id,
                "is_active": True
            }
            insert_records.append(record)
        
        # Bulk insert to database
        result = supabase.table("questions").insert(insert_records).execute()
        
        if result.data:
            inserted_ids = [r.get("id") for r in result.data]
            logger.info(f"Inserted {len(inserted_ids)} custom questions for user {user_id}")
            
            return {
                "success": True,
                "message": f"Successfully uploaded {len(inserted_ids)} questions to database",
                "count": len(inserted_ids),
                "question_ids": inserted_ids,
                "questions": result.data
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to insert questions to database")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload custom questions: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload questions: {str(e)}"
        )


# ===========================================
# Session Management Endpoints
# ===========================================

class CreateSessionRequest(BaseModel):
    """Request body for creating a new interview session."""
    user_id: str
    domain: str = "general"
    job_description: Optional[str] = None
    job_title: Optional[str] = None
    num_questions: int = 10
    session_name: Optional[str] = None


@router.post("/sessions/create")
async def create_new_session(request: CreateSessionRequest, user: dict = Depends(require_auth)):
    """
    Create a new interview session with personalized questions.
    
    This endpoint:
    1. Creates a session record in the database
    2. Selects personalized questions based on user history
    3. Returns session ID and selected questions
    
    Args:
        request: Session creation parameters
        
    Returns:
        Session ID and selected questions
    """
    request.user_id = ensure_same_user(request.user_id, user)
    logger.info(f"Creating session for user {request.user_id}, domain={request.domain}")
    
    from app.services.supabase_db import create_session, get_user_attempts
    from app.services.intelligent_question_engine import select_questions_intelligently
    
    try:
        # Get user's attempt history for personalization
        user_attempts = await get_user_attempts(request.user_id, limit=100)
        
        # Get all questions for the domain
        all_questions = await get_all_questions(domain=request.domain)
        
        # Select personalized questions
        jd_keywords = None
        if request.job_description:
            jd_analysis = analyze_job_description(request.job_description)
            jd_keywords = jd_analysis.keywords
        
        selection_result = await select_questions_intelligently(
            all_questions=[q.to_dict() if hasattr(q, 'to_dict') else q for q in all_questions],
            user_id=request.user_id,
            user_attempts=user_attempts,
            jd_text=request.job_description,
            jd_keywords=jd_keywords,
            target_domain=request.domain,
            num_questions=request.num_questions,
            allow_repeats=False
        )
        
        # Create session in database
        question_ids = [q.question_id for q in selection_result.questions]
        
        session = await create_session(
            user_id=request.user_id,
            domain=request.domain,
            job_description=request.job_description,
            job_title=request.job_title,
            total_questions=len(selection_result.questions),
            question_ids=question_ids,
            jd_keywords=jd_keywords,
            session_name=request.session_name
        )
        
        if session.get("error"):
            raise HTTPException(status_code=500, detail=session["error"])
        
        # Format questions for response
        questions = [
            {
                "id": q.question_id,
                "question": q.question_text,
                "ideal_answer": q.ideal_answer,
                "category": q.category,
                "domain": q.domain,
                "difficulty": q.difficulty,
                "keywords": q.keywords,
                "time_limit_seconds": q.time_limit_seconds
            }
            for q in selection_result.questions
        ]
        
        logger.info(f"Created session {session['id']} with {len(questions)} questions")
        
        return {
            "session_id": session["id"],
            "questions": questions,
            "total_questions": len(questions),
            "domain": request.domain,
            "user_weak_areas_targeted": selection_result.user_weak_areas_targeted,
            "category_distribution": selection_result.category_distribution,
            "difficulty_distribution": selection_result.difficulty_distribution
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    user_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Get session details."""
    user_id = ensure_same_user(user_id, user)
    from app.services.supabase_db import get_session_by_id, get_session_attempts
    from app.models.supabase_client import get_supabase
    
    session = await get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Fetch attempts
    attempts = await get_session_attempts(session_id)
    
    # Process attempts to get unique questions (latest attempt only)
    # This prevents "Question repeated in history" issue
    attempts_by_question = {}
    for attempt in attempts:
        q_id = attempt.get("question_id")
        if q_id:
            # We want the latest attempt. The attempts are ordered by question_order then created_at? 
            # get_session_attempts orders by question_order. 
            # If multiple attempts for same question, we need to pick the one with highest ID or created_at
            # Assuming typically later attempts have higher IDs or appear later if sorted by time
            # For now, let's keep the last one encountered if they are sorted by time (which they should be)
            # Actually get_session_attempts orders by question_order.
            if q_id not in attempts_by_question:
                 attempts_by_question[q_id] = attempt
            else:
                # Compare created_at to be sure
                curr_date = attempts_by_question[q_id].get("created_at")
                new_date = attempt.get("created_at")
                if new_date and curr_date and new_date > curr_date:
                    attempts_by_question[q_id] = attempt
                elif attempt.get("id") > attempts_by_question[q_id].get("id"):
                     attempts_by_question[q_id] = attempt
    
    unique_attempts = list(attempts_by_question.values())
    unique_attempts.sort(key=lambda x: x.get("question_order", 0))

    # Fetch questions for this session
    # The frontend expects 'questions' array in the session object
    if session.get("question_ids"):
        try:
            supabase = get_supabase()
            result = supabase.table("questions").select("*").in_("id", session["question_ids"]).execute()
            
            # Sort questions to match the order in question_ids
            fetched_questions = {q["id"]: q for q in (result.data or [])}
            session["questions"] = [
                fetched_questions[qid] 
                for qid in session["question_ids"] 
                if qid in fetched_questions
            ]
        except Exception as e:
            logger.error(f"Failed to fetch questions for session {session_id}: {e}")
            session["questions"] = []
    else:
        # If no question_ids in session, try to reconstruct from unique attempts
        if not session.get("questions"):
             session["questions"] = []
             for attempt in unique_attempts:
                 if attempt.get("question_text"):
                     session["questions"].append({
                         "id": attempt.get("question_id"),
                         "question": attempt.get("question_text"),
                         "category": attempt.get("category", "General"),
                         "ideal_answer": attempt.get("ideal_answer", "")
                     })

    # Count deduplicated completed questions
    completed_attempts = [a for a in unique_attempts if a.get("transcript") != "SKIPPED"]
    
    return {
        "session": session,
        "attempts": unique_attempts,
        "completed_count": len(completed_attempts),
        "skipped_count": len([a for a in unique_attempts if a.get("transcript") == "SKIPPED"])
    }


@router.get("/sessions")
async def list_user_sessions(
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    search: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """
    List all interview sessions for a user.
    
    Args:
        user_id: User ID to fetch sessions for
        status: Filter by status (in_progress, completed)
        domain: Filter by domain
        limit: Max sessions to return
        offset: Pagination offset
        search: Search in job_title or job_description
    
    Returns:
        List of sessions with summary info
    """
    from app.services.supabase_db import get_user_sessions
    
    user_id = ensure_same_user(user_id, user)
    logger.info(f"Fetching sessions for user {user_id}")
    
    try:
        sessions = await get_user_sessions(user_id, limit=limit + offset + 1, status=status)
        
        # Apply domain filter
        if domain:
            sessions = [s for s in sessions if s.get("domain", "").lower() == domain.lower()]
        
        # Apply search filter
        if search:
            search_lower = search.lower()
            sessions = [
                s for s in sessions 
                if search_lower in (s.get("job_title") or "").lower() 
                or search_lower in (s.get("job_description") or "").lower()
                or search_lower in (s.get("domain") or "").lower()
            ]
        
        # Apply pagination
        total = len(sessions)
        sessions = sessions[offset:offset + limit]
        
        # Format for frontend
        formatted_sessions = []
        for s in sessions:
            formatted_sessions.append({
                "id": s.get("id"),
                "domain": s.get("domain"),
                "job_title": s.get("job_title"),
                "session_name": s.get("session_name"),
                "job_description": (s.get("job_description") or "")[:100] + "..." if len(s.get("job_description") or "") > 100 else s.get("job_description"),
                "status": s.get("status"),
                "total_questions": s.get("total_questions", 10),
                "completed_questions": s.get("completed_questions", 0),
                "avg_final_score": s.get("avg_final_score") or 0,
                "avg_content_score": s.get("avg_content_score") or 0,
                "avg_delivery_score": s.get("avg_delivery_score") or 0,
                "avg_communication_score": s.get("avg_communication_score") or 0,
                "avg_voice_score": s.get("avg_voice_score") or 0,
                "avg_confidence_score": s.get("avg_confidence_score") or 0,
                "avg_structure_score": s.get("avg_structure_score") or 0,
                "created_at": s.get("created_at"),
                "completed_at": s.get("completed_at")
            })
        
        return {
            "sessions": formatted_sessions,
            "total": total,
            "has_more": total > offset + limit
        }
        
    except Exception as e:
        logger.error(f"Failed to fetch sessions: {e}")
        return {"sessions": [], "total": 0, "has_more": False}


@router.post("/sessions/{session_id}/complete")
async def complete_interview_session(
    session_id: str,
    user_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """
    Complete an interview session and calculate aggregate scores.
    
    Returns:
        Session summary with aggregate scores
    """
    from app.services.supabase_db import get_session_by_id, complete_session, get_session_attempts
    
    user_id = ensure_same_user(user_id, user)
    
    session = await get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Complete the session
    updated_session = await complete_session(session_id)
    
    # Get all attempts for summary
    attempts = await get_session_attempts(session_id)
    scored_attempts = [a for a in attempts if a.get("transcript") != "SKIPPED"]
    
    return {
        "session_id": session_id,
        "status": "completed",
        "total_questions": len(attempts),
        "answered_questions": len(scored_attempts),
        "skipped_questions": len(attempts) - len(scored_attempts),
        "avg_final_score": updated_session.get("avg_final_score", 0),
        "avg_content_score": updated_session.get("avg_content_score", 0),
        "avg_delivery_score": updated_session.get("avg_delivery_score", 0),
        "avg_communication_score": updated_session.get("avg_communication_score", 0),
        "strengths": updated_session.get("strengths", []),
        "improvements": updated_session.get("improvements", []),
        "attempts": attempts
    }


class SkipQuestionRequest(BaseModel):
    """Request body for skipping a question."""
    user_id: str
    question_id: int
    question_order: int
    question_text: str
    domain: str = "general"
    difficulty: str = "medium"


@router.post("/sessions/{session_id}/skip")
async def skip_question_in_session(
    session_id: str,
    request: SkipQuestionRequest,
    user: dict = Depends(require_auth)
):
    """Skip a question in the session."""
    request.user_id = ensure_same_user(request.user_id, user)
    from app.services.supabase_db import skip_attempt, get_session_by_id
    
    session = await get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("user_id") != request.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    result = await skip_attempt(
        user_id=request.user_id,
        session_id=session_id,
        question_id=request.question_id,
        question_order=request.question_order,
        question_text=request.question_text,
        domain=request.domain,
        difficulty=request.difficulty
    )
    
    logger.info(f"Skipped question {request.question_id} in session {session_id}")
    
    return {
        "success": True,
        "message": "Question skipped",
        "attempt_id": result.get("id", 0)
    }






@router.get("/sessions/{session_id}/summary")
async def get_session_summary(
    session_id: str,
    user_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Get the summary for a completed session."""
    user_id = ensure_same_user(user_id, user)
    from app.services.supabase_db import get_session_by_id, get_session_attempts, get_session_report
    
    session = await get_session_by_id(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    attempts = await get_session_attempts(session_id)
    report = await get_session_report(session_id)
    
    return {
        "session": session,
        "attempts": attempts,
        "report": report
    }


# ===========================================
# Custom Question Pool Management
# ===========================================

class AddQuestionRequest(BaseModel):
    """Request body for adding a question to the pool."""
    question: str
    ideal_answer: str
    keywords: List[str] = []
    category: str = "behavioral"
    domain: str = "general"
    difficulty: str = "medium"
    uploaded_by: Optional[str] = None


@router.post("/questions/add", dependencies=[Depends(require_admin)])
async def add_question_to_pool_endpoint(request: AddQuestionRequest):
    """Add a custom question to the question pool."""
    from app.services.supabase_db import add_question_to_pool
    
    if not request.question or len(request.question) < 10:
        raise HTTPException(status_code=400, detail="Question text too short")
    
    if not request.ideal_answer or len(request.ideal_answer) < 20:
        raise HTTPException(status_code=400, detail="Ideal answer too short")
    
    result = await add_question_to_pool(
        question=request.question,
        ideal_answer=request.ideal_answer,
        keywords=request.keywords,
        category=request.category,
        domain=request.domain,
        difficulty=request.difficulty,
        uploaded_by=request.uploaded_by
    )
    
    if result.get("error"):
        raise HTTPException(status_code=500, detail=result["error"])
    
    return {
        "success": True,
        "question_id": result.get("id"),
        "message": "Question added to pool"
    }


@router.post("/questions/upload_bulk", dependencies=[Depends(require_admin)])
async def upload_questions_bulk(
    file: UploadFile = File(..., description="JSON or CSV file containing questions"),
    uploaded_by: Optional[str] = Form(default=None)
):
    """
    Upload multiple questions to the question pool from a file.
    
    Accepts JSON or CSV format.
    """
    from app.services.supabase_db import add_questions_bulk
    
    ext = get_file_extension(file.filename)
    if ext not in [".json", ".csv"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload .json or .csv"
        )
    
    content = await file.read()
    content_str = content.decode("utf-8")
    
    try:
        if ext == ".json":
            questions = parse_questions_from_json(content_str)
        else:
            questions = parse_questions_from_csv(content_str)
        
        # Convert to dictionaries
        question_dicts = [q.to_dict() for q in questions]
        
        result = await add_questions_bulk(question_dicts, uploaded_by)
        
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result["error"])
        
        return {
            "success": True,
            "added_count": result.get("added_count", 0),
            "message": f"Added {result.get('added_count', 0)} questions to pool"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload questions: {e}")
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse file: {str(e)}"
        )
