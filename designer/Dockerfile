FROM python:3.14.10-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8095 DATA_DIR=/app/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py yamlgen.py panel.yaml.j2 default_design.json default_crowpanel_7.json start.sh ./
COPY hardware hardware
COPY templates templates
COPY static static

# No USER line: Home Assistant needs root at the start to take ownership of /data.
# start.sh drops to this user, and docker-compose.yml starts as it directly.
RUN useradd --uid 1000 --no-create-home app && mkdir -p /app/data && chown app /app/data

EXPOSE 8095
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import os,urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=3)"

CMD ["sh", "start.sh"]
