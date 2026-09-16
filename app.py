import os
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, g
from anthropic import Anthropic

load_dotenv()

app = Flask(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "coach.db")
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

HINT_SYSTEM_PROMPT = """You are a Socratic coding interview coach. The user is working on a LeetCode-style
problem. You are given the problem statement, the user's current code/thoughts, and a hint level (1-4).

Rules:
- NEVER give the full solution or working code, at any hint level.
- Hint level 1: Ask a guiding question that points at the right way to think about the problem
  (e.g. what pattern, what data structure, what to reconsider). No specifics about the approach.
- Hint level 2: Name the general technique or pattern (e.g. "two pointers", "this is a graph traversal"),
  but not how to apply it to this specific problem.
- Hint level 3: Explain how the technique applies to this specific problem, in plain English, still no code.
- Hint level 4: Give pseudocode-level structure (not runnable code) — the key steps, not implementation.
- Always be encouraging but concise. 2-4 sentences max, no matter the level.
- If their existing code has a bug, you may point at WHERE the bug likely is without fixing it for them.
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS problems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            difficulty TEXT,
            status TEXT DEFAULT 'in_progress',
            hint_count INTEGER DEFAULT 0,
            created_at TEXT,
            solved_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/hint", methods=["POST"])
def get_hint():
    data = request.get_json(force=True)
    problem = data.get("problem", "").strip()
    user_code = data.get("code", "").strip()
    hint_level = int(data.get("hint_level", 1))

    if not problem:
        return jsonify({"error": "Problem statement is required"}), 400

    hint_level = max(1, min(hint_level, 4))

    user_message = f"""Problem:
{problem}

My current code/thoughts:
{user_code if user_code else "(nothing yet, just starting)"}

Hint level requested: {hint_level}
"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=HINT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        hint_text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return jsonify({"hint": hint_text, "hint_level": hint_level})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/problems", methods=["GET"])
def list_problems():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM problems ORDER BY created_at DESC"
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/api/problems", methods=["POST"])
def add_problem():
    data = request.get_json(force=True)
    title = data.get("title", "").strip()
    difficulty = data.get("difficulty", "Medium")
    if not title:
        return jsonify({"error": "Title is required"}), 400

    db = get_db()
    cur = db.execute(
        "INSERT INTO problems (title, difficulty, created_at) VALUES (?, ?, ?)",
        (title, difficulty, datetime.utcnow().isoformat()),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/problems/<int:problem_id>/solve", methods=["POST"])
def mark_solved(problem_id):
    db = get_db()
    db.execute(
        "UPDATE problems SET status = 'solved', solved_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), problem_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/problems/<int:problem_id>/hint_used", methods=["POST"])
def increment_hint(problem_id):
    db = get_db()
    db.execute(
        "UPDATE problems SET hint_count = hint_count + 1 WHERE id = ?",
        (problem_id,),
    )
    db.commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    init_db()
