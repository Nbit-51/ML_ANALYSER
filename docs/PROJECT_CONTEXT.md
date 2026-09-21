# Project Context

## Purpose

ML Analyser is an autonomous evidence-driven optimization agent for the Nebius x NVIDIA Global AI Hackathon 2026. Its purpose is to diagnose failures in a technical project, design and safely execute controlled experiments, and retain changes only when they are supported by empirical evidence. ML is the flagship adapter and primary demonstration, not a permanent limit on the core engine.

Repository analysis is an input capability, not the product's central innovation. The defensible product is the closed loop of structured project state, falsifiable hypotheses, reproducible and reversible execution, constraint-aware evaluation, persistent experiment lineage, and adaptive experiment selection. The category distinction is intentional: coding agents optimize code; this system optimizes measurable outcomes.

This document is the durable handoff for product constraints and architectural decisions. Update it whenever a major decision changes.

## Product goals

The system should eventually be able to:

1. accept a technical repository, prior runs, a machine-readable success contract, and a project workspace;
2. build a state graph across data, code, configuration, models, checkpoints, metrics, and experiments;
3. diagnose likely failure modes without overstating certainty;
4. express each candidate explanation as a falsifiable hypothesis;
5. compile the smallest useful experiment that can test that hypothesis;
6. choose experiments by expected information gain/value, risk, and multidimensional budget;
7. execute approved experiments in a constrained environment;
8. preserve commands, outputs, metrics, errors, costs, and artifacts as evidence;
9. evaluate candidates against objectives and regression guardrails;
10. accept or reject hypotheses, keep or revert provisional changes, and adaptively select follow-up experiments;
11. preserve model lineage in an experiment DAG; and
12. produce a clear, reproducible engineering optimization report, specialized as an ML engineering report for the flagship adapter.

The core vocabulary is domain-neutral: goal, metric, constraint, hypothesis, experiment, observation, and decision. Domain adapters define project-specific inventory, interventions, measurements, and comparison rules.

## Scope strategy

Broad architecture must not become an unbounded “improve any codebase” promise. The hackathon implementation targets:

1. a fully functional ML adapter and strongest demo;
2. a smaller functional backend/software benchmark adapter proving the core loop generalizes; and
3. an AI-agent evaluation adapter only as a prototype or stretch goal.

Examples of later adapters could include data pipelines, inference services, web performance, and scientific notebooks, but they are not MVP commitments.

## Hackathon constraints

- Target track: Best Apps & Agents.
- Nebius infrastructure/Token Factory must be used.
- At least one NVIDIA open-source model must be used.
- The initial primary reasoning target is an NVIDIA Nemotron model through Nebius.
- The demonstration must show a genuine multi-step agent, not a thin chat or API wrapper.

## Current phase

**Phase 2: generalized approval and second evidence-loop adapter.**

Implemented through this phase:

- repository conventions and ignore rules;
- project and architecture documentation;
- a FastAPI application with health, read-only preview, and approved ML demo endpoints;
- strict domain models and provider/tool/evidence/persistence ports;
- explicit run lifecycle transition enforcement;
- bounded repository inventory and deterministic project state graph construction;
- a deterministic offline hypothesis provider and dry-run experiment compiler;
- deterministic objective, guardrail, and multidimensional-budget evaluation;
- an append-only SQLite evidence ledger and persistent experiment DAG;
- a narrow classification-threshold adapter and reproducible hidden-failure fixture;
- persisted fingerprint-bound approvals with explicit pending/approved/rejected/consumed states;
- single-use authorization that rejects plan tampering and replay;
- isolated baseline/candidate workspaces with deterministic retain/discard behavior;
- a bounded backend HTTP benchmark adapter and non-ML fixture;
- an environment-configured Nebius Token Factory provider with structured-output and grounding validation;
- automated API, security, provider-contract, persistence, evaluator, and end-to-end tests.

Explicitly not implemented yet:

- general-purpose command execution, container/VM sandboxing, or promotion of a retained candidate;
- repository ingestion from remote URLs/uploads;
- production experiment scheduling and recovery;
- broad ML training/evaluation adapters;
- live Nebius/Nemotron calls (the provider exists, but no credential/model deployment has been validated);
- authentication;
- frontend UI;
- domain adapters beyond the documented placeholders.

## Guiding principles

### Evidence before claims

Findings must point to source material or tool output. Experiment conclusions must be derived from captured results. The report must distinguish observed facts, agent inferences, and proposed but untested work.

### Explicit stages

Diagnosis, hypothesis generation, experiment design, authorization, execution, measurement, decision, and reporting are separate lifecycle stages. A generated plan is not proof of execution.

### Falsifiable work

Every experimental proposal should name the intervention, expected metric effect, success threshold, protected guardrails, and conditions under which the hypothesis is rejected. Recommendations without a feasible test remain explicitly untested.

### Adaptive, budget-aware selection

The experiment sequence is not predetermined. The result of one experiment changes the expected value of the next. Selection should consider expected information gain or improvement, probability of success, risk, wall time, money, compute, tokens, and experiment count within a user-defined budget. A cheap diagnostic that separates competing explanations can be more valuable than an expensive likely improvement.

