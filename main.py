import argparse
import json
import os
import sys
from pathlib import Path

import ollama
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
from pypdf import PdfReader


