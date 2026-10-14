FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GIGCA_API_HOST=0.0.0.0
WORKDIR /app
COPY data/db/requirements.txt ./data/db/requirements.txt
COPY engine/requirements.txt ./engine/requirements.txt
COPY api/requirements.txt ./api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt \
    && useradd --create-home --uid 10001 gigca \
    && mkdir /app/.cache && chown gigca:gigca /app/.cache
COPY api ./api
COPY data ./data
COPY engine ./engine
COPY config ./config
COPY contracts ./contracts
USER gigca
EXPOSE 8000
CMD ["python", "-m", "api.v1_server"]
