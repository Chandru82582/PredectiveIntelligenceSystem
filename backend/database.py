from sqlalchemy import create_engine, Column, Integer, Float, Date, DateTime, String, Index, func
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from datetime import datetime


# Using SQLite in-memory for this self-contained runnable environment.
# In production, replace with: create_engine("mysql+pymysql://user:pass@host/dbname")
SQLALCHEMY_DATABASE_URL = "mysql+mysqlconnector://root:root@localhost/telecom_activity"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class HourlyGridSummary(Base):
    """Hourly grid summary representing the materialized analytics table."""
    __tablename__ = "hourly_grid_summary"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    date = Column(Date, nullable=False, index=True)
    hour = Column(Integer, nullable=False, index=True)
    grid_id = Column(Integer, nullable=False, index=True)
    sms_in = Column(Float, default=0.0)
    sms_out = Column(Float, default=0.0)
    call_in = Column(Float, default=0.0)
    call_out = Column(Float, default=0.0)
    internet_activity = Column(Float, default=0.0)
    total_activity = Column(Float, default=0.0, index=True)
    record_count = Column(Integer, default=0)
    loaded_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index('idx_date_hour_grid', 'date', 'hour', 'grid_id'),
    )

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()