### Persistent lineage, not chat memory

An experiment DAG records parentage and complete reproducibility metadata. Disproven hypotheses are not casually repeated in later sessions; they may be reconsidered only when relevant code, data, configuration, or constraints change.

### Changes are provisional

Every modification is isolated and measured before it is retained. A passing test suite is a guardrail, not proof that the objective improved. Rejected or invalid experiments must leave the accepted project state unchanged and retain enough evidence to explain the decision.

### Structured reasoning before expensive execution

For costly experiments, the reasoning workflow should include diagnostic, skeptic, planner, and judge perspectives. These are structured responsibilities and may initially be separate prompts to one Nemotron provider rather than independent agent services. Deterministic policy code—not model confidence—has final authority over schemas, budgets, safety, and acceptance constraints.

### Safe by default

Input repositories, their scripts, and model-generated tool arguments are untrusted. Analysis begins read-only. Commands require validation, resource limits, workspace isolation, and an auditable policy decision before execution.

### Provider independence

Core orchestration depends on typed provider interfaces rather than a vendor SDK. This enables deterministic mock tests while retaining Nebius/NVIDIA as the primary production path.

### Incremental delivery

Each milestone should provide a testable vertical slice. Infrastructure complexity is added when a concrete product requirement needs it.

## Initial technical decisions

| Area | Decision | Rationale |
| --- | --- | --- |
| Backend | Python and FastAPI | Strong ML ecosystem, typed request handling, and rapid API development. |
| Configuration | Environment variables through Pydantic Settings | Centralized validation without committing secrets. |
| API layout | Versioned router under `/api/v1` | Allows future API evolution without mixing transport and domain logic. |
| Agent design | Explicit state machine with typed ports | Makes multi-step behavior, retries, and failure states observable and testable. |
| Success definition | Machine-readable objective, target, constraints, and budget | Replaces subjective “make it better” requests with verifiable completion conditions. |
| Project understanding | Versioned project state graph | Connects code and data state to experiments instead of flattening the repository into prompts. |
| Hypotheses | Structured, falsifiable records | Forces recommendations to define measurable support and rejection criteria. |
| Experiments | Compiler plus persistent DAG | Makes runs reproducible, preserves lineage, and supports adaptive follow-up. |
| Decisions | Objective plus hard regression guardrails | Prevents a gain in one metric from hiding an unacceptable regression elsewhere. |
| Selection | Expected value/information under a multidimensional budget | Treats time, money, compute, tokens, and experiment slots as optimization constraints. |
| Domain support | Domain-neutral core with ML-first adapters | Demonstrates generality without claiming universal codebase support. |
| Change safety | Isolate, measure, then keep or revert | Prevents plausible model output from silently degrading the accepted project state. |
| Model access | Deterministic mock plus configured Token Factory adapter | Enables offline tests while keeping Nebius/Nemotron as the live reasoning path. |
| Evidence | Append-only records with artifact references | Prevents reports from silently losing provenance. |
| Execution | Narrow adapters in copied workspaces; no shell; explicit limits | Provides a testable safety boundary without overstating local copies as a production sandbox. |
| Frontend | Minimal, demo-oriented UI; framework deferred | Avoids choosing UI infrastructure before workflows stabilize. |

These are initial decisions, not immutable commitments. Changes should be recorded here and expanded into architecture decision records if the tradeoff is significant.

## Configuration and secrets

The repository contains `.env.example` with empty placeholders. Real values must be supplied through a local ignored `.env` file or the deployment environment.

Provider variables include:

- `ML_ANALYSER_MODEL_PROVIDER` (`mock` by default; `nebius` enables live inference)
- `NEBIUS_API_KEY`
- `NEBIUS_BASE_URL`
- `NEBIUS_MODEL`

No working credentials, fabricated credentials, or assumed model deployment IDs are included.

## Success criteria for the demonstration

A convincing end-to-end demo should show:

- ingestion of a representative ML repository;
- a visible multi-stage run with state transitions;
- a state graph linking multiple project artifacts and previous results;
- multiple falsifiable hypotheses for a deliberately hidden ML failure;
- a constrained, budgeted choice of the next experiment;
- at least one real controlled comparison or a transparently reported failed/skipped run;
- rejection of an initially plausible hypothesis when evidence contradicts it;
- acceptance of a later change only after objectives and guardrails pass;
- a visible experiment DAG and evidence-linked final recommendation;
- a final report with reproducible commands and artifact provenance;
- NVIDIA Nemotron reasoning served via Nebius Token Factory;
- a smaller non-ML benchmark flow demonstrating that success contracts and evidence decisions are reusable.

## Near-term milestones

1. Validate the implemented Token Factory adapter against a currently available NVIDIA Nemotron model when credentials arrive.
2. Expand the ML adapter from saved-prediction calibration to a representative training/evaluation repository.
3. Add retained-candidate diff review and a separately approved promotion workflow.
4. Add the frontend run timeline, success-contract, approval, DAG, comparison, and report views.
5. Add structured observability, cancellation/recovery, and production-grade sandbox integration.
6. Prototype AI-agent evaluation only after the flagship demo is stable.
7. Prepare repeatable deployment, security review, Devpost, and presentation assets.
