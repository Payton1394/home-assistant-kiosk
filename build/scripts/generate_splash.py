#!/usr/bin/env python3
"""Builds the four rotation-specific boot splash GIFs from source assets.

Takes the static icon+wordmark logo and an animated spinner GIF (which -
as shipped by whatever generated it - has the spinner sitting inside a much
larger canvas alongside a redundant copy of the icon/wordmark) and crops
out just the spinner ring, since the source's own icon+wordmark+spinner
layout is too spread out to rotate cleanly.

The logo and the cropped spinner are then composed into a single group
image - spinner directly under the logo, sized relative to it - ONCE per
animation frame, at natural (unrotated) scale. Each of the four rotations
takes that whole group and rotates it as one rigid unit before placing it
on the target canvas, rather than rotating the logo and spinner
independently and re-stacking them afterward - that kept them "stacked" in
name but let them drift apart under independent scale rounding; rotating
the pre-composed group guarantees the spinner stays fixed directly under
the logo in every orientation.
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

    # Build the logo+spinner group ONCE per animation frame, at its natural
    # (unrotated) orientation - spinner sized relative to the logo's own
    # width, not the target canvas, so the relationship between them is
    # fixed regardless of which rotation it later gets baked into. Each
    # rotation then rotates this WHOLE group as one rigid unit and drops it
    # onto the target canvas, rather than rotating the logo and spinner
    # independently and re-stacking them afterward (which technically also
    # keeps them "stacked" but let the two elements drift apart under scale
    # rounding - keeping the group as one image guarantees the spinner stays
    # directly under the logo no matter the rotation).
    spinner_target_w = int(logo_src.width * 0.12)
    gap = int(logo_src.height * 0.35)

    group_frames = []
    for spinner_src in spinner_frames:
        sp_scale = spinner_target_w / spinner_src.width
        spinner = spinner_src.resize(
            (max(1, spinner_target_w), max(1, int(spinner_src.height * sp_scale))),
            Image.LANCZOS,
        )
        group_w = max(logo_src.width, spinner.width)
        group_h = logo_src.height + gap + spinner.height
        group = Image.new("RGBA", (group_w, group_h), (0, 0, 0, 0))
        group.alpha_composite(logo_src, dest=((group_w - logo_src.width) // 2, 0))
        group.alpha_composite(spinner, dest=((group_w - spinner.width) // 2, logo_src.height + gap))
        group_frames.append(group)

    canvases = {
        "normal": (canvas_w, canvas_h),
        "inverted": (canvas_w, canvas_h),
        "right": (canvas_h, canvas_w),
        "left": (canvas_h, canvas_w),
    }

    for rot, (w, h) in canvases.items():
        angle = ROTATE_ANGLE[rot]

        out_frames = []
        for group in group_frames:
            rotated = group.rotate(angle, expand=True)
            scale = min((w * 0.7) / rotated.width, (h * 0.7) / rotated.height, 1.0)
            if scale < 1.0:
                rotated = rotated.resize(
                    (max(1, int(rotated.width * scale)), max(1, int(rotated.height * scale))),
                    Image.LANCZOS,
                )

            frame = Image.new("RGBA", (w, h), bg)
            pos = ((w - rotated.width) // 2, (h - rotated.height) // 2)
            frame.alpha_composite(rotated, dest=pos)
            out_frames.append(frame.convert("RGB"))

        out_path = out_dir / f"HA_Splash_{rot}.gif"
        out_frames[0].save(
            out_path, save_all=True, append_images=out_frames[1:],
            duration=durations, loop=0, disposal=2,
        )
        print(f"wrote {out_path} ({len(out_frames)} frames, {w}x{h})")


if __name__ == "__main__":
    main()
