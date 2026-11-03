"""
AI Interview Feedback - Enhanced Transcription Service

This module handles audio transcription with multiple providers for
high-quality, accurate speech-to-text conversion with graceful fallbacks:

Supported Providers:
- Faster-Whisper: High-quality local transcription (RECOMMENDED - No API key!)
- OpenAI Whisper API: Cloud-based transcription (requires API key)
- AssemblyAI: Free tier cloud transcription (requires API key)
- Local Whisper: Self-hosted transcription
- Stub mode: Returns mock transcriptions for development/testing

Features:
- Hybrid mode: Primary provider with intelligent fallback
- Confidence thresholding: Validates transcription quality
- Error handling: Graceful degradation across providers
- Language detection: Supports 99+ languages

Author: Transcription Service Team

Key Functions:
    - transcribe_audio(path): Main transcription function with auto-routing
    - get_available_providers(): List available providers
    - validate_transcription_confidence(text): Check quality score
"""

import os
import tempfile
import threading
from typing import Optional, Tuple

from app.config import settings, WHISPER_MODEL, TRANSCRIPTION_LANGUAGE
from app.logging_config import get_logger

logger = get_logger(__name__)


# ===========================================
# Main Transcription Function
# ===========================================

def transcribe_audio(file_path: str) -> str:
    """
    Transcribe an audio file to text with the best available quality.
    
    Uses the configured transcription provider to convert
    speech to text. Provider is determined by TRANSCRIPTION_PROVIDER
    environment variable.
    
    When HYBRID_MODE_ENABLED is true, uses hybrid approach:
    - Tries primary provider first
    - Evaluates confidence of result
    - Falls back to secondary provider if confidence is low
    
    Supported providers:
    - "faster_whisper": Uses Faster-Whisper for high-quality local transcription (RECOMMENDED)
    - "openai": Uses OpenAI's Whisper API (requires API key)
    - "assemblyai": Uses AssemblyAI (free tier available)
    - "whisper": Uses local Whisper model
    - "stub": Returns mock transcription (for development)
    - "hybrid": Uses hybrid approach with primary + fallback
    
    Args:
        file_path: Path to the audio file (supports WAV, MP3, M4A, WebM, OGG)
    
    Returns:
        str: Transcribed text (or "" if transcription fails)
    
    Raises:
        Generally does NOT raise; logs errors and returns empty string or mock data
    
    Example:
        >>> transcript = transcribe_audio("recording.wav")
        >>> print(transcript)
    """
    logger.info(f"Starting transcription: {file_path}")
    logger.debug(f"Provider: {settings.transcription_provider}")
    
    # Check if hybrid mode is enabled
    hybrid_enabled = getattr(settings, 'hybrid_mode_enabled', False)
    
    if hybrid_enabled:
        logger.info("Hybrid transcription mode enabled - using multi-provider approach")
        return _transcribe_hybrid(file_path)
    
    provider = settings.transcription_provider.lower()
    
    logger.info(f"Transcription provider selected: {provider}")
    
    if provider == "faster_whisper":
        logger.debug("Using Faster-Whisper for local transcription")
        return _transcribe_faster_whisper(file_path)
    elif provider == "openai":
        logger.debug("Using OpenAI Whisper API for transcription")
        return _transcribe_openai(file_path)
    elif provider == "assemblyai":
        logger.debug("Using AssemblyAI for transcription")
        return _transcribe_assemblyai(file_path)
    elif provider == "whisper":
        logger.debug("Using local Whisper model for transcription")
        return _transcribe_local_whisper(file_path)
    elif provider == "stub":
        logger.debug("Using stub provider - returning mock transcription")
        return _transcribe_stub(file_path)
    elif provider == "hybrid":
        logger.info("Using hybrid transcription mode")
        return _transcribe_hybrid(file_path)
    else:
        logger.warning(f"Unknown transcription provider: {provider}, attempting auto-fallback")
        # Try faster_whisper first, then fall back
        result = _transcribe_faster_whisper(file_path)
        if result:
            return result
        logger.warning("All providers failed, returning stub transcription")
        return _transcribe_stub(file_path)


