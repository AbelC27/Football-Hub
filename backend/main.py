from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Football Analytics AI")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from backend.routers import api, ws, standings, auth_router, user_router, fantasy_router, search_router
    from backend.scheduler import start_scheduler
except ImportError:
    from routers import api, ws, standings, auth_router, user_router, fantasy_router, search_router
    from scheduler import start_scheduler

app.include_router(api.router)
app.include_router(ws.router)
app.include_router(standings.router)
app.include_router(auth_router.router)
app.include_router(user_router.router)
app.include_router(fantasy_router.router)
app.include_router(search_router.router)

@app.on_event("startup")
def startup_event():
    start_scheduler()

@app.get("/")
def read_root():
    return {"message": "Football Analytics AI Backend is running"}
