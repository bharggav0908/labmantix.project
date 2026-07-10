# AI Code Review Assistant

A lightweight starter app for reviewing code snippets or diffs with AI-powered suggestions.

## Features
- Paste code or a diff for review
- Receive structured findings with severity and explanation
- Uses OpenAI when an API key is configured
- Falls back to local heuristic review when no key is available

## Run locally

1. Create a Python environment
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy .env.example to .env and add your OpenAI API key if you want AI-backed reviews.
4. Start the app:
   ```bash
   uvicorn app.main:app --reload
   ```
5. Open http://127.0.0.1:8000
