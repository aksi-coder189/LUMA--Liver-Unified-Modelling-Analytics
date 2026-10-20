"""Deterministic synthetic equation data; no patient or external records."""

from __future__ import annotations

import random

FEATURES = [
    "intercept",
    "uptake",
    "dnl",
    "ffa",
    "tg",
    "beta_oxidation",
    "ros",
    "ecm",
    "hsc_signal",
    "mmp_signal",
]
TARGETS = ["d_ffa", "d_tg", "d_ros", "d_ecm"]


def build_dataset(
    rows: int = 8000, seed: int = 20261019
) -> list[tuple[list[float], list[float]]]:
    if not isinstance(rows, int) or rows < 100:
        raise ValueError("rows must be an integer of at least 100.")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise TypeError("seed must be an integer.")
    rng = random.Random(seed)
    dataset = []
    for _ in range(rows):
        uptake = rng.uniform(0.005, 0.09)
        dnl = rng.uniform(0.005, 0.075)
        ffa, tg = rng.uniform(0.02, 1.5), rng.uniform(0.02, 1.5)
        # Extend ROS coverage above the expected toy-ODE trajectory so the
        # internal range guard does not flag the ordinary sample scenario.
        ros, ecm = rng.uniform(0.005, 1.5), rng.uniform(0.01, 1.0)
        oxygen = rng.uniform(0.35, 1.0)
        uptake *= rng.uniform(0.85, 1.1)
        beta = 0.055 * rng.uniform(0.9, 1.2) * oxygen * ffa / (0.3 + ffa)
        hsc, mmp = ros / (0.2 + ros), ecm * rng.uniform(0.9, 1.15)
        features = [1.0, uptake, dnl, ffa, tg, beta, ros, ecm, hsc, mmp]
        targets = [
            uptake + dnl - 0.06 * ffa - beta,
            0.06 * ffa - 0.05 * tg,
            0.09 * ffa - 0.035 * ros,
            0.025 * hsc - 0.008 * mmp,
        ]
        dataset.append((features, [y + rng.gauss(0, 0.00002) for y in targets]))
    rng.shuffle(dataset)
    return dataset
