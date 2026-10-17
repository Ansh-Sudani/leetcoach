# LeetCoach

A Socratic hint engine for LeetCode-style interview prep. Paste a problem and your
current attempt, pick a hint level (1-4), and get a nudge in the right direction —
never the full solution. Tracks which problems you've solved.

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

## Deploy (Vercel + Neon, free)

1. On [vercel.com](https://vercel.com): **Add New → Project**, import this repo. Framework preset: **Other**. Deploy.
2. In the project: **Storage → Create Database → Neon** (free), connect it to the project.
   This sets `DATABASE_URL` automatically.
3. **Settings → Environment Variables**: add `ANTHROPIC_API_KEY`.
4. **Deployments → Redeploy** so the new variables load.

Locally, with no `DATABASE_URL` set, the app falls back to SQLite (`coach.db`).
