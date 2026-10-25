FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ML_ANALYSER_DEPLOYMENT_MODE=judge \
    ML_ANALYSER_MODEL_PROVIDER=mock \
    ML_ANALYSER_LAB_DAILY_LIMIT=0
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY backend ./backend
COPY frontend ./frontend
COPY workspaces/ml-training-demo ./workspaces/ml-training-demo
COPY workspaces/ml-regression-demo ./workspaces/ml-regression-demo
COPY workspaces/backend-benchmark-demo ./workspaces/backend-benchmark-demo
COPY workspaces/cli-benchmark-demo ./workspaces/cli-benchmark-demo
COPY scripts/serve.py ./scripts/serve.py
RUN python -m pip install --no-cache-dir -e . \
    && mkdir -p /app/artifacts /app/workspaces \
    && chown -R 10001:10001 /app/artifacts /app/workspaces
USER 10001
EXPOSE 8000
CMD ["python", "scripts/serve.py"]
