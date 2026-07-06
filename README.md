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

## Deploy to Azure (Container Apps)

Runs as an **Azure Container App** provisioned by `budget-infra` (shared Container
Apps environment + ACR + the `budgetai-planner` app, bound to the shared managed
identity). Deploy `budget-infra` first, then set the GitHub **secrets**
`AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` and **variables**
`AZURE_RESOURCE_GROUP`, `ACR_NAME`, and `CONTAINER_APP_NAME` (`budgetai-planner`).
Push to `main` (or run **Deploy (Planner)**) to build via `az acr build` and roll the
container app.

## Status

Scaffold with a simple proportional planner. Containerized and deployable to Azure
Container Apps.
