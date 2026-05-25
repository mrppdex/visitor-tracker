from fastapi import FastAPI, Request, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from sqlalchemy import Column, Integer, String, DateTime, create_engine, text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime
import os
import secrets
import requests
import smtplib
from email.message import EmailMessage
from typing import Optional, List

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
    country = Column(String, nullable=True)
    country_code = Column(String, nullable=True)

# Ensure data directory exists
os.makedirs("/app/data", exist_ok=True)
Base.metadata.create_all(bind=engine)

# Migration: Add country columns if they don't exist
def migrate_db():
    with engine.connect() as conn:
        # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
        res = conn.execute(text("PRAGMA table_info(visitors)"))
        columns = [row[1] for row in res.fetchall()]
        if "country" not in columns:
            conn.execute(text("ALTER TABLE visitors ADD COLUMN country TEXT"))
        if "country_code" not in columns:
            conn.execute(text("ALTER TABLE visitors ADD COLUMN country_code TEXT"))
        conn.commit()

try:
    migrate_db()
except Exception as e:
    print(f"Migration error: {e}")

app = FastAPI()
templates = Jinja2Templates(directory="templates")
security = HTTPBasic()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_country_info(ip: str):
    try:
        # Use ip-api.com (free for non-commercial use, no key needed for low volume)
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=2)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data.get("country"), data.get("countryCode")
    except Exception:
        pass
    return None, None

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = os.getenv("ADMIN_USERNAME", "admin")
    correct_password = os.getenv("ADMIN_PASSWORD", "admin")
    is_correct_username = secrets.compare_digest(credentials.username, correct_username)
    is_correct_password = secrets.compare_digest(credentials.password, correct_password)
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/track")
async def track_visitor(request: Request):
    db = SessionLocal()
    try:
        # Check X-Forwarded-For because of Sliplane's proxy
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host

        country, country_code = get_country_info(ip)

        visitor = Visitor(
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
            referer=request.headers.get("referer"),
            path=request.query_params.get("url", "unknown"),
            country=country,
            country_code=country_code
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
        return {"total_visitors": count}
    finally:
        db.close()

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request, username: str = Depends(get_current_username)):
    db = SessionLocal()
    try:
        count = db.query(Visitor).count()
        recent = db.query(Visitor).order_by(Visitor.timestamp.desc()).limit(100).all()
        recent_list = []
        for v in recent:
            recent_list.append({
                "timestamp": v.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "ip": v.ip_address,
                "path": v.path,
                "referer": v.referer,
                "country": v.country,
                "country_code": v.country_code
            })
        return templates.TemplateResponse(request, "dashboard.html", {
            "total_visitors": count,
            "recent_visitors": recent_list
        })
    finally:
        db.close()

@app.get("/api/dashboard-data")
async def get_dashboard_data(period: str = "7d", username: str = Depends(get_current_username)):
    db = SessionLocal()
    try:
        now = datetime.datetime.utcnow()
        if period == "24h":
            cutoff = now - datetime.timedelta(hours=24)
            group_format = "%Y-%m-%d %H:00"
        elif period == "7d":
            cutoff = now - datetime.timedelta(days=7)
            group_format = "%Y-%m-%d"
        elif period == "30d":
            cutoff = now - datetime.timedelta(days=30)
            group_format = "%Y-%m-%d"
        else: # all
            cutoff = datetime.datetime(2000, 1, 1)
            group_format = "%Y-%m"

        # Time series data
        time_query = db.query(
            func.strftime(group_format, Visitor.timestamp).label("label"),
            func.count(Visitor.id).label("count")
        ).filter(Visitor.timestamp >= cutoff).group_by("label").order_by("label").all()

        # Country data
        country_query = db.query(
            Visitor.country,
            func.count(Visitor.id).label("count")
        ).filter(Visitor.timestamp >= cutoff).group_by(Visitor.country).order_by(text("count DESC")).all()

        return {
            "time_chart": {
                "labels": [r[0] for r in time_query],
                "data": [r[1] for r in time_query]
            },
            "country_chart": {
                "labels": [r[0] or "Unknown" for r in country_query],
                "data": [r[1] for r in country_query]
            }
        }
    finally:
        db.close()

def send_contact_email(name: str, title: str, message: str, country: Optional[str], ip: str, files: List[UploadFile]):
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    admin_email = os.getenv("ADMIN_EMAIL", "aspiela@gmail.com")

    if not all([smtp_server, smtp_user, smtp_password]):
        print("SMTP configuration missing. Cannot send email.")
        return

    msg = EmailMessage()
    msg['Subject'] = f"Blog Contact: {title or 'No Title'} (from {name or 'Anonymous'})"
    msg['From'] = smtp_user
    msg['To'] = admin_email

    body = f"""
New contact form submission:

Name: {name or 'Anonymous'}
Title: {title or 'No Title'}
Country: {country or 'Unknown'} (IP: {ip})
Timestamp: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC

Message:
--------------------------------------------------
{message}
--------------------------------------------------
"""
    msg.set_content(body)

    for file in files:
        file_content = file.file.read()
        maintype, subtype = file.content_type.split('/', 1)
        msg.add_attachment(
            file_content,
            maintype=maintype,
            subtype=subtype,
            filename=file.filename
        )

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception as e:
        print(f"Failed to send email: {e}")

@app.post("/contact")
async def contact_me(
    background_tasks: BackgroundTasks,
    request: Request,
    name: str = Form(None),
    title: str = Form(None),
    message: str = Form(...),
    files: List[UploadFile] = File([])
):
    # Extract IP
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        ip = forwarded_for.split(",")[0].strip()
    else:
        ip = request.client.host

    country, _ = get_country_info(ip)

    # Send email in background to not block response
    background_tasks.add_task(send_contact_email, name, title, message, country, ip, files)

    return {"status": "success", "message": "Your message has been sent."}

@app.get("/")
async def root():
    return {"message": "Visitor Tracker is running"}
