from fastapi import FastAPI
from routes import router 

app = FastAPI(
    title="Telecom Network Analytics API",
    description="Core analytical endpoints backing the telemetry platform.",
    version="1.0.0"
)
app.include_router(router)