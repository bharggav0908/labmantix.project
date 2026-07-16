import json
import ast
import os
import re
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import bcrypt
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .review_utils import (
    analyze_complexity,
    ai_review,
    build_review_result,
    heuristic_review,
    language_syntax_checks,
)

load_dotenv()

app = FastAPI(title="AI Code Review Assistant")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

DATABASE_PATH = os.getenv(
    "DATABASE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "data", "app.db"),
)
DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
ALGORITHM = "HS256"


class PostgresConnection:
    def __init__(self, database_url: str):
        self.conn = psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    def execute(self, query: str, params: tuple[Any, ...] | list[Any] = ()) -> RealDictCursor:
        cursor = self.conn.cursor()
        cursor.execute(query.replace("?", "%s"), params)
        return cursor

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()


def init_db() -> None:
    if USE_POSTGRES:
        init_postgres_db()
        return

    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            github_url TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    reviews_exists = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reviews'").fetchone()
    if not reviews_exists:
        conn.execute(
            """
            CREATE TABLE reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                review_type TEXT NOT NULL,
                language TEXT NOT NULL,
                overall_score INTEGER NOT NULL,
                summary TEXT NOT NULL,
                source_code TEXT NOT NULL,
                findings TEXT NOT NULL,
                complexity TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
    else:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reviews)")}
        if "project_id" not in columns or "summary" not in columns:
            conn.execute("DROP TABLE IF EXISTS reviews_legacy")
            conn.execute("ALTER TABLE reviews RENAME TO reviews_legacy")
            conn.execute(
                """
                CREATE TABLE reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    project_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    review_type TEXT NOT NULL,
                    language TEXT NOT NULL,
                    overall_score INTEGER NOT NULL,
                    summary TEXT NOT NULL,
                    source_code TEXT NOT NULL,
                    findings TEXT NOT NULL,
                    complexity TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            severity TEXT NOT NULL,
            issue TEXT NOT NULL,
            explanation TEXT NOT NULL,
            suggested_fix TEXT NOT NULL,
            file_name TEXT,
            line_number INTEGER,
            FOREIGN KEY (review_id) REFERENCES reviews(id) ON DELETE CASCADE
        )
        """
    )
    conn.commit()
    conn.close()

def init_postgres_db() -> None:
    conn = PostgresConnection(DATABASE_URL)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_name TEXT NOT NULL,
            github_url TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            review_type TEXT NOT NULL,
            language TEXT NOT NULL,
            overall_score INTEGER NOT NULL,
            summary TEXT NOT NULL,
            source_code TEXT NOT NULL,
            findings TEXT NOT NULL,
            complexity TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_findings (
            id SERIAL PRIMARY KEY,
            review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
            severity TEXT NOT NULL,
            issue TEXT NOT NULL,
            explanation TEXT NOT NULL,
            suggested_fix TEXT NOT NULL,
            file_name TEXT,
            line_number INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def get_db_connection() -> sqlite3.Connection | PostgresConnection:
    if USE_POSTGRES:
        return PostgresConnection(DATABASE_URL)

    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_last_insert_id(conn: sqlite3.Connection | PostgresConnection) -> int:
    query = "SELECT LASTVAL() AS id" if USE_POSTGRES else "SELECT last_insert_rowid() AS id"
    return int(conn.execute(query).fetchone()["id"])


init_db()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(days=7)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


def get_current_user(request: Request) -> dict[str, Any] | None:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = decode_token(token)
    except Exception:
        return None

    try:
        user_id = int(payload.get("sub", ""))
    except (TypeError, ValueError):
        return None

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(user) if user else None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    return templates.TemplateResponse(request, "index.html", {"request": request, "user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request, "user": None, "error": request.query_params.get("error")},
    )

@app.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    conn.close()
    if not user or not verify_password(password, user["password_hash"]):
        return RedirectResponse(url="/login?error=invalid", status_code=303)
    token = create_token(user["id"])
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "signup.html", {"request": request, "user": None, "error": request.query_params.get("error")})


@app.post("/signup")
async def signup(request: Request, name: str = Form(...), email: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    if not name or not email or not password:
        return RedirectResponse(url="/signup?error=missing", status_code=303)
    conn = get_db_connection()
    existing = conn.execute("SELECT id FROM users WHERE email = ?", (email.lower(),)).fetchone()
    if existing:
        conn.close()
        return RedirectResponse(url="/signup?error=exists", status_code=303)
    created_at = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO users (name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
        (name.strip(), email.lower(), hash_password(password), created_at),
    )
    user_id = get_last_insert_id(conn)
    conn.commit()
    conn.close()
    token = create_token(user_id)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie("access_token", token, httponly=True, samesite="lax")
    return response


@app.get("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie("access_token")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db_connection()
    projects = conn.execute(
        "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
        (user["id"],),
    ).fetchall()
    reviews = conn.execute(
        "SELECT r.*, p.project_name FROM reviews r LEFT JOIN projects p ON p.id = r.project_id WHERE r.user_id = ? ORDER BY r.created_at DESC LIMIT 8",
        (user["id"],),
    ).fetchall()
    stats = conn.execute(
        "SELECT COUNT(*) AS total_reviews, COALESCE(AVG(overall_score), 0) AS avg_score FROM reviews WHERE user_id = ?",
        (user["id"],),
    ).fetchone()
    conn.close()
    error_messages = {
        "project": "Create or select a project before generating a review.",
        "unsupported": "That file type is not supported. Use Python, JavaScript, TypeScript, Java, C, or C++.",
        "empty": "Paste code or upload a source file before generating a review.",
        "name": "Enter a project name to create a workspace.",
    }
    notice_messages = {
        "project_created": "Project created. It is now available in Select Project.",
    }
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "projects": [dict(project) for project in projects],
            "reviews": [dict(review) for review in reviews],
            "stats": dict(stats),
            "error": error_messages.get(request.query_params.get("error", "")),
            "notice": notice_messages.get(request.query_params.get("notice", "")),
        },
    )


@app.post("/projects")
async def create_project(request: Request, project_name: str = Form(...), github_url: str = Form(default="")) -> RedirectResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if not project_name.strip():
        return RedirectResponse(url="/dashboard?error=name#new-review", status_code=303)

    conn = get_db_connection()
    conn.execute(
        "INSERT INTO projects (user_id, project_name, github_url, created_at) VALUES (?, ?, ?, ?)",
        (user["id"], project_name.strip(), github_url.strip(), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/dashboard?notice=project_created#new-review", status_code=303)


@app.post("/review")
async def create_review(
    request: Request,
    project_id: str = Form(default=""),
    title: str = Form(...),
    language: str = Form(...),
    code: str = Form(default=""),
    file: UploadFile | None = File(default=None),
) -> RedirectResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    source_code = code
    if file and file.filename:
        allowed = {".js", ".jsx", ".ts", ".tsx", ".py", ".java", ".cpp", ".c"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            return RedirectResponse(url="/dashboard?error=unsupported", status_code=303)
        source_code = (await file.read()).decode("utf-8", errors="replace")
    if not source_code.strip():
        return RedirectResponse(url="/dashboard?error=empty#new-review", status_code=303)
    try:
        selected_project_id = int(project_id)
    except ValueError:
        return RedirectResponse(url="/dashboard?error=project#new-review", status_code=303)

    conn = get_db_connection()
    project = conn.execute("SELECT * FROM projects WHERE id = ? AND user_id = ?", (selected_project_id, user["id"])).fetchone()
    if not project:
        conn.close()
        return RedirectResponse(url="/dashboard?error=project", status_code=303)

    review_result = build_review_result(source_code, language)
    conn.execute(
        "INSERT INTO reviews (user_id, project_id, title, review_type, language, overall_score, summary, source_code, findings, complexity, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            user["id"],
            project["id"],
            title.strip() or f"{language or 'Code'} Review",
            "upload" if file and file.filename else "paste",
            language.strip() or "Unknown",
            review_result["score"],
            review_result["summary"],
            source_code,
            json.dumps(review_result["findings"]),
            json.dumps(review_result["complexity"]),
            datetime.utcnow().isoformat(),
        ),
    )
    review_id = get_last_insert_id(conn)
    for finding in review_result["findings"]:
        conn.execute(
            "INSERT INTO review_findings (review_id, severity, issue, explanation, suggested_fix, file_name, line_number) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                review_id,
                str(finding.get("severity", "info")).lower(),
                str(finding.get("category", "general")),
                str(finding.get("message", "")),
                "Consider refactoring this area for clarity and maintainability.",
                "main.py",
                int(finding.get("line", 1)),
            ),
        )
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/review/{review_id}", status_code=303)


@app.get("/history", response_class=HTMLResponse)
async def history(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    search = request.query_params.get("q", "")
    language = request.query_params.get("language", "")
    conn = get_db_connection()
    query = "SELECT r.*, p.project_name FROM reviews r LEFT JOIN projects p ON p.id = r.project_id WHERE r.user_id = ?"
    params: list[Any] = [user["id"]]
    if search:
        query += " AND (r.title LIKE ? OR r.summary LIKE ? OR r.source_code LIKE ?)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    if language:
        query += " AND r.language = ?"
        params.append(language)
    query += " ORDER BY r.created_at DESC"
    reviews = conn.execute(query, params).fetchall()
    languages = [row["language"] for row in conn.execute("SELECT DISTINCT language FROM reviews WHERE user_id = ?", (user["id"],)).fetchall()]
    conn.close()
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "request": request,
            "user": user,
            "reviews": [dict(review) for review in reviews],
            "languages": languages,
            "search": search,
            "selected_language": language,
        },
    )


@app.get("/review/{review_id}", response_class=HTMLResponse)
async def review_detail(request: Request, review_id: int) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db_connection()
    review = conn.execute("SELECT r.*, p.project_name FROM reviews r LEFT JOIN projects p ON p.id = r.project_id WHERE r.id = ? AND r.user_id = ?", (review_id, user["id"])).fetchone()
    findings = conn.execute("SELECT * FROM review_findings WHERE review_id = ? ORDER BY line_number", (review_id,)).fetchall()
    conn.close()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    review_data = dict(review)
    review_data["findings"] = [dict(finding) for finding in findings]
    review_data["complexity"] = json.loads(review_data["complexity"])
    return templates.TemplateResponse(request, "review_detail.html", {"request": request, "user": user, "review": review_data})


@app.post("/review/{review_id}/delete")
async def delete_review(request: Request, review_id: int) -> RedirectResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)

    conn = get_db_connection()
    conn.execute("DELETE FROM review_findings WHERE review_id = ?", (review_id,))
    conn.execute("DELETE FROM reviews WHERE id = ? AND user_id = ?", (review_id, user["id"]))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/history", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request) -> HTMLResponse:
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    return templates.TemplateResponse(request, "settings.html", {"request": request, "user": user})


@app.post("/api/review")
async def api_review(payload: dict[str, Any]) -> JSONResponse:
    code = str(payload.get("code", ""))
    language = str(payload.get("language", ""))
    review_result = build_review_result(code, language)
    return JSONResponse(review_result)
