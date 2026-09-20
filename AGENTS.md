# AGENTS.md

## Project

This repository is for the Nebius x NVIDIA Global AI Hackathon 2026.

The project is an autonomous evidence-driven optimization agent, with ML as the flagship domain and hackathon demonstration.

The product is not a repository-summary wrapper or a general-purpose coding agent. Coding agents optimize code; this system optimizes measurable outcomes. Repository analysis is the intake step for an evidence-driven, closed experimentation loop. The differentiator is the execution infrastructure, structured experimental memory, reversible changes, and empirical decision process; the LLM is one component of that system.

The system should accept a technical project/repository, a machine-readable success contract, and a budget, then:

1. Inspect the repository, prior runs, and project structure.
2. Build a project state graph connecting datasets, code, configurations, models, checkpoints, metrics, and experiments.
3. Analyze ML code, training logic, results, and likely failure modes.
4. Express proposed improvements as falsifiable hypotheses.
5. Compile hypotheses into minimal, reproducible controlled experiments.
6. Select experiments based on expected information gain/value, risk, and a multidimensional budget.
7. Execute approved experiments in an isolated environment.
8. Compare results against objectives and regression guardrails.
9. Accept or reject hypotheses and choose the next experiment from the evidence.
10. Preserve provenance in an evidence ledger and persistent experiment DAG.
11. Revise recommendations based on observed evidence.
12. Produce a final engineering optimization report (an ML engineering report for the flagship adapter) without fabricating results.

The core vocabulary—goal, metric, constraint, hypothesis, experiment, observation, and decision—must remain domain-neutral. Domain adapters define how a specific project is inspected and measured.

Hackathon scope:

- ML adapter: fully functional flagship implementation.
- General software benchmark adapter: smaller functional proof of generality.
- AI-agent evaluation adapter: prototype/stretch goal only.

## Hackathon constraints

- Primary track: Best Apps & Agents.
- Must use Nebius infrastructure/Token Factory.
- Must use at least one NVIDIA open-source model.
- Primary reasoning model should initially target NVIDIA Nemotron through Nebius.
- The submission should demonstrate a real multi-step agent rather than a simple chatbot/API wrapper.

## Tech stack

Backend:

- Python
- FastAPI

Frontend:

- Keep the UI clean and recruiter/demo friendly.
- Avoid unnecessary visual complexity.

Agent:

- Tool-based architecture.
- Explicit diagnose, hypothesize, design, execute, measure, and decide stages.
- Repository state should be modeled structurally, not treated as a single text blob.
- Each proposed change must state an expected measurable outcome and guardrails.
- Experiments must be reproducible and linked by lineage in an experiment DAG.
- Every change is provisional until measured; rejected changes must be safely reverted.
- Experiment selection should respect explicit success contracts and budgets for money, compute, tokens, experiment count, and wall-clock time.
- Prefer experiments with high expected information gain per unit cost when diagnosis is uncertain.
- Expensive actions should support structured diagnostic, skeptic, planner, and judge reasoning roles before execution; these roles need not be separate deployed agents.
- Preserve tool outputs and evidence.
- Do not fabricate experiment results.

## Development principles

- Build incrementally.
- Keep modules separated.
- Prefer simple working implementations before adding complexity.
- Run tests after meaningful changes.
- Never commit API keys or credentials.
- Use environment variables for Nebius/Tavily/etc.
- Maintain README.md as development progresses.
- Update `docs/PROJECT_CONTEXT.md` when major architectural decisions change.

## Current development phase

We are at project initialization.

First milestones:

1. Create repository structure.
2. Write README.
3. Document architecture.
4. Implement FastAPI skeleton.
5. Implement agent interfaces.
6. Implement local/mock model provider.
7. Add Nebius Token Factory provider once API access is available.
8. Build frontend.
9. Create end-to-end demonstration.
10. Prepare Devpost submission.
