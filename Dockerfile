FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM builder AS final
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
WORKDIR /app
COPY . .
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
CMD ["alembic", "upgrade", "head", "&&", "python", "app.py"]

