FROM python:3.12
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/ .
RUN mkdir -p /app/backend/uploads
ENV UPLOAD_FOLDER=/app/backend/uploads
CMD ["python", "main.py"]
