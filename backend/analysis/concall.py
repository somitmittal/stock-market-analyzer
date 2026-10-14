"""Deterministic concall transcript / presentation summary."""

from __future__ import annotations

import re
from typing import Any

from analysis.documents import fetch_pdf_text


POSITIVE_TERMS = (
    "growth",
    "increase",
    "expansion",
    "strong demand",
    "robust",
    "record",
    "improved",
    "higher",
    "optimistic",
    "momentum",
    "pipeline",
    "order book",
    "margin expansion",
    "profitability",
    "beat",
    "exceeded",
    "outperformed",
    "market share gain",
    "capacity addition",
    "deleveraging",
    "cash generation",
)

NEGATIVE_TERMS = (
    "decline",
    "decrease",
    "weak demand",
    "pressure",
    "headwind",
    "challenge",
    "uncertain",
    "delay",
    "slowdown",
    "contraction",
    "loss",
    "missed",
    "below expectation",
    "impairment",
    "debt increase",
    "concern",
    "risk",
    "inflation",
    "cost increase",
    "margin compression",
    "inventory buildup",
    "regulatory",
    "litigation",
)


def summarize_concall_document(
    attachment_url: str,
    subject: str | None = None,
) -> dict[str, Any]:
    text = fetch_pdf_text(attachment_url)
    if not text:
        return {
            "available": False,
            "subject": subject,
            "attachment_url": attachment_url,
            "note": "Could not extract readable text from this filing.",
        }

    normalized = re.sub(r"\s+", " ", text)
    sentences = _split_sentences(normalized)
    positives = _rank_sentences(sentences, POSITIVE_TERMS)
    negatives = _rank_sentences(sentences, NEGATIVE_TERMS)

    return {
        "available": bool(positives or negatives),
        "subject": subject,
        "attachment_url": attachment_url,
        "positives": positives[:5],
        "negatives": negatives[:5],
        "characters_analyzed": len(normalized),
        "note": (
            "Rule-based extraction from the official filing text. "
            "Verify claims against the source PDF before acting."
        ),
    }


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    cleaned = []
    for part in parts:
        sentence = part.strip()
        if len(sentence) < 40 or len(sentence) > 400:
            continue
        if re.fullmatch(r"[\d\s\W]+", sentence):
            continue
        cleaned.append(sentence)
    return cleaned


def _rank_sentences(sentences: list[str], terms: tuple[str, ...]) -> list[str]:
    scored: list[tuple[int, str]] = []
    seen = set()
    for sentence in sentences:
        lowered = sentence.lower()
        score = sum(1 for term in terms if term in lowered)
        if score == 0:
            continue
        key = lowered[:120]
        if key in seen:
            continue
        seen.add(key)
        scored.append((score, sentence))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [sentence for _, sentence in scored]
