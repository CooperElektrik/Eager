"""Dedicated particle layer, flat-array emitter simulation, and discrete pre-baked LUT stamps."""

from __future__ import annotations

import array
import math
import random
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from eager_graphics.layout import ViewportTransform

__all__ = [
    "ParticleBatch",
    "ParticleEmitter",
    "ParticleStamp",
    "ParticleStampLUT",
]


@dataclass(slots=True)
class ParticleStamp:
    """Pre-baked discrete particle stamp ready for zero-resample pasting."""

    color: Any  # PIL.Image.Image (RGB)
    mask: Any  # PIL.Image.Image (L)
    width: int
    height: int
    off_x: float = 0.0
    off_y: float = 0.0


class ParticleStampLUT:
    """Discrete 3D lookup table of pre-baked (scale, angle, opacity) stamps.

    Eliminates all runtime .rotate(), .resize(), and alpha multiplications.
    Stamps are stored in a nested structure:
      table[scale_idx][angle_idx][alpha_idx] -> ParticleStamp
    """

    NUM_ANGLES = 16
    ANGLES: tuple[float, ...] = tuple(i * (360.0 / 16) for i in range(16))
    SCALES: tuple[float, ...] = (0.5, 0.75, 1.0, 1.25)
    ALPHAS: tuple[int, ...] = (32, 64, 96, 128, 160, 192, 224, 255)

    def __init__(
        self,
        table: list[list[list[ParticleStamp]]],
        approx_bytes: int,
    ) -> None:
        self._table = table
        self.approx_bytes = approx_bytes

    @classmethod
    def quantize_angle(cls, angle_deg: float) -> int:
        """Quantize an angle in degrees into an index in 0..15."""
        norm = angle_deg % 360.0
        # 360 / 16 = 22.5 deg per bin
        return round(norm / 22.5) % 16

    @classmethod
    def quantize_scale(cls, scale: float) -> int:
        """Quantize scale factor into an index in 0..3."""
        if scale <= 0.625:
            return 0
        if scale <= 0.875:
            return 1
        if scale <= 1.125:
            return 2
        return 3

    @classmethod
    def quantize_alpha(cls, alpha_byte: int) -> int:
        """Quantize an alpha byte (0..255) into an index in 0..7."""
        if alpha_byte <= 48:
            return 0
        if alpha_byte <= 80:
            return 1
        if alpha_byte <= 112:
            return 2
        if alpha_byte <= 144:
            return 3
        if alpha_byte <= 176:
            return 4
        if alpha_byte <= 208:
            return 5
        if alpha_byte <= 240:
            return 6
        return 7

    def get_stamp(self, scale_idx: int, angle_idx: int, alpha_idx: int) -> ParticleStamp:
        """O(1) pointer-dereference lookup of pre-baked stamp."""
        return self._table[scale_idx][angle_idx][alpha_idx]

    @classmethod
    def from_image(cls, base_img: Any) -> ParticleStampLUT:
        """Pre-bake 512 discrete stamps from a base PIL Image."""
        from PIL import Image

        if base_img.mode != "RGBA":
            base_img = base_img.convert("RGBA")

        table: list[list[list[ParticleStamp]]] = []
        total_bytes = 0

        for s in cls.SCALES:
            angle_list: list[list[ParticleStamp]] = []
            scaled_w = max(2, round(base_img.width * s))
            scaled_h = max(2, round(base_img.height * s))
            scaled_img = base_img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

            for r in cls.ANGLES:
                alpha_list: list[ParticleStamp] = []
                if r == 0.0:
                    rot_img = scaled_img
                else:
                    rot_img = scaled_img.rotate(r, resample=Image.Resampling.BILINEAR, expand=True)

                r_ch, g_ch, b_ch, a_ch = rot_img.split()
                rgb_img = Image.merge("RGB", (r_ch, g_ch, b_ch))
                total_bytes += rgb_img.width * rgb_img.height * 3

                # Pre-bake 8 quantized alpha masks
                for a in cls.ALPHAS:
                    scale_f = a / 255.0
                    mask = a_ch.point(lambda p, f=scale_f: round(p * f))
                    total_bytes += mask.width * mask.height
                    stamp = ParticleStamp(
                        color=rgb_img,
                        mask=mask,
                        width=rgb_img.width,
                        height=rgb_img.height,
                        off_x=-(rgb_img.width / 2.0),
                        off_y=-(rgb_img.height / 2.0),
                    )
                    alpha_list.append(stamp)
                angle_list.append(alpha_list)
            table.append(angle_list)

        return cls(table, approx_bytes=total_bytes)

    @classmethod
    def from_shape(
        cls,
        shape: str = "circle",
        base_size: int = 16,
        color: tuple[int, int, int] = (255, 255, 255),
    ) -> ParticleStampLUT:
        """Generate procedural stamps for built-in shapes ('circle', 'petal', 'drop', 'spark')."""
        from PIL import Image, ImageDraw

        img = Image.new("RGBA", (base_size, base_size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        r, g, b = color

        if shape == "circle":
            draw.ellipse([1, 1, base_size - 2, base_size - 2], fill=(r, g, b, 255))
        elif shape == "petal":
            # Sakura petal: tapered elliptical curve
            draw.ellipse([base_size // 4, 1, 3 * base_size // 4, base_size - 2], fill=(r, g, b, 255))
            draw.polygon(
                [
                    (base_size // 2, 0),
                    (base_size - 2, base_size // 3),
                    (base_size // 2, base_size - 1),
                    (1, base_size // 3),
                ],
                fill=(r, g, b, 255),
            )
        elif shape == "drop":
            # Rain drop: narrow streak
            draw.line([base_size // 2, 0, base_size // 2, base_size - 1], fill=(r, g, b, 255), width=max(1, base_size // 6))
        elif shape == "spark":
            # Diamond ember / star
            mid = base_size // 2
            draw.polygon([(mid, 1), (base_size - 2, mid), (mid, base_size - 2), (1, mid)], fill=(r, g, b, 255))
        else:
            draw.rectangle([1, 1, base_size - 2, base_size - 2], fill=(r, g, b, 255))

        return cls.from_image(img)


@dataclass(slots=True)
class ParticleBatch:
    """Submitted batch of screen-projected particles ready for single-pass drawing."""

    emitter_id: str
    layer: str
    z_order: int
    lut: ParticleStampLUT
    particles: list[tuple[int, int, int, int, int]]  # (dest_x, dest_y, scale_idx, angle_idx, alpha_idx)


class ParticleEmitter:
    """Flat-array particle emitter simulating weather and expressive effects."""

    def __init__(
        self,
        emitter_id: str,
        lut: ParticleStampLUT,
        max_particles: int = 200,
        *,
        layer: str = "foreground",
        z_order: int = 200000,
        preset: str | None = None,
    ) -> None:
        self.emitter_id = emitter_id
        self.lut = lut
        self.max_particles = max_particles
        self.layer = layer
        self.z_order = z_order
        self.preset = preset

        # Contiguous flat arrays
        self.px = array.array("f", [0.0] * max_particles)
        self.py = array.array("f", [0.0] * max_particles)
        self.vx = array.array("f", [0.0] * max_particles)
        self.vy = array.array("f", [0.0] * max_particles)
        self.life = array.array("f", [0.0] * max_particles)
        self.max_life = array.array("f", [1.0] * max_particles)
        self.angle = array.array("f", [0.0] * max_particles)
        self.angular_vel = array.array("f", [0.0] * max_particles)
        self.angle_idx = array.array("B", [0] * max_particles)
        self.scale_idx = array.array("B", [2] * max_particles)
        self.alpha_idx = array.array("B", [7] * max_particles)
        self.wobble_freq = array.array("f", [0.0] * max_particles)
        self.wobble_phase = array.array("f", [0.0] * max_particles)
        self.alive = array.array("B", [0] * max_particles)

        # Initial seed
        self._init_particles()

    def _init_particles(self) -> None:
        """Seed all particles with initial randomized values."""
        for i in range(self.max_particles):
            self._reset_particle(i, initial=True)

    def _reset_particle(self, i: int, initial: bool = False) -> None:
        """Re-spawn particle i at top or random viewport location."""
        self.alive[i] = 1
        self.life[i] = 0.0

        if self.preset == "rain":
            self.max_life[i] = random.uniform(1.2, 2.0)
            self.px[i] = random.uniform(-100.0, 2020.0)
            self.py[i] = random.uniform(-100.0, 1080.0) if initial else random.uniform(-120.0, -20.0)
            self.vx[i] = random.uniform(-60.0, -30.0)
            self.vy[i] = random.uniform(800.0, 1200.0)
            self.angle[i] = 15.0
            self.angular_vel[i] = 0.0
            self.angle_idx[i] = ParticleStampLUT.quantize_angle(self.angle[i])
            self.scale_idx[i] = random.choice((1, 2))
            self.alpha_idx[i] = random.randint(4, 7)
            self.wobble_freq[i] = 0.0
            self.wobble_phase[i] = 0.0

        elif self.preset == "sakura":
            self.max_life[i] = random.uniform(8.0, 14.0)
            self.px[i] = random.uniform(-50.0, 1970.0)
            self.py[i] = random.uniform(0.0, 1080.0) if initial else random.uniform(-60.0, -10.0)
            self.vx[i] = random.uniform(-20.0, 40.0)
            self.vy[i] = random.uniform(50.0, 90.0)
            self.angle[i] = random.uniform(0.0, 360.0)
            self.angular_vel[i] = random.uniform(20.0, 60.0)
            self.angle_idx[i] = ParticleStampLUT.quantize_angle(self.angle[i])
            self.scale_idx[i] = random.randint(0, 3)
            self.alpha_idx[i] = random.randint(5, 7)
            self.wobble_freq[i] = random.uniform(1.0, 2.5)
            self.wobble_phase[i] = random.uniform(0.0, 6.28)

        elif self.preset == "embers":
            self.max_life[i] = random.uniform(2.0, 4.5)
            self.px[i] = random.uniform(0.0, 1920.0)
            self.py[i] = random.uniform(0.0, 1080.0) if initial else random.uniform(1080.0, 1120.0)
            self.vx[i] = random.uniform(-30.0, 30.0)
            self.vy[i] = random.uniform(-80.0, -140.0)
            self.angle[i] = random.uniform(0.0, 360.0)
            self.angular_vel[i] = random.uniform(-40.0, 40.0)
            self.angle_idx[i] = ParticleStampLUT.quantize_angle(self.angle[i])
            self.scale_idx[i] = random.randint(0, 2)
            self.alpha_idx[i] = random.randint(4, 7)
            self.wobble_freq[i] = random.uniform(2.0, 4.0)
            self.wobble_phase[i] = random.uniform(0.0, 6.28)

        else:
            # Default / Snow
            self.max_life[i] = random.uniform(6.0, 12.0)
            self.px[i] = random.uniform(-50.0, 1970.0)
            self.py[i] = random.uniform(0.0, 1080.0) if initial else random.uniform(-50.0, -10.0)
            self.vx[i] = random.uniform(-15.0, 15.0)
            self.vy[i] = random.uniform(60.0, 130.0)
            self.angle[i] = random.uniform(0.0, 360.0)
            self.angular_vel[i] = random.uniform(-30.0, 30.0)
            self.angle_idx[i] = ParticleStampLUT.quantize_angle(self.angle[i])
            self.scale_idx[i] = random.randint(0, 3)
            self.alpha_idx[i] = random.randint(4, 7)
            self.wobble_freq[i] = random.uniform(0.8, 1.8)
            self.wobble_phase[i] = random.uniform(0.0, 6.28)

    def update(
        self,
        dt: float,
        bounds: tuple[float, float, float, float] = (0.0, 0.0, 1920.0, 1080.0),
    ) -> None:
        """Advance all particles by dt in a tight flat-array loop."""
        min_x, min_y, max_x, max_y = bounds
        wrap_bottom = max_y + 40.0
        wrap_top = min_y - 40.0
        wrap_left = min_x - 40.0
        wrap_right = max_x + 40.0

        for i in range(self.max_particles):
            if not self.alive[i]:
                continue

            self.life[i] += dt
            if self.life[i] >= self.max_life[i]:
                self._reset_particle(i)
                continue

            # Wobble sine velocity
            wobble = 0.0
            if self.wobble_freq[i] > 0.0:
                self.wobble_phase[i] += self.wobble_freq[i] * dt
                wobble = math.sin(self.wobble_phase[i]) * 20.0

            self.px[i] += (self.vx[i] + wobble) * dt
            self.py[i] += self.vy[i] * dt

            # Wrap bounds check
            if self.vy[i] > 0.0 and self.py[i] > wrap_bottom:
                self._reset_particle(i)
                continue
            if self.vy[i] < 0.0 and self.py[i] < wrap_top:
                self._reset_particle(i)
                continue
            if self.px[i] < wrap_left or self.px[i] > wrap_right:
                self._reset_particle(i)
                continue

            # Angular rotation & quantization
            if self.angular_vel[i] != 0.0:
                self.angle[i] = (self.angle[i] + self.angular_vel[i] * dt) % 360.0
                self.angle_idx[i] = ParticleStampLUT.quantize_angle(self.angle[i])

            # Fade near end of life
            progress = self.life[i] / self.max_life[i]
            if progress > 0.8:
                fade = (1.0 - progress) / 0.2
                self.alpha_idx[i] = max(0, min(7, round(fade * 7)))

    def build_batch(self, transform: ViewportTransform) -> ParticleBatch:
        """Project particles into screen-space integer pixels for single-pass drawing."""
        particles: list[tuple[int, int, int, int, int]] = []
        off_x = transform.offset_x
        off_y = transform.offset_y
        sc_x = transform.scale_x
        sc_y = transform.scale_y

        for i in range(self.max_particles):
            if not self.alive[i]:
                continue
            # Screen-space anchor position
            sx = round(off_x + self.px[i] * sc_x)
            sy = round(off_y + self.py[i] * sc_y)
            s_idx = self.scale_idx[i]
            r_idx = self.angle_idx[i]
            a_idx = self.alpha_idx[i]
            particles.append((sx, sy, s_idx, r_idx, a_idx))

        return ParticleBatch(
            emitter_id=self.emitter_id,
            layer=self.layer,
            z_order=self.z_order,
            lut=self.lut,
            particles=particles,
        )

    # -------------------------------------------------------------------------
    # Preset constructors
    # -------------------------------------------------------------------------

    @classmethod
    def create_snow(
        cls,
        emitter_id: str = "fx_snow",
        count: int = 200,
        *,
        layer: str = "foreground",
        z_order: int = 200000,
    ) -> ParticleEmitter:
        """Create a soft falling snow emitter with pre-baked circle stamps."""
        lut = ParticleStampLUT.from_shape("circle", base_size=12, color=(240, 245, 255))
        return cls(emitter_id, lut, max_particles=count, layer=layer, z_order=z_order, preset="snow")

    @classmethod
    def create_rain(
        cls,
        emitter_id: str = "fx_rain",
        count: int = 250,
        *,
        layer: str = "foreground",
        z_order: int = 200000,
    ) -> ParticleEmitter:
        """Create a swift falling rain emitter with pre-baked drop stamps."""
        lut = ParticleStampLUT.from_shape("drop", base_size=16, color=(200, 220, 255))
        return cls(emitter_id, lut, max_particles=count, layer=layer, z_order=z_order, preset="rain")

    @classmethod
    def create_sakura(
        cls,
        emitter_id: str = "fx_sakura",
        count: int = 150,
        *,
        layer: str = "foreground",
        z_order: int = 200000,
    ) -> ParticleEmitter:
        """Create a drifting sakura petal emitter with pre-baked petal stamps."""
        lut = ParticleStampLUT.from_shape("petal", base_size=18, color=(255, 190, 205))
        return cls(emitter_id, lut, max_particles=count, layer=layer, z_order=z_order, preset="sakura")

    @classmethod
    def create_embers(
        cls,
        emitter_id: str = "fx_embers",
        count: int = 100,
        *,
        layer: str = "foreground",
        z_order: int = 200000,
    ) -> ParticleEmitter:
        """Create a rising campfire embers emitter with pre-baked spark stamps."""
        lut = ParticleStampLUT.from_shape("spark", base_size=14, color=(255, 140, 40))
        return cls(emitter_id, lut, max_particles=count, layer=layer, z_order=z_order, preset="embers")
