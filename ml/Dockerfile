FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY requirements-ml-cpu.txt ./
RUN python -m pip install --no-cache-dir torch==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu \
    && python -m pip install --no-cache-dir -r requirements-ml-cpu.txt
COPY ml ./ml
COPY models/milestone4/v1 ./models/milestone4/v1
COPY scripts ./scripts
COPY simulator/backend/src/main/java ./simulator/backend/src/main/java
COPY data/processed/chennai_osm/road_graph.json ./data/processed/chennai_osm/road_graph.json
RUN python scripts/check_model_bundle.py
USER 65534:65534
EXPOSE 8090
HEALTHCHECK --interval=10s --timeout=5s --start-period=40s --retries=12 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=4)"
CMD ["python", "scripts/serve_ml.py", "--models", "models/milestone4/v1", "--host", "0.0.0.0", "--port", "8090"]
