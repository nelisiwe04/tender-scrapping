FROM postgres:16
EXPOSE 5432

LABEL org.opencontainers.image.source="https://github.com/nelisiwe04/tender-scrapping"

# Use the official Playwright Python image
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Set working directory
WORKDIR /app

# Copy requirements 
COPY backend/requirements.txt .

# Install Python dependencies 
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY backend/ .

# Expose the port Render will use
EXPOSE 10000

# Start the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "10000"]