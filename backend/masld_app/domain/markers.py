"""Blueprint marker arithmetic; no staging or diagnosis."""

from __future__ import annotations

import math
from typing import Any


def marker_summary(data: dict[str, Any]) -> dict[str, Any]:
    """Show marker observations against blueprint ranges; do not diagnose or stage."""
    out: dict[str, Any] = {
        "clinical_stage": None,
        "criteria_reference": "user-supplied blueprint only; unvalidated",
        "observations": [],
        "criterion_matches": [],
    }
    if "height_m" in data and "weight_kg" in data:
        bmi = data["weight_kg"] / data["height_m"] ** 2
        out["bmi_kg_m2"] = round(bmi, 2)
        out["indian_bmi_band_from_blueprint"] = (
            "normal (<23)"
            if bmi < 23
            else "overweight (23–24.9)"
            if bmi < 25
            else "obese (>=25)"
        )
        if bmi < 23 and data.get("cap_db_m", 0) >= 275:
            out["observations"].append(
                "Lean phenotype flag: BMI <23 and CAP >=275; this is not a MASLD diagnosis."
            )
    cap = data.get("cap_db_m")
    lsm = data.get("lsm_kpa")
    if cap is not None:
        for label, threshold in (
            ("CAP flag >=275", 275),
            ("CAP flag >=319", 319),
            ("CAP flag >=337", 337),
        ):
            out["criterion_matches"].append(
                {"criterion": label, "observed": cap >= threshold}
            )
    if lsm is not None:
        for label, low, high in (
            ("LSM range flag <7", 0, 7),
            ("LSM range flag 5.5–7.5", 5.5, 7.5),
            ("LSM range flag 7–12", 7, 12),
            ("LSM range flag >12.5", 12.5, math.inf),
        ):
            out["criterion_matches"].append(
                {"criterion": label, "observed": low <= lsm < high}
            )
        out["observations"].append(
            "LSM may overlap across blueprint bands and is not a fibrosis-stage diagnosis."
        )
    if all(k in data for k in ("age_years", "ast_u_l", "alt_u_l", "platelets_10e9_l")):
        if data["alt_u_l"] == 0:
            out["observations"].append("FIB-4 not calculated because ALT is zero.")
        else:
            out["fib4_arithmetic_only"] = round(
                data["age_years"]
                * data["ast_u_l"]
                / (data["platelets_10e9_l"] * math.sqrt(data["alt_u_l"])),
                3,
            )
            out["observations"].append(
                "FIB-4 arithmetic only; interpretation requires a validated clinical pathway."
            )
    if "ast_u_l" in data and "alt_u_l" in data and data["alt_u_l"] > 0:
        out["ast_alt_ratio_arithmetic_only"] = round(
            data["ast_u_l"] / data["alt_u_l"], 3
        )
    if "bia_phase_angle_deg" in data:
        out["criterion_matches"].append(
            {
                "criterion": "BIA phase angle <5.2 (blueprint)",
                "observed": data["bia_phase_angle_deg"] < 5.2,
            }
        )
    if "platelets_10e9_l" in data:
        out["criterion_matches"].append(
            {
                "criterion": "platelets <150 (blueprint)",
                "observed": data["platelets_10e9_l"] < 150,
            }
        )
    return out
