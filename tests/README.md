# tests/ · 测试

- `backend/tests/` —— 各模块 pytest 用例（P0 模块必须过）。
- `frontend/` 前端单测可放 `frontend/__tests__`。
- `tests/` 根目录可放跨端契约测试（如对照 `docs/api-contract.md` 校验 schema）。

## 建议
- 后端：pytest + httpx AsyncClient，覆盖诊断/匹配/支付状态机/启动包生成。
- 支付：用 mock 回调验证状态机时间戳（M5-05）与防漏单（M5-06）。
- 合规：扫描依赖许可（禁 GPL/AGPL）、确认免费层不限次/无水印/无广告。
