# wechat-agent-lite

**Language:** **English** | [简体中文](README.zh-CN.md)

![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-app-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-runtime-003B57?logo=sqlite&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-enabled-2EAD33?logo=playwright&logoColor=white)
![Status](https://img.shields.io/badge/status-active-2ea44f)

![wechat-agent-lite hero](assets/repo-hero.svg)

> Workflow-first article automation for WeChat Official Accounts.

`wechat-agent-lite` is a production-oriented content automation app for running a full daily article pipeline on a small server. It fetches topics, ranks candidates, enriches source material, writes an article, plans visuals, renders publish-ready HTML, creates a WeChat draft, and keeps the entire workflow observable through a web console.

## Overview

This repository is for teams or solo operators who want more than a prompt pack or a shell script bundle. It packages article generation as a repeatable application with:

- scheduled health checks and main runs
- source maintenance and repair
- article generation with structured intermediate state
- title, visual, and render stages
- draft publishing and daily reporting
- token, latency, and storage visibility

The goal is simple: **make daily AI-assisted publishing inspectable, recoverable, and deployable**.

## What Ships

| Area | Included in This Repository |
| --- | --- |
| Runtime App | FastAPI application, scheduler, persistence, metrics, and web console |
| Generation Pipeline | Topic intake, ranking, fact preparation, writing, title generation, and visual planning |
| Publishing Surface | WeChat draft creation and operational reporting |
| Deployment Assets | Bootstrap scripts, systemd template, packaging helpers |
| Tests | Focused unit and integration tests for the core runtime and services |
| Documentation | Public getting-started, configuration, architecture, deployment, and development docs |

## Core Capabilities

| Module | What It Does |
| --- | --- |
| Topic Intake | Collects candidates from RSS, GitHub, and curated HTML list pages |
| Source Maintenance | Tracks source health, probes fallback paths, and records repair actions |
| Ranking Pipeline | Applies rule scoring plus model-assisted reranking to choose one topic per main run |
| Fact Pipeline | Builds fact packs, compresses evidence, and prepares writing inputs |
| Writing Pipeline | Generates article drafts, titles, and quality checks |
| Visual Pipeline | Plans inline visuals, cover prompts, and render-safe image assets |
| Publishing | Creates WeChat drafts and preserves partial-success state when needed |
| Console & Metrics | Exposes runs, steps, token usage, storage, and maintenance progress |

## Who This Is For

- operators running a daily or near-daily WeChat publishing workflow
- developers who want a reference architecture for content automation
- teams that need observable runs, recoverable failures, and draft-first publishing

## Design Principles

- **workflow first**: model calls are embedded in a controlled runtime, not scattered across ad hoc scripts
- **small-server friendly**: designed to run on modest infrastructure with explicit storage and token visibility
- **observable by default**: each run, step, and major cost surface can be inspected from the console
- **draft before publish**: the system is optimized for safe draft generation, review, and staged rollout
- **public-safe packaging**: this open repository excludes private environment state and deployment secrets

## Architecture

The runtime is organized around a graph-based article workflow plus an operations console.

```text
Fetch Sources
  -> Rank & Select Topic
  -> Enrich Source Material
  -> Build Fact Pack
  -> Write Article
  -> Generate Title
  -> Plan Visuals
  -> Render HTML
  -> Publish Draft
  -> Record Metrics & Reports
```

Key application surfaces:

- `app/graphs/` - article generation graph and execution nodes
- `app/runtime/` - runtime state, persistence, projections, graph runner
- `app/agents/` - task-specific agents for classify, plan, write, title, evaluate, and publish
- `app/services/` - fetching, fact handling, title generation, visuals, pricing, settings, and WeChat publishing
- `app/templates/` - web console UI
- `config/` - default layouts, sources, and writing templates

More detail: [docs/architecture.md](docs/architecture.md)

## Quick Start

### 1. Clone and set up a virtual environment

```bash
git clone https://github.com/<your-account>/wechat-agent-lite-public.git
cd wechat-agent-lite-public
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Prepare environment variables

Copy `.env.example` or export the required values in your shell. The repository does **not** include real credentials.

Minimum local configuration:

- `WAL_TIMEZONE`
- `WAL_DATA_DIR`
- `WAL_DB_PATH`
- `WAL_ENCRYPTION_KEY`

Application credentials such as LLM keys, WeChat app credentials, SMTP settings, and optional search provider settings are configured at runtime through the settings layer.

More detail: [docs/configuration.md](docs/configuration.md)

### 3. Run the app

```bash
python run.py
```

Default local console:

- `http://127.0.0.1:8080`

## Repository Layout

```text
wechat-agent-lite-public/
├── app/
├── assets/
├── config/
├── deploy/
├── docs/
├── tests/
├── .env.example
├── .gitignore
├── README.md
├── README.zh-CN.md
├── requirements.txt
└── run.py
```

## Documentation

- [Getting Started](docs/getting-started.md)
- [Configuration](docs/configuration.md)
- [Architecture](docs/architecture.md)
- [Deployment](docs/deployment.md)
- [Development](docs/development.md)

## Privacy & Safety Notes

This public package intentionally excludes:

- personal or server-specific IP addresses
- private deployment paths and release directories
- API keys, tokens, secrets, app credentials, and SMTP passwords
- runtime databases, logs, cached outputs, and temporary artifacts
- internal acceptance reports and operational snapshots

If you package your own fork, keep the same rule: **commit code and templates, not live environment state**.

## Project Status

- active runtime with web console, scheduler, metrics, and publishing flow
- public package prepared for clean GitHub distribution
- suitable as a base for private deployment or open experimentation

## Roadmap

- improve evidence-backed writing and reduce unsupported expansion
- tighten title quality without coupling to article H1
- keep inline visual planning source-aware and render-safe
- preserve low-resource deployability while improving article quality
