# Getting Started

This guide covers the smallest setup needed to run `wechat-agent-lite` locally.

## Prerequisites

- Python 3.10 or newer
- A clean virtual environment
- Optional: Playwright browser dependencies if you use browser-backed extraction

## Install

```bash
git clone https://github.com/<your-account>/wechat-agent-lite-public.git
cd wechat-agent-lite-public
python -m venv .venv
```

Windows:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment

Start from `.env.example`.

Required variables:

- `WAL_TIMEZONE`
- `WAL_DATA_DIR`
- `WAL_DB_PATH`
- `WAL_ENCRYPTION_KEY`

If you plan to enable LLM-backed runs, configure the corresponding provider credentials through the runtime settings layer or your local environment.

## Run

```bash
python run.py
```

Default local console:

- `http://127.0.0.1:8080`

## First Checks

- Open the console and confirm the app boots cleanly
- Verify the database path resolves to a local writable directory
- Confirm no real secrets are committed to your local clone before you customize anything
