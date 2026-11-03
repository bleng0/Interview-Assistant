"""
AI Interview Assistant - Dynamic Feedback Generation System

This module provides TRULY DYNAMIC feedback generation using Gemini:
- Per-question detailed analysis
- Consolidated session reports
- Improvement tracking insights
- NO template-based or static responses

Features:
- Context-aware feedback using JD, question, and answer
- STAR method evaluation with specific quotes
- Sentence-level improvement suggestions
- Skill gap analysis
- Actionable improvement tips
- Comparison with previous attempts

Author: AI Interview Assistant Team
"""

import json
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


# ===========================================
# Prompt Templates (Dynamic, Not Static!)
# ===========================================

DYNAMIC_ANSWER_FEEDBACK_PROMPT = """You are an elite interview coach providing PERSONALIZED feedback.

CRITICAL RULES:
1. Quote EXACT phrases from the candidate's answer
2. Reference the SPECIFIC question being asked
3. Compare against the ideal answer structure
4. Consider the job context if provided
5. Be specific - no generic advice

## CONTEXT
**Question:** {question}
**Job Context:** {job_context}
**Time Taken:** {duration_seconds} seconds

## CANDIDATE'S EXACT RESPONSE
"{transcript}"

## REFERENCE IDEAL ANSWER
{ideal_answer}

## ML-CALCULATED PERFORMANCE METRICS
- Content Score: {content_score}/100 (Topic coverage & relevance)
- Delivery Score: {delivery_score}/100 (Speaking: {wpm} WPM, {filler_count} fillers)
- Communication Score: {communication_score}/100 (Grammar issues: {grammar_errors})
- Voice Score: {voice_score}/100 (Clarity, energy, variation)
- Confidence Score: {confidence_score}/100 (Assertiveness, composure)
- Structure Score: {structure_score}/100 (STAR method, organization)
- Overall: {final_score}/100

## PREVIOUS ATTEMPTS ON THIS QUESTION (IF ANY)
{previous_attempts_context}

## YOUR ANALYSIS TASK

Generate a JSON response with these EXACT fields (no markdown, pure JSON):

{{
    "overall_assessment": "2-3 sentences summarizing performance with SPECIFIC quotes. Example: 'Your opening \"[exact quote]\" was strong because... However, when you said \"[quote]\" it lacked...'",
    
    "content_analysis": {{
        "score_justification": "Why this content score - reference specific parts of their answer",
        "key_points_covered": ["List actual points they made"],
        "key_points_missed": ["What they should have included"],
        "relevance_to_question": "How directly they answered - cite specific phrases"
    }},
    
    "star_method_breakdown": {{
        "situation": {{
            "present": true/false,
            "quote": "Exact quote if present, or null",
            "feedback": "Specific feedback on their situation setup"
        }},
        "task": {{
            "present": true/false,
            "quote": "Exact quote if present, or null",
            "feedback": "Specific feedback on task clarity"
        }},
        "action": {{
            "present": true/false,
            "quote": "Exact quote if present, or null", 
            "feedback": "Were actions specific? Did they use 'I' vs 'we'?"
        }},
        "result": {{
            "present": true/false,
            "quote": "Exact quote if present, or null",
            "feedback": "Were results quantified? Impact clear?"
        }}
    }},
    
    "sentence_improvements": [
        {{
            "original": "Copy an EXACT weak sentence from their answer",
            "improved": "Professional rewrite of that sentence",
            "improvement_type": "clarity/conciseness/impact/grammar/structure"
        }},
        {{
            "original": "Another weak sentence",
            "improved": "Better version",
            "improvement_type": "type of improvement made"
        }}
    ],
    
    "delivery_feedback": {{
        "pace_analysis": "Was {wpm} WPM appropriate? Too fast/slow?",
        "filler_impact": "How did {filler_count} filler words affect impression?",
        "specific_issues": ["List specific delivery problems noted"]
    }},
    
    "strengths": [
        "Specific strength with quote: 'When you said [quote], it demonstrated...'",
        "Another specific strength"
    ],
    
    "improvement_areas": [
        "Specific area to improve with example of what to say instead",
        "Another area with actionable advice"
    ],
    
    "skill_gap_analysis": {{
        "missing_keywords": ["Terms from ideal answer they didn't use"],
        "vocabulary_suggestions": ["Professional terms to incorporate"],
        "industry_alignment": "How well does answer match job context?"
    }},
    
    "actionable_tips": [
        "Specific tip: 'Instead of [their phrase], try [better phrase]'",
        "Concrete practice exercise they can do",
        "Technique to improve weakest area"
    ],
    
    "example_answer": "A complete model answer to this specific question (4-5 sentences, STAR format, with metrics)",
    
    "improvement_from_previous": "If previous attempts provided, specific comparison. Otherwise: 'First attempt on this question'"
}}

Respond ONLY with valid JSON. No markdown code blocks, no explanations outside JSON.
"""


