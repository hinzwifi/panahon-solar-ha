FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir argon2-cffi

COPY panahon_solar_service.py /app/panahon_solar_service.py

EXPOSE 8089

CMD ["python3", "/app/panahon_solar_service.py"]
