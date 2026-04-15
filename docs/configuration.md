# Configuration

`wechat-agent-lite` uses a combination of environment variables and runtime settings.

## Environment Variables

The repository ships `.env.example` for local bootstrapping.

Important variables:

- `WAL_TIMEZONE`
- `WAL_DATA_DIR`
- `WAL_DB_PATH`
- `WAL_ENCRYPTION_KEY`

These define where the runtime stores local state and how sensitive values are encrypted at rest.

## Runtime Settings

Most operational settings live in the application settings layer and are stored in the database:

- scheduler timing
- quality thresholds
- per-role LLM configuration
- WeChat settings
- SMTP settings
- optional search provider settings
- source maintenance limits
- concurrency controls

## Secret Handling

This public repository does **not** contain live credentials.

Recommended rule:

- keep secrets in environment variables or local runtime settings
- never commit filled `.env` files
- never commit database snapshots that already contain encrypted secrets

## Config Templates

Repository-backed templates:

- `config/sources.yaml`
- `config/writing_templates.yaml`
- `config/article_layouts.yaml`

Treat these as defaults. Override behavior through runtime settings instead of editing public examples with personal values.
