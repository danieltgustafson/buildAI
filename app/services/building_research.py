from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import json
import re
from typing import Any, Protocol

import httpx

from app.config import settings
from app.schemas.building_research import (
    BuildingAssessment,
    ComponentAssessment,
    ResearchRequest,
    ResearchResponse,
)

BASE_USEFUL_LIFE_YEARS = {
    "roof": 25,
    "windows": 30,
    "hvac": 18,
    "elevators": 25,
}

NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OPEN_METEO_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"
OPENAI_RESPONSES_BASE = "https://api.openai.com/v1/responses"


@dataclass
class PublicRecordResult:
    address: str
    lat: float | None
    lon: float | None
    year_built: int | None
    elevator_present: bool | None
    sources: list[str]


@dataclass
class ClimateSummary:
    hot_days: int
    freeze_days: int
    heavy_precip_days: int


class ResearchTool(Protocol):
    def enrich(self, record: PublicRecordResult, payload: ResearchRequest) -> PublicRecordResult:
        ...


class OSMNominatimTool:
    def resolve_candidates(self, payload: ResearchRequest) -> list[PublicRecordResult]:
        if payload.address:
            return [self._search_single_address(payload.address)]
        return self._search_zip_candidates(payload)

    def enrich(self, record: PublicRecordResult, payload: ResearchRequest) -> PublicRecordResult:
        return record

    def _search_single_address(self, address: str) -> PublicRecordResult:
        params = {
            "q": address,
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 0,
            "limit": 1,
        }
        records = _nominatim_search(params)
        if not records:
            return PublicRecordResult(
                address=address,
                lat=None,
                lon=None,
                year_built=None,
                elevator_present=None,
                sources=["Nominatim: no match for provided address"],
            )

        item = records[0]
        extratags = item.get("extratags") or {}
        parsed_address = item.get("display_name") or address
        return PublicRecordResult(
            address=parsed_address,
            lat=_to_float(item.get("lat")),
            lon=_to_float(item.get("lon")),
            year_built=_extract_year(extratags),
            elevator_present=_extract_elevator(extratags),
            sources=["OpenStreetMap Nominatim geocoder + OSM tags"],
        )

    def _search_zip_candidates(self, payload: ResearchRequest) -> list[PublicRecordResult]:
        building_hint = payload.building_type.value.replace("_", " ") if payload.building_type else "building"
        params = {
            "q": f"{building_hint} in {payload.zip_code}",
            "format": "jsonv2",
            "addressdetails": 1,
            "extratags": 1,
            "namedetails": 0,
            "limit": payload.max_candidate_addresses,
            "countrycodes": "us",
        }
        records = _nominatim_search(params)
        if not records:
            return [
                PublicRecordResult(
                    address=f"ZIP {payload.zip_code} (no candidates found)",
                    lat=None,
                    lon=None,
                    year_built=None,
                    elevator_present=None,
                    sources=["Nominatim: no candidates for ZIP/building type search"],
                )
            ]

        return [
            PublicRecordResult(
                address=item.get("display_name", f"ZIP {payload.zip_code} candidate"),
                lat=_to_float(item.get("lat")),
                lon=_to_float(item.get("lon")),
                year_built=_extract_year(item.get("extratags") or {}),
                elevator_present=_extract_elevator(item.get("extratags") or {}),
                sources=["OpenStreetMap Nominatim geocoder + OSM tags"],
            )
            for item in records
        ]


class ClimateContextTool:
    def enrich(self, record: PublicRecordResult, payload: ResearchRequest) -> PublicRecordResult:
        if record.lat is None or record.lon is None:
            return record
        climate = _open_meteo_climate_summary(record.lat, record.lon)
        if climate is None:
            return record

        notes = (
            f"Open-Meteo climate archive: hot_days={climate.hot_days}, "
            f"freeze_days={climate.freeze_days}, heavy_precip_days={climate.heavy_precip_days}"
        )
        return PublicRecordResult(
            address=record.address,
            lat=record.lat,
            lon=record.lon,
            year_built=record.year_built,
            elevator_present=record.elevator_present,
            sources=[*record.sources, notes],
        )


class OpenAIResearchUnavailableError(RuntimeError):
    """Raised when building research cannot be completed with the OpenAI agent."""


class BuildingResearchAgent:
    def __init__(self) -> None:
        self.discovery_tool = OSMNominatimTool()
        self.enrichment_tools: list[ResearchTool] = [ClimateContextTool()]

    def run(self, payload: ResearchRequest) -> ResearchResponse:
        records = self.discovery_tool.resolve_candidates(payload)
        enriched = [self._enrich_record(record, payload) for record in records]
        buildings = [self._assess_building(record, payload) for record in enriched]
        mode = "address" if payload.address else "zip_discovery"
        return ResearchResponse(
            mode=mode,
            candidate_addresses=[r.address for r in enriched],
            buildings=buildings,
        )

    def _enrich_record(self, record: PublicRecordResult, payload: ResearchRequest) -> PublicRecordResult:
        enriched = record
        for tool in self.enrichment_tools:
            enriched = tool.enrich(enriched, payload)
        return enriched

    def _assess_building(self, record: PublicRecordResult, payload: ResearchRequest) -> BuildingAssessment:
        components = _openai_agent_component_assessment(record, payload)
        if components is None:
            raise OpenAIResearchUnavailableError(
                "Building research requires a successful OpenAI agent response. "
                "Check OPENAI_API_KEY and outbound connectivity."
            )
        return BuildingAssessment(address=record.address, components=components)


