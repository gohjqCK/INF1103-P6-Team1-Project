FROM python:3.11-slim

# Optimize Docker image by adding ENV variables.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 

# Working Directory for application code
WORKDIR /app

# Install dependencies first so this layer is cached between code changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy the application code into the container
COPY main.py .

# Start the application with the specified entry point and default command.
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]