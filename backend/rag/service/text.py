import re
import unicodedata
from typing import List

def clean_vietnamese_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = "".join(
        char for char in text
        if not unicodedata.category(char).startswith("C") or char in '\n\t'
    )

    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()