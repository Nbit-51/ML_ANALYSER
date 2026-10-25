# Compare predictions from any project

Open `/evaluate`. Export predictions from your own classification or regression model,
then compare a baseline and candidate on the **same labeled examples**. This path does
not need a repository manifest, GitHub sign-in, GPU, model weights or API key.

Examples include text/image classifiers, a migration between model versions, a smaller
replacement model and numeric demand/price forecasts. A GitHub URL alone cannot supply
ground-truth labels; export your evaluation outputs first.

## CSV format

```csv
id,actual,baseline,candidate,cohort
sample-1,positive,negative,positive,mobile
sample-2,negative,negative,negative,desktop
```

`actual`, `baseline` and `candidate` are required. Optional `id` values must be unique.
Optional `cohort` values group rows by device, region, language or another evaluation
segment. Use a single segment column per comparison. Standard CSV quoting and UTF-8 BOM
are supported. Classification values are label strings; regression values must be finite
numbers with absolute value at most 1e12. Use 2–5,000 rows, at most 2 MB UTF-8, 20 classes
and 20 cohorts. Values are limited to 160 characters. Supply held-out predictions; the app
cannot independently verify whether data was used for training or tuning.

## Measurements and decision

- **Classification:** accuracy, macro precision/recall/F1, weighted F1 and both confusion
  matrices. Macro averages weight each label equally; undefined class scores are zero.
  Higher accuracy/F1 is better. Primary metric: macro F1 or accuracy.
- **Regression:** MAE, RMSE and R². MAE/RMSE use the target's units and lower is better.
  R² is undefined (`null`) for constant actual targets. Primary metric: RMSE or MAE.
- **Regression Radar:** every sufficiently supported cohort must respect the allowed
  accuracy drop (classification) or MAE increase (regression). Each supported actual class
  also has a recall-drop guardrail. This can reject a model whose overall score improved.
- **Uncertainty:** 200 paired row bootstrap samples estimate an approximate 95% interval
  for improvement, using fixed whole-dataset label definitions. Positive always means
  improvement, including for error metrics. Sampling uses a canonical digest of paired
  outcomes, so renaming sample IDs or reordering rows cannot change the interval. Replay
  is deterministic. This is an approximate diagnostic assuming independent rows;
  correlated users/time-series rows need a more appropriate grouped or temporal analysis.

The candidate is rejected if the observed overall goal or a supported slice guardrail
fails. Otherwise fewer than 20 paired rows, under-supported cohorts/classes, or a bootstrap
lower bound below the required improvement make it **inconclusive**. It is accepted only
when all these checks pass. This is a decision under the displayed contract, not proof of
fairness, statistical significance, causality or future performance.
Numeric boundary comparisons use a relative tolerance of 1e-12 with no absolute epsilon,
so a small positive improvement requirement is not treated as zero.

Select **Find a hidden regression** for synthetic evidence: overall accuracy increases
**78% → 90%**, but the mobile cohort drops **90% → 60%**, so the candidate is rejected.
The other illustrative examples show a consistent classifier improvement and forecast
errors falling **RMSE 8 → 2**. These are calculated example outputs, not trained-model claims.

## Data handling and replay

CSV is sent to this app server for bounded arithmetic. The endpoint does not store rows,
persist reports, call an AI provider, install dependencies or execute repository code.
Only one comparison runs at a time per process; concurrent requests receive 429. The
existing same-origin and body-size boundaries also apply. Download your report before
leaving. The JSON includes label/cohort names, aggregate metrics and digests, not raw rows
or sample identifiers. Review labels/cohort names before sharing.

Keep the original CSV separately. From an installed checkout of the matching version:

```sh
python scripts/replay_predictions.py report.json predictions.csv
```

Check the deployed prediction page, all three examples and independent report replay:

```sh
python scripts/check_deployment.py https://ml-analyser.onrender.com --predictions
```

Replay recomputes all metrics, cohort checks, bootstrap estimates, decisions and digests.
Data hashing normalizes an initial UTF-8 BOM and line endings. Implementation hashing
normalizes source line endings. Changed data, rules, metrics or implementation fail the
comparison. The digest establishes consistency; it is not an authenticity signature.

Metric definitions follow the [scikit-learn evaluation guide](https://scikit-learn.org/stable/modules/model_evaluation.html)
and [F1 averaging definitions](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html).
The implementation uses Python's standard library; scikit-learn is not a runtime dependency.
