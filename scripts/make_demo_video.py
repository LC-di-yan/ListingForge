# -*- coding: utf-8 -*-
"""ListingForge 演示视频合成脚本

流程：Playwright 驱动真实页面走完六步 → 每步截图 → PIL 合成步骤条/字幕帧
      （含点击涟漪动效）→ ffmpeg 编码 + numpy 合成的轻背景乐 → MP4

用法: 服务运行中(python run.py)时执行  python scripts/make_demo_video.py
产物: video/listingforge_demo.mp4 (1920x1080, ~56s)
"""
import subprocess
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "video"
FRAMES_DIR = ROOT / "data" / "video_frames"
OUT_DIR.mkdir(exist_ok=True)

W, H = 1920, 1080
FPS = 24
INK, PRIMARY, ACCENT = (26, 32, 48), (79, 70, 229), (124, 108, 255)
DARK = (23, 29, 58)
REPO_URL = "github.com/LC-di-yan/ListingForge"

STEPS = ["商品录入", "AI 结构化", "文案生成", "规则校验", "审核放行", "一键上架"]


def font(size, bold=False):
    cands = ["C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
             "C:/Windows/Fonts/arial.ttf"]
    for p in cands:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------------- 卡片帧 ----------------

def gradient_card():
    img = Image.new("RGB", (W, H), DARK)
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    gd.ellipse([int(W * 0.55), -int(H * 0.35), int(W * 1.35), int(H * 0.75)], fill=110)
    gd.ellipse([-int(W * 0.2), int(H * 0.6), int(W * 0.4), int(H * 1.3)], fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(130))
    return Image.composite(Image.new("RGB", (W, H), (64, 52, 158)), img, glow)


def title_card():
    img = gradient_card()
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([W / 2 - 46, H * 0.26, W / 2 + 46, H * 0.26 + 92], radius=24, fill=PRIMARY)
    d.text((W / 2, H * 0.26 + 46), "LF", font=font(52, True), fill="white", anchor="mm")
    d.text((W / 2, H * 0.43), "ListingForge · AI 智能上新引擎",
           font=font(58, True), fill="white", anchor="mm")
    d.text((W / 2, H * 0.52), "从产品资料到四平台上架，全自动 AI 工作流",
           font=font(27), fill=(202, 206, 228), anchor="mm")
    tags = ["资料结构化", "多平台多语言文案", "规则校验·自动改写", "人审放行", "一键上架"]
    total_w = len(tags) * 276 - 20
    x0 = (W - total_w) / 2
    for i, s in enumerate(tags):
        x = x0 + i * 276
        d.rounded_rectangle([x, H * 0.64, x + 256, H * 0.64 + 58], radius=29,
                            outline=(116, 124, 168), width=2)
        d.text((x + 128, H * 0.64 + 29), s, font=font(21), fill=(216, 220, 240), anchor="mm")
    d.text((W / 2, H * 0.85), "AI+跨境黑客松巅峰赛 · 场景一 智能上新 · 基于阿里云百炼",
           font=font(21), fill=(152, 158, 188), anchor="mm")
    return img


def end_card():
    img = gradient_card()
    d = ImageDraw.Draw(img)
    d.text((W / 2, H * 0.36), "一张产品图 → 四平台上架，分钟级完成",
           font=font(46, True), fill="white", anchor="mm")
    d.rounded_rectangle([W / 2 - 450, H * 0.52 - 4, W / 2 + 450, H * 0.52 + 64], radius=20,
                        fill=(38, 46, 80))
    d.text((W / 2, H * 0.52 + 30), REPO_URL, font=font(28, True), fill=(140, 236, 190), anchor="mm")
    d.text((W / 2, H * 0.68), "体验:  pip install -r requirements.txt  &&  python run.py",
           font=font(25), fill=(204, 208, 230), anchor="mm")
    d.text((W / 2, H * 0.78), "开源组件: FastAPI · OpenCV/Pillow · Playwright · 阿里云百炼 Qwen",
           font=font(20), fill=(160, 166, 196), anchor="mm")
    return img


# ---------------- 场景帧（截图 + 步骤条 + 字幕 + 涟漪） ----------------

