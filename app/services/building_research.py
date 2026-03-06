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
CENSUS_GEOCODER_BASE = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"
ZIPPOPOTAM_BASE = "https://api.zippopotam.us"
MAPSCO_SEARCH_BASE = "https://geocode.maps.co/search"


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
        queries = _address_query_variants(address)
        for q in queries:
            records = _nominatim_search(
                {
                    "q": q,
                    "format": "jsonv2",
                    "addressdetails": 1,
                    "extratags": 1,
                    "namedetails": 0,
                    "limit": 1,
                    "countrycodes": "us",
                }
            )
            if records:
                item = records[0]
                extratags = item.get("extratags") or {}
                parsed_address = item.get("display_name") or address
                return PublicRecordResult(
                    address=parsed_address,
                    lat=_to_float(item.get("lat")),
                    lon=_to_float(item.get("lon")),
                    year_built=_extract_year(extratags),
                    elevator_present=_extract_elevator(extratags),
                    sources=[f"OpenStreetMap Nominatim geocoder + OSM tags (query: {q})"],
                )

        for q in queries:
            census_match = _census_geocode_single_line(q)
            if census_match:
                return PublicRecordResult(
                    address=census_match["address"],
                    lat=census_match["lat"],
                    lon=census_match["lon"],
                    year_built=None,
                    elevator_present=None,
                    sources=[f"US Census Geocoder (query: {q})"],
                )

        for q in queries:
            mapsco = _mapsco_search(q, limit=1)
            if mapsco:
                item = mapsco[0]
                return PublicRecordResult(
                    address=item["address"],
                    lat=item["lat"],
                    lon=item["lon"],
                    year_built=None,
                    elevator_present=None,
                    sources=[f"Maps.co geocoder fallback (query: {q})"],
                )

        return PublicRecordResult(
            address=address,
            lat=None,
            lon=None,
            year_built=None,
            elevator_present=None,
            sources=["No match from Nominatim/Census/Maps.co for provided address"],
        )

    def _search_zip_candidates(self, payload: ResearchRequest) -> list[PublicRecordResult]:
        building_hint = payload.building_type.value.replace("_", " ") if payload.building_type else "building"
        zip_code = _normalize_zip_code(payload.zip_code)
        candidate_params = [
            {
                "q": f"{building_hint} in {zip_code}",
                "countrycodes": "us",
            },
            {
                "q": f"{zip_code}, USA",
                "countrycodes": "us",
            },
            {
                "postalcode": zip_code,
                "country": "United States",
            },
        ]

        seen: set[tuple[str, str, str]] = set()
        results: list[PublicRecordResult] = []
        for params in candidate_params:
            search_params = {
                **params,
                "format": "jsonv2",
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 0,
                "limit": payload.max_candidate_addresses,
            }
            records = _nominatim_search(search_params)
            for item in records:
                key = (
                    str(item.get("display_name") or "").strip().lower(),
                    str(item.get("lat") or ""),
                    str(item.get("lon") or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                query_desc = params.get("q") or f"postalcode={zip_code}"
                results.append(
                    PublicRecordResult(
                        address=item.get("display_name", f"ZIP {zip_code} candidate"),
                        lat=_to_float(item.get("lat")),
                        lon=_to_float(item.get("lon")),
                        year_built=_extract_year(item.get("extratags") or {}),
                        elevator_present=_extract_elevator(item.get("extratags") or {}),
                        sources=[f"OpenStreetMap Nominatim geocoder + OSM tags (query: {query_desc})"],
                    )
                )
                if len(results) >= payload.max_candidate_addresses:
                    return results

        if not results:
            zip_place = _zippopotam_zip_centroid(zip_code)
            if zip_place:
                place_label = zip_place["address"].replace(f"ZIP {zip_code} centroid", "").strip(" ()")
                mapsco_queries = [
                    f"{building_hint} near {place_label} {zip_code}",
                    f"{zip_code} {building_hint}",
                    f"{zip_code} USA",
                ]
                for q in mapsco_queries:
                    for item in _mapsco_search(q, limit=payload.max_candidate_addresses):
                        key = (item["address"].strip().lower(), str(item["lat"]), str(item["lon"]))
                        if key in seen:
                            continue
                        seen.add(key)
                        results.append(
                            PublicRecordResult(
                                address=item["address"],
                                lat=item["lat"],
                                lon=item["lon"],
                                year_built=None,
                                elevator_present=None,
                                sources=[f"Maps.co geocoder fallback (query: {q})"],
                            )
                        )
                        if len(results) >= payload.max_candidate_addresses:
                            return results

                if results:
                    return results

                return [
                    PublicRecordResult(
                        address=zip_place["address"],
                        lat=zip_place["lat"],
                        lon=zip_place["lon"],
                        year_built=None,
                        elevator_present=None,
                        sources=["Zippopotam.us ZIP centroid fallback"],
                    )
                ]

            return [
                PublicRecordResult(
                    address=f"ZIP {zip_code} (no candidates found)",
                    lat=None,
                    lon=None,
                    year_built=None,
                    elevator_present=None,
                    sources=["No candidates from Nominatim, Maps.co, or ZIP centroid fallback"],
                )
            ]
        return results


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
        "run multiple search queries and cross-check diverse sources (public records, listings, local assessor/permit pages, "
        "manufacturer lifecycle guidance, and climate context) before estimating roof/windows/hvac/elevators. "
        "When tools are available, actively use web search to broaden coverage instead of relying on one source. "
        "Return strict JSON with this shape: "
        '{"components": [{"component": "roof", "age_years": 10 or null, "source": "...", '
        '"replacement_likelihood_next_2y": "low|medium|high|unknown", "confidence": 0.0-1.0}]}. '
        "Each source string should name concrete evidence. Do not include markdown."
    )

    payload_json: dict[str, Any] = {
        "model": settings.openai_research_model,
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": instructions}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(evidence)}]},
        ],
        "temperature": 0.2,
    }
    if settings.openai_research_use_web_search:
        payload_json["tools"] = [{"type": "web_search_preview"}]

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


