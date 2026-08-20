#!/usr/bin/env python3
"""Builds the four rotation-specific boot splash GIFs from source assets.

Takes the static icon+wordmark logo and an animated spinner GIF (which -
as shipped by whatever generated it - has the spinner sitting inside a much
larger canvas alongside a redundant copy of the icon/wordmark) and
recomposes just the spinner ring, grouped tightly under the real logo, on a
canvas sized correctly for each of the four display rotations.

This crop-then-recompose approach matters because a fixed lockup (icon
above wordmark above spinner, spread across a tall area) rotated wholesale
for portrait just relocates that spread along a different axis - the icon
ends up far from the spinner instead of both being centered. Cropping each
element down to only its own content and recentering the group after
rotation avoids that regardless of how the source asset is laid out.
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops

ROTATE_ANGLE = {"normal": 0, "right": -90, "left": 90, "inverted": 180}


def content_bbox(img, bg, threshold=15):
    diff = ImageChops.difference(img.convert("RGB"), Image.new("RGB", img.size, bg))
    diff = diff.point(lambda p: 255 if p > threshold else 0)
    return diff.getbbox()


def find_spinner_bbox(frame_rgba, bg):
    """The spinner is the bottommost distinct band of content in the frame -
    true for every source asset generated so far (icon, then wordmark, then
    spinner, top to bottom). Scan rows for content, group into bands
    separated by gaps, and take the last one."""
    w, h = frame_rgba.size
    rgb = frame_rgba.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", (w, h), bg))
    diff = diff.point(lambda p: 255 if p > 15 else 0)

    rows_with_content = []
    for y in range(h):
        if diff.crop((0, y, w, y + 1)).getbbox() is not None:
            rows_with_content.append(y)

    if not rows_with_content:
        raise RuntimeError("Spinner source frame appears to be entirely blank")

    bands = []
    band_start = rows_with_content[0]
    prev = rows_with_content[0]
    gap_threshold = 15
    for y in rows_with_content[1:]:
        if y - prev > gap_threshold:
            bands.append((band_start, prev))
            band_start = y
        prev = y
    bands.append((band_start, prev))

    y0, y1 = bands[-1]
    band_slice = diff.crop((0, y0, w, y1 + 1))
    x0, _, x1, _ = band_slice.getbbox()
    pad = 4
    return (
        max(0, x0 - pad), max(0, y0 - pad),
        min(w, x1 + pad), min(h, y1 + 1 + pad),
    )


def main():
    logo_path, spinner_path, out_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])

    logo_src = Image.open(logo_path).convert("RGBA")
    spinner_gif = Image.open(spinner_path)
    canvas_w, canvas_h = spinner_gif.size

    spinner_gif.seek(0)
    spin_bg = spinner_gif.convert("RGB").getpixel((0, 0))
    spin_bbox = find_spinner_bbox(spinner_gif.convert("RGBA"), spin_bg)

    n_frames = getattr(spinner_gif, "n_frames", 1)
    durations = []
    spinner_frames = []
    for i in range(n_frames):
        spinner_gif.seek(i)
        durations.append(spinner_gif.info.get("duration", 80))
        spinner_frames.append(spinner_gif.crop(spin_bbox).convert("RGBA"))

    bg = (24, 188, 241, 255)  # Home Assistant brand blue - matches the logo asset's own background

    canvases = {
        "normal": (canvas_w, canvas_h),
        "inverted": (canvas_w, canvas_h),
        "right": (canvas_h, canvas_w),
        "left": (canvas_h, canvas_w),
    }

    for rot, (w, h) in canvases.items():
        angle = ROTATE_ANGLE[rot]

        logo = logo_src.rotate(angle, expand=True)
        logo_scale = min((w * 0.5) / logo.width, (h * 0.35) / logo.height, 1.0)
        if logo_scale < 1.0:
            logo = logo.resize(
                (max(1, int(logo.width * logo_scale)), max(1, int(logo.height * logo_scale))),
                Image.LANCZOS,
            )

        out_frames = []
        for src_frame in spinner_frames:
            spinner = src_frame.rotate(angle, expand=True)
            sp_scale = min((w * 0.12) / spinner.width, (h * 0.1) / spinner.height, 2.0)
            spinner = spinner.resize(
                (max(1, int(spinner.width * sp_scale)), max(1, int(spinner.height * sp_scale))),
                Image.LANCZOS,
            )

            gap = 30
            group_h = logo.height + gap + spinner.height
            group_top = (h - group_h) // 2
            logo_pos = ((w - logo.width) // 2, group_top)
            spin_pos = ((w - spinner.width) // 2, group_top + logo.height + gap)

            frame = Image.new("RGBA", (w, h), bg)
            frame.alpha_composite(logo, dest=logo_pos)
            frame.alpha_composite(spinner, dest=spin_pos)
            out_frames.append(frame.convert("RGB"))

        out_path = out_dir / f"HA_Splash_{rot}.gif"
        out_frames[0].save(
            out_path, save_all=True, append_images=out_frames[1:],
            duration=durations, loop=0, disposal=2,
        )
        print(f"wrote {out_path} ({len(out_frames)} frames, {w}x{h})")


if __name__ == "__main__":
    main()
