"""Stage, compositor, director, and particle systems for Eager."""

from __future__ import annotations

from eager.stage.compositor import StageCompositor
from eager.stage.director import StageDirector
from eager.stage.fonts import get_default_font_data, register_pyglet_default_font
from eager.stage.particles import ParticleBatch, ParticleEmitter, ParticleStamp, ParticleStampLUT
from eager.stage.stage import ElementState, Layer, Stage, StageElement

__all__ = [
    "ElementState",
    "Layer",
    "ParticleBatch",
    "ParticleEmitter",
    "ParticleStamp",
    "ParticleStampLUT",
    "Stage",
    "StageCompositor",
    "StageDirector",
    "StageElement",
    "get_default_font_data",
    "register_pyglet_default_font",
]
