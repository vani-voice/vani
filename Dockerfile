FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY webapp/requirements.txt webapp/requirements.txt
RUN pip install --no-cache-dir -r webapp/requirements.txt

# Install vani package
COPY pyproject.toml README.md LICENSE ./
COPY vani/ vani/
RUN pip install --no-cache-dir -e .

# Copy webapp
COPY webapp/ webapp/

# Port from environment (Render/Railway set $PORT)
ENV PORT=8000
EXPOSE 8000

CMD uvicorn webapp.server:app --host 0.0.0.0 --port ${PORT}
