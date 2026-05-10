# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /app

COPY deployment/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim AS runtime
WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Expose ports
EXPOSE 8000 8501

# Environment
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Default: start FastAPI (override for Streamlit)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
