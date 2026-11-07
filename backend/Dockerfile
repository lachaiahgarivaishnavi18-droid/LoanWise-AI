FROM python:3.12-slim-bookworm
WORKDIR /app
COPY requirements.txt requirements-lock.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgl1 libgomp1 fonts-dejavu-core && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt -c requirements-lock.txt
COPY . .
RUN useradd -m loanwise && mkdir -p runtime data && chown -R loanwise:loanwise /app
USER loanwise
EXPOSE 8000
HEALTHCHECK --start-period=60s --interval=15s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
