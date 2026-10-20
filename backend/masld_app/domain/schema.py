"""Input fields, bounds, and request validation."""

from __future__ import annotations

import math
from typing import Any

NUMERIC_RANGES = {
    "age_years": (18, 120),
    "height_m": (1.0, 2.5),
    "weight_kg": (20, 400),
    "alt_u_l": (0, 10000),
    "ast_u_l": (0, 10000),
    "platelets_10e9_l": (1, 2000),
    "cap_db_m": (100, 1000),
    "lsm_kpa": (0, 200),
    "bia_phase_angle_deg": (0, 20),
    "fasting_glucose_mmol_l": (0, 100),
    "hscrp_mg_l": (0, 1000),
    "ferritin_ug_l": (0, 100000),
}
GENOTYPE_OPTIONS = {
    "pnpla3_genotype": {"CC", "CG", "GG"},
    "tm6sf2_genotype": {"CC", "CT", "TT"},
}
PERTURBATIONS = {
    "reduce_uptake",
    "reduce_dnl",
    "increase_oxidation",
    "increase_matrix_turnover",
}
ALLOWED = (
    set(NUMERIC_RANGES) | set(GENOTYPE_OPTIONS) | {"genomic_consent"} | PERTURBATIONS
)


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise TypeError("Input must be a JSON object.")
    unknown = set(data) - ALLOWED
    if unknown:
        raise ValueError("Unsupported field(s): " + ", ".join(sorted(unknown)))
    clean: dict[str, Any] = {}
    for key, value in data.items():
        if key in NUMERIC_RANGES:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number.")
            value = float(value)
            low, high = NUMERIC_RANGES[key]
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{key} must be finite and between {low} and {high}.")
        elif key == "genomic_consent" or key in PERTURBATIONS:
            if not isinstance(value, bool):
                raise ValueError(f"{key} must be true or false.")
        elif key in GENOTYPE_OPTIONS and value not in GENOTYPE_OPTIONS[key]:
            raise ValueError(f"{key} must be one of {sorted(GENOTYPE_OPTIONS[key])}.")
        clean[key] = value
    genotype_keys = set(GENOTYPE_OPTIONS) & set(clean)
    if genotype_keys and clean.get("genomic_consent") is not True:
        raise ValueError(
            "Genotype fields require genomic_consent: true; omit genotype data otherwise."
        )
    if clean.get("genomic_consent") is True and not genotype_keys:
        raise ValueError("genomic_consent was set but no genotype field was supplied.")
    return clean
