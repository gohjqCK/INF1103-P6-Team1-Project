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
     "Check the resume ONLY against the numbered items given. "
     "Ignore name, gender, age, ethnicity, religion, nationality and any other "
     "personal details that are not related to the job.\n"
     "For each item, first copy the exact words from the resume that prove it as evidence. "
     "If no words in the resume directly prove the item, the evidence is \"\" and shows is false. "
     "Do not guess or infer: a related skill is not the same as a certification or qualification.\n"
     "Reply ONLY with JSON in exactly this format, with one entry per item:\n"
     '{{"candidate": "<name, or Unknown>", '
     '"checks": [{{"id": <item number>, "evidence": "<exact quote from the resume, or empty>", "shows": true or false}}], '
     '"summary": "<one or two sentences>"}}'),
    ("human",
     "Items to check:\n{rules}\n\n"
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

def get_llm() -> ChatOllama:
    """Create the connection to the Mistral model on the Ollama server."""
    return ChatOllama(
        model=MODEL_NAME,     # which model to use ("mistral")
        base_url=OLLAMA_HOST, # where the Ollama server is
        temperature=0,        # straight forward answers, no randomness
        format="json",        # force the model to reply with valid JSON
        seed=42,              # fixed randomness so the same input gives the same output
    )

def start_chat(rules: list[dict], resume_text: str) -> dict:
    """Send one resume and the business rules to Mistral and return its answer as a dict."""
    # 1. Turn the rules into a numbered list of text
    rules_text = ""
    number = 1
    for rule in rules:
        rules_text += f"{number}. {rule['text']}\n"
        number += 1

    # 2. Fill in the blanks in the prompt template
    prompt = RESUME_PROMPT.invoke({"rules": rules_text, "resume": resume_text})

    # 3. Send the prompt to Mistral and wait for the reply
    llm = get_llm()
    reply = llm.invoke(prompt)

    # 4. Convert the JSON text reply into a Python dictionary
    result = json.loads(reply.content)
    return result


if __name__ == "__main__": # testing
    if check_connection():
        rules = [
            {"text": "At least 2 years of networking experience", "priority": "must"},
            {"text": "CCNA is listed as a certification", "priority": "important"},
            {"text": "Has cloud experience", "priority": "nice"},
            {"text": "Has a criminal record", "priority": "reject"},
        ]
        resume = ("Jane Doe\nBSc Information Technology, 2021\n"
                  "Network Administrator at ABC Pte Ltd, 2021-2024\n"
                  "Skills: Cisco routing and switching, AWS EC2, Python")

        result = start_chat(rules, resume)
        print(json.dumps(result, indent=2))