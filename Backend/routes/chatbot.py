# Public DEMOE endpoint; no portal data or persistent chat storage.
import re
from flask import Blueprint, jsonify, request
from Backend.extensions import limiter
from Backend.services.demoe_service import FIXED_FAQS, REFUSAL, ai_answer, fixed_answer
bp = Blueprint("chatbot", __name__, url_prefix="/api")
SENSITIVE = re.compile(r"\b(api\s*key|secret\s*key|database\s*password|db\s*password|system\s*prompt|internal\s*instructions|otp|upi\s*pin|credit\s*card|debit\s*card|student\s*attendance|employee\s*salary)\b", re.I)

@bp.get("/chat/faqs")
@limiter.limit("60 per minute")
def faqs():
    return jsonify(questions=[item["question"] for item in FIXED_FAQS.values()])

@bp.post("/chat")
@limiter.limit("20 per minute; 100 per hour")
def chat():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("message"), str):
        return jsonify(success=False, error="A message is required."), 400
    message = data["message"].strip()
    if not message or len(message) > 4000:
        return jsonify(success=False, error="Enter a message of up to 4000 characters."), 400
    if SENSITIVE.search(message):
        return jsonify(success=True, reply=REFUSAL)
    answer = fixed_answer(message)
    if answer is not None:
        return jsonify(success=True, reply=answer)
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []
    clean_history = []
    for item in history[-6:]:
        if (isinstance(item, dict) and item.get("role") in ("user", "assistant")
                and isinstance(item.get("content"), str) and len(item["content"]) <= 1000
                and not SENSITIVE.search(item["content"])):
            clean_history.append({"role": item["role"], "content": item["content"]})
    return jsonify(success=True, reply=ai_answer(message, clean_history))
