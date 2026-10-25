# Connect and verify the deployed app

Local `.env` settings affect only the local process. For the public app, save settings in
**Render → ML_ANALYSER → Environment**, then save/redeploy and wait for a successful deploy.
Keep actual credentials out of Git, chat and screenshots.

## GitHub identity

Register an [OAuth app](https://github.com/settings/applications/new) with:

| Field | Value |
| --- | --- |
| Homepage | `https://ml-analyser.onrender.com` |
| Redirect URI / callback | `https://ml-analyser.onrender.com/api/v1/auth/callback` |
| Wildcard matching | Disabled |
| Device Flow | Disabled |

Save these Render variables, substituting the OAuth app's values privately:

```dotenv
ML_ANALYSER_APP_URL=https://ml-analyser.onrender.com
ML_ANALYSER_GITHUB_CLIENT_ID=<OAuth client ID>
ML_ANALYSER_GITHUB_CLIENT_SECRET=<OAuth client secret>
ML_ANALYSER_GITHUB_ALLOWED_USERS=Nbit-51
```

The allowlist contains GitHub **logins**, not email addresses or URLs. Only trusted
listed accounts can access the repository workbench. Public lab visitors need no account.
Sign-in requests public identity; it does not grant private-repository access.

## Nebius reasoning

Save the following alongside the GitHub settings in Render:

```dotenv
ML_ANALYSER_MODEL_PROVIDER=nebius
NEBIUS_API_KEY=<your Token Factory key>
NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b
NEBIUS_BASE_URL=https://api.tokenfactory.us-central1.nebius.com/v1
ML_ANALYSER_LAB_DAILY_LIMIT=6
ML_ANALYSER_LAB_COOLDOWN_SECONDS=60
```

The base URL must match the region where your key/model was verified. The configuration
above is the one tested for this project. A positive daily quota enables public live lab
campaigns; each campaign can use up to three model calls. Provider credit limits still
apply. No paid hosting plan or hosted GPU is needed.

## Verify configuration and actual behavior

Open [`/api/v1/connections`](https://ml-analyser.onrender.com/api/v1/connections).
It lists missing variable names and whether live campaigns are enabled, never secret
values. `configured` means settings are present; `verification: not_tested` deliberately
does not claim valid credentials or a completed sign-in.

From an installed local checkout:

```sh
python scripts/check_deployment.py https://ml-analyser.onrender.com --exercise-lab
```

This checks health, the callback origin, anonymous workspace restrictions, real offline
measurement, approval tampering/reuse denial and independent report replay. After saving
Nebius settings, explicitly opt in to a live test using existing inference credits:

```sh
python scripts/check_deployment.py https://ml-analyser.onrender.com --live-lab --require-connections
```

Then complete the browser round trip: open `/login`, continue with your allowlisted GitHub
account, return to `/app`, and confirm your identity. Import the public
`https://github.com/Nbit-51/ML_ANALYSER` repository, select evaluation project
`workspaces/ml-training-demo`, choose F1, preview, review/approve and run. Reopen the saved
report, then sign out and confirm the workbench requires sign-in again. Automated OAuth
protocol tests use a mocked provider; only this real browser flow verifies your OAuth app.

For an owner-operated end-to-end test from the checkout, review the fixture source first:

```sh
python scripts/validate_repository_flow.py --approve-trusted-code --live
```

This downloads the real public GitHub archive, runs its declared classification evaluation
with live Nebius planning, checks guardrails and unchanged source, and reopens the saved
report. Its small fixture is an integration test. Arbitrary repositories need a supported
manifest, task data and compatible dependencies. Legacy ML/HTTP execution is for trusted
code; GitHub sign-in does not provide a hostile-code sandbox.

## If the public app still shows setup instructions

- Confirm the variables were saved in the **web service's Environment**, not only local `.env`.
- Confirm the latest Render deployment finished; a running process retains its startup settings.
- Compare exact variable names against `/api/v1/connections` and remove accidental whitespace.
- For callback errors, compare the OAuth app's registered URI with the deployed URI above.
- A 403 after OAuth means the signed-in login is absent from the allowlist.
- Export important reports: free Render storage and sessions can disappear on restart.
