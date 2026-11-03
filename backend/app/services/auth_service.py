"""
Authentication Service - Supabase Auth Integration

This module handles user authentication using Supabase Auth:
- User registration (sign up)
- User login (sign in)
- Token verification and refresh
- Session management
- User profile management

Uses Supabase REST API - no database connection string needed!

Author: AI Interview Assistant Team
"""

import logging
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from functools import lru_cache

from fastapi import HTTPException, Depends, Header, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.config import settings

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)

# ===========================================
# Supabase Client
# ===========================================

_supabase_client = None


def get_supabase_client():
    """Get or create Supabase client singleton."""
    global _supabase_client
    
    if _supabase_client is None:
        if not settings.supabase_url or not settings.supabase_key:
            logger.warning("Supabase not configured. Auth features will be limited.")
            return None
        
        try:
            from supabase import create_client, Client
            _supabase_client = create_client(
                settings.supabase_url,
                settings.supabase_key
            )
            logger.info("Supabase client initialized successfully")
        except ImportError:
            logger.error("Supabase library not installed. Run: pip install supabase")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            return None
    
    return _supabase_client


# ===========================================
# Authentication Functions
# ===========================================

async def sign_up(email: str, password: str, full_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Register a new user with Supabase Auth.
    
    Args:
        email: User's email address
        password: User's password (min 8 characters)
        full_name: User's full name (optional)
    
    Returns:
        Dict with user data and tokens
    
    Raises:
        HTTPException: If registration fails
    """
    logger.info(f"User registration attempt: {email}")
    supabase = get_supabase_client()
    
    if not supabase:
        logger.error("Supabase client not available for registration")
        raise HTTPException(
            status_code=503,
            detail="Authentication service not available"
        )
    
    try:
        # Create user in Supabase Auth
        logger.debug(f"Creating user in Supabase Auth: {email}")
        response = supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "data": {
                    "full_name": full_name
                }
            }
        })
        
        if response.user is None:
            logger.warning(f"Supabase registration failed for {email}")
            raise HTTPException(
                status_code=400,
                detail="Registration failed. Please check your email and try again."
            )
        
        user = response.user
        session = response.session
        
        logger.info(f"✓ User created in Supabase: {user.id} ({email})")
        
        # Create user record in our database
        logger.debug(f"Creating user record in database for {email}")
        await create_user_record(
            user_id=user.id,
            email=email,
            full_name=full_name
        )
        logger.info(f"✓ User record created in database")
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": full_name,
                "created_at": user.created_at
            },
            "access_token": session.access_token if session else None,
            "refresh_token": session.refresh_token if session else None,
            "token_type": "bearer",
            "expires_in": session.expires_in if session else 3600,
            "message": "Registration successful. Please check your email to verify your account." if not session else "Registration successful."
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign up error for {email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Registration failed: {str(e)}"
        )


async def sign_in(email: str, password: str) -> Dict[str, Any]:
    """
    Authenticate user and return tokens.
    
    Args:
        email: User's email address
        password: User's password
    
    Returns:
        Dict with user data and tokens (access_token, refresh_token, etc.)
    
    Raises:
        HTTPException: If login fails (invalid credentials or service unavailable)
    """
    logger.info(f"User login attempt: {email}")
    supabase = get_supabase_client()
    
    if not supabase:
        logger.error("Supabase client not available for login")
        raise HTTPException(
            status_code=503,
            detail="Authentication service not available"
        )
    
    try:
        logger.debug(f"Authenticating user with Supabase: {email}")
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if response.user is None or response.session is None:
            logger.warning(f"Login failed - invalid credentials for {email}")
            raise HTTPException(
                status_code=401,
                detail="Invalid email or password"
            )
        
        user = response.user
        session = response.session
        
        logger.info(f"✓ User authenticated: {user.id} ({email})")
        
        # Ensure user exists in our database
        logger.debug(f"Ensuring user record exists in database for {email}")
        await create_user_record(
            user_id=user.id,
            email=email,
            full_name=user.user_metadata.get("full_name")
        )
        
        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.user_metadata.get("full_name"),
                "created_at": user.created_at
            },
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "expires_in": session.expires_in
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sign in error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )


async def sign_out(access_token: str) -> Dict[str, str]:
    """
    Sign out user and invalidate token.
    
    Args:
        access_token: User's current access token
    
    Returns:
        Dict with success message
    """
    supabase = get_supabase_client()
    
    if not supabase:
        return {"message": "Signed out (local only)"}
    
    try:
        supabase.auth.sign_out()
        return {"message": "Successfully signed out"}
    except Exception as e:
        logger.error(f"Sign out error: {e}")
        return {"message": "Signed out (with warnings)"}


async def refresh_token(refresh_token: str) -> Dict[str, Any]:
    """
    Refresh access token using refresh token.
    
    Args:
        refresh_token: Current refresh token
    
    Returns:
        Dict with new tokens
    
    Raises:
        HTTPException: If refresh fails
    """
    supabase = get_supabase_client()
    
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Authentication service not available"
        )
    
    try:
        response = supabase.auth.refresh_session(refresh_token)
        
        if response.session is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired refresh token"
            )
        
        session = response.session
        user = response.user
        
        return {
            "access_token": session.access_token,
            "refresh_token": session.refresh_token,
            "token_type": "bearer",
            "expires_in": session.expires_in,
            "user": {
                "id": user.id if user else None,
                "email": user.email if user else None
            }
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Failed to refresh token"
        )


# ===========================================
# Token Verification
# ===========================================

async def verify_token(token: str) -> Dict[str, Any]:
    """
    Verify JWT token and return user info.
    
    Args:
        token: JWT access token
    
    Returns:
        Dict with user info
    
    Raises:
        HTTPException: If token is invalid
    """
    supabase = get_supabase_client()
    
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Authentication service not available"
        )
    
    try:
        # Get user from token
        response = supabase.auth.get_user(token)
        
        if response.user is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or expired token"
            )
        
        user = response.user
        
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.user_metadata.get("full_name"),
            "email_verified": user.email_confirmed_at is not None
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )


# ===========================================
# FastAPI Dependencies
# ===========================================

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[Dict[str, Any]]:
    """
    FastAPI dependency to get current authenticated user.
    
    Returns None if no valid token is provided (for optional auth).
    Raises HTTPException if token is invalid.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            if user is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return {"user_id": user["id"]}
    """
    if credentials is None:
        return None
    
    return await verify_token(credentials.credentials)


async def require_auth(
    user: Optional[Dict[str, Any]] = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    FastAPI dependency that requires authentication.
    
    Raises HTTPException if user is not authenticated.
    
    Usage:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(require_auth)):
            return {"user_id": user["id"]}
    """
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return user


def ensure_same_user(requested_user_id: Optional[str], user: Dict[str, Any]) -> str:
    """
    Return the authenticated user's ID, rejecting requests for another user's data.

    Older clients still send a user_id parameter; it is accepted only when it
    matches the token. The token is the single source of truth for identity.
    """
    if requested_user_id and requested_user_id != user["id"]:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own data"
        )
    return user["id"]


