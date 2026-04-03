# ynab-agent

A conversational budget companion for [YNAB](https://www.ynab.com/) (You Need A Budget), built as [Claude Code](https://docs.anthropic.com/en/docs/claude-code) skills backed by a Python CLI.

Instead of clicking through YNAB's UI to categorize transactions and rebalance your budget, you talk to an agent. It proposes, you approve. Every dollar gets a job.

## What It Does

**`/ynab`** — Full budget check-in. Runs three steps in sequence:

1. **Categorize** — Pulls uncategorized transactions, looks up your decision history for similar payees, proposes categories with confidence indicators, and applies after you approve.
2. **Rebalance** — Analyzes your budget against category targets/goals, proposes specific dollar moves between categories, groups by due date relative to your next payday.
3. **Status** — Shows spending by category vs. targets with pace indicators (on track, tight, overspent) and flags anything notable.

Each step is conversational — you see everything before it's applied. Split transactions are flagged but left for you to handle in YNAB. Corrections you make are weighted 3x in future proposals so the agent learns your preferences.

Sub-skills (`/ynab-categorize`, `/ynab-rebalance`, `/ynab-status`, `/ynab-setup`) are available when you only want one step.

## How It Works

```
┌──────────────────────────────────────────────┐
│  Claude Code Skills (/ynab, /ynab-status...) │
│  Reads philosophy.md + context.md            │
│  LLM reasons over data, formats proposals    │
├──────────────────────────────────────────────┤
│  Python CLI (uvx --from . ynab-agent)        │
│  fetch, apply, history, setup, category      │
├──────────────────────────────────────────────┤
│  Official YNAB SDK (pip install ynab)        │
├──────────────────────────────────────────────┤
│  ~/.config/ynab-agent/                       │
│  .env, config.json, context.md, history/     │
└──────────────────────────────────────────────┘
```

- **Skills** handle the conversation — presenting proposals, interpreting your approvals, framing tradeoffs.
- **Python CLI** handles the data — API calls, decision history lookups, fuzzy payee matching.
- **philosophy.md** gives the agent a zero-based budgeting personality (YNAB methodology + Dave Ramsey's intentional budgeting mindset). It doesn't lecture — it shapes how proposals are framed and tradeoffs are surfaced.
- **context.md** (in `~/.config/`) stores your personal preferences — pay schedule, category notes, rebalancing strategy. The agent offers to update it as you work together.

## Setup

### Prerequisites

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed
- [uv](https://docs.astral.sh/uv/) installed
- A YNAB account with a [Personal Access Token](https://app.ynab.com/settings/developer)

### Install

```bash
# Clone the repo
git clone https://github.com/evanoman/ynab-agent.git ~/dev/ynab-agent

# Create the data directory and add your YNAB token
mkdir -p ~/.config/ynab-agent
echo "YNAB_PAT=your-token-here" > ~/.config/ynab-agent/.env

# Install the skills
for skill in ynab ynab-categorize ynab-rebalance ynab-status ynab-setup; do
    ln -sf ~/dev/ynab-agent/skills/$skill ~/.claude/skills/$skill
done

# If you cloned to a different path, set this in your shell profile:
# export YNAB_AGENT_DIR="$HOME/path/to/ynab-agent"
```

### First Run

Start Claude Code and run `/ynab-setup`. It will:
1. Validate your API token
2. Select your budget
3. Seed the decision history from your last 3 months of transactions

Then run `/ynab` for your first budget check-in.

### CLI Usage (Without Claude Code)

The CLI works standalone via `uvx`:

```bash
uvx --from ~/dev/ynab-agent ynab-agent fetch uncategorized
uvx --from ~/dev/ynab-agent ynab-agent fetch budget-month
uvx --from ~/dev/ynab-agent ynab-agent fetch categories
uvx --from ~/dev/ynab-agent ynab-agent history lookup --payee-name "TRADER JOES"
uvx --from ~/dev/ynab-agent ynab-agent category <id> --goal-target 250000
```

## Development

```bash
cd ~/dev/ynab-agent
uv sync --dev          # Install dependencies
just fc                # Format + lint + type-check + test (run before every commit)
just test              # Tests only
```

## Project Structure

```
ynab-agent/
├── app/
│   ├── cli.py          # CLI entry point (fetch, apply, history, setup, category)
│   ├── client.py       # YNAB SDK wrapper (transactions, categories, payees, budget months)
│   ├── config.py       # Persistent config management
│   ├── formatting.py   # JSON output formatters for proposals and status
│   ├── history.py      # Decision history — JSONL storage, fuzzy payee matching
│   ├── models.py       # Pydantic models for all data types
│   └── paths.py        # Central path definitions (~/.config/ynab-agent/)
├── skills/
│   ├── ynab/           # Orchestrator — full budget check-in
│   ├── ynab-categorize/# Batch transaction categorization with approval
│   ├── ynab-rebalance/ # Budget rebalancing with tradeoff surfacing
│   ├── ynab-status/    # Read-only budget overview with pace indicators
│   └── ynab-setup/     # One-time configuration
├── tests/
├── philosophy.md       # Agent personality — zero-based budgeting principles
├── pyproject.toml      # Astral stack (uv, ruff, ty, pytest)
├── Justfile            # Dev commands
└── CLAUDE.md           # Project instructions for Claude Code
```

## Stack

- **Python 3.12+** with [uv](https://docs.astral.sh/uv/) for package management
- **[ynab](https://github.com/ynab/ynab-sdk-python)** — Official YNAB Python SDK (v4.0.0)
- **[thefuzz](https://github.com/seatgeek/thefuzz)** — Fuzzy string matching for payee normalization
- **[pydantic](https://docs.pydantic.dev/)** — Data models
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** — Skills framework for conversational workflows

## License

MIT
