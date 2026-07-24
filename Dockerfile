FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml README.md ./
COPY api ./api
COPY config ./config
COPY exception ./exception
COPY logger ./logger
COPY src ./src
COPY static ./static
COPY templates ./templates
COPY utils ./utils
RUN pip install --no-cache-dir .
RUN mkdir -p data/vector_store logs
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