def _address_query_variants(address: str) -> list[str]:
    base = address.strip()
    if not base:
        return []

    variants = [base]
    without_unit = re.sub(
        r"(?:,?\s*(?:apt|apartment|unit|suite|ste|#)\s*[a-z0-9-]+)",
        "",
        base,
        flags=re.IGNORECASE,
    )
    without_unit = re.sub(r"\s+", " ", without_unit).strip(" ,")
    if without_unit and without_unit != base:
        variants.append(without_unit)

    if "usa" not in base.lower():
        variants.append(f"{without_unit or base}, USA")

    deduped: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = item.strip().lower()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item.strip())
    return deduped


def _normalize_zip_code(zip_code: str | None) -> str:
    if not zip_code:
        return ""
    digits = "".join(ch for ch in zip_code if ch.isdigit())
    if len(digits) >= 5:
        return digits[:5]
    return zip_code.strip()


def _census_geocode_single_line(address: str) -> dict[str, Any] | None:
    try:
        with httpx.Client(timeout=8.0, headers=_research_headers()) as client:
            response = client.get(
                CENSUS_GEOCODER_BASE,
                params={
                    "address": address,
                    "benchmark": "Public_AR_Current",
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    matches = payload.get("result", {}).get("addressMatches", []) if isinstance(payload, dict) else []
    if not isinstance(matches, list) or not matches:
        return None

    first = matches[0] if isinstance(matches[0], dict) else None
    if not first:
        return None
    coords = first.get("coordinates") or {}
    lat = _to_float(coords.get("y"))
    lon = _to_float(coords.get("x"))
    if lat is None or lon is None:
        return None
    return {
        "address": str(first.get("matchedAddress") or address),
        "lat": lat,
        "lon": lon,
    }


def _zippopotam_zip_centroid(zip_code: str) -> dict[str, Any] | None:
    if not zip_code:
        return None
    try:
        with httpx.Client(timeout=8.0, headers=_research_headers()) as client:
            response = client.get(f"{ZIPPOPOTAM_BASE}/us/{zip_code}")
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return None

    places = payload.get("places") if isinstance(payload, dict) else None
    if not isinstance(places, list) or not places:
        return None
    first = places[0] if isinstance(places[0], dict) else None
    if not first:
        return None

    lat = _to_float(first.get("latitude"))
    lon = _to_float(first.get("longitude"))
    if lat is None or lon is None:
        return None

    place_name = str(first.get("place name") or "Unknown Place")
    state = str(first.get("state abbreviation") or first.get("state") or "")
    formatted = f"ZIP {zip_code} centroid ({place_name}{', ' + state if state else ''})"
    return {"address": formatted, "lat": lat, "lon": lon}


def _mapsco_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    if not query.strip():
        return []
    params = {
        "q": query,
        "limit": max(1, min(limit, 20)),
    }
    try:
        with httpx.Client(timeout=8.0, headers=_research_headers()) as client:
            response = client.get(MAPSCO_SEARCH_BASE, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    results: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        lat = _to_float(item.get("lat"))
        lon = _to_float(item.get("lon"))
        if lat is None or lon is None:
            continue
        address = str(item.get("display_name") or query)
        results.append({"address": address, "lat": lat, "lon": lon})
    return results


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