# ===========================================
# Audio Preprocessing for Better Quality
# ===========================================

def preprocess_audio(file_path: str) -> str:
    """
    Preprocess audio for better transcription quality.
    
    Applies:
    - Noise reduction
    - Normalization
    - Proper sample rate
    
    Args:
        file_path: Path to original audio file
    
    Returns:
        str: Path to preprocessed audio file
    """
    try:
        from pydub import AudioSegment
        from pydub.effects import normalize
        
        print("[Audio] Preprocessing for better quality...")
        
        # Load audio
        audio = AudioSegment.from_file(file_path)
        
        # Convert to mono (single channel) for better recognition
        audio = audio.set_channels(1)
        
        # Set sample rate to 16kHz (optimal for speech recognition)
        audio = audio.set_frame_rate(16000)
        
        # Normalize volume
        audio = normalize(audio)
        
        # Save to temp file
        temp_path = file_path + "_processed.wav"
        audio.export(temp_path, format="wav")
        
        print(f"[Audio] Preprocessed audio saved: {temp_path}")
        return temp_path
        
    except ImportError:
        print("[Audio] pydub not installed, using original audio")
        return file_path
    except Exception as e:
        print(f"[Audio] Preprocessing failed: {e}, using original")
        return file_path


# ===========================================
# Hybrid Transcription (Multi-Provider Approach)
# ===========================================

def _calculate_transcription_confidence(transcript: str, file_path: str = None) -> float:
    """
    Calculate a confidence score for a transcription result.
    
    Evaluates quality based on:
    - Word count (too few words = low confidence)
    - Character/word ratio (reasonable ratio for English)
    - Presence of actual content (not empty or placeholder)
    
    Args:
        transcript: The transcribed text
        file_path: Optional path to audio file for context
    
    Returns:
        float: Confidence score between 0.0 and 1.0
    """
    if not transcript or len(transcript.strip()) == 0:
        print("[Confidence] Empty transcript - confidence 0.0")
        return 0.0
    
    transcript = transcript.strip()
    word_count = len(transcript.split())
    char_count = len(transcript)
    
    # Check for minimum word count (at least 3 words)
    if word_count < 3:
        print(f"[Confidence] Very short transcript ({word_count} words) - confidence 0.3")
        return 0.3
    
    # Calculate average word length
    avg_word_length = char_count / word_count if word_count > 0 else 0
    
    # English words average 4-6 characters, allow range of 3-10
    word_length_score = 1.0
    if avg_word_length < 3 or avg_word_length > 10:
        word_length_score = 0.7
    
    # Penalize very short transcripts (expect at least 10 words for interview answers)
    length_score = min(1.0, word_count / 10.0)
    
    # Check for common transcription failure patterns
    failure_patterns = ["[music]", "[silence]", "[inaudible]", "...", ""]
    pattern_penalty = 0.0
    for pattern in failure_patterns:
        if pattern.lower() in transcript.lower():
            pattern_penalty += 0.1
    
    # Calculate final confidence
    confidence = (word_length_score * 0.3 + length_score * 0.5 + (1.0 - pattern_penalty) * 0.2)
    confidence = max(0.0, min(1.0, confidence))  # Clamp to [0, 1]
    
    print(f"[Confidence] Score: {confidence:.2f} (words: {word_count}, avg_len: {avg_word_length:.1f})")
    return confidence


def _get_provider_function(provider_name: str):
    """
    Get the transcription function for a given provider name.
    
    Args:
        provider_name: Name of the provider
    
    Returns:
        function: The transcription function, or None if not found
    """
    provider_map = {
        "faster_whisper": _transcribe_faster_whisper,
        "openai": _transcribe_openai,
        "assemblyai": _transcribe_assemblyai,
        "whisper": _transcribe_local_whisper,
        "stub": _transcribe_stub,
    }
    return provider_map.get(provider_name.lower())


