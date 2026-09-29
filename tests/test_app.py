import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as coach  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(coach, "DB_PATH", str(tmp_path / "test.db"))
    coach.init_db()
    coach._rate_limit_hits.clear()

    calls = []

    def fake_generate_hint(statement, difficulty, code, previous_hints, level):
        calls.append({"statement": statement, "level": level, "previous": list(previous_hints), "code": code})
        return f"hint for level {level}"

    monkeypatch.setattr(coach, "generate_hint", fake_generate_hint)
    monkeypatch.setattr(coach, "RATE_LIMIT_MAX_REQUESTS", 1000)
    coach.app.config["TESTING"] = True
    test_client = coach.app.test_client()
    test_client.calls = calls
    return test_client


def make_problem(client, **overrides):
    payload = {"title": "Two Sum", "difficulty": "Easy"}
    payload.update(overrides)
    return client.post("/api/problems", json=payload)


def ask_hint(client, pid, level, **extra):
    body = {"level": level, "statement": "Find two numbers.", **extra}
    return client.post(f"/api/problems/{pid}/hint", json=body)


def test_create_and_fetch_problem(client):
    res = make_problem(client)
    assert res.status_code == 201
    pid = res.get_json()["id"]

    fetched = client.get(f"/api/problems/{pid}").get_json()
    assert fetched["title"] == "Two Sum"
    assert fetched["hints"] == []
    assert fetched["status"] == "in_progress"


@pytest.mark.parametrize(
    "overrides",
    [{"title": "  "}, {"difficulty": "Impossible"}, {"title": "x" * 500}],
)
def test_create_rejects_bad_input(client, overrides):
    assert make_problem(client, **overrides).status_code == 400


def test_hints_unlock_in_order_and_stop_at_four(client):
    pid = make_problem(client).get_json()["id"]

    skip = ask_hint(client, pid, 3)
    assert skip.status_code == 409

    for level in range(1, 5):
        res = ask_hint(client, pid, level, code="x = 1")
        assert res.status_code == 200
        assert res.get_json()["hint"] == f"hint for level {level}"

    assert ask_hint(client, pid, 5).status_code == 409


def test_hints_can_be_reset_after_using_all_four(client):
    pid = make_problem(client).get_json()["id"]
    for level in range(1, 5):
        ask_hint(client, pid, level, code="x = 1")
    assert ask_hint(client, pid, 5).status_code == 409

    res = client.post(f"/api/problems/{pid}/hints/reset")
    assert res.status_code == 200
    assert res.get_json()["hints_used"] == 0
    assert client.get(f"/api/problems/{pid}").get_json()["hints"] == []

    again = ask_hint(client, pid, 1, code="x = 1")
    assert again.status_code == 200
    assert again.get_json()["hint"] == "hint for level 1"


def test_hints_are_saved_with_the_problem(client):
    pid = make_problem(client).get_json()["id"]
    ask_hint(client, pid, 1, code="def f(): pass")

    fetched = client.get(f"/api/problems/{pid}").get_json()
    assert fetched["hints"] == ["hint for level 1"]
    assert fetched["statement"] == "Find two numbers."
    assert fetched["code"] == "def f(): pass"


def test_earlier_hints_are_passed_to_later_ones(client):
    pid = make_problem(client).get_json()["id"]
    ask_hint(client, pid, 1)
    ask_hint(client, pid, 2)
    assert client.calls[1]["previous"] == ["hint for level 1"]


def test_hint_requires_a_statement(client):
    pid = make_problem(client).get_json()["id"]
    res = client.post(f"/api/problems/{pid}/hint", json={"level": 1})
    assert res.status_code == 400


def test_hint_failure_is_reported_and_not_saved(client, monkeypatch):
    def broken(*args, **kwargs):
        raise coach.HintError("rate limited", status=429)

    monkeypatch.setattr(coach, "generate_hint", broken)
    pid = make_problem(client).get_json()["id"]
    assert ask_hint(client, pid, 1).status_code == 429
    assert client.get(f"/api/problems/{pid}").get_json()["hints"] == []


def test_stats_count_hints_per_solve(client):
    a = make_problem(client, title="A").get_json()["id"]
    b = make_problem(client, title="B").get_json()["id"]
    ask_hint(client, b, 1)
    ask_hint(client, b, 2)
    client.post(f"/api/problems/{a}/solve")
    client.post(f"/api/problems/{b}/solve")

    stats = client.get("/api/stats").get_json()
    assert stats["total"] == 2
    assert stats["solved"] == 2
    assert stats["solved_without_hints"] == 1
    assert stats["avg_hints_per_solve"] == 1.0


def test_code_blocks_are_stripped_from_hints():
    leaked = "Try this:\n```python\nreturn a + b\n```\nThen test it."
    cleaned = coach.strip_code_blocks(leaked)
    assert "return a + b" not in cleaned
    assert "hints never include code" in cleaned


def test_missing_api_key_gives_clear_error(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(coach.HintError) as exc:
        coach.generate_hint("stmt", "Easy", "", [], 1)
    assert exc.value.status == 503


def test_submit_runs_code_against_tests(client):
    code = (
        "def twoSum(nums, target):\n"
        "    seen = {}\n"
        "    for i, n in enumerate(nums):\n"
        "        if target - n in seen:\n"
        "            return [seen[target - n], i]\n"
        "        seen[n] = i\n"
    )
    res = client.post("/api/submit", json={"problem_id": "1", "language": "python", "code": code})
    data = res.get_json()
    assert data["all_passed"] is True
    assert data["diagnosis"] is None


def test_submit_blocks_disallowed_imports(client):
    code = "import os\ndef twoSum(nums, target):\n    return []\n"
    res = client.post("/api/submit", json={"problem_id": "1", "language": "python", "code": code})
    assert "not allowed" in res.get_json()["error"]


class _FakeToolUseBlock:
    type = "tool_use"
    name = "report_diagnosis"

    def __init__(self, input_):
        self.input = input_


class _FakeDiagnosisResponse:
    def __init__(self, input_):
        self.content = [_FakeToolUseBlock(input_)]


def test_submit_failure_returns_structured_diagnosis(client, monkeypatch):
    fake_input = {
        "root_cause": "Your loop returns before checking every pair.",
        "notes": [
            {"type": "bug", "text": "You return on the first iteration regardless of match."},
            {"type": "edge_case", "text": "The third test needs indices 3 and 4, which you never reach."},
            {"type": "approach", "text": "A hash map from value to index would let you check in one pass."},
        ],
    }
    monkeypatch.setattr(
        coach.client.messages, "create", lambda **kwargs: _FakeDiagnosisResponse(fake_input)
    )
    code = "def twoSum(nums, target):\n    return [0, 1]\n"
    res = client.post("/api/submit", json={"problem_id": "1", "language": "python", "code": code})
    data = res.get_json()
    assert data["all_passed"] is False
    assert data["diagnosis"]["root_cause"] == fake_input["root_cause"]
    assert [n["type"] for n in data["diagnosis"]["notes"]] == ["bug", "edge_case", "approach"]
