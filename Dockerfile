FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY datasets ./datasets
COPY config ./config
RUN pip install --no-cache-dir .

ENTRYPOINT ["gnomon"]
CMD ["--config", "config/docker.toml"]