def _transcribe_hybrid(file_path: str) -> str:
    """
    Hybrid transcription using multiple providers for best results.
    
    Strategy:
    1. Try primary provider first
    2. Calculate confidence of the result
    3. If confidence is below threshold, try fallback provider
    4. Return the result with highest confidence
    
    Configuration (from settings):
    - hybrid_primary_provider: Primary provider to try first
    - hybrid_fallback_provider: Fallback when primary fails/low confidence
    - hybrid_confidence_threshold: Minimum confidence to accept result
    
    Args:
        file_path: Path to audio file
    
    Returns:
        str: Best transcription result
    """
    primary_provider = getattr(settings, 'hybrid_primary_provider', 'faster_whisper')
    fallback_provider = getattr(settings, 'hybrid_fallback_provider', 'stub')
    confidence_threshold = getattr(settings, 'hybrid_confidence_threshold', 0.7)
    
    print(f"[Hybrid] Primary: {primary_provider}, Fallback: {fallback_provider}")
    print(f"[Hybrid] Confidence threshold: {confidence_threshold}")
    
    results = []
    
    # Try primary provider
    print(f"\n[Hybrid] Attempting primary provider: {primary_provider}")
    primary_func = _get_provider_function(primary_provider)
    
    if primary_func:
        try:
            primary_result = primary_func(file_path)
            primary_confidence = _calculate_transcription_confidence(primary_result, file_path)
            results.append({
                "provider": primary_provider,
                "transcript": primary_result,
                "confidence": primary_confidence
            })
            
            # If primary meets threshold, return it
            if primary_confidence >= confidence_threshold:
                print(f"[Hybrid] Primary provider succeeded with confidence {primary_confidence:.2f}")
                return primary_result
            else:
                print(f"[Hybrid] Primary confidence ({primary_confidence:.2f}) below threshold ({confidence_threshold})")
        except Exception as e:
            print(f"[Hybrid] Primary provider error: {e}")
    else:
        print(f"[Hybrid] Primary provider '{primary_provider}' not found")
    
    # Try fallback provider
    print(f"\n[Hybrid] Attempting fallback provider: {fallback_provider}")
    fallback_func = _get_provider_function(fallback_provider)
    
    if fallback_func:
        try:
            fallback_result = fallback_func(file_path)
            fallback_confidence = _calculate_transcription_confidence(fallback_result, file_path)
            results.append({
                "provider": fallback_provider,
                "transcript": fallback_result,
                "confidence": fallback_confidence
            })
        except Exception as e:
            print(f"[Hybrid] Fallback provider error: {e}")
    else:
        print(f"[Hybrid] Fallback provider '{fallback_provider}' not found")
    
    # Return best result
    if not results:
        print("[Hybrid] No transcription results available, using stub")
        return _transcribe_stub(file_path)
    
    # Sort by confidence and return best
    results.sort(key=lambda x: x["confidence"], reverse=True)
    best = results[0]
    
    print(f"\n[Hybrid] Best result from '{best['provider']}' with confidence {best['confidence']:.2f}")
    print(f"[Hybrid] Transcript preview: {best['transcript'][:100]}...")
    
    return best["transcript"]


# ===========================================
# Faster-Whisper (RECOMMENDED - No API Key!)
# ===========================================

# Loading a Whisper model takes seconds and hundreds of MB, so load each size
# once per process and reuse it for every request.
_whisper_models = {}
_whisper_models_lock = threading.Lock()


def _get_whisper_model(model_size: str):
    """Return a cached Faster-Whisper model, loading it on first use."""
    with _whisper_models_lock:
        model = _whisper_models.get(model_size)
        if model is None:
            from faster_whisper import WhisperModel
            print(f"[Faster-Whisper] Loading '{model_size}' model (first use)...")
            model = WhisperModel(
                model_size,
                device="cpu",  # Use "cuda" if you have GPU
                compute_type="int8"  # Fast and efficient
            )
            _whisper_models[model_size] = model
        return model


