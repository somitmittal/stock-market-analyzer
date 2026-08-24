"""Recent official BSE disclosures and deterministic filing evidence extraction."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
import tempfile
from typing import Any

from bse import BSE
from dateutil.relativedelta import relativedelta
from pypdf import PdfReader
import requests


ATTACHMENT_BASE_URL = "https://www.bseindia.com/xml-data/corpfiling/AttachLive"
REQUEST_TIMEOUT_SECONDS = 15

DISCLOSURE_KEYWORDS = {
    "concall": (
        "conference call",
        "earnings call",
        "analyst call",
        "investor call",
        "audio recording",
        "transcript",
    ),
    "management_guidance": (
        "investor presentation",
        "earnings presentation",
        "guidance",
        "business update",
    ),
    "order_book": (
        "order book",
        "order received",
        "orders received",
        "work order",
        "letter of award",
        "contract award",
        "new order",
    ),
    "shareholding": (
        "shareholding pattern",
        "pledge",
        "pledged",
        "encumbrance",
        "encumbered",
    ),
}

EVIDENCE_TERMS = {
    "management_guidance": (
        "guidance",
        "outlook",
        "revenue growth",
        "margin",
        "capex",
        "capacity",
    ),
    "order_book": (
        "order book",
        "order inflow",
        "unexecuted order",
        "orders in hand",
        "letter of award",
    ),
    "promoter_pledging": (
        "pledged",
        "pledge",
        "encumbered",
        "encumbrance",
    ),
}


def fetch_recent_disclosures(symbol: str) -> dict[str, Any]:
    """Fetch the user-selected three-month filing window from official BSE data."""
    clean_symbol = symbol.upper().replace(".NS", "").replace(".BO", "")
    fetched_at = datetime.now().astimezone().isoformat()
    to_date = datetime.now()
    from_date = to_date - relativedelta(months=3)
    download_dir = Path(tempfile.gettempdir()) / "stock-market-analyzer-bse"
    download_dir.mkdir(parents=True, exist_ok=True)

    try:
        with BSE(str(download_dir)) as client:
            scrip_code = client.getScripCode(clean_symbol)
            announcements = _fetch_all_pages(
                client,
                str(scrip_code),
                from_date,
                to_date,
            )
    except Exception as exc:
        return {
            "available": False,
            "filing_window": {
                "from": from_date.date().isoformat(),
                "to": to_date.date().isoformat(),
            },
            "categories": {},
            "analysis": _empty_filing_analysis(),
            "provenance": {
                "provider": "BSE India public corporate-announcements feed",
                "status": "error",
                "fetched_at": fetched_at,
                "error": str(exc),
                "official_source": True,
                "api_status": "public_undocumented_endpoint",
            },
        }

    records = [_normalize_announcement(item) for item in announcements]
    categorized = {
        category: [record for record in records if category in record["categories"]]
        for category in DISCLOSURE_KEYWORDS
    }
    analysis = _analyze_latest_category_documents(categorized)

    return {
        "available": bool(records),
        "scrip_code": str(scrip_code),
        "filing_window": {
            "from": from_date.date().isoformat(),
            "to": to_date.date().isoformat(),
        },
        "announcement_count": len(records),
        "categories": categorized,
        "analysis": analysis,
        "provenance": {
            "provider": "BSE India public corporate-announcements feed",
            "status": "ok",
            "fetched_at": fetched_at,
            "official_source": True,
            "api_status": "public_undocumented_endpoint",
            "note": "Metadata and attachments originate from BSE; the JSON endpoint is not a supported developer API.",
        },
    }


def _fetch_all_pages(
    client: BSE,
    scrip_code: str,
    from_date: datetime,
    to_date: datetime,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    page = 1
    total = None
    while total is None or len(records) < total:
        response = client.announcements(
            page_no=page,
            from_date=from_date,
            to_date=to_date,
            scripcode=scrip_code,
        )
        page_records = response.get("Table") or []
        records.extend(page_records)
        if total is None:
            summary = response.get("Table1") or []
            total = int(summary[0].get("ROWCNT", len(page_records))) if summary else len(page_records)
        if not page_records:
            break
        page += 1
    return records


def _normalize_announcement(item: dict[str, Any]) -> dict[str, Any]:
    searchable = " ".join(
        str(item.get(key) or "")
        for key in ("NEWSSUB", "HEADLINE", "MORE", "CATEGORYNAME", "SUBCATNAME")
    ).lower()
    categories = [
        category
        for category, keywords in DISCLOSURE_KEYWORDS.items()
        if any(keyword in searchable for keyword in keywords)
    ]
    attachment_name = str(item.get("ATTACHMENTNAME") or "").strip()
    return {
        "id": item.get("NEWSID"),
        "date": item.get("NEWS_DT") or item.get("DT_TM"),
        "subject": item.get("NEWSSUB"),
        "headline": item.get("HEADLINE") or item.get("MORE"),
        "category": item.get("CATEGORYNAME"),
        "subcategory": item.get("SUBCATNAME"),
        "categories": categories,
        "attachment_url": (
            f"{ATTACHMENT_BASE_URL}/{attachment_name}" if attachment_name else None
        ),
        "audio_video_url": item.get("AUDIO_VIDEO_FILE"),
        "company_url": item.get("NSURL"),
    }


def _analyze_latest_category_documents(
    categorized: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    results = _empty_filing_analysis()
    source_categories = {
        "management_guidance": ("management_guidance", "concall"),
        "order_book": ("order_book", "management_guidance"),
        "promoter_pledging": ("shareholding",),
    }
    text_cache: dict[str, str | None] = {}

    for analysis_name, categories in source_categories.items():
        candidates = [
            record
            for category in categories
            for record in categorized.get(category, [])
            if record.get("attachment_url")
        ]
        candidates.sort(key=lambda record: str(record.get("date") or ""), reverse=True)
        for record in candidates:
            url = record["attachment_url"]
            if url not in text_cache:
                text_cache[url] = _extract_pdf_text(url)
            text = text_cache[url]
            if not text:
                continue
            excerpts = _matching_sentences(text, EVIDENCE_TERMS[analysis_name])
            if excerpts:
                results[analysis_name] = {
                    "available": True,
                    "excerpts": excerpts,
                    "source": {
                        "date": record.get("date"),
                        "subject": record.get("subject"),
                        "attachment_url": url,
                    },
                    "note": "Extracted text is evidence, not an inferred forecast; verify numerical claims in the source PDF.",
                }
                break
    return results


def _extract_pdf_text(url: str) -> str | None:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "StockMarketAnalyzer/1.0"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        return re.sub(r"\s+", " ", text).strip() or None
    except Exception:
        return None


def _matching_sentences(text: str, terms: tuple[str, ...]) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    matches = []
    seen = set()
    for sentence in sentences:
        lowered = sentence.lower()
        if not any(term in lowered for term in terms):
            continue
        normalized = sentence.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            matches.append(normalized)
    return matches


def _empty_filing_analysis() -> dict[str, dict[str, Any]]:
    return {
        "management_guidance": {"available": False},
        "order_book": {"available": False},
        "promoter_pledging": {"available": False},
    }
