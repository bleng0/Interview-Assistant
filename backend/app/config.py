"""
AI Interview Feedback MVP - Backend Configuration

This module contains all configuration settings, constants, and environment
variable handling for the application.

Author: Member 1 (Backend API)
"""

import os
from typing import List, Dict
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Attributes:
        llm_provider: LLM provider to use ("gemini", "openai")
        llm_api_key: API key for the LLM provider
        llm_model: Model name to use for LLM calls
        transcription_provider: Transcription provider ("faster_whisper", "openai", "whisper", "assemblyai", "stub")
        whisper_model_size: Model size for Faster-Whisper (tiny, base, small, medium, large-v2, large-v3)
        openai_api_key: OpenAI API key for transcription
        assemblyai_api_key: AssemblyAI API key (free tier available)
        database_url: Database connection URL (PostgreSQL for Supabase)
        cors_origins: Allowed CORS origins
        debug: Debug mode flag
    """
    
    # LLM Configuration (Gemini Free Tier - PRIMARY)
    llm_provider: str = "gemini"
    llm_api_key: str = ""  # Primary key - REQUIRED
    
    # Additional API keys for rotation (2-12)
    llm_api_key_2: str = ""
    llm_api_key_3: str = ""
    llm_api_key_4: str = ""
    llm_api_key_5: str = ""
    llm_api_key_6: str = ""
    llm_api_key_7: str = ""
    llm_api_key_8: str = ""
    llm_api_key_9: str = ""
    llm_api_key_10: str = ""
    llm_api_key_11: str = ""
    llm_api_key_12: str = ""
    
    llm_model: str = "gemini-2.5-flash"  # Updated model name
    
    # Transcription Configuration (Faster-Whisper for local high-quality transcription)
    transcription_provider: str = "faster_whisper"
    whisper_model_size: str = "small"
    openai_api_key: str = ""
    assemblyai_api_key: str = ""
    
    # Hybrid Transcription Configuration
    hybrid_mode_enabled: bool = True
    hybrid_primary_provider: str = "faster_whisper"
    hybrid_fallback_provider: str = "stub"
    hybrid_confidence_threshold: float = 0.7
    
    # Supabase Configuration (Cloud Database + Auth + Storage)
    # ONLY needs URL + anon key - NO DATABASE_URL NEEDED!
    supabase_url: str = ""  # https://your-project.supabase.co
    supabase_key: str = ""  # anon/public key (starts with eyJ...)
    supabase_service_role_key: str = ""  # Service role key for server-side operations (bypasses RLS)
    supabase_jwt_secret: str = ""  # Optional: JWT secret for token validation
    
    # REMOVED: database_url - Not needed, using Supabase REST API only!
    
    # Storage Configuration
    storage_bucket_audio: str = "audio-recordings"
    storage_bucket_resumes: str = "resumes"
    storage_bucket_transcripts: str = "transcripts"
    
    # CORS Configuration
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    # Debug Mode (off by default; set DEBUG=true in .env for local development).
    # When off, /docs and /redoc are disabled and error details are hidden.
    debug: bool = False

    # Admin users (comma-separated emails) allowed to manage the question pool.
    # Empty = no admins, so admin-only endpoints are closed.
    admin_emails: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"
    
    def get_cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def get_admin_emails(self) -> List[str]:
        """Parse admin emails from comma-separated string (lower-cased)."""
        return [e.strip().lower() for e in self.admin_emails.split(",") if e.strip()]

    def get_all_api_keys(self) -> List[str]:
        """
        Get all configured Gemini API keys.
        
        Returns:
            List of valid API keys (non-empty)
        """
        keys = []
        
        # Add primary key
        if self.llm_api_key:
            keys.append(self.llm_api_key)
        
        # Add additional keys (2-12)
        for i in range(2, 13):
            key_attr = f"llm_api_key_{i}"
            key_value = getattr(self, key_attr, "")
            if key_value and key_value.strip():
                keys.append(key_value.strip())
        
        return keys

# ===========================================
# 6-SCORE SYSTEM Configuration
# ===========================================

# Main score weights (must sum to 1.0)
# Enhanced from 4 to 6 categories for better user clarity
SCORE_WEIGHTS: Dict[str, float] = {
    "content": 0.30,        # Answer relevance & topic coverage
    "delivery": 0.15,       # Speaking pace, filler words
    "communication": 0.15,  # Grammar, vocabulary, coherence
    "voice": 0.15,          # Pitch, energy, pauses, rhythm (NEW)
    "confidence": 0.15,     # Voice + video confidence metrics (NEW)
    "structure": 0.10       # STAR method, organization (NEW)
}

# Valid score range
MIN_SCORE: int = 0
MAX_SCORE: int = 100


# ===========================================
# Delivery Scoring Configuration
# ===========================================

# Optimal words-per-minute range for speaking
# Professional speaking rate is typically 130-160 WPM
OPTIMAL_WPM_MIN: int = 130
OPTIMAL_WPM_MAX: int = 160

# WPM penalty thresholds
WPM_TOO_SLOW: int = 100     # Speaking too slowly below this
WPM_TOO_FAST: int = 180     # Speaking too fast above this

# List of common filler words to detect
FILLER_WORDS: List[str] = [
    "um", "uh", "umm", "uhh", "er", "err",
    "like", "you know", "basically", "actually",
    "literally", "honestly", "right", "okay",
    "so", "well", "I mean", "kind of", "sort of",
    "you see", "I guess", "anyway"
]

# Filler word penalty per occurrence (subtracted from delivery score)
FILLER_PENALTY_PER_WORD: float = 2.0

# Maximum filler penalty (cap to avoid negative scores)
MAX_FILLER_PENALTY: float = 30.0


# ===========================================
# Grammar/Communication Configuration
# ===========================================

# Penalty per grammar error (subtracted from communication score)
GRAMMAR_PENALTY_PER_ERROR: float = 3.0

# Maximum grammar penalty
MAX_GRAMMAR_PENALTY: float = 40.0


# ===========================================
# Enhanced Communication Scoring Configuration
# ===========================================

# Weights for communication score components (must sum to 1.0)
COMMUNICATION_WEIGHTS: Dict[str, float] = {
    "grammar": 0.30,               # Grammar quality (existing)
    "vocabulary_diversity": 0.25,  # Type-Token Ratio scoring
    "sentence_complexity": 0.15,   # Sentence structure variety
    "coherence": 0.15,             # Flow and transitions
    "professional_vocab": 0.15     # Professional language usage
}

# --- Vocabulary Diversity (Type-Token Ratio) ---
TTR_EXCELLENT: float = 0.65  # Above = excellent vocabulary diversity
TTR_GOOD: float = 0.50       # Above = good vocabulary diversity
TTR_POOR: float = 0.30       # Below = poor vocabulary diversity

# --- Sentence Complexity ---
SENTENCE_LENGTH_MIN: int = 8    # Too short below this
SENTENCE_LENGTH_MAX: int = 30   # Too long above this
SENTENCE_LENGTH_OPTIMAL_MIN: int = 12
SENTENCE_LENGTH_OPTIMAL_MAX: int = 20

# --- Coherence/Flow: Transition Words ---
TRANSITION_WORDS: List[str] = [
    # Sequence/Order
    "first", "second", "third", "finally", "next", "then", "lastly",
    # Addition
    "additionally", "moreover", "furthermore", "also", "besides", "in addition",
    # Contrast
    "however", "although", "nevertheless", "on the other hand", "conversely", "but",
    # Cause/Effect
    "therefore", "consequently", "as a result", "because", "thus", "hence",
    # Examples
    "for example", "for instance", "specifically", "such as", "namely",
    # Conclusion
    "in conclusion", "to summarize", "overall", "in summary", "ultimately"
]

# --- Professional Vocabulary ---
PROFESSIONAL_TERMS: List[str] = [
    # Action verbs (power words for interviews)
    "implemented", "developed", "managed", "coordinated", "analyzed",
    "designed", "optimized", "established", "facilitated", "achieved",
    "collaborated", "executed", "strategized", "delegated", "evaluated",
    "led", "created", "resolved", "improved", "streamlined",
    "initiated", "delivered", "mentored", "negotiated", "presented",
    # Business/Technical terms
    "stakeholder", "deliverable", "milestone", "objective", "deadline",
    "benchmark", "metrics", "strategy", "framework", "methodology",
    "scalable", "efficient", "innovative", "proactive", "comprehensive"
]

# --- Articulation/Clarity (Additional Factor) ---
CLARITY_INDICATORS: List[str] = [
    # Clear expression markers
    "specifically", "clearly", "precisely", "exactly", "particularly",
    # Structure markers
    "the reason is", "this means", "in other words", "to clarify"
]

# Minimum words for reliable communication analysis
MIN_WORDS_FOR_ANALYSIS: int = 20


# ===========================================
# Content/Relevance Configuration
# ===========================================

# Minimum similarity threshold for positive content score
MIN_SIMILARITY_THRESHOLD: float = 0.3

# Similarity to score conversion factor
# similarity_score * SIMILARITY_MULTIPLIER = content_score
SIMILARITY_MULTIPLIER: float = 100.0


# ===========================================
# Resume Analysis Configuration
# ===========================================

# Minimum skill match percentage to be considered a good match
MIN_SKILL_MATCH_PCT: float = 60.0

# Common skill keywords to look for (can be extended)
COMMON_SKILLS: List[str] = [
    # Programming Languages
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby", "php",
    # Web Technologies
    "html", "css", "react", "angular", "vue", "node.js", "express", "django", "flask", "fastapi",
    # Databases
    "sql", "mysql", "postgresql", "mongodb", "redis", "elasticsearch",
    # Cloud & DevOps
    "aws", "azure", "gcp", "docker", "kubernetes", "ci/cd", "jenkins", "terraform",
    # Data & ML
    "machine learning", "deep learning", "tensorflow", "pytorch", "pandas", "numpy", "data analysis",
    # Soft Skills
    "leadership", "communication", "teamwork", "problem solving", "agile", "scrum"
]


# ===========================================
# VOICE ANALYSIS Configuration (NEW)
# ===========================================

# Voice score component weights (must sum to 1.0)
VOICE_WEIGHTS: Dict[str, float] = {
    "pitch_variation": 0.25,      # Expressive vs monotone
    "energy_projection": 0.25,    # Volume/confidence
    "pause_appropriateness": 0.20, # Natural pausing
    "energy_consistency": 0.15,   # Nervousness indicator
    "rhythm_stability": 0.15      # Pacing consistency
}

# Pitch variation thresholds (Hz standard deviation)
PITCH_STD_MONOTONE: float = 15.0      # Below = monotone
PITCH_STD_OPTIMAL_MIN: float = 25.0   # Optimal range start
PITCH_STD_OPTIMAL_MAX: float = 50.0   # Optimal range end
PITCH_STD_DRAMATIC: float = 70.0      # Above = overly dramatic

# Energy/Volume thresholds (dB)
ENERGY_DB_QUIET: float = 45.0         # Below = too quiet
ENERGY_DB_OPTIMAL_MIN: float = 55.0   # Optimal range start
ENERGY_DB_OPTIMAL_MAX: float = 70.0   # Optimal range end
ENERGY_DB_LOUD: float = 80.0          # Above = too loud

# Pause thresholds (pauses per minute)
PAUSE_PER_MIN_TOO_FEW: int = 2        # Too rushed
PAUSE_PER_MIN_OPTIMAL_MIN: int = 3    # Natural start
PAUSE_PER_MIN_OPTIMAL_MAX: int = 8    # Natural end
PAUSE_PER_MIN_TOO_MANY: int = 12      # Too hesitant


# ===========================================
# CONFIDENCE Score Configuration (NEW)
# ===========================================

# Confidence score component weights (must sum to 1.0)
CONFIDENCE_WEIGHTS: Dict[str, float] = {
    "voice_confidence": 0.40,     # From voice analysis
    "eye_contact": 0.30,          # From video
    "body_stability": 0.20,       # From video
    "emotion_positivity": 0.10    # From voice/video
}


# ===========================================
# STRUCTURE Score Configuration (NEW)
# ===========================================

# Structure score component weights (must sum to 1.0)
STRUCTURE_WEIGHTS: Dict[str, float] = {
    "star_method": 0.50,          # STAR format usage
    "organization": 0.30,         # Logical flow
    "conclusion": 0.20            # Clear ending
}

# STAR method keywords for detection
STAR_SITUATION_KEYWORDS: List[str] = [
    "situation", "context", "background", "when", "there was", "faced with",
    "challenge was", "problem was", "at the time", "in my role"
]

STAR_TASK_KEYWORDS: List[str] = [
    "task", "responsible for", "my role", "needed to", "had to",
    "goal was", "objective was", "assigned to", "in charge of"
]

STAR_ACTION_KEYWORDS: List[str] = [
    "action", "i did", "i took", "implemented", "developed", "created",
    "initiated", "led", "organized", "coordinated", "decided to"
]

STAR_RESULT_KEYWORDS: List[str] = [
    "result", "outcome", "achieved", "increased", "decreased", "improved",
    "saved", "reduced", "generated", "led to", "resulted in", "percent"
]


# ===========================================
# CONTENT Score Sub-weights (NEW)
# ===========================================

CONTENT_WEIGHTS: Dict[str, float] = {
    "semantic_similarity": 0.50,  # Overall meaning match
    "keyword_coverage": 0.30,     # Topic keywords covered
    "topic_depth": 0.20           # Detail level
}


# ===========================================
# QUALITY GATES - Strict Scoring Validation (NEW)
# ===========================================

# Quality gates to prevent inflated scores for poor answers
QUALITY_GATES: Dict[str, Dict] = {
    # Minimum word count for a valid answer
    "min_word_count": {
        "threshold": 15,
        "penalty": 50,  # Subtract 50 from final if below threshold
        "message": "Answer too short - provide more detail"
    },
    # Minimum unique words (vocabulary)
    "min_unique_words": {
        "threshold": 10,
        "penalty": 30,
        "message": "Limited vocabulary - use more varied words"
    },
    # Maximum filler ratio (fillers / total words)
    "max_filler_ratio": {
        "threshold": 0.15,  # 15% fillers = bad
        "penalty": 25,
        "message": "Too many filler words - practice speaking clearly"
    },
    # Minimum relevance to question
    "min_relevance": {
        "threshold": 0.25,  # 25% semantic match minimum
        "penalty": 40,
        "message": "Answer does not address the question"
    },
    # Maximum repetition score (same phrases repeated)
    "max_repetition": {
        "threshold": 0.3,  # 30% repetition = bad
        "penalty": 20,
        "message": "Avoid repeating the same phrases"
    }
}

# Nonsense detection patterns
NONSENSE_PATTERNS: List[str] = [
    r'\b(asdf|qwerty|lorem|ipsum|blah|test|testing|hello|hi|hey)\b',
    r'(.)\1{4,}',  # Same character repeated 5+ times
    r'\b(\w{1,2}\s){5,}',  # Many 1-2 letter words in sequence
]

# Minimum coherence thresholds
MIN_COHERENCE_SCORE: float = 30.0  # Below this = gibberish

# Score caps for poor quality answers
SCORE_CAPS: Dict[str, int] = {
    "very_short": 40,      # < 15 words
    "short": 60,           # < 30 words
    "no_structure": 55,    # No STAR components
    "off_topic": 35,       # < 20% relevance
    "nonsense": 15,        # Detected nonsense patterns
}


# ===========================================
# DELIVERY Score Sub-weights (NEW)
# ===========================================

DELIVERY_WEIGHTS: Dict[str, float] = {
    "speaking_pace": 0.50,        # WPM score
    "filler_words": 0.30,         # Filler penalty
    "clarity": 0.20               # Clear articulation
}


# ===========================================
# File Upload Configuration
# ===========================================

# Maximum file sizes (in bytes)
MAX_RESUME_SIZE: int = 10 * 1024 * 1024  # 10 MB
MAX_AUDIO_SIZE: int = 50 * 1024 * 1024   # 50 MB

# Allowed file extensions
ALLOWED_RESUME_EXTENSIONS: List[str] = [".pdf", ".docx", ".doc"]
ALLOWED_AUDIO_EXTENSIONS: List[str] = [".wav", ".mp3", ".m4a", ".webm", ".ogg"]

# Upload directory
UPLOAD_DIR: str = os.path.join(os.path.dirname(__file__), "..", "uploads")


# ===========================================
# Transcription Configuration
# ===========================================

# OpenAI Whisper model for transcription
WHISPER_MODEL: str = "whisper-1"

# Language for transcription (None for auto-detect)
TRANSCRIPTION_LANGUAGE: str = "en"


# ===========================================
# Singleton Settings Instance
# ===========================================

# Create a global settings instance
settings = Settings()


# Initialize Key Manager if multiple keys are configured
try:
    from app.services.key_manager import initialize_key_manager
    
    api_keys = settings.get_all_api_keys()
    if len(api_keys) > 1:
        initialize_key_manager(api_keys)
        print(f"✓ Initialized key rotation with {len(api_keys)} Gemini API keys")
    elif len(api_keys) == 1:
        print(f"ℹ Using single Gemini API key (add more keys to .env for rotation)")
    else:
        print(f"⚠ Warning: No Gemini API keys configured")
except Exception as e:
    print(f"⚠ Failed to initialize key manager: {e}")


def get_settings() -> Settings:
    """
    Get the application settings instance.
    
    Returns:
        Settings: The global settings instance
    """
    return settings


# ===========================================
# Upload Directory Configuration
# ===========================================

# Create upload directory path
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
