from pathlib import Path
import gc
import sqlite3
import tempfile

import app as studymax


def assert_status(response, expected=200):
    if response.status_code != expected:
        raise AssertionError(f"Expected {expected}, got {response.status_code}")


def assert_redirect(response):
    if response.status_code not in {302, 303}:
        raise AssertionError(f"Expected redirect, got {response.status_code}")


def run():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
        studymax.DATABASE = Path(tmpdir) / "studymax_test.db"
        studymax.app.config["TESTING"] = True
        studymax.init_db()
        client = studymax.app.test_client()

        pages = [
            "/",
            "/daily-plan",
            "/flashcards",
            "/flashcards/review",
            "/notes",
            "/todos",
            "/pomodoro",
            "/exams",
        ]
        for path in pages:
            assert_status(client.get(path))

        assert_redirect(client.post("/flashcard-decks", data={"name": "Demo Deck"}))
        with sqlite3.connect(studymax.DATABASE) as db:
            deck_id = db.execute(
                "SELECT id FROM flashcard_decks WHERE name = ?",
                ("Demo Deck",),
            ).fetchone()[0]

        assert_redirect(
            client.post(
                f"/flashcard-decks/{deck_id}/cards/new",
                data={"question": "Front", "answer": "Back"},
            )
        )
        assert_status(client.get(f"/flashcard-decks/{deck_id}"))

        with sqlite3.connect(studymax.DATABASE) as db:
            card_id = db.execute(
                "SELECT id FROM flashcards WHERE deck_id = ?",
                (deck_id,),
            ).fetchone()[0]
        assert_redirect(
            client.post(
                f"/flashcards/{card_id}/review",
                data={"rating": "good", "deck_id": deck_id},
            )
        )

        assert_redirect(
            client.post(
                "/todos",
                data={"action": "add_project", "project_name": "Demo Project"},
            )
        )
        with sqlite3.connect(studymax.DATABASE) as db:
            project_id = db.execute(
                "SELECT id FROM todo_projects WHERE name = ?",
                ("Demo Project",),
            ).fetchone()[0]
        assert_redirect(
            client.post(
                "/todos",
                data={
                    "action": "add_task",
                    "title": "Demo task",
                    "due_date": "2026-06-08",
                    "project_id": project_id,
                },
            )
        )

        assert_redirect(
            client.post(
                "/notes",
                data={
                    "title": "Demo note",
                    "content": "term (definition)",
                    "alignment": "left",
                },
            )
        )
        assert_redirect(
            client.post(
                "/notes/flashcards",
                data={
                    "deck_id": deck_id,
                    "terms": ["term"],
                    "definitions": ["definition"],
                },
            )
        )

        assert_redirect(
            client.post(
                "/pomodoro",
                data={
                    "action": "save_settings",
                    "focus_minutes": 25,
                    "short_break_minutes": 5,
                    "long_break_minutes": 15,
                    "sessions_until_long_break": 4,
                },
            )
        )

        assert_redirect(
            client.post(
                "/exams",
                data={
                    "title": "Demo Exam",
                    "exam_date": "2026-06-20",
                    "deck_ids": [deck_id],
                    "project_ids": [project_id],
                },
            )
        )
        with sqlite3.connect(studymax.DATABASE) as db:
            exam_id = db.execute(
                "SELECT id FROM exams WHERE title = ?",
                ("Demo Exam",),
            ).fetchone()[0]
        assert_status(client.get(f"/exams/{exam_id}/study"))

        del client
        gc.collect()

    print("Smoke test passed.")


if __name__ == "__main__":
    run()
