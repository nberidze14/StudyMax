import os
import re
import calendar
import random
from datetime import datetime, timedelta
from pathlib import Path
import sqlite3

from flask import Flask, flash, g, redirect, render_template, request, session, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "studymax.db"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "studymax-local-key")


# Database setup
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    schema_path = BASE_DIR / "schema.sql"
    rename_exam_table(db)
    db.executescript(schema_path.read_text(encoding="utf-8"))
    ensure_schema(db)
    db.close()


# Database migrations
def ensure_schema(db):
    rename_exam_table(db)
    ensure_table(
        db,
        "flashcard_decks",
        """
        CREATE TABLE IF NOT EXISTS flashcard_decks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    ensure_table(
        db,
        "todo_projects",
        """
        CREATE TABLE IF NOT EXISTS todo_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    ensure_table(
        db,
        "pomodoro_settings",
        """
        CREATE TABLE IF NOT EXISTS pomodoro_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            focus_minutes INTEGER NOT NULL DEFAULT 25,
            break_minutes INTEGER NOT NULL DEFAULT 5,
            short_break_minutes INTEGER NOT NULL DEFAULT 5,
            long_break_minutes INTEGER NOT NULL DEFAULT 15,
            sessions_until_long_break INTEGER NOT NULL DEFAULT 4
        )
        """,
    )
    ensure_table(
        db,
        "review_history",
        """
        CREATE TABLE IF NOT EXISTS review_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flashcard_id INTEGER NOT NULL,
            rating TEXT NOT NULL,
            reviewed_at TEXT NOT NULL,
            FOREIGN KEY (flashcard_id) REFERENCES flashcards (id)
        )
        """,
    )
    ensure_table(
        db,
        "exams",
        """
        CREATE TABLE IF NOT EXISTS exams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            exam_date TEXT NOT NULL,
            deck_id INTEGER,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id)
        )
        """,
    )
    ensure_table(
        db,
        "exam_decks",
        """
        CREATE TABLE IF NOT EXISTS exam_decks (
            exam_id INTEGER NOT NULL,
            deck_id INTEGER NOT NULL,
            PRIMARY KEY (exam_id, deck_id),
            FOREIGN KEY (exam_id) REFERENCES exams (id),
            FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id)
        )
        """,
    )
    ensure_table(
        db,
        "exam_todos",
        """
        CREATE TABLE IF NOT EXISTS exam_todos (
            exam_id INTEGER NOT NULL,
            todo_id INTEGER NOT NULL,
            PRIMARY KEY (exam_id, todo_id),
            FOREIGN KEY (exam_id) REFERENCES exams (id),
            FOREIGN KEY (todo_id) REFERENCES todos (id)
        )
        """,
    )
    ensure_table(
        db,
        "exam_projects",
        """
        CREATE TABLE IF NOT EXISTS exam_projects (
            exam_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            PRIMARY KEY (exam_id, project_id),
            FOREIGN KEY (exam_id) REFERENCES exams (id),
            FOREIGN KEY (project_id) REFERENCES todo_projects (id)
        )
        """,
    )
    ensure_todo_columns(db)
    ensure_note_columns(db)
    ensure_flashcard_columns(db)
    ensure_pomodoro_columns(db)
    ensure_default_deck(db)
    ensure_default_pomodoro_settings(db)
    db.commit()


def rename_exam_table(db):
    tables = {
        row["name"]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    }
    if "exam_targets" in tables and "exams" not in tables:
        db.execute("ALTER TABLE exam_targets RENAME TO exams")
        db.commit()


def ensure_table(db, table_name, create_sql):
    exists = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    if exists is None:
        db.execute(create_sql)


def ensure_todo_columns(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(todos)").fetchall()}
    migrations = {
        "due_date": "ALTER TABLE todos ADD COLUMN due_date TEXT",
        "project_id": "ALTER TABLE todos ADD COLUMN project_id INTEGER",
        "completed_at": "ALTER TABLE todos ADD COLUMN completed_at TEXT",
    }
    for column_name, sql in migrations.items():
        if column_name not in columns:
            db.execute(sql)


def ensure_note_columns(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(notes)").fetchall()}
    migrations = {
        "alignment": "ALTER TABLE notes ADD COLUMN alignment TEXT NOT NULL DEFAULT 'left'",
    }
    for column_name, sql in migrations.items():
        if column_name not in columns:
            db.execute(sql)


def ensure_flashcard_columns(db):
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(flashcards)").fetchall()
    }
    migrations = {
        "review_count": "ALTER TABLE flashcards ADD COLUMN review_count INTEGER NOT NULL DEFAULT 0",
        "interval_days": "ALTER TABLE flashcards ADD COLUMN interval_days REAL NOT NULL DEFAULT 0",
        "ease_factor": "ALTER TABLE flashcards ADD COLUMN ease_factor REAL NOT NULL DEFAULT 2.5",
        "last_reviewed_at": "ALTER TABLE flashcards ADD COLUMN last_reviewed_at TEXT",
        "due_at": "ALTER TABLE flashcards ADD COLUMN due_at TEXT",
        "deck_id": "ALTER TABLE flashcards ADD COLUMN deck_id INTEGER",
        "source_note_id": "ALTER TABLE flashcards ADD COLUMN source_note_id INTEGER",
    }
    for column_name, sql in migrations.items():
        if column_name not in columns:
            db.execute(sql)


def ensure_pomodoro_columns(db):
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(pomodoro_settings)").fetchall()
    }
    migrations = {
        "short_break_minutes": "ALTER TABLE pomodoro_settings ADD COLUMN short_break_minutes INTEGER NOT NULL DEFAULT 5",
        "long_break_minutes": "ALTER TABLE pomodoro_settings ADD COLUMN long_break_minutes INTEGER NOT NULL DEFAULT 15",
        "sessions_until_long_break": "ALTER TABLE pomodoro_settings ADD COLUMN sessions_until_long_break INTEGER NOT NULL DEFAULT 4",
    }
    for column_name, sql in migrations.items():
        if column_name not in columns:
            db.execute(sql)
    if "short_break_minutes" not in columns and "break_minutes" in columns:
        db.execute(
            """
            UPDATE pomodoro_settings
            SET short_break_minutes = COALESCE(break_minutes, short_break_minutes)
            WHERE id = 1
            """
        )


def ensure_default_deck(db):
    deck = db.execute(
        "SELECT id FROM flashcard_decks WHERE lower(name) = lower(?)",
        ("General",),
    ).fetchone()
    if deck is None:
        db.execute("INSERT INTO flashcard_decks (name) VALUES (?)", ("General",))
        deck_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    else:
        deck_id = deck["id"]

    db.execute(
        """
        UPDATE flashcards
        SET due_at = COALESCE(due_at, created_at, CURRENT_TIMESTAMP),
            deck_id = COALESCE(deck_id, ?)
        """,
        (deck_id,),
    )


def ensure_default_pomodoro_settings(db):
    db.execute(
        """
        INSERT INTO pomodoro_settings (
            id,
            focus_minutes,
            break_minutes,
            short_break_minutes,
            long_break_minutes,
            sessions_until_long_break
        )
        VALUES (1, 25, 5, 5, 15, 4)
        ON CONFLICT(id) DO NOTHING
        """
    )


# Database helpers
def query_all(sql, params=()):
    return get_db().execute(sql, params).fetchall()


def query_one(sql, params=()):
    return get_db().execute(sql, params).fetchone()


def execute(sql, params=()):
    db = get_db()
    db.execute(sql, params)
    db.commit()


# Date and formatting helpers
def utc_now():
    return datetime.utcnow()


def today_utc_date():
    return utc_now().date()


def parse_timestamp(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def format_timestamp(value):
    return value.replace(microsecond=0).isoformat(sep=" ")


def describe_due_time(raw_due_at):
    due_at = parse_timestamp(raw_due_at)
    if due_at is None:
        return "Now"
    now = utc_now()
    delta = due_at - now
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "Now"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"In {max(1, minutes)} min"
    hours = total_seconds // 3600
    if hours < 48:
        return f"In {hours} hr"
    days = total_seconds // 86400
    return f"In {days} days"


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_display_date(value):
    parsed = parse_date(value)
    if parsed is None:
        return ""
    today = today_utc_date()
    if parsed == today - timedelta(days=1):
        return "Yesterday"
    if parsed == today:
        return "Today"
    if parsed == today + timedelta(days=1):
        return "Tomorrow"
    return f"{parsed.day} {parsed.strftime('%B %Y')}"


# Flashcard review scheduling
def sm2_ease_factor(ease_factor, quality):
    ease_factor = ease_factor + (
        0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
    )
    return max(1.3, ease_factor)


def lapse_interval_days(interval_days, rating, again_count):
    base_interval = max(1, float(interval_days or 0))
    if rating == "good":
        if again_count <= 1:
            return max(1, round(base_interval * 0.25))
        if again_count == 2:
            return max(0.5, base_interval * 0.15)
        return max(10 / 1440, base_interval * 0.05)

    if again_count <= 1:
        return max(2, round(max(2, base_interval) * 0.5))
    if again_count == 2:
        return max(1, base_interval * 0.35)
    return max(1, base_interval * 0.25)


def apply_repeated_lapse_penalty(ease_factor, again_count):
    if again_count <= 1:
        return ease_factor
    return max(1.3, ease_factor - (0.05 * (again_count - 1)))


def schedule_flashcard(card, rating, missed_this_round=False, again_count=0):
    """Calculate the next due time for a card after Again, Good, or Easy."""
    now = utc_now()
    interval_days = float(card["interval_days"] or 0)
    ease_factor = float(card["ease_factor"] or 2.5)
    review_count = int(card["review_count"] or 0)
    again_count = int(again_count or 0)

    if rating == "again":
        review_count = 0
        interval_days = 0
        ease_factor = sm2_ease_factor(ease_factor, 1)
        due_at = now
    elif missed_this_round and rating == "good":
        review_count = 1
        ease_factor = sm2_ease_factor(ease_factor, 4)
        ease_factor = apply_repeated_lapse_penalty(ease_factor, again_count)
        interval_days = lapse_interval_days(interval_days, rating, again_count)
        due_at = now + timedelta(days=interval_days)
    elif missed_this_round and rating == "easy":
        review_count = 1
        ease_factor = sm2_ease_factor(ease_factor, 5)
        ease_factor = apply_repeated_lapse_penalty(ease_factor, again_count)
        interval_days = lapse_interval_days(interval_days, rating, again_count)
        due_at = now + timedelta(days=interval_days)
    elif rating == "good":
        ease_factor = sm2_ease_factor(ease_factor, 4)
        review_count += 1
        if review_count == 1:
            interval_days = 1
        elif review_count == 2:
            interval_days = 6
        else:
            interval_days = max(1, round(interval_days * ease_factor))
        due_at = now + timedelta(days=interval_days)
    else:
        ease_factor = sm2_ease_factor(ease_factor, 5)
        review_count += 1
        if review_count == 1:
            interval_days = 4
        elif review_count == 2:
            interval_days = 8
        else:
            interval_days = max(2, round(interval_days * ease_factor * 1.2))
        due_at = now + timedelta(days=interval_days)

    return {
        "review_count": review_count,
        "interval_days": interval_days,
        "ease_factor": ease_factor,
        "last_reviewed_at": format_timestamp(now),
        "due_at": format_timestamp(due_at),
    }


def format_review_interval_label(result):
    interval_days = float(result.get("interval_days") or 0)
    if interval_days >= 1:
        return f"{max(1, round(interval_days))}d"
    due_at = parse_timestamp(result["due_at"])
    if due_at is None:
        return ""
    delta = due_at - utc_now()
    total_seconds = max(0, int(delta.total_seconds()))
    if total_seconds < 3600:
        minutes = max(1, total_seconds // 60)
        return f"<{minutes + 1}m" if minutes < 10 else f"{minutes}m"
    if total_seconds < 86400:
        return f"{max(1, round(total_seconds / 3600))}h"
    days = max(1, round(total_seconds / 86400))
    return f"{days}d"


def build_review_time_labels(card, missed_this_round=False, again_count=0):
    return {
        "again": "<10m",
        "good": format_review_interval_label(
            schedule_flashcard(card, "good", missed_this_round, again_count)
        ),
        "easy": format_review_interval_label(
            schedule_flashcard(card, "easy", missed_this_round, again_count)
        ),
    }


def review_session_key(deck_id=None, exam_id=None):
    if exam_id:
        return f"exam:{exam_id}"
    if deck_id:
        return f"deck:{deck_id}"
    return "all"


def redirect_to_review(deck_id=None, exam_id=None, shuffle=False):
    params = {}
    if deck_id:
        params["deck_id"] = deck_id
    if exam_id:
        params["exam_id"] = exam_id
    if shuffle:
        params["shuffle"] = 1
    return redirect(url_for("review_flashcards", **params))


def review_url(deck_id=None, exam_id=None, shuffle=False):
    params = {}
    if deck_id:
        params["deck_id"] = deck_id
    if exam_id:
        params["exam_id"] = exam_id
    if shuffle:
        params["shuffle"] = 1
    return url_for("review_flashcards", **params)


def get_review_state(context_key):
    states = session.setdefault("review_states", {})
    state = states.setdefault(
        context_key,
        {"seen": 0, "retry_queue": [], "lapsed": [], "again_counts": {}},
    )
    state.setdefault("seen", 0)
    state.setdefault("retry_queue", [])
    state.setdefault("lapsed", [])
    state.setdefault("again_counts", {})
    for card_id in state["lapsed"]:
        state["again_counts"].setdefault(str(card_id), 1)
    return state


def save_review_state(context_key, state):
    states = session.setdefault("review_states", {})
    states[context_key] = state
    session["review_states"] = states
    session.modified = True


def queue_retry_card(context_key, card_id):
    state = get_review_state(context_key)
    card_id = int(card_id)
    card_key = str(card_id)
    state["seen"] += 1
    state["retry_queue"] = [
        item for item in state["retry_queue"] if int(item["card_id"]) != card_id
    ]
    state["retry_queue"].append({"card_id": card_id, "ready_after": state["seen"] + 3})
    if card_id not in state["lapsed"]:
        state["lapsed"].append(card_id)
    state["again_counts"][card_key] = int(state["again_counts"].get(card_key, 0)) + 1
    save_review_state(context_key, state)


def mark_review_answered(context_key, card_id):
    state = get_review_state(context_key)
    card_id = int(card_id)
    card_key = str(card_id)
    lapsed = card_id in state["lapsed"]
    again_count = int(state["again_counts"].get(card_key, 0))
    state["seen"] += 1
    state["retry_queue"] = [
        item for item in state["retry_queue"] if int(item["card_id"]) != card_id
    ]
    state["lapsed"] = [item for item in state["lapsed"] if int(item) != card_id]
    state["again_counts"].pop(card_key, None)
    save_review_state(context_key, state)
    return lapsed, again_count


def pop_ready_retry_card(context_key, due_card_ids):
    state = get_review_state(context_key)
    retry_queue = state["retry_queue"]
    if not retry_queue:
        return None

    due_card_ids = {int(card_id) for card_id in due_card_ids}
    ready_index = None
    for index, item in enumerate(retry_queue):
        card_id = int(item["card_id"])
        if card_id not in due_card_ids and int(item["ready_after"]) <= state["seen"]:
            ready_index = index
            break

    if ready_index is None and not due_card_ids:
        ready_index = 0

    if ready_index is None:
        return None

    card_id = int(retry_queue.pop(ready_index)["card_id"])
    save_review_state(context_key, state)
    return card_id


# Shared data lookups
def get_flashcard_decks():
    return query_all(
        """
        SELECT d.id,
               d.name,
               COUNT(f.id) AS card_count,
               SUM(CASE WHEN datetime(f.due_at) <= datetime('now') THEN 1 ELSE 0 END) AS due_count
        FROM flashcard_decks d
        LEFT JOIN flashcards f ON f.deck_id = d.id
        GROUP BY d.id, d.name
        ORDER BY lower(d.name)
        """
    )


def get_deck(deck_id):
    if not deck_id:
        return None
    return query_one("SELECT * FROM flashcard_decks WHERE id = ?", (deck_id,))


def get_pomodoro_settings():
    return query_one("SELECT * FROM pomodoro_settings WHERE id = 1")


def get_todo_projects():
    return query_all(
        """
        SELECT p.id,
               p.name,
               COUNT(t.id) AS task_count
        FROM todo_projects p
        LEFT JOIN todos t ON t.project_id = p.id AND t.is_done = 0
        GROUP BY p.id, p.name
        ORDER BY lower(p.name)
        """
    )


def parse_positive_int(value):
    value = (value or "").strip()
    if not value.isdigit():
        return None
    number = int(value)
    return number if number > 0 else None


# Calendar and exam helpers
def get_month_activity(year=None, month=None):
    """Build the monthly study calendar from flashcard review history."""
    today = today_utc_date()
    year = year or today.year
    month = month or today.month
    if month < 1 or month > 12:
        year = today.year
        month = today.month
    first_day = datetime(year, month, 1).date()
    _, days_in_month = calendar.monthrange(year, month)
    last_day = datetime(year, month, days_in_month).date()
    previous_month = first_day - timedelta(days=1)
    next_month = last_day + timedelta(days=1)
    rows = query_all(
        """
        SELECT substr(reviewed_at, 1, 10) AS day, COUNT(DISTINCT flashcard_id) AS total
        FROM review_history
        WHERE date(reviewed_at) BETWEEN date(?) AND date(?)
        GROUP BY substr(reviewed_at, 1, 10)
        """,
        (first_day.isoformat(), last_day.isoformat()),
    )
    counts = {row["day"]: row["total"] for row in rows}
    max_total = max(counts.values(), default=0)
    cells = []
    for _ in range(first_day.weekday()):
        cells.append({"empty": True})
    for day_number in range(1, days_in_month + 1):
        day = datetime(year, month, day_number).date()
        total = counts.get(day.isoformat(), 0)
        level = 0 if max_total == 0 else min(4, ((total * 4) + max_total - 1) // max_total)
        cells.append(
            {
                "empty": False,
                "day": day.isoformat(),
                "number": day_number,
                "count": total,
                "level": level,
                "is_today": day == today,
            }
        )
    return {
        "label": first_day.strftime("%B %Y"),
        "year": year,
        "month": month,
        "previous_year": previous_month.year,
        "previous_month": previous_month.month,
        "next_year": next_month.year,
        "next_month": next_month.month,
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "cells": cells,
    }


def get_exams():
    exams = query_all(
        """
        SELECT e.*, d.name AS deck_name
        FROM exams e
        LEFT JOIN flashcard_decks d ON d.id = e.deck_id
        ORDER BY date(e.exam_date) ASC
        """
    )
    return [exam_details(exam) for exam in exams]


def get_exam(exam_id):
    exam = query_one(
        """
        SELECT e.*, d.name AS deck_name
        FROM exams e
        LEFT JOIN flashcard_decks d ON d.id = e.deck_id
        WHERE e.id = ?
        """,
        (exam_id,),
    )
    return exam_details(exam) if exam else None


def exam_details(exam):
    deck_rows = query_all(
        """
        SELECT d.id, d.name
        FROM exam_decks ed
        JOIN flashcard_decks d ON d.id = ed.deck_id
        WHERE ed.exam_id = ?
        ORDER BY lower(d.name)
        """,
        (exam["id"],),
    )
    project_rows = query_all(
        """
        SELECT p.id, p.name
        FROM exam_projects ep
        JOIN todo_projects p ON p.id = ep.project_id
        WHERE ep.exam_id = ?
        ORDER BY lower(p.name)
        """,
        (exam["id"],),
    )
    todo_rows = query_all(
        """
        SELECT DISTINCT t.id, t.title, t.created_at
        FROM todos t
        LEFT JOIN exam_todos et ON et.todo_id = t.id AND et.exam_id = ?
        LEFT JOIN exam_projects ep ON ep.project_id = t.project_id AND ep.exam_id = ?
        WHERE et.exam_id IS NOT NULL OR ep.exam_id IS NOT NULL
        ORDER BY t.created_at ASC
        """,
        (exam["id"], exam["id"]),
    )
    direct_todo_rows = query_all(
        """
        SELECT t.id
        FROM exam_todos et
        JOIN todos t ON t.id = et.todo_id
        WHERE et.exam_id = ?
        """,
        (exam["id"],),
    )
    deck_names = [row["name"] for row in deck_rows]
    if not deck_names and exam["deck_name"]:
        deck_names = [exam["deck_name"]]
    exam_dict = dict(exam)
    exam_dict["deck_ids"] = [row["id"] for row in deck_rows]
    exam_dict["deck_names"] = deck_names
    exam_dict["project_ids"] = [row["id"] for row in project_rows]
    exam_dict["project_names"] = [row["name"] for row in project_rows]
    exam_dict["todo_ids"] = [row["id"] for row in direct_todo_rows]
    exam_dict["todo_titles"] = [row["title"] for row in todo_rows]
    return exam_dict


def exam_days_left():
    """Return exams with the number of days left until each exam date."""
    exams = []
    today = today_utc_date()
    for exam in get_exams():
        exam_date = parse_date(exam["exam_date"])
        if exam_date is None:
            continue
        days_left = (exam_date - today).days
        exams.append(
            {
                "id": exam["id"],
                "title": exam["title"],
                "deck_name": exam["deck_name"],
                "deck_names": exam["deck_names"],
                "project_names": exam["project_names"],
                "todo_titles": exam["todo_titles"],
                "exam_date": exam["exam_date"],
                "days_left": days_left,
                "status": "Upcoming" if days_left >= 0 else "Passed",
            }
        )
    return exams


def get_exam_study_todos(exam_id):
    rows = query_all(
        """
        SELECT DISTINCT t.*, p.name AS project_name
        FROM todos t
        LEFT JOIN todo_projects p ON p.id = t.project_id
        LEFT JOIN exam_todos et ON et.todo_id = t.id AND et.exam_id = ?
        LEFT JOIN exam_projects ep ON ep.project_id = t.project_id AND ep.exam_id = ?
        WHERE et.exam_id IS NOT NULL OR ep.exam_id IS NOT NULL
        ORDER BY t.is_done ASC, date(t.due_date) IS NULL, date(t.due_date) ASC, t.created_at ASC
        """,
        (exam_id, exam_id),
    )
    todos = []
    for row in rows:
        todo = dict(row)
        todo["due_label"] = format_display_date(todo["due_date"])
        todos.append(todo)
    return todos


def get_exam_study_decks(exam):
    decks = []
    for deck_id in exam["deck_ids"]:
        deck = query_one(
            """
            SELECT d.id,
                   d.name,
                   COUNT(f.id) AS card_count,
                   SUM(CASE WHEN datetime(f.due_at) <= datetime('now') THEN 1 ELSE 0 END) AS due_count
            FROM flashcard_decks d
            LEFT JOIN flashcards f ON f.deck_id = d.id
            WHERE d.id = ?
            GROUP BY d.id, d.name
            """,
            (deck_id,),
        )
        if deck:
            decks.append(deck)
    return decks


def plan_exam_prep_dates(exam_id):
    exam = get_exam(exam_id)
    if exam is None:
        return False

    exam_date = parse_date(exam["exam_date"])
    if exam_date is None:
        return False

    today = today_utc_date()
    prep_deadline = exam_date - timedelta(days=1) if exam_date > today else today
    prep_deadline_text = prep_deadline.isoformat()
    db = get_db()

    todos = get_exam_study_todos(exam_id)
    for todo in todos:
        due_date = todo["due_date"]
        if not due_date or due_date > prep_deadline_text:
            db.execute(
                "UPDATE todos SET due_date = ? WHERE id = ?",
                (prep_deadline_text, todo["id"]),
            )

    if exam["deck_ids"]:
        placeholders = ", ".join("?" for _ in exam["deck_ids"])
        cards = db.execute(
            f"""
            SELECT id, due_at
            FROM flashcards
            WHERE deck_id IN ({placeholders})
              AND (due_at IS NULL OR date(due_at) > date(?))
            ORDER BY datetime(due_at) ASC, id ASC
            """,
            (*exam["deck_ids"], prep_deadline_text),
        ).fetchall()

        available_days = max(1, (prep_deadline - today).days + 1)
        for index, card in enumerate(cards):
            scheduled_day = today + timedelta(days=index % available_days)
            scheduled_at = datetime.combine(scheduled_day, datetime.min.time()) + timedelta(hours=9)
            db.execute(
                "UPDATE flashcards SET due_at = ? WHERE id = ?",
                (format_timestamp(scheduled_at), card["id"]),
            )

    db.commit()
    return True


def get_daily_plan():
    """Build today's study plan from due flashcards, tasks, and exams."""
    today = today_utc_date().isoformat()
    due_flashcards = query_all(
        """
        SELECT f.id, f.question, f.due_at, d.name AS deck_name
        FROM flashcards f
        JOIN flashcard_decks d ON d.id = f.deck_id
        WHERE datetime(f.due_at) <= datetime('now')
        ORDER BY datetime(f.due_at) ASC
        LIMIT 10
        """
    )
    carryover_tasks = query_all(
        """
        SELECT id, title, due_date, created_at
        FROM todos
        WHERE is_done = 0
          AND due_date IS NOT NULL
          AND due_date < ?
        ORDER BY date(due_date) ASC, created_at ASC
        """,
        (today,),
    )
    todays_tasks = query_all(
        """
        SELECT id, title, due_date, is_done, created_at
        FROM todos
        WHERE due_date IS NOT NULL
          AND due_date = ?
        ORDER BY is_done ASC, created_at ASC
        """,
        (today,),
    )
    undated_tasks = query_all(
        """
        SELECT id, title, created_at
        FROM todos
        WHERE is_done = 0
          AND due_date IS NULL
        ORDER BY created_at ASC
        LIMIT 5
        """
    )
    exams = [exam for exam in exam_days_left() if exam["days_left"] >= 0][:3]
    return {
        "due_flashcards": due_flashcards,
        "carryover_tasks": carryover_tasks,
        "todays_tasks": todays_tasks,
        "undated_tasks": undated_tasks,
        "exam_countdowns": exams,
    }


def get_today_summary(plan):
    """Prepare the small dashboard schedule cards for today's overview."""
    due_exam_count = sum(1 for exam in plan["exam_countdowns"] if exam["days_left"] == 0)
    return [
        {
            "initial": "F",
            "title": "Flashcards",
            "meta": f"{len(plan['due_flashcards'])} due today",
            "tone": "green",
        },
        {
            "initial": "D",
            "title": "Decks",
            "meta": f"{len(get_flashcard_decks())} total decks",
            "tone": "purple",
        },
        {
            "initial": "T",
            "title": "To-dos",
            "meta": f"{len(plan['carryover_tasks']) + len(plan['todays_tasks'])} need attention",
            "tone": "orange",
        },
        {
            "initial": "E",
            "title": "Exams",
            "meta": f"{due_exam_count} due today",
            "tone": "blue",
        },
    ]


@app.context_processor
def site_data():
    """Share common template data across pages."""
    return {
        "decks": get_flashcard_decks(),
    }


# Dashboard
@app.route("/")
def index():
    stats = {
        "flashcards": query_one("SELECT COUNT(*) AS count FROM flashcards")["count"],
        "decks": query_one("SELECT COUNT(*) AS count FROM flashcard_decks")["count"],
        "todos": query_one("SELECT COUNT(*) AS count FROM todos")["count"],
        "open_todos": query_one("SELECT COUNT(*) AS count FROM todos WHERE is_done = 0")["count"],
        "notes": query_one("SELECT COUNT(*) AS count FROM notes")["count"],
    }
    plan = get_daily_plan()
    calendar_year = request.args.get("year", type=int)
    calendar_month = request.args.get("month", type=int)
    activity_calendar = get_month_activity(calendar_year, calendar_month)
    return render_template(
        "index.html",
        stats=stats,
        plan=plan,
        activity_calendar=activity_calendar,
        today_summary=get_today_summary(plan),
    )


@app.route("/daily-plan")
def daily_plan():
    plan = get_daily_plan()
    calendar_year = request.args.get("year", type=int)
    calendar_month = request.args.get("month", type=int)
    return render_template(
        "daily_plan.html",
        plan=plan,
        activity_calendar=get_month_activity(calendar_year, calendar_month),
        exam_countdowns=plan["exam_countdowns"],
    )


# Exam study page
@app.get("/exams/<int:exam_id>/study")
def study_exam(exam_id):
    exam = get_exam(exam_id)
    if exam is None:
        flash("Exam not found.", "error")
        return redirect(url_for("exams"))
    return render_template(
        "exam_study.html",
        exam=exam,
        decks=get_exam_study_decks(exam),
        todos=get_exam_study_todos(exam_id),
    )


# Flashcards
@app.route("/flashcards", methods=["GET", "POST"])
def flashcards():
    selected_deck_id = request.args.get("deck_id", type=int)
    if request.method == "POST":
        question = request.form["question"].strip()
        answer = request.form["answer"].strip()
        deck_id = request.form.get("deck_id", type=int)
        if not question or not answer or not deck_id:
            pass
        elif get_deck(deck_id) is None:
            flash("Selected deck does not exist.", "error")
        else:
            execute(
                """
                INSERT INTO flashcards (question, answer, deck_id, due_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (question, answer, deck_id),
            )
        return redirect(url_for("flashcards", deck_id=deck_id or selected_deck_id))

    decks = get_flashcard_decks()
    selected_deck = get_deck(selected_deck_id)

    params = []
    where_clause = ""
    if selected_deck is not None:
        where_clause = "WHERE f.deck_id = ?"
        params.append(selected_deck_id)

    cards = query_all(
        f"""
        SELECT f.*, d.name AS deck_name
        FROM flashcards f
        JOIN flashcard_decks d ON d.id = f.deck_id
        {where_clause}
        ORDER BY datetime(f.due_at) ASC, f.created_at DESC
        """,
        tuple(params),
    )

    if selected_deck is not None:
        due_count = query_one(
            """
            SELECT COUNT(*) AS count
            FROM flashcards
            WHERE deck_id = ? AND datetime(due_at) <= datetime('now')
            """,
            (selected_deck_id,),
        )["count"]
    else:
        due_count = query_one(
            "SELECT COUNT(*) AS count FROM flashcards WHERE datetime(due_at) <= datetime('now')"
        )["count"]

    card_list = [
        {
            "id": card["id"],
            "question": card["question"],
            "answer": card["answer"],
            "deck_name": card["deck_name"],
            "review_count": card["review_count"],
            "due_label": describe_due_time(card["due_at"]),
        }
        for card in cards
    ]
    return render_template(
        "flashcards.html",
        cards=card_list,
        decks=decks,
        due_count=due_count,
        selected_deck_id=selected_deck_id,
        selected_deck=selected_deck,
    )


@app.get("/flashcard-decks/<int:deck_id>")
def flashcard_deck(deck_id):
    deck = get_deck(deck_id)
    if deck is None:
        flash("Deck not found.", "error")
        return redirect(url_for("flashcards"))

    cards = query_all(
        """
        SELECT *
        FROM flashcards
        WHERE deck_id = ?
        ORDER BY datetime(due_at) ASC, created_at DESC
        """,
        (deck_id,),
    )
    due_count = query_one(
        """
        SELECT COUNT(*) AS count
        FROM flashcards
        WHERE deck_id = ? AND datetime(due_at) <= datetime('now')
        """,
        (deck_id,),
    )["count"]
    return render_template(
        "deck_detail.html",
        deck=deck,
        cards=cards,
        due_count=due_count,
    )


@app.route("/flashcard-decks/<int:deck_id>/cards/new", methods=["GET", "POST"])
def new_flashcard(deck_id):
    deck = get_deck(deck_id)
    if deck is None:
        flash("Deck not found.", "error")
        return redirect(url_for("flashcards"))

    if request.method == "POST":
        question = request.form["question"].strip()
        answer = request.form["answer"].strip()
        if not question or not answer:
            pass
        else:
            execute(
                """
                INSERT INTO flashcards (question, answer, deck_id, due_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (question, answer, deck_id),
            )
            return redirect(url_for("new_flashcard", deck_id=deck_id))

    return render_template("new_flashcard.html", deck=deck)


@app.route("/flashcards/<int:card_id>/edit", methods=["GET", "POST"])
def edit_flashcard(card_id):
    card = query_one("SELECT * FROM flashcards WHERE id = ?", (card_id,))
    if card is None:
        flash("Flashcard not found.", "error")
        return redirect(url_for("flashcards"))

    deck = get_deck(card["deck_id"])
    if deck is None:
        flash("Deck not found.", "error")
        return redirect(url_for("flashcards"))

    if request.method == "POST":
        question = request.form["question"].strip()
        answer = request.form["answer"].strip()
        if question and answer:
            execute(
                """
                UPDATE flashcards
                SET question = ?, answer = ?
                WHERE id = ?
                """,
                (question, answer, card_id),
            )
            return redirect(url_for("flashcard_deck", deck_id=deck["id"]))

    return render_template("new_flashcard.html", deck=deck, card=card, is_edit=True)


@app.post("/flashcard-decks")
def create_flashcard_deck():
    name = request.form["name"].strip()
    if not name:
        return redirect(url_for("new_flashcard_deck"))
    try:
        execute("INSERT INTO flashcard_decks (name) VALUES (?)", (name,))
    except sqlite3.IntegrityError:
        flash("A deck with that name already exists.", "error")
        return redirect(url_for("new_flashcard_deck"))
    return redirect(url_for("flashcards"))


@app.get("/flashcard-decks/new")
def new_flashcard_deck():
    return render_template("new_deck.html")


@app.get("/flashcards/review")
def review_flashcards():
    """Show the next due flashcard, including deck, exam, and retry-session filters."""
    selected_deck_id = request.args.get("deck_id", type=int)
    selected_exam_id = request.args.get("exam_id", type=int)
    shuffle_cards = request.args.get("shuffle") == "1"
    selected_deck = get_deck(selected_deck_id)
    selected_exam = get_exam(selected_exam_id) if selected_exam_id else None
    decks = get_flashcard_decks()
    context_key = review_session_key(selected_deck_id, selected_exam_id)
    review_state = get_review_state(context_key)

    params = []
    deck_filter = ""
    if selected_exam is not None:
        if selected_exam["deck_ids"]:
            placeholders = ", ".join("?" for _ in selected_exam["deck_ids"])
            deck_filter = f"AND f.deck_id IN ({placeholders})"
            params.extend(selected_exam["deck_ids"])
        else:
            deck_filter = "AND 1 = 0"
    elif selected_deck is not None:
        deck_filter = "AND f.deck_id = ?"
        params.append(selected_deck_id)

    raw_due_cards = query_all(
        f"""
        SELECT f.*, d.name AS deck_name
        FROM flashcards f
        JOIN flashcard_decks d ON d.id = f.deck_id
        WHERE datetime(f.due_at) <= datetime('now')
        {deck_filter}
        ORDER BY datetime(f.due_at) ASC, f.created_at ASC
        """,
        tuple(params),
    )
    queued_card_ids = {
        int(item["card_id"]) for item in review_state["retry_queue"]
    }
    due_cards = [
        card for card in raw_due_cards if int(card["id"]) not in queued_card_ids
    ]
    if shuffle_cards:
        due_cards = list(due_cards)
        random.shuffle(due_cards)
    retry_card_id = pop_ready_retry_card(
        context_key,
        [card["id"] for card in due_cards],
    )
    retry_card = None
    if retry_card_id:
        retry_card = query_one(
            """
            SELECT f.*, d.name AS deck_name
            FROM flashcards f
            JOIN flashcard_decks d ON d.id = f.deck_id
            WHERE f.id = ?
            """,
            (retry_card_id,),
        )
    current_card = retry_card or (due_cards[0] if due_cards else None)
    retry_count = len(get_review_state(context_key)["retry_queue"])
    remaining = max(0, len(due_cards) - (0 if retry_card else 1)) + retry_count
    review_time_labels = None
    if current_card:
        state = get_review_state(context_key)
        current_card_key = str(int(current_card["id"]))
        current_again_count = int(state["again_counts"].get(current_card_key, 0))
        review_time_labels = build_review_time_labels(
            current_card,
            int(current_card["id"]) in state["lapsed"],
            current_again_count,
        )
    next_due = None
    if current_card is None:
        if selected_exam is not None:
            if selected_exam["deck_ids"]:
                placeholders = ", ".join("?" for _ in selected_exam["deck_ids"])
                next_due = query_one(
                    f"""
                    SELECT due_at
                    FROM flashcards
                    WHERE deck_id IN ({placeholders})
                    ORDER BY datetime(due_at) ASC
                    LIMIT 1
                    """,
                    tuple(selected_exam["deck_ids"]),
                )
        elif selected_deck is not None:
            next_due = query_one(
                """
                SELECT due_at
                FROM flashcards
                WHERE deck_id = ?
                ORDER BY datetime(due_at) ASC
                LIMIT 1
                """,
                (selected_deck_id,),
            )
        else:
            next_due = query_one(
                """
                SELECT due_at
                FROM flashcards
                ORDER BY datetime(due_at) ASC
                LIMIT 1
                """
            )
    return render_template(
        "flashcard_review.html",
        card=current_card,
        decks=decks,
        remaining=remaining,
        selected_deck_id=selected_deck_id,
        selected_deck=selected_deck,
        selected_exam=selected_exam,
        selected_exam_id=selected_exam_id,
        shuffle_cards=shuffle_cards,
        shuffled_review_url=review_url(selected_deck_id, selected_exam_id, True),
        normal_review_url=review_url(selected_deck_id, selected_exam_id, False),
        review_time_labels=review_time_labels,
        next_due_label=describe_due_time(next_due["due_at"]) if next_due else None,
    )


@app.post("/flashcards/<int:card_id>/review")
def review_flashcard(card_id):
    """Save one flashcard review answer and schedule the next review time."""
    rating = request.form["rating"]
    deck_id = request.form.get("deck_id", type=int)
    exam_id = request.form.get("exam_id", type=int)
    shuffle_cards = request.form.get("shuffle") == "1"
    context_key = review_session_key(deck_id, exam_id)
    if rating not in {"again", "good", "easy"}:
        flash("Unknown review rating.", "error")
        return redirect_to_review(deck_id, exam_id, shuffle_cards)

    card = query_one("SELECT * FROM flashcards WHERE id = ?", (card_id,))
    if card is None:
        flash("Flashcard not found.", "error")
        return redirect_to_review(deck_id, exam_id, shuffle_cards)

    missed_this_round = False
    again_count = 0
    if rating == "again":
        queue_retry_card(context_key, card_id)
        result = schedule_flashcard(card, rating)
    else:
        missed_this_round, again_count = mark_review_answered(context_key, card_id)
        result = schedule_flashcard(card, rating, missed_this_round, again_count)
    db = get_db()
    db.execute(
        """
        UPDATE flashcards
        SET review_count = ?,
            interval_days = ?,
            ease_factor = ?,
            last_reviewed_at = ?,
            due_at = ?
        WHERE id = ?
        """,
        (
            result["review_count"],
            result["interval_days"],
            result["ease_factor"],
            result["last_reviewed_at"],
            result["due_at"],
            card_id,
        ),
    )
    db.execute(
        """
        INSERT INTO review_history (flashcard_id, rating, reviewed_at)
        VALUES (?, ?, ?)
        """,
        (card_id, rating, result["last_reviewed_at"]),
    )
    db.commit()
    return redirect_to_review(deck_id, exam_id, shuffle_cards)


@app.post("/flashcards/<int:card_id>/delete")
def delete_flashcard(card_id):
    deck_id = request.form.get("deck_id", type=int)
    execute("DELETE FROM flashcards WHERE id = ?", (card_id,))
    if deck_id:
        return redirect(url_for("flashcard_deck", deck_id=deck_id))
    return redirect(url_for("flashcards"))


# To-dos
@app.route("/todos", methods=["GET", "POST"])
def todos():
    if request.method == "POST":
        action = request.form.get("action", "add_task")
        if action == "add_project":
            project_name = request.form.get("project_name", "").strip()
            if not project_name:
                flash("Project name cannot be empty.", "error")
            else:
                try:
                    execute("INSERT INTO todo_projects (name) VALUES (?)", (project_name,))
                except sqlite3.IntegrityError:
                    flash("A project with that name already exists.", "error")
            return redirect(url_for("todos"))

        title = request.form.get("title", "").strip()
        due_date = request.form.get("due_date", "").strip() or None
        project_id = request.form.get("project_id", type=int)
        if project_id and query_one("SELECT id FROM todo_projects WHERE id = ?", (project_id,)) is None:
            pass
        elif not title:
            pass
        else:
            execute(
                "INSERT INTO todos (title, due_date, project_id) VALUES (?, ?, ?)",
                (title, due_date, project_id),
            )
        return redirect(url_for("todos"))

    view = request.args.get("view", "inbox")
    search = request.args.get("search", "").strip()
    project_id = request.args.get("project_id", type=int)
    today = today_utc_date().isoformat()

    where = []
    params = []
    page_title = "Inbox"

    if search:
        where.append("lower(t.title) LIKE lower(?)")
        params.append(f"%{search}%")
        page_title = "Search Results"
    elif project_id:
        where.append("t.project_id = ?")
        params.append(project_id)
        project = query_one("SELECT name FROM todo_projects WHERE id = ?", (project_id,))
        page_title = project["name"] if project else "Project"
    elif view == "done":
        where.append("t.is_done = 1")
        page_title = "Done"
    elif view == "today":
        where.append("t.is_done = 0")
        where.append("t.due_date = ?")
        params.append(today)
        page_title = "Today"
    elif view == "upcoming":
        where.append("t.is_done = 0")
        where.append("t.due_date > ?")
        params.append(today)
        page_title = "Upcoming"
    else:
        view = "inbox"
        where.append("t.is_done = 0")

    where_clause = f"WHERE {' AND '.join(where)}" if where else ""
    raw_items = query_all(
        f"""
        SELECT t.*, p.name AS project_name
        FROM todos t
        LEFT JOIN todo_projects p ON p.id = t.project_id
        {where_clause}
        ORDER BY t.is_done, date(t.due_date) IS NULL, date(t.due_date) ASC, t.created_at DESC
        """,
        tuple(params),
    )
    items = []
    for item in raw_items:
        item_data = dict(item)
        item_data["due_label"] = format_display_date(item["due_date"])
        items.append(item_data)
    counts = {
        "done": query_one("SELECT COUNT(*) AS count FROM todos WHERE is_done = 1")["count"],
        "inbox": query_one("SELECT COUNT(*) AS count FROM todos WHERE is_done = 0")["count"],
        "today": query_one(
            "SELECT COUNT(*) AS count FROM todos WHERE is_done = 0 AND due_date = ?",
            (today,),
        )["count"],
        "upcoming": query_one(
            "SELECT COUNT(*) AS count FROM todos WHERE is_done = 0 AND due_date > ?",
            (today,),
        )["count"],
    }
    return render_template(
        "todos.html",
        items=items,
        projects=get_todo_projects(),
        counts=counts,
        active_view=view,
        active_project_id=project_id,
        page_title=page_title,
        search=search,
        today=today,
    )


@app.post("/todos/<int:todo_id>/toggle")
def toggle_todo(todo_id):
    item = query_one("SELECT is_done FROM todos WHERE id = ?", (todo_id,))
    if item is not None:
        new_value = 0 if item["is_done"] else 1
        completed_at = format_timestamp(utc_now()) if new_value == 1 else None
        execute(
            "UPDATE todos SET is_done = ?, completed_at = ? WHERE id = ?",
            (new_value, completed_at, todo_id),
        )
    next_page = request.form.get("next")
    if next_page == "daily_plan":
        return redirect(url_for("daily_plan"))
    if next_page == "exam_study":
        exam_id = request.form.get("exam_id", type=int)
        if exam_id:
            return redirect(url_for("study_exam", exam_id=exam_id))
    return redirect(url_for("todos"))


@app.post("/todos/<int:todo_id>/delete")
def delete_todo(todo_id):
    execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return redirect(url_for("todos"))


# Notes
@app.route("/notes", methods=["GET", "POST"])
def notes():
    if request.method == "POST":
        note_id = request.form.get("note_id", type=int)
        title = request.form["title"].strip()
        content = request.form["content"].strip()
        alignment = request.form.get("alignment", "left")
        if alignment not in {"left", "center", "right"}:
            alignment = "left"
        if not title or not content:
            pass
        elif note_id and query_one("SELECT id FROM notes WHERE id = ?", (note_id,)) is not None:
            execute(
                """
                UPDATE notes
                SET title = ?, content = ?, alignment = ?
                WHERE id = ?
                """,
                (title, content, alignment, note_id),
            )
            return redirect(url_for("notes", note_id=note_id))
        else:
            execute(
                "INSERT INTO notes (title, content, alignment) VALUES (?, ?, ?)",
                (title, content, alignment),
            )
        return redirect(url_for("notes"))

    all_notes = query_all("SELECT * FROM notes ORDER BY created_at DESC")
    selected_note_id = request.args.get("note_id", type=int)
    selected_note = None
    if selected_note_id:
        selected_note = query_one("SELECT * FROM notes WHERE id = ?", (selected_note_id,))
    decks = get_flashcard_decks()
    return render_template(
        "notes.html",
        notes=all_notes,
        selected_note=selected_note,
        decks=decks,
    )


@app.post("/notes/flashcards")
def save_note_flashcards():
    """Create flashcards from the draft rows prepared on the notes page."""
    deck_id = request.form.get("deck_id", type=int)
    source_note_id = request.form.get("note_id", type=int)
    terms = request.form.getlist("terms")
    definitions = request.form.getlist("definitions")
    if not deck_id or get_deck(deck_id) is None:
        return redirect(url_for("notes", note_id=source_note_id) if source_note_id else url_for("notes"))

    cards = []
    for term, definition in zip(terms, definitions):
        term = term.strip()
        definition = definition.strip()
        if term and definition:
            cards.append((term, definition))

    if not cards:
        return redirect(url_for("notes", note_id=source_note_id) if source_note_id else url_for("notes"))

    db = get_db()
    note_exists = (
        source_note_id
        and query_one("SELECT id FROM notes WHERE id = ?", (source_note_id,)) is not None
    )
    for term, definition in cards:
        db.execute(
            """
            INSERT INTO flashcards (question, answer, deck_id, source_note_id, due_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (term, definition, deck_id, source_note_id if note_exists else None),
        )
    db.commit()
    return redirect(url_for("flashcard_deck", deck_id=deck_id))


@app.post("/notes/<int:note_id>/delete")
def delete_note(note_id):
    execute("DELETE FROM notes WHERE id = ?", (note_id,))
    return redirect(url_for("notes"))


# Pomodoro
@app.route("/pomodoro", methods=["GET", "POST"])
def pomodoro():
    if request.method == "POST":
        action = request.form.get("action")
        if action == "save_settings":
            focus_minutes = parse_positive_int(request.form.get("focus_minutes"))
            short_break_minutes = parse_positive_int(request.form.get("short_break_minutes"))
            long_break_minutes = parse_positive_int(request.form.get("long_break_minutes"))
            sessions_until_long_break = parse_positive_int(
                request.form.get("sessions_until_long_break")
            )
            if None in {
                focus_minutes,
                short_break_minutes,
                long_break_minutes,
                sessions_until_long_break,
            }:
                pass
            else:
                execute(
                    """
                    UPDATE pomodoro_settings
                    SET focus_minutes = ?,
                        break_minutes = ?,
                        short_break_minutes = ?,
                        long_break_minutes = ?,
                        sessions_until_long_break = ?
                    WHERE id = 1
                    """,
                    (
                        focus_minutes,
                        short_break_minutes,
                        short_break_minutes,
                        long_break_minutes,
                        sessions_until_long_break,
                    ),
                )
            return redirect(url_for("pomodoro"))

        duration = request.form["duration_minutes"].strip()
        if not duration.isdigit():
            pass
        else:
            execute(
                "INSERT INTO pomodoro_sessions (duration_minutes) VALUES (?)",
                (int(duration),),
            )
        return redirect(url_for("pomodoro"))

    sessions = query_all(
        "SELECT * FROM pomodoro_sessions ORDER BY completed_at DESC LIMIT 10"
    )
    settings = get_pomodoro_settings()
    return render_template("pomodoro.html", sessions=sessions, settings=settings)


# Exams
@app.route("/exams", methods=["GET", "POST"])
def exams():
    if request.method == "POST":
        exam_id = request.form.get("exam_id", type=int)
        title = request.form.get("title", "").strip()
        exam_date = request.form.get("exam_date", "").strip()
        deck_ids = request.form.getlist("deck_ids")
        todo_ids = request.form.getlist("todo_ids")
        project_ids = request.form.getlist("project_ids")
        notes = request.form.get("notes", "").strip()
        if not title or not exam_date:
            pass
        else:
            db = get_db()
            if exam_id and db.execute(
                "SELECT id FROM exams WHERE id = ?", (exam_id,)
            ).fetchone():
                db.execute(
                    """
                    UPDATE exams
                    SET title = ?, exam_date = ?, notes = ?
                    WHERE id = ?
                    """,
                    (title, exam_date, notes or None, exam_id),
                )
                db.execute("DELETE FROM exam_decks WHERE exam_id = ?", (exam_id,))
                db.execute("DELETE FROM exam_todos WHERE exam_id = ?", (exam_id,))
                db.execute("DELETE FROM exam_projects WHERE exam_id = ?", (exam_id,))
            else:
                db.execute(
                    """
                    INSERT INTO exams (title, exam_date, notes)
                    VALUES (?, ?, ?)
                    """,
                    (title, exam_date, notes or None),
                )
                exam_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            for deck_id in deck_ids:
                db.execute(
                    "INSERT INTO exam_decks (exam_id, deck_id) VALUES (?, ?)",
                    (exam_id, deck_id),
                )
            for todo_id in todo_ids:
                db.execute(
                    "INSERT INTO exam_todos (exam_id, todo_id) VALUES (?, ?)",
                    (exam_id, todo_id),
                )
            for project_id in project_ids:
                db.execute(
                    "INSERT INTO exam_projects (exam_id, project_id) VALUES (?, ?)",
                    (exam_id, project_id),
                )
            db.commit()
        return redirect(url_for("exams", exam_id=exam_id) if exam_id else url_for("exams"))

    all_exams = get_exams()
    selected_exam_id = request.args.get("exam_id", type=int)
    selected_exam = None
    if selected_exam_id:
        selected_exam = next(
            (exam for exam in all_exams if exam["id"] == selected_exam_id),
            None,
        )
    return render_template(
        "exams.html",
        exams=exam_days_left(),
        raw_exams=all_exams,
        selected_exam=selected_exam,
        todo_projects=get_todo_projects(),
        open_todos=query_all(
            """
            SELECT t.id, t.title, t.due_date, p.name AS project_name
            FROM todos t
            LEFT JOIN todo_projects p ON p.id = t.project_id
            WHERE is_done = 0
            ORDER BY date(t.due_date) ASC, t.created_at ASC
            """
        ),
    )


@app.post("/exams/<int:exam_id>/delete")
def delete_exam(exam_id):
    db = get_db()
    db.execute("DELETE FROM exam_decks WHERE exam_id = ?", (exam_id,))
    db.execute("DELETE FROM exam_todos WHERE exam_id = ?", (exam_id,))
    db.execute("DELETE FROM exam_projects WHERE exam_id = ?", (exam_id,))
    db.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    db.commit()
    return redirect(url_for("exams"))


@app.post("/exams/<int:exam_id>/plan-prep")
def plan_exam_prep(exam_id):
    if not plan_exam_prep_dates(exam_id):
        flash("Exam not found.", "error")
        return redirect(url_for("exams"))
    flash("Dates updated for the exam")
    next_page = request.form.get("next")
    if next_page == "exam_study":
        return redirect(url_for("study_exam", exam_id=exam_id))
    return redirect(url_for("exams", exam_id=exam_id))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
