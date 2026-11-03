"""
AI Interview Feedback - Admin API Endpoints

This module provides admin endpoints for managing the question pool:
- List/filter questions from database
- Add individual questions
- Upload questions via JSON/CSV
- Get question statistics
- Analyze job descriptions

All questions are stored in the Supabase 'questions' table.

Author: AI Interview Assistant Team
"""

import json
from typing import List, Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query, Depends
from pydantic import BaseModel, Field

from app.services.question_service import (
    get_all_questions,
    get_question_by_id,
    add_question_to_pool,
    add_questions_bulk,
    parse_questions_from_json,
    parse_questions_from_csv,
    get_questions_for_interview,
    analyze_job_description,
    get_question_stats,
    Question,
    CATEGORIES
)
from app.logging_config import get_logger
from app.services.auth_service import require_admin, require_auth

logger = get_logger(__name__)

# Create router.
# Reads are public (the question bank is not secret); every write requires an admin
# (ADMIN_EMAILS in backend/.env).
router = APIRouter(prefix="/admin/questions", tags=["Admin - Questions"])


# ===========================================
# Pydantic Models
# ===========================================

class QuestionCreate(BaseModel):
    """Schema for creating a new question."""
    question: str = Field(..., min_length=10, description="The interview question")
    ideal_answer: str = Field(..., min_length=20, description="The ideal answer")
    keywords: List[str] = Field(default=[], description="Keywords for matching")
    category: str = Field(default="behavioral", description="Question category")
    domain: str = Field(default="general", description="Domain (e.g., software_engineering)")
    difficulty: str = Field(default="medium", description="easy, medium, or hard")
    time_limit_seconds: int = Field(default=120, ge=30, le=600)


class QuestionResponse(BaseModel):
    """Response schema for a question."""
    id: int
    question: str
    ideal_answer: str
    keywords: List[str]
    category: str
    domain: str
    difficulty: str
    time_limit_seconds: int
    is_custom: bool = False


class BulkQuestionsCreate(BaseModel):
    """Schema for bulk question creation."""
    questions: List[QuestionCreate]


class StatsResponse(BaseModel):
    """Response for question pool statistics."""
    total: int
    custom: int
    by_category: dict
    by_difficulty: dict
    by_domain: dict


class JDAnalysisResponse(BaseModel):
    """Response for JD analysis."""
    keywords: List[str]
    skills: List[str]
    domain: str
    seniority: str
    is_management: bool


# ===========================================
# Question Pool Endpoints
# ===========================================

@router.get("/stats", response_model=StatsResponse)
async def get_pool_statistics():
    """
    Get statistics about the question pool.
    Returns counts by category, difficulty, domain, and custom vs standard.
    """
    stats = get_question_stats()
    return StatsResponse(
        total=stats.get("total", 0),
        custom=stats.get("custom", 0),
        by_category=stats.get("by_category", {}),
        by_difficulty=stats.get("by_difficulty", {}),
        by_domain=stats.get("by_domain", {})
    )


@router.get("/categories")
async def get_categories():
    """Get list of available question categories with descriptions."""
    return {
        "categories": CATEGORIES,
        "descriptions": {
            "general": "General interview questions (tell me about yourself, etc.)",
            "behavioral": "STAR-based behavioral questions",
            "technical": "Domain-specific technical questions",
            "management": "Leadership and management questions",
            "situational": "Role-specific situational questions"
        }
    }


@router.get("/", response_model=List[QuestionResponse])
async def list_questions(
    category: Optional[str] = Query(None, description="Filter by category"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    limit: int = Query(100, ge=1, le=500)
):
    """
    List all questions with optional filtering.
    Supports filtering by category, domain, and difficulty.
    """
    questions = get_all_questions(
        domain=domain,
        category=category,
        difficulty=difficulty,
        limit=limit
    )
    
    return [
        QuestionResponse(
            id=q.id,
            question=q.question,
            ideal_answer=q.ideal_answer,
            keywords=q.keywords,
            category=q.category,
            domain=q.domain,
            difficulty=q.difficulty,
            time_limit_seconds=q.time_limit_seconds,
            is_custom=q.is_custom
        )
        for q in questions
    ]


@router.get("/{question_id}", response_model=QuestionResponse)
async def get_question(question_id: int):
    """Get a specific question by ID."""
    question = get_question_by_id(question_id)
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    return QuestionResponse(
        id=question.id,
        question=question.question,
        ideal_answer=question.ideal_answer,
        keywords=question.keywords,
        category=question.category,
        domain=question.domain,
        difficulty=question.difficulty,
        time_limit_seconds=question.time_limit_seconds,
        is_custom=question.is_custom
    )


# ===========================================
# Question Management Endpoints
# ===========================================

@router.post("/", response_model=QuestionResponse, dependencies=[Depends(require_admin)])
async def create_question(data: QuestionCreate):
    """
    Add a new question to the pool.
    Custom questions are marked with is_custom=True.
    """
    if data.category not in CATEGORIES:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid category. Must be one of: {CATEGORIES}"
        )
    
    question_id = add_question_to_pool(
        question=data.question,
        ideal_answer=data.ideal_answer,
        keywords=data.keywords,
        category=data.category,
        domain=data.domain,
        difficulty=data.difficulty,
        is_custom=True
    )
    
    if not question_id:
        raise HTTPException(status_code=500, detail="Failed to add question")
    
    # Fetch the created question
    question = get_question_by_id(question_id)
    
    return QuestionResponse(
        id=question.id,
        question=question.question,
        ideal_answer=question.ideal_answer,
        keywords=question.keywords,
        category=question.category,
        domain=question.domain,
        difficulty=question.difficulty,
        time_limit_seconds=question.time_limit_seconds,
        is_custom=question.is_custom
    )


