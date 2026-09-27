"""High-level screen analysis service coordinating window context, screen capture, and vision intelligence."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import config
from command_executor import ToolResult
from vision.analyzer import (
    NvidiaVisionAnalyzer,
    VisionAnalysis,
    VisionAnalyzer,
)
from vision.screen_capture import capture_screen

logger = logging.getLogger(__name__)

# In-memory visual context cache for multi-turn conversation follow-ups
_LAST_VISION_RESULT: Optional[VisionAnalysis] = None
_LAST_VISION_TIMESTAMP: float = 0.0
_ACTIVE_ANALYZER: Optional[VisionAnalyzer] = None


def get_vision_analyzer() -> VisionAnalyzer:
    """Return the active vision analyzer (defaults to NvidiaVisionAnalyzer)."""
    global _ACTIVE_ANALYZER
    if _ACTIVE_ANALYZER is None:
        _ACTIVE_ANALYZER = NvidiaVisionAnalyzer(
            model=config.DEFAULT_VISION_MODEL,
        )
    return _ACTIVE_ANALYZER


def set_vision_analyzer(analyzer: VisionAnalyzer) -> None:
    """Override active vision analyzer (useful for unit tests or alternative backends)."""
    global _ACTIVE_ANALYZER
    _ACTIVE_ANALYZER = analyzer


def get_last_vision_result() -> Optional[VisionAnalysis]:
    """Retrieve the cached result of the most recent screen vision analysis."""
    return _LAST_VISION_RESULT


def clear_vision_cache() -> None:
    """Clear cached vision analysis."""
    global _LAST_VISION_RESULT, _LAST_VISION_TIMESTAMP
    _LAST_VISION_RESULT = None
    _LAST_VISION_TIMESTAMP = 0.0


def is_vision_cache_valid(ttl_seconds: float = 90.0) -> bool:
    """Check if the cached screen analysis is within its validity period."""
    if _LAST_VISION_RESULT is None:
        return False
    return (time.time() - _LAST_VISION_TIMESTAMP) < ttl_seconds


def perform_screen_analysis(
    user_query: str = "",
    use_cache_if_recent: bool = False,
    cache_ttl: float = 45.0,
) -> ToolResult:
    """Perform on-demand visual screen analysis and code understanding.

    1. Checks if recent cached vision result can answer a rapid follow-up.
    2. Identifies active window context (e.g. VS Code, Chrome, Terminal).
    3. Captures screen silently on-demand (zero continuous recording).
    4. Analyzes with multimodal vision LLM to understand code, errors, and algorithms.
    5. Caches structured result for subsequent follow-up questions.
    6. Returns standard ToolResult with TTS-ready spoken response.
    """
    global _LAST_VISION_RESULT, _LAST_VISION_TIMESTAMP

    clean_query = (user_query or "").strip()

    # 1. Check cache for follow-up questions if requested and still fresh
    if use_cache_if_recent and is_vision_cache_valid(ttl_seconds=cache_ttl) and _LAST_VISION_RESULT:
        logger.info("Reusing fresh visual context from cache for follow-up")
        cached = _LAST_VISION_RESULT
        return ToolResult(
            success=True,
            message=f"Reused visual analysis: {cached.summary}",
            response_text=cached.spoken_response,
            data=cached.to_dict(),
        )

    # 2. Get active window metadata for supplementary context
    window_data: Dict[str, Any] = {}
    try:
        from tools.developer_tools import get_active_window
        win_res = get_active_window()
        if win_res.success and isinstance(win_res.data, dict):
            window_data = win_res.data
    except Exception as win_err:
        logger.debug("Could not inspect active window for vision context: %s", win_err)

    # 3. Capture screen on-demand
    try:
        capture = capture_screen(
            max_dimension=config.VISION_MAX_DIMENSION,
            quality=config.VISION_JPEG_QUALITY,
        )
    except Exception as cap_err:
        logger.error("Screen capture failed for visual intelligence: %s", cap_err)
        err_msg = f"Screen capture failed: {cap_err}"
        spoken = "I was unable to capture your screen. Please check system permissions."
        return ToolResult(success=False, message=err_msg, response_text=spoken)

    # 4. Perform multimodal vision analysis
    analyzer = get_vision_analyzer()
    try:
        analysis = analyzer.analyze(
            image_data_uri=capture.data_uri,
            user_query=clean_query,
            window_context=window_data,
        )
    except Exception as vision_err:
        logger.error("Vision analysis failed: %s", vision_err)
        err_str = str(vision_err)
        if "NVIDIA_API_KEY" in err_str:
            spoken = "I couldn't analyze the screen because your NVIDIA API key is missing."
        else:
            spoken = f"I encountered an issue analyzing your screen: {err_str}"
        return ToolResult(
            success=False,
            message=f"Vision analysis error: {err_str}",
            response_text=spoken,
        )

    # 5. Cache result for follow-ups
    _LAST_VISION_RESULT = analysis
    _LAST_VISION_TIMESTAMP = time.time()

    logger.info(
        "Screen analysis complete. Content: %s, Language: %s, Readability: %s",
        analysis.content_type,
        analysis.language,
        analysis.readability,
    )

    return ToolResult(
        success=True,
        message=analysis.summary or f"Analyzed {analysis.content_type} on screen",
        response_text=analysis.spoken_response,
        data=analysis.to_dict(),
    )
