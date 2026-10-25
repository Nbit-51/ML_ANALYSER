"""Portable free-host entrypoint. Secrets come from host settings, never the image."""

import os

import uvicorn

if __name__ == "__main__":
    os.environ.setdefault("ML_ANALYSER_DEPLOYMENT_MODE", "judge")
    # Render supplies its canonical URL; other hosts set APP_URL explicitly.
    if os.environ.get("RENDER_EXTERNAL_URL"):
        os.environ.setdefault("ML_ANALYSER_APP_URL", os.environ["RENDER_EXTERNAL_URL"])
    uvicorn.run(
        "ml_analyser.main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
