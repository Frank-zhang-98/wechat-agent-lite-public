# Deployment

This repository is designed to run on a small server, but all deployment instructions in the public package are intentionally generic.

## Local Development Deployment

```bash
python -m venv .venv
source .venv/bin/activate   # or activate on Windows
pip install -r requirements.txt
python run.py
```

## Generic Linux Deployment

The repository includes helper scripts under `deploy/`.

Common pattern:

1. Copy the project to your target machine
2. Create a virtual environment
3. Install dependencies
4. Set environment variables and runtime configuration
5. Start `run.py` behind your preferred process manager

## Suggested Production Practices

- keep runtime data outside the git checkout
- back up the SQLite database before upgrading
- inject secrets at deploy time
- place the app behind your preferred reverse proxy or private access layer
- treat the console as an internal operations surface

## Included Deployment Assets

- `deploy/bootstrap_ubuntu.sh`
- `deploy/package_release.ps1`
- `deploy/deploy_uploaded_zip.sh`

Review them before use and adapt them to your own infrastructure.
