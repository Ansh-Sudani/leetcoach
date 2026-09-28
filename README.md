# LeetCoach

A Socratic hint engine for LeetCode-style interview prep. Pick a problem, write your
attempt, run it against real test cases, and unlock hints one step at a time — never
the full solution. Tracks which problems you've solved and how many hints each took.

## The four hints

| Level | What you get |
|-------|--------------|
| 1. Nudge | One question that changes how you're looking at the problem |
| 2. Name the approach | The technique or data structure, without how to apply it |
| 3. Apply it here | How that approach fits this specific problem, in plain English |
| 4. Outline the steps | A numbered plain-English outline. Still no code |

- **Hints unlock in order, enforced by the server.** The API rejects level 3 until level 2 is used.
- **Each hint sees the earlier ones**, so level 3 builds on level 2 instead of repeating it.
- **Hints are saved per problem**, so you can leave and come back.
- **Code never comes back.** The prompt forbids it, and the server strips any fenced code block as a second check.
- **Problem and code are treated as data**, wrapped in tags so instructions inside them are ignored.

Built with Flask + the Anthropic API + SQLite.

## Why this project

Most "I called an LLM API" projects are a thin wrapper with no real logic. This one
has an actual constraint system (the hint-level prompt design forces graduated,
non-spoiler responses) plus a real backend, persistence, and a UI — a complete,
usable tool rather than a demo.

## Run locally

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env and add your ANTHROPIC_API_KEY

python app.py
```

Visit `http://localhost:5000`.

Optional environment variables: `ANTHROPIC_MODEL` (defaults to `claude-haiku-4-5-20251001`), `DB_PATH`, `PORT`.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

The Anthropic call is mocked; the submit tests run the real sandbox.

## Deploy (Railway — easiest free option)

1. Push this folder to a GitHub repo.
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo.
3. Add an environment variable: `ANTHROPIC_API_KEY` = your key.
4. Railway auto-detects Python. Set the start command to:
   ```
   gunicorn app:app
   ```
5. Deploy. You'll get a live `.up.railway.app` URL — that's your resume link.

## Next steps to make this even stronger

- [ ] Add difficulty-aware hinting (adjust tone/depth based on Easy/Medium/Hard)
- [ ] Show the `/api/stats` numbers (solved, avg hints per solve) in the UI
- [ ] Add a simple auth layer if you want multi-user support
- [ ] Write a short blog post / README case study on the prompt design decisions

## Resume bullet (draft)

> Built and deployed LeetCoach, a full-stack interview-prep tool (Flask, SQLite,
> Anthropic API) that uses a graduated Socratic hint system to guide users toward
> solutions without revealing them, with persistent progress tracking.
