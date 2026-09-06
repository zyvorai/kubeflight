FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN addgroup --system --gid 10001 kubeflight && adduser --system --uid 10001 --gid 10001 --home /nonexistent --no-create-home kubeflight
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml README.md LICENSE ./
COPY kubeflight ./kubeflight
COPY examples ./examples
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python","-m","kubeflight.cli"]
CMD ["serve","--host","0.0.0.0","--port","8080"]
