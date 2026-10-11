FROM postgres:18-alpine
RUN apk add --no-cache python3 py3-pip \
    && python3 -m venv /opt/backup-venv \
    && /opt/backup-venv/bin/pip install --no-cache-dir 'boto3>=1.35,<2'
ENV PATH="/opt/backup-venv/bin:${PATH}" PYTHONUNBUFFERED=1
WORKDIR /opt/zombo-backup
COPY ops/backup/worker.py /opt/zombo-backup/worker.py
CMD ["python", "worker.py"]
