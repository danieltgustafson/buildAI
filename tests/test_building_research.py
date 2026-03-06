"""Tests for building systems research endpoint."""

from app.services import building_research


def test_research_by_address_uses_multi_source_agent(client, monkeypatch):
    def _fake_search(_params):
        return [
            {
                "display_name": "123 Main St, Austin, TX",
                "lat": "30.2672",
                "lon": "-97.7431",
                "extratags": {"start_date": "1998", "building:elevator": "yes"},
            }
        ]

    monkeypatch.setattr(building_research, "_nominatim_search", _fake_search)
    monkeypatch.setattr(
        building_research,
        "_open_meteo_climate_summary",
        lambda _lat, _lon: building_research.ClimateSummary(hot_days=110, freeze_days=2, heavy_precip_days=15),
    )
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(
                component="roof",
                age_years=13,
                source="OpenAI agent synthesis from permits",
                replacement_likelihood_next_2y="medium",
                confidence=0.8,
            ),
            building_research.ComponentAssessment(
                component="windows",
                age_years=20,
                source="OpenAI agent synthesis from assessor data",
                replacement_likelihood_next_2y="low",
                confidence=0.76,
            ),
            building_research.ComponentAssessment(
                component="hvac",
                age_years=9,
                source="OpenAI agent synthesis from listing history",
                replacement_likelihood_next_2y="low",
                confidence=0.75,
            ),
            building_research.ComponentAssessment(
                component="elevators",
                age_years=18,
                source="OpenAI agent synthesis from records",
                replacement_likelihood_next_2y="medium",
                confidence=0.72,
            ),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={
            "address": "123 Main St, Austin, TX",
            "building_type": "office",
            "system_install_years": {"roof": 2012, "hvac": 2015},
        },
    )
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["mode"] == "address"
    assert payload["candidate_addresses"] == ["123 Main St, Austin, TX"]

    components = {c["component"]: c for c in payload["buildings"][0]["components"]}
    assert components["windows"]["source"].startswith("OpenAI agent synthesis")
    assert components["roof"]["replacement_likelihood_next_2y"] == "medium"


def test_research_can_use_openai_agent_synthesis(client, monkeypatch):
    def _fake_search(_params):
        return [
            {
                "display_name": "500 Example Ave, Denver, CO",
                "lat": "39.7392",
                "lon": "-104.9903",
                "extratags": {"start_date": "2001"},
            }
        ]

    monkeypatch.setattr(building_research, "_nominatim_search", _fake_search)
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(
                component="roof",
                age_years=12,
                source="OpenAI agent synthesis from permit snippets",
                replacement_likelihood_next_2y="medium",
                confidence=0.82,
            ),
            building_research.ComponentAssessment(
                component="windows",
                age_years=20,
                source="OpenAI agent synthesis from assessor + listing text",
                replacement_likelihood_next_2y="medium",
                confidence=0.77,
            ),
            building_research.ComponentAssessment(
                component="hvac",
                age_years=16,
                source="OpenAI agent synthesis from service records",
                replacement_likelihood_next_2y="high",
                confidence=0.8,
            ),
            building_research.ComponentAssessment(
                component="elevators",
                age_years=18,
                source="OpenAI agent synthesis from inspection records",
                replacement_likelihood_next_2y="medium",
                confidence=0.75,
            ),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={"address": "500 Example Ave, Denver, CO", "building_type": "office"},
    )
    assert resp.status_code == 200

    comps = {c["component"]: c for c in resp.json()["buildings"][0]["components"]}
    assert comps["roof"]["source"].startswith("OpenAI agent synthesis")
    assert comps["hvac"]["replacement_likelihood_next_2y"] == "high"


def test_research_by_zip_discovery_mode_hits_search(client, monkeypatch):
    def _fake_search(_params):
        return [
            {
                "display_name": "Tower A, 78701, Austin, TX",
                "lat": "30.1",
                "lon": "-97.7",
                "extratags": {"start_date": "2005"},
            },
            {
                "display_name": "Tower B, 78701, Austin, TX",
                "lat": "30.2",
                "lon": "-97.8",
                "extratags": {"start_date": "2010", "building:elevator": "no"},
            },
        ]

    monkeypatch.setattr(building_research, "_nominatim_search", _fake_search)
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(
                component="roof",
                age_years=13,
                source="OpenAI agent synthesis from permits",
                replacement_likelihood_next_2y="medium",
                confidence=0.8,
            ),
            building_research.ComponentAssessment(
                component="windows",
                age_years=20,
                source="OpenAI agent synthesis from assessor data",
                replacement_likelihood_next_2y="low",
                confidence=0.76,
            ),
            building_research.ComponentAssessment(
                component="hvac",
                age_years=9,
                source="OpenAI agent synthesis from listing history",
                replacement_likelihood_next_2y="low",
                confidence=0.75,
            ),
            building_research.ComponentAssessment(
                component="elevators",
                age_years=18,
                source="OpenAI agent synthesis from records",
                replacement_likelihood_next_2y="medium",
                confidence=0.72,
            ),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={
            "zip_code": "78701",
            "building_type": "office",
            "max_candidate_addresses": 2,
        },
    )
    assert resp.status_code == 200
    payload = resp.json()

    assert payload["mode"] == "zip_discovery"
    assert len(payload["candidate_addresses"]) == 2
    assert len(payload["buildings"]) == 2


