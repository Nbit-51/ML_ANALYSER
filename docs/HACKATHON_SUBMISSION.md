# Nebius × NVIDIA submission draft

Official event: https://nebiusglobalaihackathon.devpost.com/
Deadline: October 30, 2026, 10:00 a.m. PDT / 10:30 p.m. IST.
Recommended track: **Coding and Agentic Engineering**.

**Current license:** GNU AGPLv3 for original project code, with a narrow GSAP
linking permission and retained third-party notices. The owner approved this switch
on October 26. See [the license decision](LICENSING_DECISION.md) and [NOTICE](../NOTICE.md).

**Public links:**

- Application: https://ml-analyser.onrender.com/
- Counterexample Lab: https://ml-analyser.onrender.com/lab
- Prediction Comparison: https://ml-analyser.onrender.com/evaluate
- Repository: https://github.com/Nbit-51/ML_ANALYSER
- Owner-provided demo video: https://www.youtube.com/watch?v=pIJEN7S9128

The owner reports the video has been recorded and uploaded. Verify its public visibility
and length separately; recording and uploading are not evidence that Devpost is submitted.

## Pitch

**ML Analyser — an optimization must survive a counterexample.**

AI can propose a faster implementation while silently breaking a rare but important
case. ML Analyser makes proposals earn acceptance: define success, review the change,
measure baseline and candidate, enforce correctness, and retain inspectable evidence.

The new Counterexample Lab puts that workflow in a short public demo. NVIDIA Nemotron
3 Super 120B-A12B on Nebius Token Factory reads real Python source and proposes cache
configuration changes. A deterministic verifier runs fresh multi-tenant workloads,
returns exact failing queries for revision, and accepts only improvements with zero
incorrect prices. Judges can download and replay every observation without an LLM.

In the captured live run, the model's candidate reduced reference lookups from 120 to
30, while preserving all prices. The deliberately unsafe product-only control performs
even fewer lookups but fails on 100 queries. Work counts are synthetic measurements;
we claim neither a production latency improvement nor measured dollar savings.

Prediction Comparison adds framework-independent evaluation of supplied predictions.
Developers upload paired actual/baseline/candidate rows; deterministic calculations
produce classifier or regression metrics, cohort checks and an approximate paired
bootstrap interval. Its hidden-regression example improves overall accuracy from
78% to 90% while mobile accuracy falls from 90% to 60%, triggering rejection.
These are synthetic example predictions; the page does not train or run models.

The broader local workbench imports repositories, inventories capabilities, grounds
hypotheses in evidence, and executes declared ML/HTTP/process benchmarks after exact
approval. The public demo intentionally restricts execution to the built-in workload.

## Three-minute demo storyboard

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:20 | Lab problem and success contract | Faster alone can be wrong; target developers reviewing AI optimizations. |
| 0:20–0:45 | Select live Nemotron, prepare | Name NVIDIA Nemotron 3 Super and Nebius Token Factory aloud. Source is read; no benchmark has run. |
| 0:45–1:05 | Exact configuration, commitment, approve | One bounded campaign, three possible attempts; human approves scope. |
| 1:05–1:40 | Actual control and candidate results | Product-only cache fails; safe model choice passes. Distinguish control from model output. |
| 1:40–2:05 | Counterexamples, diff, paired counts | Explain what was measured; show rejected alternatives and any actual revisions honestly. |
| 2:05–2:30 | Download capsule and run replay script | Reproduce the verdict without trusting the LLM. |
| 2:30–3:00 | Repository workbench and boundaries | Broader architecture, specific users, public demo scope and what remains. |

Record actual execution, then edit idle waiting time. Do not present recorded evidence
as a new live call. Keep at least a minute of working application modules visible.

## Judging assessment

The official criteria are equally weighted: implementation, design, impact and idea.
The [organizer's guidance](https://nebiusglobalaihackathon.devpost.com/updates/46204-here-s-how-judging-works)
specifically favors agents that plan, run, test and iterate on repositories.

Our strongest differentiator is falsifiable optimization plus replayable evidence,
including rejections. The main remaining weakness is demonstrated breadth: the public
challenge is a small synthetic workload, not proof that arbitrary production repositories
can be optimized autonomously. A real user case and convincing video would strengthen
the impact claim. A finish or prize cannot be predicted from code quality alone.

## Items the owner must complete before submitting

- Check the public deployment links above and ensure the public workflows remain
  available through the judging period, December 1–15, 2026.
- Confirm the uploaded YouTube video is public and under three minutes.
- Confirm GitHub detects the AGPLv3 LICENSE and retains the setup instructions,
  original-code notice, GSAP linking permission and third-party license files.
- Complete feedback on Nebius and NVIDIA tools using actual experience. Observed:
  live source-grounded hypothesis and cache proposals worked; typed validation was useful;
  long reasoning responses make visible progress/wait states important. Do not invent
  service incidents or product claims.
- If applicable, describe which work was added during the event and disclose AI assistance
  accurately. Codex assisted implementation, testing and documentation; the hosted
  Nemotron model supplies runtime engineering proposals, not our deterministic verifier.
- Recheck the [official submission requirements](https://nebiusglobalaihackathon.devpost.com/)
  and [rules](https://nebiusglobalaihackathon.devpost.com/rules) before submission.

This is a local submission draft, not an entry posted or submitted on the user's behalf.
