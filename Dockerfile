FROM python:3.12-slim
WORKDIR /app
COPY src/frontdoor_lab/__init__.py src/frontdoor_lab/origin.py ./frontdoor_lab/
USER 65534:65534
EXPOSE 8080
CMD ["python", "-u", "-m", "frontdoor_lab.origin", "--host", "0.0.0.0", "--port", "8080"]
