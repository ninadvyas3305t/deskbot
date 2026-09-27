"""Procedural icon generator creating DeskBot robot face icons for System Tray / Menu Bar."""

from __future__ import annotations

from PIL import Image, ImageDraw


def create_tray_icon_image(status: str = "ready", size: int = 64) -> Image.Image:
    """Generate a clean DeskBot robot face icon matching the OLED display."""
    img = Image.new("RGBA", (size, size), color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Base color theme based on status
    if status == "ready":
        head_color = (35, 130, 240)       # Friendly DeskBot Blue
        eye_color = (255, 255, 255)
        pupil_color = (20, 60, 120)
    elif status == "listening":
        head_color = (40, 200, 120)       # Active Green
        eye_color = (255, 255, 255)
        pupil_color = (10, 80, 40)
    elif status == "thinking":
        head_color = (170, 90, 240)       # Purple AI thinking
        eye_color = (255, 255, 255)
        pupil_color = (60, 20, 100)
    elif status == "disconnected":
        head_color = (130, 140, 150)      # Gray standby
        eye_color = (220, 220, 220)
        pupil_color = (80, 85, 90)
    else:  # error
        head_color = (235, 75, 75)        # Red Alert
        eye_color = (255, 255, 255)
        pupil_color = (120, 20, 20)

    # Robot head rounded rectangle
    margin = int(size * 0.08)
    corner = int(size * 0.22)
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=corner,
        fill=head_color,
    )

    # Antennas / Ear accents
    ear_w = int(size * 0.06)
    ear_h = int(size * 0.2)
    ear_y = int(size * 0.4)
    draw.rounded_rectangle((0, ear_y, ear_w + margin, ear_y + ear_h), radius=2, fill=head_color)
    draw.rounded_rectangle((size - margin - ear_w, ear_y, size, ear_y + ear_h), radius=2, fill=head_color)

    # Screen visor
    v_top = int(size * 0.25)
    v_bottom = int(size * 0.75)
    v_left = int(size * 0.18)
    v_right = int(size * 0.82)
    draw.rounded_rectangle((v_left, v_top, v_right, v_bottom), radius=corner // 2, fill=(18, 22, 28))

    # Eyes
    eye_w = int(size * 0.18)
    eye_h = int(size * 0.26)
    left_x = int(size * 0.26)
    right_x = int(size * 0.56)
    eye_y = int(size * 0.37)

    draw.rounded_rectangle((left_x, eye_y, left_x + eye_w, eye_y + eye_h), radius=4, fill=eye_color)
    draw.rounded_rectangle((right_x, eye_y, right_x + eye_w, eye_y + eye_h), radius=4, fill=eye_color)

    # Pupils
    p_size = int(size * 0.08)
    p_offset_y = 0
    p_offset_x = 0
    if status == "thinking":
        p_offset_y = -int(size * 0.04)
    elif status == "listening":
        p_offset_x = int(size * 0.02)

    p_y = eye_y + (eye_h - p_size) // 2 + p_offset_y
    draw.ellipse((left_x + (eye_w - p_size) // 2 + p_offset_x, p_y,
                  left_x + (eye_w + p_size) // 2 + p_offset_x, p_y + p_size), fill=pupil_color)
    draw.ellipse((right_x + (eye_w - p_size) // 2 + p_offset_x, p_y,
                  right_x + (eye_w + p_size) // 2 + p_offset_x, p_y + p_size), fill=pupil_color)

    return img