CONSOLIDATED_SESSION_FEEDBACK_PROMPT = """You are a senior interview coach creating a comprehensive session report.

## SESSION OVERVIEW
- Total Questions: {num_questions}
- Session Duration: {total_duration} minutes
- Domain Focus: {domain}
- Job Context: {job_context}

## PER-QUESTION PERFORMANCE
{questions_breakdown}

## AGGREGATE SCORES
- Content Average: {avg_content}/100
- Delivery Average: {avg_delivery}/100  
- Communication Average: {avg_communication}/100
- Voice Average: {avg_voice}/100
- Confidence Average: {avg_confidence}/100
- Structure Average: {avg_structure}/100
- Overall Session Score: {session_score}/100

## USER'S IMPROVEMENT HISTORY (IF AVAILABLE)
{improvement_history}

Generate a comprehensive JSON report:

{{
    "session_summary": "3-4 sentence executive summary of this interview session",
    
    "performance_profile": {{
        "strongest_skill": "Which of the 6 skills was best, with evidence",
        "weakest_skill": "Which skill needs most work, with evidence",
        "most_improved": "If history available, which skill improved most",
        "consistency_rating": "How consistent was performance across questions"
    }},
    
    "question_by_question": [
        {{
            "question_num": 1,
            "question_snippet": "First 50 chars of question...",
            "score": 75,
            "one_line_feedback": "Brief assessment of this answer"
        }}
    ],
    
    "top_strengths": [
        "Pattern of strength across multiple answers with examples",
        "Another consistent strength"
    ],
    
    "priority_improvements": [
        {{
            "area": "Skill area needing work",
            "current_level": "Specific assessment of current ability",
            "target_level": "What good looks like",
            "action_plan": "3-step plan to improve"
        }},
        {{
            "area": "Second priority area",
            "current_level": "Assessment",
            "target_level": "Goal",
            "action_plan": "Improvement steps"
        }}
    ],
    
    "interview_readiness": {{
        "score": 0-100,
        "assessment": "Ready / Needs work / Not ready",
        "reasoning": "Why this readiness level"
    }},
    
    "recommended_practice": [
        {{
            "focus_area": "What to practice",
            "exercise": "Specific exercise to do",
            "frequency": "How often"
        }}
    ],
    
    "next_session_focus": "What to prioritize in next practice session"
}}
"""


IMPROVEMENT_INSIGHT_PROMPT = """Analyze this user's improvement journey:

## SKILL PROGRESS DATA
{skill_progress_data}

## RECENT ATTEMPTS (Last 10)
{recent_attempts}

## HISTORICAL TREND
{historical_trend}

Generate improvement insights as JSON:

{{
    "overall_trajectory": "improving/stable/declining with explanation",
    
    "skill_wise_analysis": {{
        "content": {{
            "trend": "improving/stable/declining",
            "change": "+X or -X points",
            "insight": "Why this trend is happening"
        }},
        "delivery": {{...same structure...}},
        "communication": {{...same structure...}},
        "voice": {{...same structure...}},
        "confidence": {{...same structure...}},
        "structure": {{...same structure...}}
    }},
    
    "milestones_achieved": [
        "Specific achievement like 'Improved content score by 15 points'",
        "Another milestone"
    ],
    
    "areas_needing_attention": [
        "Skill that's declining or stagnant with recommendation"
    ],
    
    "personalized_recommendations": [
        "Based on their specific pattern, do X",
        "Given their weakness in Y, practice Z"
    ],
    
    "motivational_message": "Encouraging message based on their actual progress"
}}
"""


