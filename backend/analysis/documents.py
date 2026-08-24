"""Offer-document extraction for DRHP/RHP research."""

from __future__ import annotations

from io import BytesIO
import re
from typing import Any

from pypdf import PdfReader
import requests


REQUEST_TIMEOUT_SECONDS = 15

SECTION_PATTERNS = {
    "risk_factors": ("risk factors",),
    "objects_of_issue": ("objects of the issue", "objects of the offer"),
    "business": ("our business", "business overview"),
    "industry": ("industry overview",),
    "financial_information": ("financial information", "restated financial"),
    "management": ("our management", "management discussion"),
    "litigation": ("outstanding litigation", "legal proceedings"),
}


def analyze_offer_document(document_url: str) -> dict[str, Any]:
    response = requests.get(
        document_url,
        headers={"User-Agent": "StockMarketAnalyzer/1.0"},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    reader = PdfReader(BytesIO(response.content))
    pages = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(pages)
    normalized = re.sub(r"\s+", " ", text)

    sections = {
        name: _extract_section_excerpt(normalized, headings)
        for name, headings in SECTION_PATTERNS.items()
    }
    available_sections = [name for name, value in sections.items() if value]

    return {
        "document_url": document_url,
        "pages_read": len(pages),
        "characters_extracted": len(text),
        "sections": sections,
        "coverage": {
            "available_sections": available_sections,
            "missing_sections": [
                name for name in SECTION_PATTERNS if name not in available_sections
            ],
        },
        "review_checklist": {
            "business_model": bool(sections["business"]),
            "risk_factors": bool(sections["risk_factors"]),
            "use_of_proceeds": bool(sections["objects_of_issue"]),
            "financial_history": bool(sections["financial_information"]),
            "management": bool(sections["management"]),
            "litigation": bool(sections["litigation"]),
        },
        "note": (
            "This is deterministic document extraction, not an investment recommendation. "
            "Numerical tables and management claims require source-page verification."
        ),
    }


def _extract_section_excerpt(text: str, headings: tuple[str, ...]) -> str | None:
    lowered = text.lower()
    positions = [lowered.find(heading) for heading in headings]
    positions = [position for position in positions if position >= 0]
    if not positions:
        return None
    start = min(positions)
    later_headings = []
    for candidate_headings in SECTION_PATTERNS.values():
        for heading in candidate_headings:
            position = lowered.find(heading, start + len(heading))
            if position > start:
                later_headings.append(position)
    end = min(later_headings) if later_headings else len(text)
    return text[start:end].strip()
