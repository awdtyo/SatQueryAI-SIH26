"""
Deterministic scene ranking — heuristic, not scientific quality metric.

Score formula (documented for tests):
  coverage_norm = coverage / 100               in 0..1
  cloud_score   = 1 - cloud_cover/100          in 0..1 (lower cloud = higher)
  temporal_score = freshness within window:
     For ranking stability without “now” drift in tests, temporal relevance
     is scored as 0.5 + 0.5 * positional weight: older scenes in window slightly
     penalized? Actually we score by proximity to end_date (more recent preferred)
     normalized: (datetime - start) / (end - start)  in 0..1, midpoint 0.5.
     If datetime missing, 0.5 fallback.
  sensor_score = 1.0 for sentinel-2/l2a, 0.9 for l1c, else 0.8

Then:
  selection_score = 0.45*coverage_norm + 0.35*cloud_score + 0.15*temporal_score + 0.05*sensor_score
  clamped 0..1

Weights: coverage dominates, cloud second, temporal tie-breaker, sensor small.
This is a SatQuery scene-selection heuristic (see README).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from .models import SatelliteScene


def _parse_scene_dt(s: SatelliteScene) -> datetime | None:
    if s.datetime is None:
        return None
    dt = s.datetime
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def compute_selection_score(
    scene: SatelliteScene,
    start_date: date | None = None,
    end_date: date | None = None,
) -> float:
    coverage = float(scene.coverage or 0.0)
    coverage_norm = max(0.0, min(1.0, coverage / 100.0))

    cloud = scene.cloud_cover
    if cloud is None:
        cloud_score = 0.5
    else:
        cloud_score = max(0.0, min(1.0, 1.0 - float(cloud) / 100.0))

    # temporal
    temporal_score = 0.5
    if start_date and end_date and scene.datetime:
        try:
            dt = _parse_scene_dt(scene)
            if dt is not None:
                start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
                end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
                total = (end_dt - start_dt).total_seconds()
                if total > 0:
                    pos = (dt - start_dt).total_seconds() / total
                    pos = max(0.0, min(1.0, pos))
                    # prefer more recent (higher pos) -> higher score, but center 0.5
                    # map pos 0..1 -> 0.5..1.0 to avoid penalizing older too heavily
                    temporal_score = 0.5 + 0.5 * pos
        except Exception:
            temporal_score = 0.5

    # sensor/product suitability
    coll = (scene.collection or "").lower()
    if "l2a" in coll:
        sensor_score = 1.0
    elif "l1c" in coll:
        sensor_score = 0.9
    else:
        sensor_score = 0.8
    # If collection is sentinel-2-l2a, bonus already; sentinel-1 lower but still handled
    if "sentinel-1" in coll:
        sensor_score = 0.85

    score = 0.45 * coverage_norm + 0.35 * cloud_score + 0.15 * temporal_score + 0.05 * sensor_score
    return max(0.0, min(1.0, float(round(score, 4))))


def rank_scenes(
    scenes: list[SatelliteScene],
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[SatelliteScene]:
    """Mutate selection_score in place and return sorted descending."""
    for s in scenes:
        s.selection_score = compute_selection_score(s, start_date, end_date)
    # sort stable: score desc, coverage desc, cloud asc, datetime desc
    def _key(s: SatelliteScene):
        dt = s.datetime.timestamp() if s.datetime else 0
        cloud = s.cloud_cover if s.cloud_cover is not None else 50
        return (-(s.selection_score or 0), -(s.coverage or 0), cloud, -dt)

    return sorted(scenes, key=_key)
