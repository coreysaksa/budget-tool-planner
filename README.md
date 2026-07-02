# budget-tool-planner

Agent tool that **generates a budget** from your goals and analyzed spending for
[BudgetAI](https://github.com/cosaksa_microsoft/BudgetAgent).

## What it does

Given:
- a **spending analysis** (from `budget-tool-analyzer`), and
- your **goals** (e.g. "save $12k emergency fund by Dec", "extra $300/mo to mortgage"),

it produces a **BudgetPlan** with:
- per-category allocations,
- a **petty-cash allocation** for the discretionary checking account,
- goal contributions, feasibility-checked against income/outflow.

## Run (local dev)

```
pip install -e ".[dev]"
uvicorn planner.service:app --port 8003
```

## Status

Scaffold with a simple proportional planner.