def test_research_requires_address_or_zip(client):
    resp = client.post("/research/building-systems", json={})
    assert resp.status_code == 422


def test_research_returns_503_when_openai_agent_unavailable(client, monkeypatch):
    monkeypatch.setattr(building_research, "_nominatim_search", lambda _params: [])
    monkeypatch.setattr(building_research, "_openai_agent_component_assessment", lambda _r, _p: None)

    resp = client.post(
        "/research/building-systems",
        json={"address": "1 Failing St, Austin, TX", "building_type": "office"},
    )
    assert resp.status_code == 503
    assert "OpenAI agent response" in resp.json()["detail"]


def test_research_address_uses_fallback_queries_when_first_lookup_misses(client, monkeypatch):
    seen_queries: list[str] = []

    def _fake_search(params):
        seen_queries.append(str(params.get("q") or params.get("postalcode") or ""))
        if params.get("q") == "456 Oak St Apt 3, Austin, TX":
            return []
        if params.get("q") == "456 Oak St, Austin, TX":
            return [
                {
                    "display_name": "456 Oak St, Austin, TX 78701",
                    "lat": "30.2672",
                    "lon": "-97.7431",
                    "extratags": {"start_date": "2003"},
                }
            ]
        return []

    monkeypatch.setattr(building_research, "_nominatim_search", _fake_search)
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(
                component="roof", age_years=10, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="windows", age_years=10, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="hvac", age_years=10, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="elevators", age_years=10, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={"address": "456 Oak St Apt 3, Austin, TX", "building_type": "office"},
    )
    assert resp.status_code == 200
    assert seen_queries[:2] == ["456 Oak St Apt 3, Austin, TX", "456 Oak St, Austin, TX"]


def test_research_zip_uses_broad_fallback_queries(client, monkeypatch):
    calls: list[dict] = []

    def _fake_search(params):
        calls.append(params)
        if params.get("q") == "office in 78701":
            return []
        if params.get("q") == "78701, USA":
            return [
                {
                    "display_name": "ZIP candidate A",
                    "lat": "30.10",
                    "lon": "-97.70",
                    "extratags": {"start_date": "2001"},
                }
            ]
        return []

    monkeypatch.setattr(building_research, "_nominatim_search", _fake_search)
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(
                component="roof", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="windows", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="hvac", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
            building_research.ComponentAssessment(
                component="elevators", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8
            ),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={"zip_code": "78701", "building_type": "office", "max_candidate_addresses": 2},
    )
    assert resp.status_code == 200
    assert any(c.get("q") == "office in 78701" for c in calls)
    assert any(c.get("q") == "78701, USA" for c in calls)
    assert resp.json()["candidate_addresses"] == ["ZIP candidate A"]


def test_research_address_falls_back_to_census_geocoder(client, monkeypatch):
    monkeypatch.setattr(building_research, "_nominatim_search", lambda _params: [])
    monkeypatch.setattr(
        building_research,
        "_census_geocode_single_line",
        lambda _q: {"address": "100 Main St, Austin, TX", "lat": 30.27, "lon": -97.74},
    )
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(component="roof", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="windows", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="hvac", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="elevators", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={"address": "100 Main St, Austin, TX", "building_type": "office"},
    )
    assert resp.status_code == 200
    assert resp.json()["candidate_addresses"][0] == "100 Main St, Austin, TX"


def test_research_zip_falls_back_to_zippopotam_centroid(client, monkeypatch):
    monkeypatch.setattr(building_research, "_nominatim_search", lambda _params: [])
    monkeypatch.setattr(
        building_research,
        "_zippopotam_zip_centroid",
        lambda _zip: {"address": "ZIP 78701 centroid (Austin, TX)", "lat": 30.271, "lon": -97.742},
    )
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(component="roof", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="windows", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="hvac", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="elevators", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
        ],
    )

    resp = client.post(
        "/research/building-systems",
        json={"zip_code": "78701", "building_type": "office", "max_candidate_addresses": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["candidate_addresses"] == ["ZIP 78701 centroid (Austin, TX)"]


def test_research_accepts_zip_in_address_field(client, monkeypatch):
    monkeypatch.setattr(building_research, "_nominatim_search", lambda _params: [])
    monkeypatch.setattr(
        building_research,
        "_zippopotam_zip_centroid",
        lambda _zip: {"address": "ZIP 10001 centroid (New York, NY)", "lat": 40.75, "lon": -73.99},
    )
    monkeypatch.setattr(building_research, "_open_meteo_climate_summary", lambda _lat, _lon: None)
    monkeypatch.setattr(
        building_research,
        "_openai_agent_component_assessment",
        lambda _r, _p: [
            building_research.ComponentAssessment(component="roof", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="windows", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="hvac", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
            building_research.ComponentAssessment(component="elevators", age_years=8, source="OpenAI", replacement_likelihood_next_2y="low", confidence=0.8),
        ],
    )

    resp = client.post("/research/building-systems", json={"address": "10001", "building_type": "office"})
    assert resp.status_code == 200
    assert resp.json()["mode"] == "zip_discovery"
