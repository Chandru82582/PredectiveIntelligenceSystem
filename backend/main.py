from fastapi import FastAPI
from routes import router 
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="Telecom Network Analytics API",
    description="Core analytical endpoints backing the telemetry platform.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)