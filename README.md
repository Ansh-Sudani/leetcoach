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
- [ ] Track hint count per problem and show a "hints used" stat on your profile
- [ ] Add a simple auth layer if you want multi-user support
- [ ] Write a short blog post / README case study on the prompt design decisions
- [ ] Add tests for the API endpoints

## Resume bullet (draft)

> Built and deployed LeetCoach, a full-stack interview-prep tool (Flask, SQLite,
> Anthropic API) that uses a graduated Socratic hint system to guide users toward
> solutions without revealing them, with persistent progress tracking.
