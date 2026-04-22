import json
import time
from typing import Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.core.config import settings
from app.core.exceptions import AIServiceError
from app.core.logging import get_logger
from app.schemas.analysis import AnalysisResult

logger = get_logger(__name__)

# ── Prompt ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert German rental contract analyst with deep knowledge of German tenancy law (BGB §§ 535-580a).

Your job is to analyze German rental contracts and return a structured JSON response that helps non-German speakers understand what they are signing.

You MUST return ONLY valid JSON — no markdown, no explanation, no preamble.

The JSON must follow this exact structure:
{
  "summary": "A clear 2-4 sentence overview of the contract in plain English",
  "clauses": [
    {
      "type": "Category name (e.g. Rent, Deposit, Notice Period, Pets, Subletting, Maintenance, Utilities, Early Termination)",
      "text": "The relevant clause text (original German or translated)",
      "explanation": "Plain English explanation of what this means for the tenant"
    }
  ],
  "risks": [
    "Description of a risky or unusual condition the tenant should be aware of"
  ],
  "risk_score": "low | medium | high"
}

Risk scoring guide:
- low: Standard contract, no unusual clauses
- medium: Some clauses that require attention or negotiation
- high: Significant risks, unusual penalties, or clauses that heavily favour the landlord

Extract at least 5 clauses covering the most important terms. Flag any clause that:
- Imposes unusual financial penalties
- Restricts tenant rights beyond standard German law
- Has ambiguous or potentially unfair terms
- Involves significant costs (renovation, repairs, etc.)"""


USER_PROMPT_TEMPLATE = """Analyze this German rental contract and return the structured JSON response:

CONTRACT TEXT:
{document_text}"""


# ── OpenAI client ─────────────────────────────────────────────────────────────

def _get_client() -> OpenAI:
    return OpenAI(api_key=settings.openai_api_key)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _call_openai(client: OpenAI, document_text: str) -> tuple[str, int]:
    """
    Call OpenAI and return (raw_json_string, tokens_used).
    Retries up to 3 times with exponential backoff.
    """
    response = client.chat.completions.create(
        model=settings.openai_model,
        max_tokens=settings.openai_max_tokens,
        temperature=settings.openai_temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT_TEMPLATE.format(document_text=document_text)},
        ],
    )
    content = response.choices[0].message.content
    tokens = response.usage.total_tokens if response.usage else 0
    return content, tokens


def _parse_response(raw: str) -> AnalysisResult:
    """Parse and validate the raw JSON string into our AnalysisResult schema."""
    try:
        data: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AIServiceError(f"AI returned invalid JSON: {exc}") from exc

    # Normalise risk_score — model sometimes returns unexpected values
    risk = data.get("risk_score", "medium").lower().strip()
    if risk not in ("low", "medium", "high"):
        risk = "medium"
    data["risk_score"] = risk

    # Ensure required fields exist
    data.setdefault("summary", "No summary available.")
    data.setdefault("clauses", [])
    data.setdefault("risks", [])

    try:
        return AnalysisResult(**data)
    except Exception as exc:
        raise AIServiceError(f"AI response did not match expected schema: {exc}") from exc


# ── Public interface ──────────────────────────────────────────────────────────

def analyze_document(document_text: str) -> tuple[AnalysisResult, int, float]:
    """
    Send document text to OpenAI and return:
      (AnalysisResult, tokens_used, processing_time_seconds)

    For long documents, analyzes the first chunk only (most contracts fit in one chunk).
    Future enhancement: merge multi-chunk analyses.
    """
    from app.services.document_processor import chunk_text

    chunks = chunk_text(document_text, max_chars=12000)
    primary_chunk = chunks[0]

    if len(chunks) > 1:
        logger.info("Document has %d chunks — analyzing primary chunk", len(chunks))

    client = _get_client()
    start = time.perf_counter()

    try:
        raw, tokens = _call_openai(client, primary_chunk)
        elapsed = round(time.perf_counter() - start, 2)
        logger.info("OpenAI call complete", extra={"tokens": tokens, "seconds": elapsed})
    except Exception as exc:
        logger.error("OpenAI call failed after retries: %s", exc)
        raise AIServiceError(f"AI analysis failed: {exc}") from exc

    result = _parse_response(raw)
    return result, tokens, elapsed