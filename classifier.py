"""LLM complaint classifier with a safe offline fallback."""
import json
import os
import re
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_system_prompt(path):
    return Path(path).read_text(encoding="utf-8")


def _extract_json(text):
    """Extract a JSON object even if the model wraps it in Markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in LLM response")
    return json.loads(text[start:end + 1])


def _offline_classify(complaint):
    """Basic deterministic fallback used when API access is unavailable."""
    text = complaint.lower()
    room_match = re.search(r"(?<![A-Z0-9])([A-D])[- ]?([1-4](?:0[1-9]|1[0-9]|20))(?![0-9])", complaint.upper())
    room = f"{room_match.group(1)}{room_match.group(2)}" if room_match else None

    if any(word in text for word in ("fan", "light", "switch", "wire", "socket", "power", "sparks")):
        issue = "electrical"
    elif any(word in text for word in ("tap", "pipe", "water leak", "toilet", "drain", "flush", "shower")):
        issue = "plumbing"
    elif any(word in text for word in ("door", "lock", "chair", "table", "bed", "cupboard", "window")):
        issue = "carpentry"
    elif any(word in text for word in ("dirty", "clean", "garbage", "dust", "washroom", "rubbish")):
        issue = "cleaning"
    elif any(word in text for word in ("wifi", "wi-fi", "internet", "network", "router")):
        issue = "internet"
    else:
        issue = "other"

    urgent = any(word in text for word in (
        "spark", "shock", "burning smell", "overflowing", "flood",
        "near the switch", "water near the socket", "water near electrical",
    ))
    summary_words = complaint.strip().split()
    summary = " ".join(summary_words[:10])
    return {"room": room, "issue": issue, "urgent": urgent, "summary": summary}


def classify(complaint, system_prompt, offline=False):
    """
    Ask Gemini to classify one complaint.
    Set GEMINI_API_KEY in the environment to enable the API.
    If offline=True or no key is set, use the local fallback.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if offline or not api_key:
        return _offline_classify(complaint)

    try:
        from google import genai
    except ImportError as error:
        raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from error

    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
    client = genai.Client(api_key=api_key)
    full_prompt = (
        system_prompt
        + "\n\nClassify this single complaint. Return only one JSON object.\n"
        + "Complaint: "
        + json.dumps(complaint, ensure_ascii=False)
    )
    response = client.interactions.create(model=model, input=full_prompt)
    parsed = _extract_json(response.output_text)

    # Normalize only field formatting, not the room identity.
    parsed["issue"] = str(parsed.get("issue", "other")).strip().lower()
    parsed["summary"] = " ".join(str(parsed.get("summary", "")).split()[:10])
    if not isinstance(parsed.get("urgent"), bool):
        raise ValueError("LLM urgent field must be true or false")
    return parsed