def run_building_system_research(payload: ResearchRequest) -> ResearchResponse:
    return BuildingResearchAgent().run(payload)


def _openai_agent_component_assessment(
    record: PublicRecordResult,
    payload: ResearchRequest,
) -> list[ComponentAssessment] | None:
    if not settings.openai_api_key:
        return None

    evidence = {
        "address": record.address,
        "year_built": payload.year_built or record.year_built,
        "building_type": payload.building_type.value if payload.building_type else None,
        "system_install_years": payload.system_install_years,
        "elevator_present": record.elevator_present,
        "sources": record.sources,
    }

    instructions = (
        "You are a building systems research agent. Given evidence from public data tools, "
        "produce conservative estimates for roof/windows/hvac/elevators. "
        "Return strict JSON with this shape: "
        '{"components": [{"component": "roof", "age_years": 10 or null, "source": "...", '
        '"replacement_likelihood_next_2y": "low|medium|high|unknown", "confidence": 0.0-1.0}]}. '
        "Do not include markdown."
    )

    payload_json = {
        "model": settings.openai_research_model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(evidence)}]},
        ],
        "temperature": 0.2,
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                OPENAI_RESPONSES_BASE,
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload_json,
            )
            response.raise_for_status()
            body = response.json()
    except Exception:
        return None

    text = _extract_response_text(body)
    if not text:
        return None

    parsed = _parse_agent_json(text)
    if not parsed:
        return None

    return _normalize_component_assessments(parsed)


def _extract_response_text(body: dict[str, Any]) -> str | None:
    output = body.get("output")
    if not isinstance(output, list):
        return body.get("output_text") if isinstance(body.get("output_text"), str) else None

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text = block.get("text")
            if isinstance(text, str):
                chunks.append(text)
    if chunks:
        return "\n".join(chunks)
    return body.get("output_text") if isinstance(body.get("output_text"), str) else None


def _parse_agent_json(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _normalize_component_assessments(parsed: dict[str, Any]) -> list[ComponentAssessment] | None:
    raw_components = parsed.get("components")
    if not isinstance(raw_components, list):
        return None

    by_name: dict[str, ComponentAssessment] = {}
    for item in raw_components:
        if not isinstance(item, dict):
            continue
        component = str(item.get("component", "")).strip().lower()
        if component not in BASE_USEFUL_LIFE_YEARS:
            continue

        age = item.get("age_years")
        age_years = int(age) if isinstance(age, (int, float)) else None
        likelihood = str(item.get("replacement_likelihood_next_2y", "unknown")).lower().strip()
        if likelihood not in {"low", "medium", "high", "unknown"}:
            likelihood = "unknown"

        confidence = item.get("confidence", 0.4)
        if not isinstance(confidence, (int, float)):
            confidence = 0.4
        confidence = min(max(float(confidence), 0.0), 1.0)

        source = str(item.get("source") or "OpenAI agent synthesis")
        by_name[component] = ComponentAssessment(
            component=component,
            age_years=age_years,
            source=source,
            replacement_likelihood_next_2y=likelihood,
            confidence=confidence,
        )

    if not by_name:
        return None

    for component in BASE_USEFUL_LIFE_YEARS:
        if component not in by_name:
            by_name[component] = ComponentAssessment(
                component=component,
                age_years=None,
                source="OpenAI agent synthesis (insufficient evidence)",
                replacement_likelihood_next_2y="unknown",
                confidence=0.2,
            )

    return [by_name[name] for name in BASE_USEFUL_LIFE_YEARS]


def _research_headers() -> dict[str, str]:
    """Headers for outbound research HTTP calls.

    The User-Agent is required by many public APIs (notably OSM Nominatim)
    and should identify the calling application.
    """
    return {"User-Agent": settings.research_user_agent}


def _nominatim_search(params: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=8.0, headers=_research_headers()) as client:
            response = client.get(f"{NOMINATIM_BASE}/search", params=params)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return [item for item in payload if isinstance(item, dict)]
    except Exception:
        return []
    return []


def _open_meteo_climate_summary(lat: float, lon: float) -> ClimateSummary | None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365)
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "UTC",
    }

    try:
        with httpx.Client(timeout=8.0, headers=_research_headers()) as client:
            response = client.get(OPEN_METEO_ARCHIVE_BASE, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not isinstance(daily, dict):
        return None

    max_t = daily.get("temperature_2m_max") or []
    min_t = daily.get("temperature_2m_min") or []
    precip = daily.get("precipitation_sum") or []

    hot_days = sum(1 for t in max_t if isinstance(t, (float, int)) and t >= 35)
    freeze_days = sum(1 for t in min_t if isinstance(t, (float, int)) and t <= 0)
    heavy_precip_days = sum(1 for p in precip if isinstance(p, (float, int)) and p >= 20)
    return ClimateSummary(hot_days=hot_days, freeze_days=freeze_days, heavy_precip_days=heavy_precip_days)


def _extract_year(extratags: dict[str, Any]) -> int | None:
    candidates = [extratags.get("start_date"), extratags.get("construction_date"), extratags.get("opening_date")]
    for value in candidates:
        if not value:
            continue
        match = re.search(r"(18|19|20)\d{2}", str(value))
        if not match:
            continue
        year = int(match.group(0))
        if 1800 <= year <= datetime.now().year:
            return year
    return None


def _extract_elevator(extratags: dict[str, Any]) -> bool | None:
    value = extratags.get("building:elevator") or extratags.get("elevator")
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "1"}:
        return True
    if normalized in {"no", "false", "0"}:
        return False
    return None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

