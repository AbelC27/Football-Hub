from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

try:
    from backend.database import get_db
    from backend.models import User
    from backend.schemas import User as UserSchema
    from backend.auth import get_current_user
except ImportError:
    from database import get_db
    from models import User
    from schemas import User as UserSchema
    from auth import get_current_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Note: /login and /register endpoints have been removed.
# Authentication (signup/login) is now handled directly by the frontend using the Supabase JS SDK.
# Once the frontend obtains the Supabase JWT, it includes it in the Authorization header 
# which is validated by `get_current_user`.

@router.get("/me", response_model=UserSchema)
def read_users_me(current_user: User = Depends(get_current_user)):
    """
    Returns the currently authenticated user based on the Supabase JWT.
    """
    return current_user
