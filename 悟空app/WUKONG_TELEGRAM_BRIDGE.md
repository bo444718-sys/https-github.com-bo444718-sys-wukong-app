# 悟空 Telegram / Codex Bridge

这个目录是悟空 Apple App 和现有 Telegram/Codex 机器人的共享工作区。

- 悟空推送模式：push-only，不调用 Telegram getUpdates。
- 推送频率：每 300 秒。
- 最新快照：`wukong_latest_snapshot.json`。
- Telegram 接收和继续操作由现有 Hermes/Codex 网关负责。

当用户在 Telegram 里要求操作悟空时，优先读取 `wukong_latest_snapshot.json`，再根据用户问题给出摘要、风险、候选列表或下一步动作。
所有内容只作为公开研究信号与复盘，不构成投资建议。
