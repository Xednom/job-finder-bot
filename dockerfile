# Dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# copy poetry lock + pyproject then install deps
COPY pyproject.toml poetry.lock* /app/
RUN pip install --no-cache-dir poetry
RUN poetry config virtualenvs.create false \
 && poetry install --only main --no-interaction --no-ansi --no-root

COPY . /app

# Expose nothing; bot connects out.
CMD ["python", "job_finder_bot.py"]
