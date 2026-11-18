FROM python:3.13-alpine

WORKDIR /app
RUN pip install --no-cache-dir "psycopg[binary]>=3.2,<4"
COPY app.py .

CMD ["python", "app.py"]
