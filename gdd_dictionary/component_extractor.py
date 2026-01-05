
# gdd_dictionary/component_extractor.py
from typing import List, Dict, Any
import json
from backend.code_service import OpenAI, client  # reuse OpenAI client configured in repo  [2](https://unisydneyedu-my.sharepoint.com/personal/alee0103_uni_sydney_edu_au/Documents/Microsoft%20Copilot%20Chat%20Files/repomix-output-aaronlee0321-Unified_RAG.git.xml)
from .component_prompt import SYSTEM_PROMPT

def extract_components_from_chunk(chunk_text: str, doc_id: str, section_path: str) -> List[Dict[str, Any]]:
    """
    Returns list of component dicts matching the JSON schema in component_prompt.py.
    Ensures Vietnamese-only fields and attaches doc/section context to evidence items.
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Chunk (doc_id={doc_id}, section={section_path}):\n\n{chunk_text}\n\nHãy trích xuất JSON."}
    ]
    resp = client.chat.completions.create(model="qwen-plus", messages=messages, temperature=0)
    text = resp.choices[0].message.content
    # tolerate wrapping; find JSON
    start = text.find("{")
    end = text.rfind("}")
    data = json.loads(text[start:end+1]) if start != -1 and end != -1 else {"components": []}
    # attach doc/section to each evidence
    for c in data.get("components", []):
        for ev in c.get("evidence", []):
            ev.setdefault("doc_id", doc_id)
            ev.setdefault("section_path", section_path)
            ev.setdefault("source_language", "vi")
            ev.setdefault("confidence_score", 0.0)
    return data.get("components", [])
