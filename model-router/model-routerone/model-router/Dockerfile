FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Expose the API port (default)
EXPOSE 8000

# Use shell form so $PORT (injected by hosting platforms) can be respected; remove --reload for production
ENTRYPOINT ["sh", "-c", "uvicorn model_router_api:app --host 0.0.0.0 --port ${PORT:-8000}"]