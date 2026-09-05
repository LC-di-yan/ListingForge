# -*- coding: utf-8 -*-
"""生成内置示例商品的产品照片（PIL 绘制，供 Demo/视频使用）"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ASSETS = Path(__file__).resolve().parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)


def canvas(w=900, h=900, top=(245, 247, 252), bottom=(225, 230, 242)):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return img, d


def shadow(img, cx, cy, w, h, blur=18, alpha=60):
    s = Image.new("RGBA", (int(w), int(h)), (0, 0, 0, 0))
    ImageDraw.Draw(s).ellipse([0, 0, w - 1, h - 1], fill=(25, 30, 45, alpha))
    s = s.filter(ImageFilter.GaussianBlur(blur))
    img.paste(s, (int(cx - w / 2), int(cy - h / 2)), s)


def bottle():
    img, d = canvas()
    W, H = img.size
    # 杯身
    body = [W * 0.36, H * 0.28, W * 0.64, H * 0.80]
    d.rounded_rectangle(body, radius=70, fill=(28, 32, 44), outline=(70, 78, 96), width=3)
    # 金属高光带
    d.rounded_rectangle([W * 0.385, H * 0.30, W * 0.415, H * 0.78], radius=12, fill=(90, 98, 118))
    # LED 温显屏
    d.rounded_rectangle([W * 0.43, H * 0.42, W * 0.57, H * 0.52], radius=16, fill=(10, 12, 18))
    f = ImageFont_safe(46)
    d.text((W * 0.44, H * 0.445), "24°", font=f, fill=(120, 230, 180))
    # 杯盖
    d.rounded_rectangle([W * 0.40, H * 0.20, W * 0.60, H * 0.29], radius=22, fill=(50, 56, 72))
    d.rounded_rectangle([W * 0.455, H * 0.14, W * 0.545, H * 0.22], radius=14, fill=(60, 66, 84))
    shadow(img, W / 2, H * 0.855, W * 0.42, H * 0.05)
    img.save(ASSETS / "sample_bottle.png")


def earbuds():
    img, d = canvas()
    W, H = img.size
    # 充电盒
    d.rounded_rectangle([W * 0.30, H * 0.42, W * 0.70, H * 0.78], radius=90, fill=(245, 246, 250),
                        outline=(200, 205, 218), width=3)
    d.rounded_rectangle([W * 0.30, H * 0.42, W * 0.70, H * 0.58], radius=60, fill=(232, 235, 243))
    # 耳机两只
    for cx, tilt in [(W * 0.40, -18), (W * 0.60, 18)]:
        d.ellipse([cx - 55, H * 0.30, cx + 55, H * 0.30 + 110], fill=(30, 34, 46))
        d.rounded_rectangle([cx - 20, H * 0.38, cx + 20, H * 0.50], radius=20, fill=(30, 34, 46))
        d.ellipse([cx - 30, H * 0.33, cx - 6, H * 0.33 + 24], fill=(90, 96, 115))
    # 指示灯
    d.ellipse([W * 0.485, H * 0.615, W * 0.515, H * 0.645], fill=(80, 220, 150))
    shadow(img, W / 2, H * 0.85, W * 0.46, H * 0.05)
    img.save(ASSETS / "sample_earbuds.png")


def feeder():
    img, d = canvas()
    W, H = img.size
    # 顶部粮仓（透明）
    d.rounded_rectangle([W * 0.34, H * 0.18, W * 0.66, H * 0.52], radius=40, fill=(226, 234, 244),
                        outline=(188, 198, 216), width=3)
    # 粮食颗粒
    for i in range(14):
        x = W * (0.38 + 0.035 * (i % 6)) + (6 if i % 2 else 0)
        y = H * (0.30 + 0.028 * (i % 5))
        d.ellipse([x, y, x + 16, y + 12], fill=(214, 168, 96))
    # 机身底座
    d.rounded_rectangle([W * 0.30, H * 0.52, W * 0.70, H * 0.80], radius=34, fill=(255, 255, 255),
                        outline=(210, 216, 230), width=3)
    # 出粮口
    d.rounded_rectangle([W * 0.44, H * 0.60, W * 0.56, H * 0.70], radius=18, fill=(24, 28, 38))
    # 夜灯
    d.ellipse([W * 0.35, H * 0.63, W * 0.39, H * 0.67], fill=(255, 205, 120))
    d.ellipse([W * 0.61, H * 0.63, W * 0.65, H * 0.67], fill=(255, 205, 120))
    # 按键屏
    d.rounded_rectangle([W * 0.475, H * 0.735, W * 0.525, H * 0.775], radius=10, fill=(35, 42, 58))
    shadow(img, W / 2, H * 0.86, W * 0.5, H * 0.05)
    img.save(ASSETS / "sample_feeder.png")


def default_product():
    img, d = canvas()
    W, H = img.size
    d.rounded_rectangle([W * 0.35, H * 0.35, W * 0.65, H * 0.68], radius=48, fill=(70, 78, 98))
    d.ellipse([W * 0.44, H * 0.44, W * 0.56, H * 0.56], fill=(235, 238, 246))
    shadow(img, W / 2, H * 0.82, W * 0.4, H * 0.05)
    img.save(ASSETS / "default_product.png")


def ImageFont_safe(size):
    from PIL import ImageFont
    for p in ["C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/msyh.ttc"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


if __name__ == "__main__":
    bottle(); earbuds(); feeder(); default_product()
    print("示例商品图已生成到", ASSETS)
