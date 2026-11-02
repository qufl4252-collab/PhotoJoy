FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PHOTOJOY_DATA_DIR=/data PORT=8765
WORKDIR /app
COPY requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements-web.txt
COPY photojoy ./photojoy
COPY photojoy_web ./photojoy_web
COPY models/manifest.json ./models/manifest.json
COPY scripts/prepare_models.py ./scripts/prepare_models.py
COPY licenses ./licenses
RUN python scripts/prepare_models.py && useradd --create-home photojoy && mkdir /data && chown photojoy:photojoy /data
USER photojoy
EXPOSE 8765
CMD ["sh", "-c", "exec uvicorn photojoy_web.app:app_factory --factory --host 0.0.0.0 --port ${PORT:-8765} --workers 1 --no-proxy-headers"]
