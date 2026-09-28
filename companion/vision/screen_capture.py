"""Cross-platform on-demand in-process screen capture and image optimization for DeskBot."""

from __future__ import annotations

import base64
import io
import logging
import os
import sys
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
        new_w = max(1, int(round(orig_w * scale)))
        new_h = max(1, int(round(orig_h * scale)))
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        processed = processed.resize((new_w, new_h), resample=resample_filter)

    buffer = io.BytesIO()
    processed.save(buffer, format="JPEG", quality=quality, optimize=True)
    base64_str = base64.b64encode(buffer.getvalue()).decode("ascii")
    return processed, base64_str


def _capture_macos_in_process(bbox: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Capture screen in-process via CoreGraphics CGWindowListCreateImage without spawning subprocesses.

    Spawning external CLI binaries like /usr/sbin/screencapture causes macOS TCC to attribute
    permissions to the helper binary or parent shell rather than DeskBot.app.
    Direct in-process CoreGraphics capture keeps permission evaluation strictly within DeskBot.app.
    """
    try:
        import ctypes
        from ctypes import Structure, c_double, c_size_t, c_uint8, c_uint32, c_void_p, POINTER

        class CGPoint(Structure):
            _fields_ = [("x", c_double), ("y", c_double)]

        class CGSize(Structure):
            _fields_ = [("width", c_double), ("height", c_double)]

        class CGRect(Structure):
            _fields_ = [("origin", CGPoint), ("size", CGSize)]

        cg = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
        cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")

        cg.CGWindowListCreateImage.restype = c_void_p
        cg.CGWindowListCreateImage.argtypes = [CGRect, c_uint32, c_uint32, c_uint32]
        cg.CGImageGetWidth.restype = c_size_t
        cg.CGImageGetWidth.argtypes = [c_void_p]
        cg.CGImageGetHeight.restype = c_size_t
        cg.CGImageGetHeight.argtypes = [c_void_p]
        cg.CGImageGetBytesPerRow.restype = c_size_t
        cg.CGImageGetBytesPerRow.argtypes = [c_void_p]
        cg.CGImageGetDataProvider.restype = c_void_p
        cg.CGImageGetDataProvider.argtypes = [c_void_p]
        cg.CGDataProviderCopyData.restype = c_void_p
        cg.CGDataProviderCopyData.argtypes = [c_void_p]

        cf.CFDataGetBytePtr.restype = POINTER(c_uint8)
        cf.CFDataGetBytePtr.argtypes = [c_void_p]
        cf.CFDataGetLength.restype = c_size_t
        cf.CFDataGetLength.argtypes = [c_void_p]
        cf.CFRelease.restype = None
        cf.CFRelease.argtypes = [c_void_p]

        if bbox is not None:
            x1, y1, x2, y2 = bbox
            rect = CGRect(
                CGPoint(float(x1), float(y1)),
                CGSize(max(1.0, float(x2 - x1)), max(1.0, float(y2 - y1))),
            )
        else:
            rect = CGRect.in_dll(cg, "CGRectInfinite")

        # kCGWindowListOptionOnScreenOnly = 1, kCGNullWindowID = 0, kCGWindowImageDefault = 0
        img_ref = cg.CGWindowListCreateImage(rect, 1, 0, 0)
        if not img_ref:
            return None

        try:
            w = cg.CGImageGetWidth(img_ref)
            h = cg.CGImageGetHeight(img_ref)
            bpr = cg.CGImageGetBytesPerRow(img_ref)
            if w <= 0 or h <= 0:
                return None

            prov = cg.CGImageGetDataProvider(img_ref)
            if not prov:
                return None

            data_ref = cg.CGDataProviderCopyData(prov)
            if not data_ref:
                return None

            try:
                ptr = cf.CFDataGetBytePtr(data_ref)
                length = cf.CFDataGetLength(data_ref)
                buf = ctypes.string_at(ptr, length)
                # macOS CoreGraphics returns BGRA pixel buffer
                return Image.frombytes("RGBA", (w, h), buf, "raw", "BGRA", bpr, 1)
            finally:
                cf.CFRelease(data_ref)
        finally:
            cf.CFRelease(img_ref)

    except Exception as err:
        logger.debug("In-process macOS screen capture error: %s", err)
        return None


def capture_raw_screen(bbox: Optional[Tuple[int, int, int, int]] = None) -> Optional[Image.Image]:
    """Capture raw, uncompressed full or region screenshot in memory across platforms."""
    # 1. On macOS, prioritize direct in-process CoreGraphics capture
    if sys.platform == "darwin":
        img = _capture_macos_in_process(bbox=bbox)
        if img is not None:
            return img

    # 2. Windows / Linux or fallback via Pillow ImageGrab
    grab_module = ImageGrab
    if grab_module is None:
        try:
            from PIL import ImageGrab as pil_grab
            grab_module = pil_grab
        except Exception:
            pass

    if grab_module is not None:
        try:
            return grab_module.grab(bbox=bbox, all_screens=False)
        except Exception as err:
            logger.debug("Pillow ImageGrab failed: %s", err)

    return None


def capture_screen(
    max_dimension: int = 1024,
    quality: int = 85,
    bbox: Optional[Tuple[int, int, int, int]] = None,
) -> ScreenCaptureResult:
    """Capture the screen on-demand, optimize for vision models, and return ScreenCaptureResult.

    Strictly on-demand: Never continuously records or captures in the background.
    macOS: In-process CoreGraphics capture preserves TCC app identity.
    Windows: Pillow ImageGrab with desktop coordinates.
    """
    capture_time = time.time()
    raw_image = capture_raw_screen(bbox=bbox)

    if raw_image is None:
        if sys.platform == "darwin":
            raise RuntimeError(
                "Could not capture screen. Screen Recording permission is required.\n"
                "Please grant permission under System Settings → Privacy & Security → Screen & System Audio Recording."
            )
        raise RuntimeError(
            "Could not capture screen. Pillow ImageGrab is unavailable and native capture failed."
        )

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
