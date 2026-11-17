FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-nep poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
RUN mkdir -p /app/uploads && useradd --create-home --uid 10001 app && chown -R app /app
USER app

EXPOSE 8000
# Production default: migrate, then serve with several workers behind the nginx proxy.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-3} --proxy-headers --forwarded-allow-ips='*'"]