# ===========================================
# Core Feedback Generation Functions
# ===========================================

async def generate_dynamic_answer_feedback(
    question: str,
    transcript: str,
    ideal_answer: str,
    ml_scores: Dict[str, Any],
    job_description: Optional[str] = None,
    previous_attempts: Optional[List[Dict]] = None,
    duration_seconds: float = 0
) -> Dict[str, Any]:
    """
    Generate truly dynamic, personalized feedback for an interview answer.
    
    NO templates, NO static responses - pure LLM generation with context.
    
    Args:
        question: The interview question asked
        transcript: Candidate's transcribed answer
        ideal_answer: Reference answer for comparison
        ml_scores: ML-calculated scores (content, delivery, etc.)
        job_description: Optional JD for context
        previous_attempts: Optional list of previous attempts on same question
        duration_seconds: Time taken to answer
    
    Returns:
        Dict with comprehensive, dynamic feedback
    """
    logger.info("Generating dynamic answer feedback with Gemini")
    
    # Build context sections
    job_context = job_description[:1000] if job_description else "No specific job context provided"
    
    previous_context = "No previous attempts on this question"
    if previous_attempts:
        prev_scores = [a.get("final_score", 0) for a in previous_attempts[:3]]
        previous_context = f"Previous attempt scores: {prev_scores}. Comparing for improvement."
    
    # Format prompt
    prompt = DYNAMIC_ANSWER_FEEDBACK_PROMPT.format(
        question=question,
        transcript=transcript,
        ideal_answer=ideal_answer,
        job_context=job_context,
        duration_seconds=duration_seconds,
        content_score=ml_scores.get("content", 0),
        delivery_score=ml_scores.get("delivery", 0),
        communication_score=ml_scores.get("communication", 0),
        voice_score=ml_scores.get("voice", 70),
        confidence_score=ml_scores.get("confidence", 70),
        structure_score=ml_scores.get("structure", 0),
        final_score=ml_scores.get("final", 0),
        wpm=ml_scores.get("wpm", 0),
        filler_count=ml_scores.get("filler_count", 0),
        grammar_errors=ml_scores.get("grammar_errors", 0),
        previous_attempts_context=previous_context
    )
    
    # Call Gemini
    response = await _call_gemini_async(prompt)
    
    # Parse response
    feedback = _parse_json_response(response, _default_dynamic_feedback())
    
    # Add metadata
    feedback["generated_at"] = datetime.utcnow().isoformat()
    feedback["generator_version"] = "dynamic_v2"
    feedback["is_dynamic"] = True
    
    return feedback


