# Deploy the judge demo without buying a plan

The application needs CPU web hosting; NVIDIA inference runs on Nebius Token Factory.
Neither local Docker Desktop nor a hosted GPU is required for the Render route.
No free host promises unlimited traffic, perpetual availability, or unlimited inference.

## Render: use the existing free account

1. Create a **Web Service** from `Nbit-51/ML_ANALYSER`, branch `main`, or use the committed
   `render.yaml` Blueprint. Select the **Free** instance. Do not add a paid disk or database.
2. For manual setup: runtime **Python**, build `pip install -e .`, start
   `python scripts/serve.py`, health path `/api/v1/health`. Use Python 3.12.
3. Set these nonsecret environment variables:

   ```text
   ML_ANALYSER_DEPLOYMENT_MODE=judge
   ML_ANALYSER_MODEL_PROVIDER=mock
   ML_ANALYSER_LAB_DAILY_LIMIT=0
   ```

   Render's canonical service URL is read from `RENDER_EXTERNAL_URL`. For other hosts,
   set `ML_ANALYSER_APP_URL=https://your-actual-service-hostname` explicitly.
4. Deploy, open `/lab`, prepare an offline campaign, approve it, download the capsule,
   and replay it locally. The recorded live example needs no new inference credits.
5. To enable live inference using existing Nebius credits, put **only in the host's
   environment/secret settings**:

   ```text
   ML_ANALYSER_MODEL_PROVIDER=nebius
   NEBIUS_API_KEY=<your key, never commit>
   NEBIUS_MODEL=nvidia/nemotron-3-super-120b-a12b
   NEBIUS_BASE_URL=<your verified Token Factory regional base URL>
   ML_ANALYSER_LAB_DAILY_LIMIT=6
   ML_ANALYSER_LAB_COOLDOWN_SECONDS=60
   ```

   Restart/redeploy, select live reasoning in the UI and verify one campaign. Every
   campaign permits at most three calls with bounded output tokens. These are application
   limits, not billing guarantees. Keep provider spending/credit limits under your control.
6. Share the HTTPS `/lab` URL. Keep the recorded evidence and source available to judges.

[Render's current free plan](https://render.com/docs/free) sleeps after 15 idle minutes,
wakes on a visitor request (approximately a minute), grants 750 instance hours per
workspace/month and has bandwidth/build limits. Files and SQLite state can disappear
on restart or sleep. Export important evidence; do not promise durable online history.
Review dashboard limits without enabling chargeable upgrades or adding payment details
just to remove the sleep behavior.

## Other hosts

The nonroot `Dockerfile` contains explicit source copies and no `.env`. Its default
profile is the public judge lab, with live inference disabled. Set `PORT` (default 8000)
and the canonical HTTPS app URL on any compatible host. Builds can run on the host;
local Docker Desktop is optional. `Procfile` provides the same Python entrypoint for
compatible native build systems.

- [Koyeb free instance](https://www.koyeb.com/docs/reference/instances): 512 MB RAM,
  0.1 vCPU, one free service, sleep after one idle hour, no volume. However,
  [its billing FAQ](https://www.koyeb.com/docs/faqs/pricing) specifies a **$29 card hold**
  and plan-dependent charges. This is unsuitable when even a temporary hold is unaffordable.
  If an existing account already qualifies, choose only the `free` instance and Dockerfile
  build method; the platform builds the image remotely.
- [Cloudflare Workers](https://developers.cloudflare.com/workers/platform/limits/): the
  free tier has 100,000 requests/day and 10 ms CPU/request. It is a possible future
  target for a port of the controlled demo. This repository's SQLite/filesystem/process
  implementation has not been ported or validated there.
- [Oracle Always Free](https://www.oracle.com/cloud/free/faq/): card verification,
  capacity and idle-resource policies apply. Do not depend on obtaining a new VM hours
  before submission.
- [Hugging Face Spaces](https://huggingface.co/docs/hub/en/spaces-overview): current
  documentation says creating Docker/Gradio compute Spaces requires a paid plan; the
  CPU Basic hourly label alone does not establish free account eligibility.

## Access and secrets

The public lab requires no judge account. The full repository workbench requires an
explicit, ready GitHub OAuth setup in judge mode; otherwise `/app` redirects to `/login`
and repository/run APIs return 403. Keep imported code execution on a controlled
installation. This image is not a production hostile-code worker.

Actual `.env`, credentials, artifacts, test databases and local workspaces must never be
uploaded. The Docker context uses an allowlist and explicit `COPY` instructions. Hosting
credentials are separate from the Nebius inference key; a Token Factory key cannot
authorize deployment to Render, Koyeb or Nebius Cloud.

Follow [connection setup and verification](CONNECTIONS.md) to connect GitHub and Nebius.
`/api/v1/connections` exposes configuration readiness without returning credential values.
The container also ships the four account starter fixtures; CI executes the packaged
classifier as the image's nonroot user rather than checking only the public lab.
