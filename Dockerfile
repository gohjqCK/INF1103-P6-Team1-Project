# Resume Screener - the Python app only. The AI model runs in the separate Ollama container
# (docker compose up -d), which this app reaches over the network.
FROM python:3.11-slim

# PYTHONDONTWRITEBYTECODE / PYTHONUNBUFFERED: no .pyc files, and print() shows up straight away
# PIP_*: smaller image, quieter install
# OLLAMA_HOST: inside a container "localhost" is the container itself, so reach Ollama on the host PC
# ANONYMIZED_TELEMETRY: stop ChromaDB sending usage data - the app should stay fully offline
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    OLLAMA_HOST=http://host.docker.internal:11434 \
    ANONYMIZED_TELEMETRY=False

# The program code lives in /app
WORKDIR /app

# Install dependencies first so this layer is cached between code changes
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy all the program files (main.py and the four managers)
COPY *.py ./

# The program reads resume folders and writes its JSON files in its current folder.
# Run it from /work and mount your project folder there, so it can see your PDFs and
# the results are saved back onto your computer:
#   docker run -it --rm -v "${PWD}:/work" resume-cli
WORKDIR /work

# -it is needed when running: the program is an interactive menu
ENTRYPOINT ["python", "/app/main.py"]
