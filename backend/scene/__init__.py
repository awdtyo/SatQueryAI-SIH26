"""Selected-scene analysis support — real asset resolution for the active scene.

Selected Satellite Image Query Mode: the user picks a live satellite scene
("Query This Image") and subsequent NL queries are analyzed against that scene's
real STAC band assets rather than an uploaded demo image.
"""

from __future__ import annotations

from .raster import resolve_scene_rgb

__all__ = ["resolve_scene_rgb"]