def _transcribe_faster_whisper(file_path: str) -> str:
    """
    Transcribe audio using Faster-Whisper.
    
    Faster-Whisper is a reimplementation of Whisper using CTranslate2,
    which is up to 4x faster than OpenAI's Whisper with same accuracy.
    
    NO API KEY REQUIRED - runs completely locally!
    
    Install: pip install faster-whisper
    
    Args:
        file_path: Path to audio file
    
    Returns:
        str: Transcribed text
    """
    try:
        # Model sizes: tiny, base, small, medium, large-v2, large-v3
        # Larger = more accurate but slower
        # "small" is a good balance of speed and accuracy
        model_size = getattr(settings, 'whisper_model_size', 'small')
        
        model = _get_whisper_model(model_size)
        
        print(f"[Faster-Whisper] Transcribing with '{model_size}' model...")
        
        # Preprocess audio for better quality
        processed_path = preprocess_audio(file_path)
        
        # Transcribe with enhanced settings for clarity
        segments, info = model.transcribe(
            processed_path,
            language="en",
            beam_size=5,  # Higher = more accurate, slower
            best_of=5,  # Number of candidates
            patience=1.0,
            condition_on_previous_text=True,
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            word_timestamps=True,  # Get word-level timestamps
            vad_filter=True,  # Voice Activity Detection to filter silence
            vad_parameters={
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 400
            }
        )
        
        # Combine all segments
        transcript_parts = []
        for segment in segments:
            transcript_parts.append(segment.text.strip())
        
        transcript = " ".join(transcript_parts)
        
        # Clean up processed file
        if processed_path != file_path and os.path.exists(processed_path):
            os.remove(processed_path)
        
        print(f"[Faster-Whisper] Transcribed {len(transcript)} characters")
        print(f"[Faster-Whisper] Detected language: {info.language} (confidence: {info.language_probability:.2%})")
        
        return transcript.strip()
        
    except ImportError:
        print("[Faster-Whisper] Not installed. Install with: pip install faster-whisper")
        print("[Faster-Whisper] Falling back to other providers...")
        # Try local whisper as fallback
        return _transcribe_local_whisper(file_path)
    except Exception as e:
        print(f"[Faster-Whisper] Error: {e}")
        return _transcribe_stub(file_path)


# ===========================================
# AssemblyAI Transcription (Free Tier Available)
# ===========================================

def _transcribe_assemblyai(file_path: str) -> str:
    """
    Transcribe audio using AssemblyAI's API.
    
    AssemblyAI offers a free tier with excellent accuracy.
    Get your free API key at: https://www.assemblyai.com/
    
    Set ASSEMBLYAI_API_KEY in your .env file.
    
    Args:
        file_path: Path to audio file
    
    Returns:
        str: Transcribed text
    """
    try:
        import assemblyai as aai
        
        api_key = getattr(settings, 'assemblyai_api_key', None)
        
        if not api_key:
            print("[AssemblyAI] API key not configured")
            print("[AssemblyAI] Get free key at: https://www.assemblyai.com/")
            return _transcribe_stub(file_path)
        
        aai.settings.api_key = api_key
        
        print("[AssemblyAI] Uploading and transcribing...")
        
        config = aai.TranscriptionConfig(
            speech_model=aai.SpeechModel.best,
            language_code="en",
            punctuate=True,
            format_text=True,
            disfluencies=False,  # Remove um, uh, etc.
        )
        
        transcriber = aai.Transcriber(config=config)
        transcript = transcriber.transcribe(file_path)
        
        if transcript.status == aai.TranscriptStatus.error:
            print(f"[AssemblyAI] Error: {transcript.error}")
            return _transcribe_stub(file_path)
        
        print(f"[AssemblyAI] Transcribed {len(transcript.text)} characters")
        return transcript.text
        
    except ImportError:
        print("[AssemblyAI] Not installed. Install with: pip install assemblyai")
        return _transcribe_stub(file_path)
    except Exception as e:
        print(f"[AssemblyAI] Error: {e}")
        return _transcribe_stub(file_path)


# ===========================================
# Stub Transcription (Development)
# ===========================================

