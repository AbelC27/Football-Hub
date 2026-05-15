from typing import Optional
import os
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from supabase import create_client, Client

try:
    from backend.database import get_db
    from backend.models import User
except ImportError:
    from database import get_db
    from models import User

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# The tokenUrl is changed to just help Swagger UI, although actual login happens on the frontend
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    if not supabase:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Supabase credentials not configured",
        )

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        # Ask Supabase to verify the JWT
        user_response = supabase.auth.get_user(token)
        if not user_response or not user_response.user:
            raise credentials_exception
            
        # Extract the user's UUID from the token
        user_id = user_response.user.id
        
        # Look up the user in our public.users table
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            # If the user doesn't exist in our table yet but has a valid Supabase auth token,
            # this either means the database trigger hasn't fired or it's a new user.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User authenticated but profile not found in database",
            )
            
        return user
        
    except Exception as e:
        print(f"Auth error: {e}")
        raise credentials_exception
