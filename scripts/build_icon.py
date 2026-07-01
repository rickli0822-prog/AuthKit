"""从官方盾形标志生成多尺寸 .ico / .png（无文字）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


MARK_NAME = "authkit-logo-mark.png"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def load_mark(path: Path) -> Image.Image:
    img = Image.open(path).convert("RGBA")
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    return img


def render_icon(mark: Image.Image, size: int) -> Image.Image:
    """分步缩小 + 小尺寸二值化，保持白线锐利。"""
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 255))
    inner = max(int(size * 0.9), 8)
    current = mark.copy()

    while min(current.size) > inner * 2:
        nw = max(current.width // 2, inner)
        nh = max(current.height // 2, inner)
        current = current.resize((nw, nh), Image.Resampling.LANCZOS)

    resample = Image.Resampling.BOX if size <= 32 else Image.Resampling.LANCZOS
    scale = min(inner / current.width, inner / current.height)
    scaled_size = (max(1, int(current.width * scale)), max(1, int(current.height * scale)))
    scaled = current.resize(scaled_size, resample)

    if size <= 48:
        gray = ImageOps.grayscale(scaled)
        bw = gray.point(lambda p: 255 if p > 100 else 0)
        alpha = scaled.split()[-1]
        scaled = Image.merge("RGBA", (bw, bw, bw, alpha))

    offset = ((size - scaled.width) // 2, (size - scaled.height) // 2)
    canvas.paste(scaled, offset, scaled)
    return canvas


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    mark_path = assets / MARK_NAME
    if not mark_path.is_file():
        raise SystemExit(f"找不到标志文件: {mark_path}")

    mark = load_mark(mark_path)

    png_512 = assets / "authkit-icon-512.png"
    png_48 = assets / "authkit-icon-48.png"
    ico_path = assets / "authkit.ico"

    render_icon(mark, 512).save(png_512, format="PNG")
    render_icon(mark, 48).save(png_48, format="PNG")

    # Pillow creates a real multi-size .ico from one high-resolution source.
    # Saving pre-sized append_images can collapse to the first frame on Windows.
    render_icon(mark, 512).save(ico_path, format="ICO", sizes=[(s, s) for s in ICO_SIZES])

    print(f"已生成: {png_512}")
    print(f"已生成: {png_48}")
    print(f"已生成: {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
