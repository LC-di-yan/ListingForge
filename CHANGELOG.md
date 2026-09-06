# CHANGELOG

## v1.5.0 — 前端专项（2026-09-06）

第五轮优化，主题「现代前端体验」，全部零依赖 vanilla 实现：

- **暗色模式**：69 处硬编码颜色全部令牌化，`.dark` 深灰主题（非纯黑），顶栏切换 + localStorage 持久化 + `prefers-color-scheme` 默认
- **⌘K 命令面板**：模糊搜索步骤/商品切换/主题/导出（灵感 cmdk / GitHub palette，轻量自研 ~80 行）
- **成功彩带**：四平台上架成功触发 canvas 彩带（灵感 catdad/canvas-confetti，内联实现，`prefers-reduced-motion` 降级）
- **骨架屏**：结构化/生成/校验异步等待期显示形状匹配 shimmer 骨架
- **自定义模态**：promise 化 `uiConfirm` 替换 2 处原生 confirm
- **一键复制**：Listing 标题/五点/描述 hover 复制按钮；**图片灯箱**：白底主图/变体点击放大
- **键盘快捷键**：1-6 切步骤 / D 切主题 / ? 帮助；顶部步骤进度条；统计数字 CountUp
- **A11y**：aria-label 补齐、`:focus-visible` 样式、reduced-motion 降级
- UI 冒烟 12 → **19 项**（主题切换/持久化、命令面板、灯箱、快捷键、复制、审计行）

## v1.4.0 — 交付成熟度（2026-09-06）

第四轮优化：

- **物料导出 CSV**：`GET /api/products/{id}/export`（UTF-8 BOM，Excel 中文兼容，逗号/换行/引号转义），第 6 步一键下载，打通"生成→审核→交付"最后一米
- **规则引擎注册表化重构**：`_eval_rule` 11 分支 / `autofix` 9 分支长链改为 `@register_check` / `@register_fix` 注册表分发，新增规则类型 = 注册一个函数（37 用例回归保护，行为零变化）
- **500 错误治理**：对外统一通用文案，异常详情仅入服务端日志，`LISTINGFORGE_DEBUG=1` 联调可开
- **一键打包** `scripts/package.py`（git archive + CI 追加 + 22 项关键文件自检）；**性能基准** `scripts/benchmark.py`（首次管线 219ms / 幂等 10ms / 生成 8 条 199ms / 全流程 <1s）
- 测试 37 → 40（导出转义、500 治理、注册表覆盖）

## v1.3.0 — 可审计性闭环（2026-09-06）

第三轮优化，主题「承诺与实现一致」：

- **规则库版本化真正落地**：`app/rules/*.json` 增加 `version` 元字段，校验报告的 `ruleset_version` 从规则库读取（此前硬编码 v1.0.0，规则改了两轮版本号不变）
- **自动改写日志落库**：`fix_log` 并入校验报告持久化，前端报告区展示"上次自动改写 N 项 + 规则清单 + 时间"，兑现"全流程留痕可追溯"
- 校验报告增加 `validated_at` 时间戳
- **测试盲区补齐**：qwen 实时模式（mock 传输层）——JSON 解析 / VL 消息构造 / 异常自动降级；本地化 fallback；非白底图片规则拦截；删除级联（26 → 34 用例）
- 重新生成前确认（防误清已放行物料）；上传文件名 uuid 化防同秒覆盖
- 新增 `CHANGELOG.md`；技术说明补部署安全边界

## v1.2.0 — 第二轮全面优化（2026-09-06）

- 修复重复生成物料翻倍（重建式生成）；上传文件名路径穿越修复 + 扩展名白名单
- VL 图片预处理（大图压缩 + EXIF 转正）；PIM 渲染转义；`.env` 防误提交
- 审核台保存草稿、商品删除、阿语 RTL、生成页展开全部
- 新规则 `keyword_hits`（标题关键词布局，四平台共 27 条）；规则引擎词边界截断统一
- pytest 26 用例；`scripts/ui_smoke.py`（Playwright 六步流 11 项断言）

## v1.1.0 — 第一轮全面优化（2026-09-06）

- 会话恢复 + 历史商品切换；全物料合规校验矩阵 + 批量校验接口
- 生成接口 4 线程并发；图片管线幂等缓存；SQLite WAL + 索引
- 修复 requirements 缺失 opencv/numpy（评审新机会崩）
- lifespan / 上传校验 / 日志 / 规则库热加载；pytest 19 用例；GitHub Actions 工作流
- README 截图 + CI 徽章 + LICENSE + `.env.example`

## v1.0.0 — 可运行 Demo（2026-09-06）

- FastAPI 六步流编排 + 零构建 SPA 工作台
- 双轨文案引擎（本地模拟 / 阿里云百炼 qwen-vl-max + qwen-plus，失败自动降级）
- 平台规则引擎（规则即代码：4 平台规则库 + 校验 + 6 类自动改写）
- 图片管线（OpenCV 抠图 → 白底主图 → 4 尺寸适配 → 场景图）
- 演示视频合成脚本、E2E 脚本、技术说明、体验方式