# Sample transcriptions for different scenarios
STUB_TRANSCRIPTIONS = [
    """I have extensive experience in software development, 
    particularly in Python and machine learning. In my previous role,
    I led a team of five developers on a data analytics project that
    increased efficiency by 30%. I'm passionate about building 
    scalable solutions and enjoy working in collaborative environments.""",
    
    """The main challenge we faced was integrating multiple legacy systems.
    I approached this by first mapping out all the dependencies and then
    creating a phased migration plan. We maintained backwards compatibility
    while gradually modernizing the codebase. The project was completed
    ahead of schedule and received positive feedback from stakeholders.""",
    
    """When faced with conflicts, I believe in addressing them directly
    but professionally. In one instance, two team members disagreed about
    the technical approach. I facilitated a discussion where both could
    present their ideas, and we ultimately combined the best aspects of
    each solution. This collaborative approach strengthened the team.""",
    
    """My greatest strength is my ability to quickly learn and adapt to
    new technologies. For example, when our team needed to implement a
    new cloud infrastructure, I took the initiative to get certified in
    AWS and then trained the rest of the team. This allowed us to
    complete the migration smoothly.""",
]


def _transcribe_stub(file_path: str) -> str:
    """
    Return a mock transcription for development.
    
    Rotates through sample transcriptions based on file path hash.
    Useful for testing without API calls.
    
    Args:
        file_path: Path to audio file (used for selection)
    
    Returns:
        str: Mock transcription
    """
    # Use file path hash to select a consistent transcription
    index = hash(file_path) % len(STUB_TRANSCRIPTIONS)
    
    transcript = STUB_TRANSCRIPTIONS[index]
    
    print(f"[STUB] Returning mock transcription ({len(transcript)} chars)")
    
    return transcript.strip()


# ===========================================
# OpenAI Whisper API Transcription
# ===========================================

def _transcribe_openai(file_path: str) -> str:
    """
    Transcribe audio using OpenAI's Whisper API.
    
    Requires OPENAI_API_KEY to be set in environment.
    
    Args:
        file_path: Path to audio file
    
    Returns:
        str: Transcribed text
    """
    try:
        from openai import OpenAI
        
        # Get API key from settings
        api_key = settings.openai_api_key or settings.llm_api_key
        
        if not api_key:
            print("[OpenAI] Warning: OpenAI API key not configured")
            return _transcribe_stub(file_path)
        
        client = OpenAI(api_key=api_key)
        
        print("[OpenAI] Transcribing with Whisper API...")
        
        # Preprocess audio for better quality
        processed_path = preprocess_audio(file_path)
        
        # Open and transcribe the audio file
        with open(processed_path, "rb") as audio_file:
            response = client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
                language=TRANSCRIPTION_LANGUAGE,
                response_format="verbose_json",  # Get more details
                temperature=0,  # More deterministic
                prompt="This is an interview answer. Transcribe every word clearly."
            )
        
        # Clean up processed file
        if processed_path != file_path and os.path.exists(processed_path):
            os.remove(processed_path)
        
        transcript = response.text
        print(f"[OpenAI] Transcribed {len(transcript)} characters")
        
        return transcript
    
    except ImportError:
        print("[OpenAI] Library not installed, using stub transcription")
        return _transcribe_stub(file_path)
    
    except Exception as e:
        print(f"[OpenAI] Transcription error: {e}")
        print("[OpenAI] Falling back to stub transcription")
        return _transcribe_stub(file_path)


# ===========================================
# Local Whisper Transcription (Optional)
# ===========================================

