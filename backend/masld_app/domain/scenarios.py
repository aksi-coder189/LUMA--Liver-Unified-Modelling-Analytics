"""Illustrative modifier and generic parameter-perturbation assumptions."""

from __future__ import annotations

from typing import Any

from .schema import GENOTYPE_OPTIONS


def genetic_modifier(data: dict[str, Any]) -> dict[str, Any]:
    present = set(GENOTYPE_OPTIONS) & set(data)
    if not present:
        return {"included": False, "reason": "No genotype input."}
    # Arbitrary coefficients are deliberately exposed as assumptions, not clinical GRI estimates.
    pnpla3_g = data.get("pnpla3_genotype", "CC").count("G")
    tm6sf2_t = data.get("tm6sf2_genotype", "CC").count("T")
    return {
        "included": True,
        "grI_toy_multiplier": round(1 + 0.15 * pnpla3_g + 0.10 * tm6sf2_t, 3),
        "assumptions": {"pnpla3_per_G_allele": 0.15, "tm6sf2_per_T_allele": 0.10},
        "warning": "Unvalidated synthetic coefficients; not a genetic risk estimate. Raw genotypes are not echoed or persisted.",
    }


def parameter_perturbations(data: dict[str, Any]) -> tuple[dict[str, float], list[str]]:
    """Apply explicitly synthetic coefficient perturbations, never treatment effects."""
    factors = {"uptake": 1.0, "dnl": 1.0, "beta_oxidation": 1.0, "mmp_degradation": 1.0}
    active = []
    assumptions = {
        "reduce_uptake": {"uptake": 0.90},
        "reduce_dnl": {"dnl": 0.90},
        "increase_oxidation": {"beta_oxidation": 1.10},
        "increase_matrix_turnover": {"mmp_degradation": 1.10},
    }
    for name, changes in assumptions.items():
        if data.get(name):
            active.append(name)
            for key, multiplier in changes.items():
                factors[key] *= multiplier
    return factors, active
