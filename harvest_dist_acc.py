"""Harvest DRIVING DISTANCE and ACCURACY separately — SG_OTT conflates them.

The question "does this course favour accuracy over distance" cannot be answered from SG_OTT,
which is one number for both. PGA Tour publishes them as separate stats (101 = driving distance,
102 = driving accuracy %), free, on the same orchestrator key.
"""
import pga_sg as S
S.SG_STATS = {"101": "DRIVE_DIST", "102": "DRIVE_ACC", "02420": "GIR", "159": "SCRAMBLE"}
S.harvest(years=(2023, 2024, 2025, 2026))