@router.post("/bulk", dependencies=[Depends(require_admin)])
async def create_questions_bulk(data: BulkQuestionsCreate):
    """
    Add multiple questions at once.
    All questions will be marked as custom.
    """
    questions_data = [q.dict() for q in data.questions]
    
    count = add_questions_bulk(questions_data)
    
    return {
        "success": True,
        "message": f"Added {count} questions to the pool",
        "count": count
    }


# ===========================================
# Upload Endpoints (JSON/CSV)
# ===========================================

@router.post("/upload/json", dependencies=[Depends(require_admin)])
async def upload_questions_json(
    file: UploadFile = File(..., description="JSON file with questions")
):
    """
    Upload questions from a JSON file.
    
    Expected format (array of questions):
    ```json
    [
        {
            "question": "Tell me about yourself",
            "ideal_answer": "A structured overview...",
            "keywords": ["introduction", "background"],
            "category": "general",
            "domain": "general",
            "difficulty": "easy"
        }
    ]
    ```
    
    Or with wrapper:
    ```json
    {
        "questions": [...]
    }
    ```
    """
    if not file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="File must be a JSON file")
    
    try:
        content = await file.read()
        json_str = content.decode('utf-8')
        json_data = json.loads(json_str)
        
        # Handle both formats: {"questions": [...]} or [...]
        if isinstance(json_data, dict) and "questions" in json_data:
            questions_list = json_data["questions"]
        elif isinstance(json_data, list):
            questions_list = json_data
        else:
            raise HTTPException(status_code=400, detail="Invalid JSON format")
        
        # Parse and validate
        parsed = parse_questions_from_json(questions_list)
        
        if not parsed:
            raise HTTPException(status_code=400, detail="No valid questions found in file")
        
        # Add to database
        count = add_questions_bulk(parsed)
        
        return {
            "success": True,
            "message": f"Successfully imported {count} questions to the pool",
            "count": count,
            "filename": file.filename
        }
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        logger.error(f"JSON upload failed: {e}")
        raise HTTPException(status_code=500, detail="Import failed. Please try again.")


@router.post("/upload/csv", dependencies=[Depends(require_admin)])
async def upload_questions_csv(
    file: UploadFile = File(..., description="CSV file with questions")
):
    """
    Upload questions from a CSV file.
    
    Expected columns:
    - question (required)
    - ideal_answer (required)  
    - keywords (semicolon-separated, e.g., "python;backend;api")
    - category (general/behavioral/technical/management/situational)
    - domain (e.g., software_engineering, finance, general)
    - difficulty (easy/medium/hard)
    - time_limit_seconds (default: 120)
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV file")
    
    try:
        content = await file.read()
        csv_str = content.decode('utf-8')
        
        # Parse CSV
        parsed = parse_questions_from_csv(csv_str)
        
        if not parsed:
            raise HTTPException(status_code=400, detail="No valid questions found in CSV")
        
        # Add to database
        count = add_questions_bulk(parsed)
        
        return {
            "success": True,
            "message": f"Successfully imported {count} questions to the pool",
            "count": count,
            "filename": file.filename
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File must be UTF-8 encoded")
    except Exception as e:
        logger.error(f"CSV upload failed: {e}")
        raise HTTPException(status_code=500, detail="Import failed. Please try again.")


# ===========================================
# Templates
# ===========================================

@router.get("/template/json")
async def get_json_template():
    """Get a JSON template for question upload."""
    template = [
        {
            "question": "What is your experience with [technology]?",
            "ideal_answer": "I have X years of experience with [technology]. I've used it to [achievements]. For example, [specific project].",
            "keywords": ["experience", "technology", "years", "projects"],
            "category": "technical",
            "domain": "software_engineering",
            "difficulty": "medium"
        },
        {
            "question": "Tell me about a time you faced a challenge.",
            "ideal_answer": "Situation: [context]. Task: [responsibility]. Action: [steps taken]. Result: [outcome with metrics].",
            "keywords": ["challenge", "STAR", "problem", "solution", "result"],
            "category": "behavioral",
            "domain": "general",
            "difficulty": "medium"
        }
    ]
    return template


@router.get("/template/csv")
async def get_csv_template():
    """Get a CSV template for question upload."""
    template = """question,ideal_answer,keywords,category,domain,difficulty
"What is your experience with Python?","I have X years of Python experience. I've used it for web development, data analysis, and automation.","python;experience;projects",technical,software_engineering,medium
"Tell me about a time you led a team.","Situation: I was asked to lead a team of 5 engineers. Task: Deliver a product in 3 months. Action: I organized sprints and daily standups. Result: We delivered on time with 95% customer satisfaction.","leadership;team;management",behavioral,management,medium
"""
    return {"template": template, "content_type": "text/csv"}


# ===========================================
# JD Analysis
# ===========================================

@router.post("/analyze-jd", response_model=JDAnalysisResponse, dependencies=[Depends(require_auth)])
async def analyze_jd(job_description: str = Form(...)):
    """
    Analyze a job description to extract keywords, skills, and domain.
    Useful for understanding what the JD focuses on.
    """
    analysis = analyze_job_description(job_description)
    
    return JDAnalysisResponse(
        keywords=analysis.keywords,
        skills=analysis.skills,
        domain=analysis.domain,
        seniority=analysis.seniority,
        is_management=analysis.is_management
    )

