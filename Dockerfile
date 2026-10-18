FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
    && curl -fsSL https://ollama.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV OLLAMA_MODEL=gemma3:4b \
    OLLAMA_MODELS=/var/lib/ollama/models \
    PORT=10000 \
    REPAIRDESK_DEMO_AI=true \
    PYTHONUNBUFFERED=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ai_service.py customer_updates.py database.py demo_app.py demo_data.py \
    estimates.py prepare_demo.py schemas.py ./
RUN python prepare_demo.py

EXPOSE 10000

CMD ["sh", "start_demo.sh"]