async def generate_consolidated_session_feedback(
    session_data: Dict[str, Any],
    attempts: List[Dict[str, Any]],
    user_history: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Generate comprehensive feedback for an entire interview session.
    
    Creates a recruiter-level assessment of the candidate's performance
    across all questions in the session.
    
    Args:
        session_data: Session configuration (domain, JD, etc.)
        attempts: List of all attempts in this session
        user_history: Optional historical performance data
    
    Returns:
        Dict with consolidated session feedback
    """
    logger.info(f"Generating consolidated feedback for session with {len(attempts)} attempts")
    
    # Build questions breakdown
    questions_breakdown = ""
    for i, attempt in enumerate(attempts, 1):
        questions_breakdown += f"""
Question {i}: {attempt.get('question_text', 'Unknown')[:50]}...
- Answer excerpt: "{attempt.get('transcript', '')[:100]}..."
- Score: {attempt.get('final_score', 0)}/100
- Content: {attempt.get('content_score', 0)} | Delivery: {attempt.get('delivery_score', 0)} | Structure: {attempt.get('structure_score', 0)}
---
"""
    
    # Calculate averages
    def safe_avg(field):
        values = [a.get(field, 0) or 0 for a in attempts]
        return round(sum(values) / len(values), 1) if values else 0
    
    # Build improvement history context
    improvement_history = "No previous sessions available for comparison"
    if user_history:
        improvement_history = f"Previous average score: {user_history.get('avg_score', 0)}. Total attempts: {user_history.get('total_attempts', 0)}"
    
    # Calculate total duration
    total_duration = sum(a.get("duration_seconds", 0) for a in attempts) / 60
    
    prompt = CONSOLIDATED_SESSION_FEEDBACK_PROMPT.format(
        num_questions=len(attempts),
        total_duration=round(total_duration, 1),
        domain=session_data.get("domain", "general"),
        job_context=session_data.get("job_description", "No JD provided")[:500],
        questions_breakdown=questions_breakdown,
        avg_content=safe_avg("content_score"),
        avg_delivery=safe_avg("delivery_score"),
        avg_communication=safe_avg("communication_score"),
        avg_voice=safe_avg("voice_score"),
        avg_confidence=safe_avg("confidence_score"),
        avg_structure=safe_avg("structure_score"),
        session_score=safe_avg("final_score"),
        improvement_history=improvement_history
    )
    
    response = await _call_gemini_async(prompt)
    
    feedback = _parse_json_response(response, _default_session_feedback())
    feedback["generated_at"] = datetime.utcnow().isoformat()
    feedback["is_consolidated"] = True
    
    return feedback


async def generate_improvement_insights(
    skill_progress: List[Dict[str, Any]],
    recent_attempts: List[Dict[str, Any]],
    historical_averages: Dict[str, float]
) -> Dict[str, Any]:
    """
    Generate insights about user's improvement over time.
    
    Analyzes trends, milestones, and provides personalized recommendations.
    
    Args:
        skill_progress: Skill-wise progress records
        recent_attempts: Last 10-20 attempts
        historical_averages: Historical average scores
    
    Returns:
        Dict with improvement insights
    """
    logger.info("Generating improvement insights")
    
    # Format skill progress data
    skill_data = json.dumps(skill_progress, indent=2) if skill_progress else "No skill progress data"
    
    # Format recent attempts
    attempts_data = ""
    for i, a in enumerate(recent_attempts[:10], 1):
        attempts_data += f"{i}. Score: {a.get('final_score', 0)} | Date: {a.get('created_at', 'unknown')}\n"
    
    # Historical trend
    trend_data = json.dumps(historical_averages, indent=2)
    
    prompt = IMPROVEMENT_INSIGHT_PROMPT.format(
        skill_progress_data=skill_data,
        recent_attempts=attempts_data or "No recent attempts",
        historical_trend=trend_data
    )
    
    response = await _call_gemini_async(prompt)
    
    return _parse_json_response(response, _default_improvement_insights())


# ===========================================
# Gemini API Integration
# ===========================================

async def _call_gemini_async(prompt: str) -> str:
    """
    Call Gemini API asynchronously for feedback generation.
    
    Handles:
    - API key validation
    - Rate limiting
    - Error handling
    - Response validation
    """
    try:
        import asyncio
        import google.generativeai as genai
        
        # Use the same settings as llm_bridge (LLM_API_KEY / LLM_MODEL).
        # These previously read settings.google_api_key / settings.gemini_model,
        # which don't exist, so every call silently failed and fell back to defaults.
        api_keys = settings.get_all_api_keys()
        if not api_keys:
            logger.warning("No Gemini API key configured (LLM_API_KEY)")
            return ""
        
        genai.configure(api_key=api_keys[0])
        
        model = genai.GenerativeModel(
            model_name=settings.llm_model or "gemini-2.5-flash",
            generation_config={
                "temperature": 0.7,
                "top_p": 0.9,
                "max_output_tokens": 4096,
            }
        )
        
        # The SDK call blocks; run it in a thread so the server stays responsive
        response = await asyncio.to_thread(model.generate_content, prompt)
        
        if response and response.text:
            logger.debug(f"Gemini response length: {len(response.text)}")
            return response.text
        
        logger.warning("Empty response from Gemini")
        return ""
        
    except Exception as e:
        logger.error(f"Gemini API error: {e}", exc_info=True)
        return ""


def _parse_json_response(response: str, default: Dict) -> Dict[str, Any]:
    """
    Parse JSON from LLM response, handling common issues.
    """
    if not response:
        return default
    
    # Clean response
    text = response.strip()
    
    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    
    # Try to find JSON in response
    try:
        # Direct parse
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON object
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except json.JSONDecodeError:
        pass
    
    logger.warning("Could not parse JSON from response, using default")
    return default


# ===========================================
# Default Response Templates (Fallbacks Only)
# ===========================================

def _default_dynamic_feedback() -> Dict[str, Any]:
    """Default feedback structure when LLM fails."""
    return {
        "overall_assessment": "Unable to generate detailed assessment. Please try again.",
        "content_analysis": {
            "score_justification": "Analysis unavailable",
            "key_points_covered": [],
            "key_points_missed": [],
            "relevance_to_question": "Unable to analyze"
        },
        "star_method_breakdown": {
            "situation": {"present": False, "quote": None, "feedback": "Analysis unavailable"},
            "task": {"present": False, "quote": None, "feedback": "Analysis unavailable"},
            "action": {"present": False, "quote": None, "feedback": "Analysis unavailable"},
            "result": {"present": False, "quote": None, "feedback": "Analysis unavailable"}
        },
        "sentence_improvements": [],
        "delivery_feedback": {
            "pace_analysis": "Analysis unavailable",
            "filler_impact": "Analysis unavailable",
            "specific_issues": []
        },
        "strengths": ["Unable to identify strengths - try again"],
        "improvement_areas": ["Unable to identify areas - try again"],
        "skill_gap_analysis": {
            "missing_keywords": [],
            "vocabulary_suggestions": [],
            "industry_alignment": "Analysis unavailable"
        },
        "actionable_tips": [
            "Practice speaking clearly and at a moderate pace",
            "Use the STAR method for behavioral questions",
            "Include specific examples and metrics"
        ],
        "example_answer": "Unable to generate example answer",
        "improvement_from_previous": "Unable to compare",
        "llm_failed": True,
        "llm_error": "Feedback generation failed - using defaults"
    }


def _default_session_feedback() -> Dict[str, Any]:
    """Default session feedback when LLM fails."""
    return {
        "session_summary": "Session feedback generation failed. Please review individual question feedback.",
        "performance_profile": {
            "strongest_skill": "Unable to determine",
            "weakest_skill": "Unable to determine",
            "most_improved": "Unable to determine",
            "consistency_rating": "Unable to assess"
        },
        "question_by_question": [],
        "top_strengths": [],
        "priority_improvements": [],
        "interview_readiness": {
            "score": 0,
            "assessment": "Unable to assess",
            "reasoning": "Feedback generation failed"
        },
        "recommended_practice": [],
        "next_session_focus": "Unable to determine",
        "llm_failed": True
    }


def _default_improvement_insights() -> Dict[str, Any]:
    """Default improvement insights when LLM fails."""
    return {
        "overall_trajectory": "Unable to analyze improvement trajectory",
        "skill_wise_analysis": {},
        "milestones_achieved": [],
        "areas_needing_attention": [],
        "personalized_recommendations": [
            "Continue practicing regularly",
            "Focus on STAR method for behavioral questions",
            "Work on speaking pace and clarity"
        ],
        "motivational_message": "Keep practicing! Every attempt helps you improve.",
        "llm_failed": True
    }
