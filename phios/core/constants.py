"""Core mathematical and experimental metadata constants for PhiOS.

These values are used for *operator-side interpretation*. They are not claims of
empirical finality.
"""

from __future__ import annotations

from math import sqrt

PHI = (1.0 + sqrt(5.0)) / 2.0
"""Golden ratio φ = (1 + sqrt(5)) / 2."""

C_STAR_THEORETICAL = PHI / 2.0
"""Theoretical attractor C* = φ/2 = (1 + sqrt(5))/4 = cos(36°) = sin(54°)."""

C_STAR_THEORETICAL_TRIG_EQUIV = "cos(36°) = sin(54°)"
"""Documentational symbolic equivalence for C* (not a separate measured constant)."""

BIO_VACUUM_TARGET = 0.81055
BIO_VACUUM_BAND_LOW = 0.807
BIO_VACUUM_BAND_HIGH = 0.813
BIO_VACUUM_STATUS = "experimental"
HUNTER_C_STATUS = "unconfirmed"
BIO_MODEL_PROVENANCE = "proxy-calibrated, not empirically confirmed"
