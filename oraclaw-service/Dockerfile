FROM python:3.12-slim AS builder

WORKDIR /app

# Install system dependencies for oracledb
RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

# Copy source and install
COPY pyproject.toml ./
COPY oraclaw_service/ ./oraclaw_service/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libaio1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY oraclaw_service/ ./oraclaw_service/

EXPOSE 8100

CMD ["uvicorn", "oraclaw_service.main:app", "--host", "0.0.0.0", "--port", "8100"]
