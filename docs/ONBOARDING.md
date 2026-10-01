# Repository intake and GitHub sign-in

Open `/` for the landing page, `/app` for the workbench and `/login` for sign-in. The old service metadata is now at `/status`; `/api/v1/health` remains available.

## Bring a repository

In **My repository**, paste a public `https://github.com/owner/repository` URL, or choose a folder anywhere on your computer. GitHub import downloads the default-branch source archive without running Git, hooks, installers or project code. Folder import uploads selected files to the app server; it does not give the server access to arbitrary local paths. A local clone can come from any Git host.

Imports are source snapshots under a generated folder in the managed workspace. The original is unchanged. Limits are 1,000 source files, 2 MB per file and 20 MB total; GitHub archives are also bounded before and after decompression. Credential-like filenames, `.env`, dependency/cache folders and common generated artifacts are excluded. This filename filter cannot identify every secret embedded in source code: review the source before importing or using live reasoning. Symlinks, special archive entries, traversal, Windows reserved names and duplicate paths are rejected.

Private GitHub URLs and remote hosts other than github.com are not fetched. Choose a local clone for those projects. This is not a Git synchronization or pull/push integration. File uploads and GitHub imports both create managed copies.

**Import and preview do not imply execution support.** To run an experiment, provide a supported manifest, compatible dependencies/runtime and explicit approval. General process execution still requires Linux with working bubblewrap namespaces. ML/HTTP scripts are trusted local execution only. The UI reports when configuration is needed.

## What does higher or lower mean?

| Goal | Better direction | Example |
| --- | --- | --- |
| F1 / accuracy | Increase | F1 0.70 to 0.80 improves by 0.10 |
| P95 latency | Decrease | 50 ms to 40 ms improves by 10 ms |
| Validation RMSE | Decrease | Smaller prediction error |
| Throughput | Increase | 100 to 150 requests per second |

Presets select an exact metric and direction and explain the scale. Custom metrics require an explicit choice; the evaluator does not guess. These settings specify how results are judged, not how an LLM generates text. Optional targets and minimum improvements use the metric's units. A correctness limit is a guardrail another metric must respect. Preview proposes tests; only approved execution produces measured results.

## Configure GitHub sign-in

1. Create a GitHub OAuth App in [Developer settings](https://github.com/settings/developers).
2. For local use, set the homepage to `http://127.0.0.1:8000` and callback URL to `http://127.0.0.1:8000/api/v1/auth/callback`.
3. Add these values to your existing ignored `.env` without replacing your Nebius settings:

```dotenv
ML_ANALYSER_APP_URL=http://127.0.0.1:8000
ML_ANALYSER_GITHUB_CLIENT_ID=your-client-id
ML_ANALYSER_GITHUB_CLIENT_SECRET=your-client-secret
ML_ANALYSER_GITHUB_ALLOWED_USERS=your-github-login
```

4. Restart the API, open `/login`, and select **Continue with GitHub**. Use the same hostname and port as `ML_ANALYSER_APP_URL` throughout the flow. List multiple approved logins separated by commas if needed. Keep this allowlist limited to people you trust to run local code.

The flow follows [GitHub's OAuth authorization-code protocol](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps), uses one-time browser-bound state and PKCE, and requests public identity without private-repository scopes. The temporary GitHub access token is discarded after reading identity. Sessions use opaque random cookies (HttpOnly, SameSite=Lax, Secure on HTTPS), with only token hashes stored server-side. Sessions expire after eight hours and sign-out revokes them.

Configuring either client credential enables the authentication boundary immediately; incomplete configuration fails closed. With both credentials blank, the existing local demo mode remains available. Do not expose demo mode publicly. GitHub sign-in is implemented and protocol-tested; a real OAuth round trip needs your registered client credentials.

## Account storage and boundaries

Authenticated users receive separate workspace, execution and run-database paths under `artifacts/accounts/<github-id>/`. Included demos are copied on first sign-in. Reports and approvals resolve within the requesting user's database; one user cannot address another user's imports or run IDs through the API. Existing anonymous runs remain in the original local workspace and are not migrated automatically. Active experiments may finish after sign-out; sign-out revokes access rather than cancelling workers.

Cross-origin write requests and unexpected Host headers are denied. Upload bodies are bounded before JSON parsing. This remains a trusted, local-first prototype: authentication does not make legacy ML/HTTP execution safe for hostile code. Shared production deployment still needs hardened workers, quotas/rate limits, HTTPS, operational recovery and security review.