async def current_user_id(
    user_id: Optional[str] = Query(default=None, description="Deprecated: ignored unless it matches the logged-in user"),
    user: Dict[str, Any] = Depends(require_auth)
) -> str:
    """
    FastAPI dependency: the logged-in user's ID.

    Drop-in replacement for endpoints that used to trust a `user_id`
    query parameter.
    """
    return ensure_same_user(user_id, user)


async def require_admin(
    user: Dict[str, Any] = Depends(require_auth)
) -> Dict[str, Any]:
    """
    FastAPI dependency that requires an admin user.

    Admins are listed by email in the ADMIN_EMAILS setting (comma-separated).
    With no admins configured, admin-only endpoints are closed to everyone.
    """
    email = (user.get("email") or "").strip().lower()
    if not email or email not in settings.get_admin_emails():
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
    return user


# ===========================================
# Database User Management (Uses Supabase REST API)
# ===========================================

async def create_user_record(
    user_id: str,
    email: str,
    full_name: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create or update user record in Supabase.
    
    Uses Supabase REST API - no database connection string needed!
    
    Args:
        user_id: Supabase user UUID
        email: User's email
        full_name: User's full name
    
    Returns:
        User data dict
    """
    try:
        from app.services.supabase_db import get_or_create_user
        return await get_or_create_user(user_id, email, full_name)
    except Exception as e:
        logger.error(f"Failed to create/update user record: {e}")
        # Return basic user data even if DB fails
        return {"id": user_id, "email": email, "full_name": full_name}


async def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user from Supabase by ID.
    
    Uses Supabase REST API - no database connection string needed!
    
    Args:
        user_id: Supabase user UUID
    
    Returns:
        User data dict or None
    """
    try:
        from app.models.supabase_client import get_supabase
        supabase = get_supabase()
        result = supabase.table("users").select("*").eq("id", user_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        return None


# ===========================================
# Password Reset (via Supabase)
# ===========================================

async def request_password_reset(email: str) -> Dict[str, str]:
    """
    Send password reset email.
    
    Args:
        email: User's email address
    
    Returns:
        Dict with success message
    """
    supabase = get_supabase_client()
    
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Authentication service not available"
        )
    
    try:
        supabase.auth.reset_password_for_email(email)
        return {"message": "Password reset email sent. Please check your inbox."}
    except Exception as e:
        logger.error(f"Password reset error: {e}")
        # Don't reveal if email exists
        return {"message": "If an account exists with this email, a password reset link has been sent."}
