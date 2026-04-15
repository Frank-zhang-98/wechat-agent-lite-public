# Architecture

`wechat-agent-lite` is a workflow-first publishing system with explicit runtime state.

## High-Level Flow

```text
Collectors
  -> Ranking
  -> Selection
  -> Source Enrichment
  -> Fact Pack / Fact Compression
  -> Writing
  -> Title
  -> Visual Planning
  -> Render
  -> Publish
  -> Metrics / Reports
```

## Main Subsystems

### `app/graphs`

The graph layer defines article generation stages and node order.

Typical nodes include:

- classify
- plan sections
- validate plan
- write article
- generate title
- evaluate article
- plan visuals
- render article
- publish

### `app/runtime`

The runtime layer coordinates:

- persistent run state
- graph execution
- run projections
- audit metadata
- API-facing summaries

### `app/agents`

Task-specific agents encapsulate higher-level decision prompts for:

- classification
- section planning
- writing
- title generation
- evaluation
- publishing
- visuals

### `app/services`

Services provide the execution layer:

- fetch and extraction
- settings and secret handling
- model gateway and pricing
- source maintenance
- visual planning and rendering support
- WeChat publishing
- metrics

## Persistence

The runtime uses SQLite and structured tables such as:

- `runs`
- `run_steps`
- `llm_calls`
- `config_entries`
- `source_health_states`

This keeps each run inspectable after the fact.
