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
from runners import run_compiled

load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Postgres when DATABASE_URL is set (Vercel + Neon), SQLite otherwise (local dev).
DATABASE_URL = os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL")
USE_PG = bool(DATABASE_URL)
if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/coach.db"  # only writable dir on Vercel; used only if no DATABASE_URL
else:
    DB_PATH = os.path.join(BASE_DIR, "coach.db")
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

HINT_SYSTEM_PROMPT = """You are LeetCoach, a sharp coding interview coach. The user is stuck on a
LeetCode-style problem. You get the problem, their current code, and a hint level (1-4).

Hard rules:
- Max 2 sentences, under 45 words total. No intro, no praise, no "Great question", no recap of the problem.
- Never give the full solution or runnable code.
- Be specific to THEIR code. If they wrote something, react to what's actually there.
- If their code has a bug, say exactly where (line or expression) and what's off, without writing the fix.

Levels:
1. One pointed question that makes the key insight click (e.g. "What would you need to remember about
   numbers you've already seen?").
2. Name the pattern or data structure, plus one line on why it fits.
3. How that pattern maps onto this problem: what you store, what you check, when.
4. Pseudocode skeleton: 3-5 short numbered steps, plain English, no real syntax.

Use `backticks` for variable names. Level 4 may use a short numbered list; every other level is plain text.
"""


def _connect():
    if USE_PG:
        import psycopg2
        import psycopg2.extras
        return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        g.db = _connect()
    return g.db


def db_query(sql, params=(), fetch=None):
    """Run a query on either backend. Write SQL with ? placeholders."""
    db = get_db()
    if USE_PG:
        sql = sql.replace("?", "%s")
    cur = db.cursor()
    cur.execute(sql, params)
    result = None
    if fetch == "all":
        result = [dict(r) for r in cur.fetchall()]
    elif fetch == "one":
        row = cur.fetchone()
        result = dict(row) if row else None
    db.commit()
    cur.close()
    return result


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    id_col = "SERIAL PRIMARY KEY" if USE_PG else "INTEGER PRIMARY KEY AUTOINCREMENT"
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        f"""
        CREATE TABLE IF NOT EXISTS problems (
            id {id_col},
            client_id TEXT,
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
    cur.close()
    conn.close()


def client_id():
    """Anonymous per-browser id so each visitor gets their own progress."""
    return (request.headers.get("X-Client-Id") or "anon")[:64]


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
            max_tokens=200,
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
    limits = [
        (resource.RLIMIT_CPU, 5),
        (resource.RLIMIT_AS, 256 * 1024 * 1024),
        (resource.RLIMIT_NOFILE, 64),
        (resource.RLIMIT_FSIZE, 1024 * 1024),
    ]
    for kind, value in limits:
        try:
            resource.setrlimit(kind, (value, value))
        except (ValueError, OSError):
            pass  # some hosts won't let us set every limit; the timeout still applies


def _same(a, b):
    """Deep equality, with a small tolerance for floats (e.g. 2.0 vs 2.00000001)."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-5 * max(1.0, abs(b))
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _values_match(actual, expected, comparator):
    try:
        if comparator == "sorted":
            return sorted(actual) == sorted(expected)
        if comparator == "set":
            return set(actual) == set(expected)
        if comparator == "set_of_sorted_lists":
            norm = lambda v: sorted(tuple(sorted(x)) for x in v)
            return norm(actual) == norm(expected)
        if comparator == "set_of_tuples":
            return {tuple(x) for x in actual} == {tuple(x) for x in expected}
    except Exception:
        pass
    return _same(actual, expected)


