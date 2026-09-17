import os
import sys
import json
import time
import subprocess
import sqlite3
from collections import defaultdict, deque
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template, g
from anthropic import Anthropic
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

DB_PATH = os.path.join(os.path.dirname(__file__), "coach.db")
BASE_DIR = os.path.dirname(__file__)
SANDBOX_RUNNER = os.path.join(BASE_DIR, "sandbox_runner.py")
client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

with open(os.path.join(BASE_DIR, "static", "problem_details.json")) as f:
    PROBLEM_DETAILS = json.load(f)

RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 8
_rate_limit_hits = defaultdict(deque)


def _rate_limited(key):
    now = time.time()
    hits = _rate_limit_hits[key]
    while hits and now - hits[0] > RATE_LIMIT_WINDOW_SECONDS:
        hits.popleft()
    if len(hits) >= RATE_LIMIT_MAX_REQUESTS:
        return True
    hits.append(now)
    return False

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


def _limit_resources():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))


def _values_match(actual, expected, comparator):
    try:
        if comparator == "sorted":
            return sorted(actual) == sorted(expected)
        if comparator == "set":
            return set(actual) == set(expected)
    except Exception:
        pass
    return actual == expected


SUBMIT_SYSTEM_PROMPT = """You are a concise, encouraging coding interview coach helping a candidate whose
LeetCode-style submission just failed some test cases. You are given the problem, their code, and the
test results.

Write a SHORT (3-6 sentences) breakdown: name the likely root cause (off-by-one, wrong base case,
unhandled edge case, etc.) by reasoning about the specific failing test case(s), but do NOT rewrite
their solution or give working code. Keep it tight — no walls of text, no restating the whole problem
back to them.
"""


def _get_submit_explanation(problem, code, results, all_passed):
    lines = []
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        lines.append(
            f"{status} args={r['args']} expected={r['expected']} actual={r['actual']} error={r['error']}"
        )
    summary = "\n".join(lines)

    user_message = f"""Problem:
{problem['description']}

Candidate's code:
{code}

Test results ({'ALL PASSED' if all_passed else 'SOME FAILED'}):
{summary}
"""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=350,
            system=SUBMIT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")
    except Exception as e:
        return "Couldn't generate an explanation: " + str(e)


@app.route("/api/submit", methods=["POST"])
def submit_code():
    if _rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many submissions — wait a bit before trying again."}), 429

    data = request.get_json(force=True)
    problem_id = str(data.get("problem_id", ""))
    language = data.get("language", "python")
    code = data.get("code", "")

    if language != "python":
        return jsonify({"error": "Real execution currently only supports Python — try Get Hint instead, or switch the language to Python."}), 400

    problem = PROBLEM_DETAILS.get(problem_id)
    if not problem:
        return jsonify({"error": "This problem doesn't have executable test cases yet — try Get Hint instead."}), 400

    if not code.strip():
        return jsonify({"error": "Write some code first."}), 400
    if len(code) > 20000:
        return jsonify({"error": "Solution is too long."}), 400

    payload = json.dumps({
        "code": code,
        "function_name": problem["functionName"],
        "tests": [{"args": t["args"]} for t in problem["tests"]],
    })

    run_kwargs = dict(input=payload, capture_output=True, text=True, timeout=6, env={})
    if os.name == "posix":
        run_kwargs["preexec_fn"] = _limit_resources

    try:
        proc = subprocess.run([sys.executable, "-I", "-S", SANDBOX_RUNNER], **run_kwargs)
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Time limit exceeded — your code took too long to run."})

    stdout = (proc.stdout or "")[-20000:]
    try:
        sandbox_result = json.loads(stdout)
    except ValueError:
        return jsonify({"error": "The sandbox couldn't run your code.", "detail": (proc.stderr or "")[:2000]})

    if sandbox_result.get("compile_error"):
        return jsonify({"error": sandbox_result["compile_error"]})

    comparator = problem.get("comparator", "exact")
    results = []
    all_passed = True
    for test, r in zip(problem["tests"], sandbox_result["results"]):
        passed = r["error"] is None and _values_match(r["actual"], test["expected"], comparator)
        all_passed = all_passed and passed
        results.append({
            "args": test["args"],
            "expected": test["expected"],
            "actual": r["actual"],
            "error": r["error"],
            "passed": passed,
        })

    explanation = None if all_passed else _get_submit_explanation(problem, code, results, all_passed)

    return jsonify({"results": results, "all_passed": all_passed, "explanation": explanation})


FOLLOWUP_SYSTEM_PROMPT = """You are a concise coding interview coach continuing a conversation about a
LeetCode-style submission you just reviewed. Answer the user's follow-up question directly, referencing
their code and test results where relevant. Keep answers short (2-5 sentences) unless the question genuinely
needs more. Don't dump a full rewritten solution unless they explicitly ask you to show working code."""


@app.route("/api/followup", methods=["POST"])
def followup():
    if _rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many requests — wait a bit before trying again."}), 429

    data = request.get_json(force=True)
    context = (data.get("context") or "").strip()
    history = data.get("history") or []
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Ask something first."}), 400

    messages = []
    if context:
        messages.append({"role": "user", "content": f"Context for this conversation:\n{context[:6000]}"})
        messages.append({"role": "assistant", "content": "Got it, I have the context."})
    for turn in history[-10:]:
        role = turn.get("role")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": str(turn.get("content", ""))[:4000]})
    messages.append({"role": "user", "content": question[:2000]})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            system=FOLLOWUP_SYSTEM_PROMPT,
            messages=messages,
        )
        reply = "".join(block.text for block in response.content if block.type == "text")
        return jsonify({"reply": reply})
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
