"""Cross-platform on-demand screen capture and image optimization for DeskBot."""

from __future__ import annotations

import base64
import io
import logging
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

try:
    from PIL import ImageGrab
except ImportError:
    ImageGrab = None

logger = logging.getLogger(__name__)


@dataclass
class ScreenCaptureResult:
    """Encapsulates captured screen image data and metadata."""
    image: Image.Image
    width: int
    height: int
    base64_data: str
    format: str = "jpeg"
    timestamp: float = 0.0

    @property
    def data_uri(self) -> str:
        """Return base64 data URI suitable for multimodal LLM vision APIs."""
        return f"data:image/{self.format};base64,{self.base64_data}"


def optimize_image_for_vision(
    image: Image.Image,
    max_dimension: int = 1024,
    quality: int = 85,
) -> Tuple[Image.Image, str]:

    """Resize image to fit within max_dimension preserving aspect ratio, encode as base64 JPEG.

    Uses Lanczos resampling to keep code characters and syntax crisp while compressing
    retina screenshots from 10MB+ down to ~200-400KB.
    """
    # Convert RGBA / P mode to RGB for clean JPEG encoding
    if image.mode in ("RGBA", "LA", "P"):
        rgb_image = Image.new("RGB", image.size, (255, 255, 255))
        if image.mode == "P":
            image = image.convert("RGBA")
        rgb_image.paste(image, mask=image.split()[-1] if image.mode in ("RGBA", "LA") else None)
        processed = rgb_image
    elif image.mode != "RGB":
        processed = image.convert("RGB")
    else:
        processed = image

    orig_w, orig_h = processed.size
    max_side = max(orig_w, orig_h)

    if max_side > max_dimension:
        scale = max_dimension / float(max_side)
        new_w = max(1, int(orig_w * scale))
        new_h = max(1, int(orig_h * scale))
        # Support both Pillow >= 9.1 (Resampling.LANCZOS) and legacy Image.LANCZOS
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        processed = processed.resize((new_w, new_h), resample=resample_filter)

    buffer = io.BytesIO()
    processed.save(buffer, format="JPEG", quality=quality, optimize=True)
    base64_str = base64.b64encode(buffer.getvalue()).decode("ascii")
    return processed, base64_str


def _capture_macos_native(bbox: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Native macOS fallback using /usr/sbin/screencapture -x (soundless, zero-click)."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        cmd = ["/usr/sbin/screencapture", "-x"]
        if bbox is not None:
            x1, y1, x2, y2 = bbox
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            cmd.extend(["-R", f"{x1},{y1},{w},{h}"])
        cmd.append(tmp_path)

        res = subprocess.run(cmd, capture_output=True, timeout=3.0)
        if res.returncode == 0 and os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            with Image.open(tmp_path) as img:
                return img.copy()
    except Exception as err:
        logger.debug("macOS native screencapture fallback failed: %s", err)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except OSError:
            pass

    return None


def capture_screen(
    max_dimension: int = 1024,
    quality: int = 85,
    bbox: Optional[Tuple[int, int, int, int]] = None,
) -> ScreenCaptureResult:

    """Capture the screen on-demand, optimize for vision models, and return ScreenCaptureResult.

    Strictly on-demand: Never continuously records or captures in the background.
    Cross-platform: Windows (Pillow ImageGrab) & macOS (ImageGrab with screencapture fallback).
    """
    raw_image: Optional[Image.Image] = None
    capture_time = time.time()

    # 1. Primary capture via Pillow ImageGrab
    if ImageGrab is not None:
        try:
            raw_image = ImageGrab.grab(bbox=bbox, all_screens=False)
        except Exception as err:
            logger.debug("Pillow ImageGrab failed: %s", err)

    # 2. macOS fallback if ImageGrab unavailable or failed
    if raw_image is None and sys.platform == "darwin":
        raw_image = _capture_macos_native(bbox=bbox)

    if raw_image is None:
        raise RuntimeError(
            "Could not capture screen. Pillow ImageGrab is unavailable and native capture failed."
        )

    # 3. Optimize resolution and encode to base64 JPEG
    optimized_img, b64_data = optimize_image_for_vision(
        raw_image,
        max_dimension=max_dimension,
        quality=quality,
    )

    return ScreenCaptureResult(
        image=optimized_img,
        width=optimized_img.width,
        height=optimized_img.height,
        base64_data=b64_data,
        format="jpeg",
        timestamp=capture_time,
    )