def scene_frame(shot: Image.Image, step, title, sub="", click=None, t=0.0):
    frame = shot.resize((W, H), Image.LANCZOS).convert("RGB")
    d = ImageDraw.Draw(frame, "RGBA")
    # 顶部步骤条（88px 不透明，完全遮盖应用自身顶栏）
    STRIP = 88
    d.rectangle([0, 0, W, STRIP], fill=DARK + (255,))
    f = font(20, True)
    x = 28
    for i, s in enumerate(STEPS, 1):
        color = (124, 236, 180) if i < step else ("white" if i == step else (122, 130, 160))
        d.ellipse([x, STRIP / 2 - 15, x + 30, STRIP / 2 + 15], fill=PRIMARY if i == step else (46, 54, 88))
        d.text((x + 15, STRIP / 2), str(i), font=font(16, True), fill="white", anchor="mm")
        d.text((x + 42, STRIP / 2), s, font=f, fill=color, anchor="lm")
        x += 42 + d.textlength(s, font=f) + 38
    d.text((W - 28, STRIP / 2), "ListingForge Demo", font=font(18, True), fill=(142, 150, 192), anchor="rm")
    # 底部字幕
    bar = 96
    d.rectangle([0, H - bar, W, H], fill=DARK + (255,))
    d.rectangle([0, H - bar, W, H - bar + 3], fill=ACCENT)
    d.text((48, H - bar + 32), title, font=font(30, True), fill="white", anchor="lm")
    if sub:
        d.text((48, H - bar + 70), sub, font=font(19), fill=(188, 194, 220), anchor="lm")
    # 点击涟漪
    if click and t >= click[2]:
        tt = t - click[2]
        cx, cy = int(click[0] * W), int(click[1] * H)
        for k in (0.0, 0.3):
            dt = tt - k
            if dt < 0:
                continue
            r = int(12 + dt * 70)
            a = max(0, 200 - int(dt * 220))
            if a > 0 and r > 0:
                d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(140, 236, 190, a), width=6)
        d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(140, 236, 190, 225))
    return frame


# ---------------- Playwright 截图 ----------------

