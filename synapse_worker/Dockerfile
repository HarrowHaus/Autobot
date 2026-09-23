FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 SYNAPSE_DATA_DIR=/data
WORKDIR /app
COPY worker.py ./worker.py
COPY tests ./tests
RUN python -m py_compile worker.py && python -m unittest discover -s tests -v
# Railway volumes mount as root. All persistent credentials are stored mode 0600.
# TLS terminates at the host; expose only the generated HTTPS service domain.
EXPOSE 8080
CMD ["python", "worker.py", "serve", "--host", "0.0.0.0"]
