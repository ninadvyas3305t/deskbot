"""DeskBot Visual Screen Intelligence and Code Understanding package."""

from vision.analyzer import (
    MockVisionAnalyzer,
    NvidiaVisionAnalyzer,
    VisionAnalysis,
    VisionAnalyzer,
)
from vision.screen_capture import (
    ScreenCaptureResult,
    capture_screen,
    optimize_image_for_vision,
)
from vision.service import (
    clear_vision_cache,
    get_last_vision_result,
    get_vision_analyzer,
    is_vision_cache_valid,
    perform_screen_analysis,
    set_vision_analyzer,
)

__all__ = [
    "capture_screen",
    "optimize_image_for_vision",
    "ScreenCaptureResult",
    "VisionAnalysis",
    "VisionAnalyzer",
    "NvidiaVisionAnalyzer",
    "MockVisionAnalyzer",
    "perform_screen_analysis",
    "get_last_vision_result",
    "get_vision_analyzer",
    "set_vision_analyzer",
    "clear_vision_cache",
    "is_vision_cache_valid",
]
