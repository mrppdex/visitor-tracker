from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os

# Database setup
# Using an absolute path or relative to /app in container
DATABASE_URL = "sqlite:////app/data/visitor_logs.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Visitor(Base):
    __tablename__ = "visitors"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    ip_address = Column(String)
    user_agent = Column(String)
    referer = Column(String)
    path = Column(String)

# Ensure data directory exists
os.makedirs("/app/data", exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/track")
async def track_visitor(request: Request):
    db = SessionLocal()
    try:
        visitor = Visitor(
            ip_address=request.client.host,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            path=request.query_params.get("url", "unknown")
        )
        db.add(visitor)
        db.commit()
    finally:
        db.close()
    
    # Return a 1x1 transparent GIF
    from fastapi.responses import Response
    pixel = b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
    return Response(content=pixel, media_type="image/gif")

@app.get("/stats")
async def get_stats():
    db = SessionLocal()
    try:
        count = db.query(Visitor).count()
        recent = db.query(Visitor).order_by(Visitor.timestamp.desc()).limit(10).all()
        # Convert to dict for JSON serialization
        recent_list = []
        for v in recent:
            recent_list.append({
                "timestamp": v.timestamp.isoformat(),
                "ip": v.ip_address,
                "ua": v.user_agent,
                "referer": v.referer,
                "path": v.path
            })
        return {"total_visitors": count, "recent_visitors": recent_list}
    finally:
        db.close()

@app.get("/")
async def root():
    return {"message": "Visitor Tracker is running"}
