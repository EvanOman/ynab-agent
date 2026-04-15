---
name: ynab
description: Daily YNAB budget sync. Categorize + approve transactions, review budget status, rebalance if needed, check account balances. The single entry point for daily budget management.
allowed-tools: Bash(uvx --from * ynab-agent *), Bash(echo *), Bash(cat *), Bash(uv cache prune *), Read, AskUserQuestion
user-invocable: true
---

**Repo path:** All commands use `YNAB_AGENT_DIR` which defaults to `~/dev/ynab-agent`. If the repo is cloned elsewhere, set this variable in your shell profile.

# YNAB Daily Sync

The daily budget workflow. One skill, one loop, until everything is clean:
- 0 uncategorized transactions
- 0 unapproved transactions
- No negative category balances
- Ready to Assign as close to $0 as practical
- Account balances reviewed

## CLI Pattern

```bash
YNAB_AGENT_DIR="${YNAB_AGENT_DIR:-$HOME/dev/ynab-agent}"
uvx --from "$YNAB_AGENT_DIR" ynab-agent <command> [args]
```

Note: After code changes, bump the version in `pyproject.toml` so `uvx` picks up the new code. If the CLI runs stale code, run `uv cache prune --force` to clear the cache.

---

## Pre-flight: Load Context + Fetch ALL Data

**Run everything in parallel.** These calls are independent — fire them all at once using parallel tool calls in a single message:

```bash
# Context (3 parallel reads)
cat "$YNAB_AGENT_DIR/philosophy.md" 2>/dev/null
cat ~/.config/ynab-agent/context.md 2>/dev/null
cat ~/.config/ynab-agent/config.json 2>/dev/null

# Data (4 parallel fetches — run these in the SAME batch as the reads above)
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch uncategorized
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch unapproved
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch budget-month
uvx --from "$YNAB_AGENT_DIR" ynab-agent fetch accounts
```

That's **7 parallel calls in one message**. Wait for all to return, then process results in order below.

If config doesn't exist or has no `plan_id`, tell the user to run `/ynab-setup` first.

- **philosophy.md** is the agent's soul — zero-based budgeting principles, tone, framing. Read it and internalize it. Don't recite it — let it inform your voice.
- **context.md** has workflow preferences: pay schedule, category notes, rebalancing strategy. Apply relevant context throughout.
- If the user gives new hints or corrections during the session, offer to update context.md.

---

## Step 1: Transactions — Categorize & Approve

Use the uncategorized and unapproved results from pre-flight. **Do NOT re-fetch.**

### 1a. Uncategorized transactions

If count is 0 → say "No uncategorized transactions" and skip to 1c.

### 1b. Propose categories and apply

- Look up decision history for each payee (`ynab-agent history lookup-batch`)
- Fetch the full category list (`ynab-agent fetch categories`) for proposals
- Present a table: date, payee, amount, proposed category, confidence
- Flag transfers (payee starts with "Transfer :") separately — these usually auto-resolve in YNAB and don't need categories
- Wait for user approval or corrections
- Apply categorizations — this **automatically approves** the transactions too:

```bash
echo '{"updates": [{"id": "...", "category_id": "..."}]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent apply categorize
```

- Record decisions to history:

```bash
echo '{"decisions": [...]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent history record
```

### 1c. Unapproved transactions (ALWAYS check this)

**This step is not optional.** Use the unapproved results from pre-flight. Auto-imported transactions often arrive already categorized but unapproved.

If count is 0, report "No unapproved transactions" and move on.

If any exist, show them in a table (date, payee, amount, category) and ask the user to approve or skip:

```bash
echo '{"transaction_ids": ["...", "..."]}' | uvx --from "$YNAB_AGENT_DIR" ynab-agent apply approve
```

**Goal:** 0 uncategorized, 0 unapproved when this step is done.

---

## Step 2: Budget Status

Use the budget-month results from pre-flight. **Do NOT re-fetch.**

The output includes:
- `to_be_budgeted` — the **real** Ready to Assign (unassigned dollars). This is NOT income.
- `income` — total inflows this month (informational only, don't show unless asked)
- `age_of_money` — days
- All category details

**IMPORTANT:** Never confuse income with Ready to Assign. See philosophy.md "Key Distinctions" section.

**Present the status overview:**
- Filter out hidden categories, internal categories, "Uncategorized", "Inflow: Ready to Assign"
- Calculate pace for each budgeted category:
  - % budget used vs % month elapsed
  - If % used > % elapsed + 20pp → "tight"
  - If balance < 0 → "overspent"
  - If activity = 0 and budgeted > 0 and >30% of month elapsed → "inactive"
  - Otherwise → "on track"
- Group by category group if there are many categories
- Show Ready to Assign and Age of Money
- Flag any negative balances or tight categories

---

## Step 3: Rebalance (if needed)

Use the budget-month results from pre-flight. **Do NOT re-fetch.**

Trigger rebalancing if any of these are true:
- Ready to Assign > $0 (dollars without jobs)
- Any category has a negative balance
- Any funded category is significantly underfunded vs its target

Follow the `/ynab-rebalance` workflow (skip its pre-flight and fetch steps — data is already loaded):
1. Analyze for over/under-funded categories
2. Propose specific dollar moves with tradeoff reasoning
3. Wait for approval
4. Apply moves and record decisions

If everything looks balanced, say so and skip.

---

## Step 4: Account Balances

Use the accounts results from pre-flight. **Do NOT re-fetch.**

Show a simple table: account name, type, balance, cleared, uncleared.

This is informational — flag anything that looks unusual (very low balance, large uncleared amounts) but don't take action unless the user asks.

---

## Wrap-up

Summarize what happened in this session:
- Transactions: N categorized + approved, M already clean
- Budget: Ready to Assign status, any moves made
- Accounts: quick health check

If there are things needing manual attention (split transactions, transfer matching, credit card issues), mention them.

**Goal state:** everything categorized, approved, balanced, and accounted for. Every dollar has a job.
