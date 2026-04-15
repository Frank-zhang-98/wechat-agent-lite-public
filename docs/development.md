# Development

This repository is intended to stay workflow-oriented and easy to inspect.

## Local Workflow

1. Create a virtual environment
2. Install dependencies
3. Run focused tests for touched modules
4. Start the app locally and verify the console

## Tests

The project uses Python `unittest` suites under `tests/`.

Example:

```bash
python -m unittest tests.test_title_generation_service tests.test_api_runs
```

## Recommended Change Discipline

- keep service functions focused
- validate external input at boundaries
- prefer explicit state over hidden coupling
- avoid committing runtime data or generated artifacts

## Public Packaging Rules

If you plan to publish your own fork:

- scan for paths, IPs, tokens, and secrets before pushing
- keep `.env`, `.db`, logs, caches, and private docs out of Git
- use placeholder values in examples
- avoid checking in server-specific acceptance notes
