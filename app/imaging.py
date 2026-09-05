"""图片管线（F3）：白底主图 / 场景图 / 多尺寸适配

Demo 版用 Pillow 实现（零重依赖、秒级出图）：
- 白底主图：产品图等比缩放居中放到纯白 1:1 画布（亚马逊规范 ≥1000px）
- 多尺寸：1:1 / 4:5 / 16:9 / 9:16 四种平台适配尺寸 + 角标
- 场景图：渐变背景 + 产品 + 投影
生产版可平滑替换为 rembg 抠图 + ComfyUI 保真重绘 + Qwen-Image 生成，
对外接口（process_product_image / ensure_compliant_main / image_meta）保持不变。
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

UPLOADS = Path(__file__).resolve().parent.parent / "data" / "uploads"
FONT_CANDIDATES = ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/msyhbd.ttc", "C:/Windows/Fonts/arial.ttf"]

SIZE_PRESETS = {
    "1x1": (1200, 1200),
    "4x5": (1080, 1350),
    "16x9": (1600, 900),
    "9x16": (1080, 1920),
}


def _font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _white_ratio(img: Image.Image) -> float:
    small = img.convert("RGB").resize((64, 64))
    px = list(small.getdata())
    white = sum(1 for r, g, b in px if r > 245 and g > 245 and b > 245)
    return white / len(px)


def image_meta(path: str | Path) -> dict:
    img = Image.open(path)
    return {"width": img.width, "height": img.height, "white_ratio": _white_ratio(img)}


def _fit_contain(img: Image.Image, box: int) -> Image.Image:
    img = img.convert("RGBA")
    img.thumbnail((box, box), Image.LANCZOS)
    return img


def _cutout(img: Image.Image, tol: int = 34) -> Image.Image:
    """从边缘洪水填充抠除背景（demo 级抠图；生产替换为 rembg 模型抠图）"""
    import cv2
    import numpy as np

    rgb = np.array(img.convert("RGB"))
    h, w = rgb.shape[:2]
    work = rgb.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    for seed in seeds:
        if mask[seed[1], seed[0]] == 0:
            cv2.floodFill(work, mask, seed, 0, (tol,) * 3, (tol,) * 3,
                          cv2.FLOODFILL_MASK_ONLY | (255 << 8) | 4)
    alpha = 255 - mask[1:-1, 1:-1]
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)
    return Image.fromarray(np.dstack([rgb, alpha]), "RGBA")


def _soft_shadow(canvas: Image.Image, product: Image.Image, cx: int, bottom: int, scale: float = 1.0):
    w = int(product.width * 0.7 * scale)
    h = max(10, int(product.height * 0.045 * scale))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(shadow)
    d.ellipse([0, 0, w - 1, h - 1], fill=(30, 30, 40, 70))
    shadow = shadow.filter(ImageFilter.GaussianBlur(h / 3))
    canvas.alpha_composite(shadow, (cx - w // 2, bottom - h // 2))


def make_white_bg(src: str | Path, out_path: str | Path, canvas_px: int = 1200, margin: float = 0.18):
    """产品图 -> 抠图 -> 纯白背景 1:1 主图"""
    product = _fit_contain(_cutout(Image.open(src)), int(canvas_px * (1 - margin * 2)))
    canvas = Image.new("RGB", (canvas_px, canvas_px), (255, 255, 255))
    canvas = canvas.convert("RGBA")
    cx, cy = canvas_px // 2, canvas_px // 2
    _soft_shadow(canvas, product, cx, cy + product.height // 2 - int(product.height * 0.02), 0.9)
    canvas.alpha_composite(product, (cx - product.width // 2, cy - product.height // 2))
    canvas.convert("RGB").save(out_path, quality=92)
    return str(out_path)


def make_scene(src: str | Path, out_path: str | Path, size: tuple = (1200, 900)):
    """场景图：柔和渐变背景 + 产品 + 投影 + 光斑"""
    w, h = size
    top, bottom = (238, 242, 250), (208, 216, 235)
    bg = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / h
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        d.line([(0, y), (w, y)], fill=c)
    bg = bg.convert("RGBA")
    product = _fit_contain(_cutout(Image.open(src)), int(min(w, h) * 0.62))
    cx, cy = w // 2, int(h * 0.54)
    _soft_shadow(bg, product, cx, cy + product.height // 2, 1.1)
    bg.alpha_composite(product, (cx - product.width // 2, cy - product.height // 2))
    # 光斑
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(w * 0.62), int(h * 0.08), int(w * 0.95), int(h * 0.38)], fill=(255, 255, 255, 60))
    glow = glow.filter(ImageFilter.GaussianBlur(60))
    bg.alpha_composite(glow)
    bg.convert("RGB").save(out_path, quality=92)
    return str(out_path)


def make_size_variants(main: str | Path, out_dir: str | Path) -> dict:
    """主图 -> 多平台尺寸适配，带尺寸角标"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    src = Image.open(main).convert("RGB")
    label_font = _font(34)
    results = {}
    for key, (w, h) in SIZE_PRESETS.items():
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        product = src.copy()
        product.thumbnail((int(w * 0.82), int(h * 0.82)), Image.LANCZOS)
        canvas.paste(product, ((w - product.width) // 2, (h - product.height) // 2))
        d = ImageDraw.Draw(canvas)
        tag = {"1x1": "1:1 主图", "4x5": "4:5 详情页", "16x9": "16:9 横幅", "9x16": "9:16 短视频封面"}[key]
        text = f"{w}x{h} · {tag}"
        bbox = d.textbbox((0, 0), text, font=label_font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        pad = 14
        d.rounded_rectangle([w - tw - pad * 3, h - th - pad * 3, w - pad, h - pad],
                            radius=10, fill=(17, 24, 39))
        d.text((w - tw - pad * 2, h - th - pad * 2 - 2), text, font=label_font, fill=(255, 255, 255))
        out = out_dir / f"variant_{key}.jpg"
        canvas.save(out, quality=90)
        results[key] = str(out)
    return results


def process_product_image(src: str | Path, product_id: int) -> dict:
    """F3 主流程：输入产品照片 -> 白底主图 + 场景图 + 多尺寸适配"""
    out_dir = UPLOADS / str(product_id) / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    main = make_white_bg(src, out_dir / "main_white.jpg")
    scene = make_scene(src, out_dir / "scene.jpg")
    variants = make_size_variants(main, out_dir)
    return {"main": main, "scene": scene, "variants": variants}


def ensure_compliant_main(src: str | Path) -> str:
    """规则修复钩子：重新生成合规白底 1:1 主图"""
    src = Path(src)
    out = src.parent / "main_white.jpg"
    if src.name == "main_white.jpg":
        return str(src)
    return make_white_bg(src, out)