SUBMIT_SYSTEM_PROMPT = """You are a concise, encouraging coding interview coach helping a candidate whose
LeetCode-style submission just failed some test cases. You are given the problem, their code, and the
test results.

In 2-3 short sentences: name the root cause (off-by-one, wrong base case, unhandled edge case, etc.),
point to the exact line or expression responsible, and reference the failing input. Don't rewrite their
solution or give working code. No intro, no praise, no restating the problem.
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


def _run_python(code, problem):
    payload = json.dumps({
        "code": code,
        "function_name": problem["functionName"],
        "tests": [{"args": t["args"]} for t in problem["tests"]],
        "arg_types": problem.get("argTypes"),
        "return_type": problem.get("returnType"),
        "result_mode": problem.get("resultMode", "return"),
    })
    run_kwargs = dict(input=payload, capture_output=True, text=True, timeout=6, env={})
    if os.name == "posix":
        run_kwargs["preexec_fn"] = _limit_resources
    try:
        proc = subprocess.run([sys.executable, "-I", "-S", SANDBOX_RUNNER], **run_kwargs)
    except subprocess.TimeoutExpired:
        return {"error": "Time limit exceeded — your code took too long to run."}
    stdout = (proc.stdout or "")[-200000:]
    try:
        return json.loads(stdout)
    except ValueError:
        return {"error": "The sandbox couldn't run your code. " + (proc.stderr or "")[-300:]}


@app.route("/api/submit", methods=["POST"])
def submit_code():
    if _rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many submissions — wait a bit before trying again."}), 429

    data = request.get_json(force=True)
    problem_id = str(data.get("problem_id", ""))
    language = data.get("language", "python")
    code = data.get("code", "")

    if language not in ("python", "javascript", "java", "cpp"):
        return jsonify({"error": "That language isn't supported yet."}), 400

    problem = PROBLEM_DETAILS.get(problem_id)
    if not problem:
        return jsonify({"error": "This problem doesn't have test cases yet — try Get Hint instead."}), 400

    if not code.strip():
        return jsonify({"error": "Write some code first."}), 400
    if len(code) > 20000:
        return jsonify({"error": "Solution is too long."}), 400

    if language == "python":
        sandbox_result = _run_python(code, problem)
    elif language == "javascript":
        # JavaScript runs in the user's browser (a sandboxed Web Worker); we only judge the results here.
        client_results = data.get("client_results")
        if isinstance(client_results, dict) and client_results.get("compile_error"):
            sandbox_result = {"compile_error": str(client_results["compile_error"])[:2000]}
        elif not isinstance(client_results, list) or len(client_results) != len(problem["tests"]):
            return jsonify({"error": "Couldn't run your JavaScript. Refresh and try again."}), 400
        else:
            sandbox_result = {"results": [
                {"actual": r.get("actual") if isinstance(r, dict) else None,
                 "error": (str(r.get("error"))[:500] if isinstance(r, dict) and r.get("error") else None)}
                for r in client_results
            ]}
    else:
        sandbox_result = run_compiled(language, code, problem)

    if sandbox_result.get("error"):
        return jsonify({"error": sandbox_result["error"]})
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


CHAT_SYSTEM_PROMPT = """You are LeetCoach, a friendly, sharp coding interview coach built into a
LeetCode-style practice site. The user can ask you anything: about the current problem, their code,
a concept (Big-O, recursion, hash maps), or interview prep in general.

How to answer:
- Short and direct. Default to 1-3 sentences. Go longer only if they ask for an explanation.
- Teach, don't spoil: for the current problem, guide them toward the answer instead of handing over a
  full solution, unless they explicitly ask to see one after trying.
- Be specific to their code when it's relevant. Point at exact lines or expressions.
- Use `backticks` for code and **bold** sparingly. Small code snippets (a few lines) are fine for
  concepts, not full solutions.
"""


@app.route("/api/chat", methods=["POST"])
def chat():
    if _rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "Too many requests, give it a few seconds."}), 429

    data = request.get_json(force=True)
    problem = (data.get("problem") or "").strip()
    code = (data.get("code") or "").strip()
    history = data.get("history") or []
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Ask something first."}), 400

    context = f"Current problem:\n{problem or '(none selected yet)'}\n\nTheir current code:\n{code or '(empty)'}"
    messages = []
    for turn in history[-10:]:
        role = turn.get("role")
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": str(turn.get("content", ""))[:4000]})
    if messages and messages[0]["role"] != "user":
        messages = messages[1:]
    messages.append({"role": "user", "content": f"{context[:8000]}\n\nMy question: {question[:2000]}"})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            system=CHAT_SYSTEM_PROMPT,
            messages=messages,
        )
        reply = "".join(block.text for block in response.content if block.type == "text")
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/problems", methods=["GET"])
def list_problems():
    rows = db_query(
        "SELECT * FROM problems WHERE client_id = ? ORDER BY created_at DESC",
        (client_id(),),
        fetch="all",
    )
    return jsonify(rows)


@app.route("/api/problems", methods=["POST"])
def add_problem():
    data = request.get_json(force=True)
    title = data.get("title", "").strip()
    difficulty = data.get("difficulty", "Medium")
    if not title:
        return jsonify({"error": "Title is required"}), 400

    row = db_query(
        "INSERT INTO problems (client_id, title, difficulty, created_at) VALUES (?, ?, ?, ?) RETURNING id",
        (client_id(), title, difficulty, datetime.utcnow().isoformat()),
        fetch="one",
    )
    return jsonify({"id": row["id"]}), 201


@app.route("/api/problems/<int:problem_id>/solve", methods=["POST"])
def mark_solved(problem_id):
    db_query(
        "UPDATE problems SET status = 'solved', solved_at = ? WHERE id = ? AND client_id = ?",
        (datetime.utcnow().isoformat(), problem_id, client_id()),
    )
    return jsonify({"ok": True})


@app.route("/api/problems/<int:problem_id>/unsolve", methods=["POST"])
def mark_unsolved(problem_id):
    db_query(
        "UPDATE problems SET status = 'in_progress', solved_at = NULL WHERE id = ? AND client_id = ?",
        (problem_id, client_id()),
    )
    return jsonify({"ok": True})


@app.route("/api/problems/<int:problem_id>/hint_used", methods=["POST"])
def increment_hint(problem_id):
    db_query(
        "UPDATE problems SET hint_count = hint_count + 1 WHERE id = ? AND client_id = ?",
        (problem_id, client_id()),
    )
    return jsonify({"ok": True})


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
else:
    init_db()
