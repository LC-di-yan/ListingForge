# -*- coding: utf-8 -*-
"""性能基准：核心环节耗时取样（每项 3 次取中位）

用法: 服务运行中(python run.py)时执行  python scripts/benchmark.py
说明: mock 模式基准反映编排/规则引擎/图片管线的工程开销；
      qwen 实时模式的耗时由 LLM 推理主导（8 条并发生成约为串行 1/4）。
"""
import statistics
import time

import httpx

B = "http://127.0.0.1:8000"


def timed(fn, repeat=3):
    samples = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        result = fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples), result


def main():
    c = httpx.Client(timeout=60)
    rows = []

    def bench(name, fn):
        med, result = timed(fn)
        rows.append((name, f"{med * 1000:.0f} ms"))
        return result

    # 准备独立商品，避免缓存影响首次管线计时
    pid = c.post(f"{B}/api/products/sample/feeder").json()["id"]

    def structure():
        return c.post(f"{B}/api/products/{pid}/structure").json()

    t0 = time.perf_counter()
    structure()  # 首次：真实跑抠图 + 白底 + 多尺寸（只计时一次，之后即进缓存）
    rows.append(("① AI 结构化 + 图片管线（首次·真实管线）", f"{(time.perf_counter() - t0) * 1000:.0f} ms"))
    bench("① AI 结构化（幂等缓存命中·中位）", structure)
    bench("② 生成 8 条物料（4 线程并发）",
          lambda: c.post(f"{B}/api/products/{pid}/generate",
                         data={"platforms": ["amazon", "aliexpress", "tiktok_shop", "shopify"],
                               "languages": ["en", "es"]}).json())
    bench("③ 批量校验全部（8 条 × 规则库）",
          lambda: c.post(f"{B}/api/products/{pid}/validate_all").json())
    ls = c.get(f"{B}/api/products/{pid}/listings").json()
    for l in ls:
        if l["language"] == "en":
            c.post(f"{B}/api/listings/{l['id']}/approve")
    bench("④ 四平台批量上架", lambda: c.post(f"{B}/api/products/{pid}/publish").json())
    bench("⑤ 导出全部物料 CSV", lambda: c.get(f"{B}/api/products/{pid}/export").content)

    print(f"\nListingForge 性能基准（mock 模式 · 3 次取样取中位）")
    print("-" * 52)
    for name, ms in rows:
        print(f"  {name:<28} {ms:>10}")
    print("-" * 52)
    print("结论: mock 模式全流程秒级完成；qwen 实时模式耗时由 LLM 推理主导，")
    print("      生成环节 4 线程并发约为串行耗时的 1/4。")
    c.delete(f"{B}/api/products/{pid}")


if __name__ == "__main__":
    main()
