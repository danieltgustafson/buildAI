from __future__ import annotations

from datetime import datetime
from enum import Enum
import re

from pydantic import BaseModel, Field, model_validator


class BuildingType(str, Enum):
    office = "office"
    multifamily = "multifamily"
    single_family = "single_family"
    industrial = "industrial"
    mixed_use = "mixed_use"


class ResearchRequest(BaseModel):
    address: str | None = Field(
        default=None,
        description="Single address to research. If omitted, zip_code mode is used.",
    )
    zip_code: str | None = Field(
        default=None,
        description="Zip code for discovery mode (find likely addresses first).",
    )
    building_type: BuildingType | None = Field(
        default=None,
        description="Used for zip-code discovery and baseline assumptions.",
    )
    max_candidate_addresses: int = Field(default=5, ge=1, le=20)
    year_built: int | None = Field(default=None, ge=1800, le=datetime.now().year)
    system_install_years: dict[str, int] = Field(
        default_factory=dict,
        description=(
            "Optional known install/replacement years keyed by component name "
            "(e.g. roof, windows, hvac, elevators)."
        ),
    )

    @model_validator(mode="after")
    def validate_search_mode(self):
        if self.address and not self.zip_code:
            normalized_address = self.address.strip()
            if re.fullmatch(r"\d{5}(?:-\d{4})?", normalized_address):
                self.zip_code = normalized_address
                self.address = None

        if not self.address and not self.zip_code:
            raise ValueError(
                "Provide either 'address' (e.g., '123 Main St, Austin, TX 78701') or 'zip_code' (e.g., '78701')."
            )
        return self


class ComponentAssessment(BaseModel):
    component: str
    age_years: int | None = None
    source: str
    replacement_likelihood_next_2y: str
    confidence: float = Field(ge=0, le=1)


class BuildingAssessment(BaseModel):
    address: str
    components: list[ComponentAssessment]


class ResearchResponse(BaseModel):
    mode: str
    candidate_addresses: list[str]
    buildings: list[BuildingAssessment]
