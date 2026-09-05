# -*- coding: utf-8 -*-
"""ListingForge 一键启动入口"""
import uvicorn

if __name__ == "__main__":
    print("=" * 56)
    print("  ListingForge · AI 智能上新引擎 Demo")
    print("  体验地址:  http://127.0.0.1:8000")
    print("  接口文档:  http://127.0.0.1:8000/docs")
    print("=" * 56)
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
