"""Convert a transparent PNG into a Windows .ico file for PyInstaller."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter


ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
PADDING_RATIO = 0.04
SMALL_ICON_SIZES = {(16, 16), (24, 24), (32, 32), (48, 48)}


def prepare_icon_canvas(image: Image.Image) -> Image.Image:
    """Center visible artwork on a transparent square canvas."""
    image = image.convert("RGBA")
    alpha = image.getchannel("A")
    bbox = alpha.getbbox()
    if bbox:
        image = image.crop(bbox)

    side = max(image.size)
    padding = max(1, round(side * PADDING_RATIO))
    canvas_side = side + padding * 2
    canvas = Image.new("RGBA", (canvas_side, canvas_side), (0, 0, 0, 0))
    left = (canvas_side - image.width) // 2
    top = (canvas_side - image.height) // 2
    canvas.alpha_composite(image, (left, top))
    return canvas


def make_icon_frames(image: Image.Image) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for size in ICON_SIZES:
        if size in SMALL_ICON_SIZES:
            frame = make_small_icon_frame(image, size)
        else:
            frame = image.resize(size, Image.Resampling.LANCZOS)
        frames.append(frame)
    return frames


def make_small_icon_frame(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Render a simplified high-contrast frame for tiny taskbar sizes."""
    scale = 4
    work_size = (size[0] * scale, size[1] * scale)
    inset = max(2, round(size[0] * 0.14))
    inner_size = ((size[0] - inset * 2) * scale, (size[1] - inset * 2) * scale)
    source = image.resize(inner_size, Image.Resampling.LANCZOS).convert("RGBA")
    padded_source = Image.new("RGBA", work_size, (0, 0, 0, 0))
    padded_source.alpha_composite(source, (inset * scale, inset * scale))
    source = padded_source.filter(ImageFilter.UnsharpMask(radius=1.0, percent=180, threshold=1))
    source = source.resize(size, Image.Resampling.LANCZOS)
    source = source.filter(ImageFilter.UnsharpMask(radius=0.6, percent=220, threshold=0))

    alpha = source.getchannel("A").point(lambda value: 0 if value < 32 else min(255, value * 2))
    outline = alpha.filter(ImageFilter.MaxFilter(3))
    outline = ImageChops.subtract(outline, alpha)

    frame = Image.new("RGBA", size, (0, 0, 0, 0))
    outline_layer = Image.new("RGBA", size, (0, 8, 56, 0))
    outline_layer.putalpha(outline.point(lambda value: min(180, value * 2)))
    frame.alpha_composite(outline_layer)

    icon_layer = Image.new("RGBA", size, (0, 0, 0, 0))
    source_pixels = source.load()
    icon_pixels = icon_layer.load()
    for y in range(source.height):
        for x in range(source.width):
            red, green, blue, a = source_pixels[x, y]
            if a < 32:
                continue

            is_cyan_path = green > 105 and blue > 130 and blue >= red + 28
            if is_cyan_path:
                icon_pixels[x, y] = (0, 240, 255, min(255, max(180, a * 2)))
            elif blue > 45:
                icon_pixels[x, y] = (0, 22, 130, min(235, max(120, a + 48)))

    frame.alpha_composite(icon_layer)
    return frame


def validate_transparency(path: Path):
    icon = Image.open(path)
    for size in ICON_SIZES:
        frame = icon.ico.getimage(size).convert("RGBA")
        alpha = frame.getchannel("A")
        if alpha.getextrema()[0] != 0:
            raise ValueError(f"{path} {size[0]}x{size[1]} frame has no transparent pixels")

        corners = (
            frame.getpixel((0, 0)),
            frame.getpixel((frame.width - 1, 0)),
            frame.getpixel((0, frame.height - 1)),
            frame.getpixel((frame.width - 1, frame.height - 1)),
        )
        if any(pixel[3] != 0 for pixel in corners):
            raise ValueError(f"{path} {size[0]}x{size[1]} frame has opaque corners")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    if not args.input.exists():
        raise FileNotFoundError(args.input)

    args.output.parent.mkdir(parents=True, exist_ok=True)

    image = prepare_icon_canvas(Image.open(args.input))
    frames = make_icon_frames(image)
    frames[-1].save(
        args.output,
        format="ICO",
        sizes=ICON_SIZES,
        append_images=frames[:-1],
        bitmap_format="png",
    )
    validate_transparency(args.output)

    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
