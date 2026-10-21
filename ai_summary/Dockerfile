FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy service files
COPY . /app/

# Expose port
EXPOSE 8000

# Start FastAPI proxy server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
