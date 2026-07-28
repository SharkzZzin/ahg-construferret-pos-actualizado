FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV AHG_HOST=0.0.0.0
ENV PORT=8080
ENV AHG_PORT=8080

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8080
CMD ["python", "-m", "ahg_pos.app"]