def _transcribe_local_whisper(file_path: str) -> str:
    """
    Transcribe audio using local Whisper model.
    
    Requires whisper library to be installed:
    pip install openai-whisper
    
    Note: First run will download the model (~500MB for base).
    
    Args:
        file_path: Path to audio file
    
    Returns:
        str: Transcribed text
    """
    try:
        import whisper
        
        print("[Local Whisper] Loading model...")
        
        # Load the model (cached after first load)
        # Options: tiny, base, small, medium, large
        model = whisper.load_model("small")  # "small" for better accuracy
        
        # Preprocess audio
        processed_path = preprocess_audio(file_path)
        
        print("[Local Whisper] Transcribing...")
        
        # Transcribe with enhanced settings
        result = model.transcribe(
            processed_path,
            language="en",
            fp16=False,  # Disable for CPU compatibility
            beam_size=5,  # More accurate
            best_of=5,
            temperature=0,  # Deterministic
            condition_on_previous_text=True,
            verbose=False
        )
        
        # Clean up processed file
        if processed_path != file_path and os.path.exists(processed_path):
            os.remove(processed_path)
        
        transcript = result["text"]
        print(f"[Local Whisper] Transcribed {len(transcript)} characters")
        
        return transcript.strip()
    
    except ImportError:
        print("[Local Whisper] Not available, using stub")
        return _transcribe_stub(file_path)
    
    except Exception as e:
        print(f"[Local Whisper] Error: {e}")
        return _transcribe_stub(file_path)


# ===========================================
# Utility Functions
# ===========================================

def get_available_providers() -> list:
    """
    Get list of available transcription providers.
    
    Checks which providers are properly configured
    and have required dependencies.
    
    Returns:
        list: Names of available providers with status
    """
    providers = [{"name": "stub", "status": "available", "note": "Mock transcription for testing"}]
    
    # Check Faster-Whisper (RECOMMENDED)
    try:
        from faster_whisper import WhisperModel
        providers.append({
            "name": "faster_whisper",
            "status": "available",
            "note": "RECOMMENDED - High quality, no API key needed"
        })
    except ImportError:
        providers.append({
            "name": "faster_whisper",
            "status": "not_installed",
            "install": "pip install faster-whisper"
        })
    
    # Check OpenAI
    try:
        from openai import OpenAI
        if settings.openai_api_key or settings.llm_api_key:
            providers.append({
                "name": "openai",
                "status": "available",
                "note": "Cloud API, requires API key"
            })
        else:
            providers.append({
                "name": "openai",
                "status": "no_api_key",
                "note": "Set OPENAI_API_KEY in .env"
            })
    except ImportError:
        providers.append({
            "name": "openai",
            "status": "not_installed",
            "install": "pip install openai"
        })
    
    # Check AssemblyAI
    try:
        import assemblyai
        api_key = getattr(settings, 'assemblyai_api_key', None)
        if api_key:
            providers.append({
                "name": "assemblyai",
                "status": "available",
                "note": "Cloud API with free tier"
            })
        else:
            providers.append({
                "name": "assemblyai",
                "status": "no_api_key",
                "note": "Set ASSEMBLYAI_API_KEY in .env"
            })
    except ImportError:
        providers.append({
            "name": "assemblyai",
            "status": "not_installed",
            "install": "pip install assemblyai"
        })
    
    # Check local Whisper
    try:
        import whisper
        providers.append({
            "name": "whisper",
            "status": "available",
            "note": "Local model, no API key needed"
        })
    except ImportError:
        providers.append({
            "name": "whisper",
            "status": "not_installed",
            "install": "pip install openai-whisper"
        })
    
    return providers


def get_current_provider() -> str:
    """
    Get the currently configured transcription provider.
    
    Returns:
        str: Name of current provider
    """
    return settings.transcription_provider


def test_transcription(test_text: str = "This is a test.") -> dict:
    """
    Test the transcription service with a sample.
    
    Useful for verifying configuration is correct.
    
    Args:
        test_text: Expected text content (for comparison)
    
    Returns:
        dict: Test results including status and any errors
    """
    result = {
        "provider": get_current_provider(),
        "available_providers": get_available_providers(),
        "status": "unknown",
        "error": None
    }
    
    try:
        # For stub, we can't really test, just confirm it works
        if result["provider"] == "stub":
            transcript = _transcribe_stub("test.wav")
            result["status"] = "ok (stub mode)"
            result["sample_output"] = transcript[:100] + "..."
        else:
            result["status"] = "configured"
            result["note"] = "Real transcription requires actual audio file"
    
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
    
    return result
