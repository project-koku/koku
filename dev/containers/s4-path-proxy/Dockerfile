FROM docker.io/library/python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY path_maps.yaml .
COPY s4_path_proxy/ ./s4_path_proxy/
COPY tests/ ./tests/

ENV PYTHONPATH=/app
RUN pytest -q

ENV S4_PROXY_HOST=0.0.0.0
ENV S4_PROXY_PORT=7480
ENV S4_BACKEND_URL=http://koku-s4:7480
ENV S4_PATH_MAPS=/app/path_maps.yaml

EXPOSE 7480

CMD ["python", "-m", "s4_path_proxy.main"]
