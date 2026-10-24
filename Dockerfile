# The notes service. The pipeline builds this image on every push.
FROM python:3.14-slim

WORKDIR /app

# Dependencies first: this layer is reused until requirements.txt changes (week 5).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the code.
COPY source/ src/
COPY scripts/ scripts/

# A folder the service may write to, owned by the user it runs as.
RUN mkdir -p /app/data && chown 1000:1000 /app/data

USER 1000:1000
ENV PORT=8080
EXPOSE 8080
CMD ["./scripts/run.sh"]
