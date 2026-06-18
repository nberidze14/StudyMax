CREATE TABLE IF NOT EXISTS flashcard_decks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    deck_id INTEGER NOT NULL,
    review_count INTEGER NOT NULL DEFAULT 0,
    interval_days REAL NOT NULL DEFAULT 0,
    ease_factor REAL NOT NULL DEFAULT 2.5,
    last_reviewed_at TEXT,
    due_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_note_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id),
    FOREIGN KEY (source_note_id) REFERENCES notes (id)
);

CREATE TABLE IF NOT EXISTS todos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    is_done INTEGER NOT NULL DEFAULT 0,
    due_date TEXT,
    project_id INTEGER,
    completed_at TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES todo_projects (id)
);

CREATE TABLE IF NOT EXISTS todo_projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    alignment TEXT NOT NULL DEFAULT 'left',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pomodoro_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    duration_minutes INTEGER NOT NULL,
    completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS pomodoro_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    focus_minutes INTEGER NOT NULL DEFAULT 25,
    break_minutes INTEGER NOT NULL DEFAULT 5,
    short_break_minutes INTEGER NOT NULL DEFAULT 5,
    long_break_minutes INTEGER NOT NULL DEFAULT 15,
    sessions_until_long_break INTEGER NOT NULL DEFAULT 4
);

CREATE TABLE IF NOT EXISTS review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flashcard_id INTEGER NOT NULL,
    rating TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    FOREIGN KEY (flashcard_id) REFERENCES flashcards (id)
);

CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    deck_id INTEGER,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id)
);

CREATE TABLE IF NOT EXISTS exam_decks (
    exam_id INTEGER NOT NULL,
    deck_id INTEGER NOT NULL,
    PRIMARY KEY (exam_id, deck_id),
    FOREIGN KEY (exam_id) REFERENCES exams (id),
    FOREIGN KEY (deck_id) REFERENCES flashcard_decks (id)
);

CREATE TABLE IF NOT EXISTS exam_todos (
    exam_id INTEGER NOT NULL,
    todo_id INTEGER NOT NULL,
    PRIMARY KEY (exam_id, todo_id),
    FOREIGN KEY (exam_id) REFERENCES exams (id),
    FOREIGN KEY (todo_id) REFERENCES todos (id)
);

CREATE TABLE IF NOT EXISTS exam_projects (
    exam_id INTEGER NOT NULL,
    project_id INTEGER NOT NULL,
    PRIMARY KEY (exam_id, project_id),
    FOREIGN KEY (exam_id) REFERENCES exams (id),
    FOREIGN KEY (project_id) REFERENCES todo_projects (id)
);
