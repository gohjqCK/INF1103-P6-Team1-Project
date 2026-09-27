import json
import os
import sys
from pathlib import Path

import ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pypdf import PdfReader

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "mistral")

RESUME_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are an impartial resume screening assistant. "
     "Judge the resume ONLY against the business rules given. "
     "Ignore name, gender, age, ethnicity, religion, nationality and any other "
     "personal details that are not related to the job.\n"
     "For each rule, decide whether the resume clearly meets it. "
     "If the resume does not mention something, the rule is NOT met - do not guess.\n"
     "Reply ONLY with JSON in exactly this format:\n"
     '{{"candidate": "<name, or Unknown>", '
     '"rules": [{{"rule": "<rule text>", "met": true or false, "evidence": "<short reason>"}}], '
     '"summary": "<one or two sentences>"}}'),
    ("human",
     "Business rules:\n{rules}\n\n"
     "Resume:\n{resume}"),
])

def check_connection() -> bool:
    """Check that the Ollama server is reachable and the model is downloaded."""
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        models = client.list().models
    except ConnectionError:
        print(f"Cannot reach Ollama at {OLLAMA_HOST}. Is it running? (docker compose up -d)")
        return False

    model_names = [m.model for m in models]   # e.g. ["mistral:latest"]
    found = any(name == MODEL_NAME or name.split(":")[0] == MODEL_NAME
                for name in model_names)
    if not found:
        print(f"Connected, but model '{MODEL_NAME}' is not downloaded. Found: {model_names}")
        print(f"Download it with: docker compose exec ollama ollama pull {MODEL_NAME}")
        return False

    print(f"Connected to {OLLAMA_HOST} and '{MODEL_NAME}' is ready.")
    return True

