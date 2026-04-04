# YNAB Agent

Agentic budget companion for YNAB. Claude Code skills backed by a Python CLI.

## Quick Commands

```bash
just fc                                              # Format, lint, type-check, test
just test                                            # Run tests only
uvx --from . ynab-agent --help                       # CLI help (no install needed)
```

## Usage

The CLI runs via `uvx` — no installation step, dependencies auto-resolve:

```bash
export YNAB_AGENT_DIR="$HOME/dev/ynab-agent"  # or wherever you cloned it
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch uncategorized
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch unapproved
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch categories
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch accounts
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch budget-month
```

Skills are symlinked from `skills/` to `~/.claude/skills/`:

```bash
for skill in ynab ynab-categorize ynab-rebalance ynab-status ynab-setup; do
    ln -sf "$YNAB_AGENT_DIR/skills/$skill" ~/.claude/skills/$skill
done
```

## Data Location

All persistent data lives in `~/.config/ynab-agent/`:
- `.env` — YNAB Personal Access Token
- `config.json` — plan ID, server_knowledge for delta requests
- `context.md` — personal budget preferences and category notes
- `history/decisions.jsonl` — categorization decision history
- `history/rebalances.jsonl` — rebalancing decision history

## Architecture

- **Skills:** `/ynab` is the primary daily workflow skill. Other skills (`/ynab-categorize`, `/ynab-rebalance`, `/ynab-status`) are focused sub-workflows.
- **CLI:** Python CLI (`app/cli.py`) with subcommands for fetch, apply, history, setup, category
- **Client:** Thin wrapper around official YNAB SDK (`app/client.py`)
- **Models:** Pydantic models for API data (`app/models.py`)
- **Paths:** Central path definitions (`app/paths.py`) — all data under `~/.config/ynab-agent/`
- **History:** JSONL-based decision history with fuzzy payee matching (`app/history.py`)
- **Formatting:** JSON output for machine consumption by skills (`app/formatting.py`)
- **Skills:** Claude Code skills in `skills/`, symlinked to `~/.claude/skills/`
- **Philosophy:** `philosophy.md` — the agent's personality and zero-based budgeting principles

## Key Conventions

- All CLI output is JSON to stdout (skills handle formatting for humans)
- Amounts are in YNAB milliunits ($10.00 = 10000) internally, converted to dollars in output
- Delta requests via `server_knowledge` stored in config
- Decision history is append-only JSONL
- Bump version in `pyproject.toml` after code changes to bust the `uvx` cache
- Set `YNAB_AGENT_DIR` env var if repo is not at `~/dev/ynab-agent`