def capture_scenes():
    import httpx
    from playwright.sync_api import sync_playwright

    B = "http://127.0.0.1:8000"
    c = httpx.Client(timeout=60)
    FRAMES_DIR.mkdir(exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
        page.goto("http://127.0.0.1:8000", wait_until="networkidle")
        page.wait_for_selector(".sample-card")
        page.wait_for_timeout(400)
        page.screenshot(path=str(FRAMES_DIR / "raw_1.png"))
        page.click(".sample-card:nth-child(1)")
        page.wait_for_selector("#panel-2.active")
        pid = page.evaluate("state.product.id")
        page.click("#btnStructure")
        page.wait_for_selector("#structureResult:not(.hidden)", timeout=30000)
        page.wait_for_timeout(2200)  # 等待图片加载与 toast 消失
        page.screenshot(path=str(FRAMES_DIR / "raw_2.png"))
        page.click("#goto3")
        page.wait_for_selector("#panel-3.active")
        page.click("#pickLanguages .chip:nth-child(2)")
        page.click("#btnGenerate")
        page.wait_for_selector("#generateResult:not(.hidden)", timeout=60000)
        page.wait_for_timeout(2200)
        page.screenshot(path=str(FRAMES_DIR / "raw_3.png"))
        ls = c.get(f"{B}/api/products/{pid}/listings").json()
        alx_en = str(next(l["id"] for l in ls if l["platform"] == "aliexpress" and l["language"] == "en"))
        page.click("#goto4")
        page.wait_for_selector("#panel-4.active")
        page.select_option("#reportListing", alx_en)
        page.wait_for_timeout(600)
        page.screenshot(path=str(FRAMES_DIR / "raw_4.png"))
        page.click("#btnAutofix")
        page.wait_for_timeout(1400)
        page.screenshot(path=str(FRAMES_DIR / "raw_5.png"))
        page.click("#goto5")
        page.wait_for_selector("#panel-5.active")
        page.wait_for_timeout(900)
        page.screenshot(path=str(FRAMES_DIR / "raw_6.png"))
        page.click("#btnApproveAll")
        page.wait_for_timeout(1400)
        page.click("#goto6")
        page.wait_for_selector("#panel-6.active")
        page.click("#btnPublish")
        page.wait_for_selector("#publishResult:not(.hidden)", timeout=30000)
        page.wait_for_timeout(1600)
        page.screenshot(path=str(FRAMES_DIR / "raw_7.png"))
        browser.close()

    return {i: Image.open(FRAMES_DIR / f"raw_{i}.png").convert("RGB") for i in range(1, 8)}


# ---------------- 场景表 ----------------

def build_scenes(shots):
    return [
        {"kind": "card", "img": title_card(), "dur": 4.0},
        {"kind": "scene", "img": shots[1], "step": 1, "dur": 5.0,
         "title": "① 商品录入：内置示例商品，或表单/照片自定义录入",
         "sub": "点击「智能温显保温杯」卡片创建商品", "click": (0.42, 0.34, 1.0)},
        {"kind": "scene", "img": shots[2], "step": 2, "dur": 7.0,
         "title": "② AI 结构化：多模态模型识别商品，输出结构化 PIM 数据",
         "sub": "同步产出合规白底主图（1:1 1200px）与 4:5 / 16:9 / 9:16 多尺寸图"},
        {"kind": "scene", "img": shots[3], "step": 3, "dur": 7.0,
         "title": "③ 文案工厂：一次生成 4 平台 × 多语言全套 Listing",
         "sub": "标题 / 五点描述 / 长描述 / SEO · 多语言为本地化重写而非直译"},
        {"kind": "scene", "img": shots[4], "step": 4, "dur": 6.0,
         "title": "④ 规则引擎「规则即代码」：逐条校验平台规范",
         "sub": "速卖通稿件检出「标题禁用促销词 / 标题超长」等违规项"},
        {"kind": "scene", "img": shots[5], "step": 4, "dur": 6.0,
         "title": "④ 一键自动改写：违规内容按规则库修复，校验全部通过",
         "sub": "修复日志可审计 · 规则变更只需更新规则库版本，不改生成逻辑"},
        {"kind": "scene", "img": shots[6], "step": 5, "dur": 5.0,
         "title": "⑤ 审核工作台：AI 出稿 + 人审放行，全流程留痕",
         "sub": "支持逐条修改与批量放行"},
        {"kind": "scene", "img": shots[7], "step": 6, "dur": 6.5,
         "title": "⑥ 一键上架：四平台批量上架成功，状态回传",
         "sub": "自动生成新品运营任务清单（定价 / 广告素材 / 库存）"},
        {"kind": "card", "img": end_card(), "dur": 5.0},
    ]


# ---------------- 背景乐 ----------------

def make_music(path, total_s):
    """轻氛围乐：C-G-Am-F 琶音 + 软垫底（纯 numpy 合成）"""
    sr = 44100
    bpm = 96
    beat = 60 / bpm
    bar = beat * 2
    chords = [[261.63, 329.63, 392.00], [196.00, 246.94, 392.00],
              [220.00, 261.63, 329.63], [174.61, 220.00, 349.23]]
    n_total = int(total_s * sr)
    mix = np.zeros(n_total)
    t_bar = np.arange(int(bar * sr)) / sr
    env = np.exp(-t_bar * 3.0)
    bars = int(np.ceil(total_s / bar))
    for b in range(bars):
        ch = chords[b % 4]
        base = int(b * bar * sr)
        for vi, f in enumerate(ch):
            for rep in range(2):
                ts = base + rep * int(beat * sr) + vi * int(beat * sr / 3)
                note = 0.14 * env * np.sin(2 * np.pi * f * t_bar)
                e = min(n_total, ts + len(note))
                if ts < n_total and e > ts:
                    mix[ts:e] += note[:e - ts]
        plen = min(len(t_bar), n_total - base)
        if plen > 0:
            pad = sum(0.045 * np.sin(2 * np.pi * (f / 2) * t_bar[:plen]) for f in ch)
            pad *= np.clip(t_bar[:plen] / 0.5, 0, 1) * np.clip((bar - t_bar[:plen]) / 0.5, 0, 1)
            mix[base:base + plen] += pad
    mix = np.tanh(mix * 1.2) * 0.45
    fi, fo = int(1.2 * sr), int(2.0 * sr)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((mix * 32767 * 0.9).astype(np.int16).tobytes())


# ---------------- 编码 ----------------

def write_video(scenes, music_path):
    out = OUT_DIR / "listingforge_demo.mp4"
    total = sum(s["dur"] for s in scenes)
    print(f"合成: {total:.1f}s @ {FPS}fps → {out.name}")
    proc = subprocess.Popen(
        ["ffmpeg", "-y",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-i", str(music_path),
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-shortest", str(out)],
        stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t_done = 0.0
    for si, s in enumerate(scenes):
        n = int(s["dur"] * FPS)
        for f_i in range(n):
            t = f_i / FPS
            if s["kind"] == "card":
                frame = s["img"]
                k = min(1.0, t / 0.5) * min(1.0, (s["dur"] - t) / 0.5)
                if k < 1.0:
                    frame = Image.blend(Image.new("RGB", (W, H), DARK), s["img"], max(0.0, k))
            else:
                frame = scene_frame(s["img"], s["step"], s["title"], s.get("sub", ""),
                                    click=s.get("click"), t=t)
            proc.stdin.write(frame.tobytes())
        t_done += s["dur"]
        print(f"  场景 {si + 1}/{len(scenes)} 完成 ({t_done:.1f}s)")
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg 编码失败")
    return out


if __name__ == "__main__":
    print("1) Playwright 驱动页面截图…")
    shots = capture_scenes()
    print("2) 构建场景…")
    scenes = build_scenes(shots)
    music = FRAMES_DIR / "bgm.wav"
    print("3) 合成背景乐…")
    make_music(music, sum(s["dur"] for s in scenes))
    print("4) 编码视频…")
    out = write_video(scenes, music)
    print("✅ 演示视频:", out)
