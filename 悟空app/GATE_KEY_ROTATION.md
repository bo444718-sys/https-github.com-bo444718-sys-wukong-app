# Gate Key Rotation

## 目的

当前聊天中出现过的 Gate Key 只能用于只读验证和 dry-run，不允许实盘下单。

## 换 Key 步骤

1. 在 Gate 撤销旧 Key。
2. 创建新的未暴露 Key。
3. 只开放必要交易权限。
4. 设置 IP 白名单。
5. 把新 Key 写入本机后端文件：

```bash
/Users/wangbo/Documents/New project/悟空app/.env.gate
```

字段模板见 `.env.gate.example`。

## 实盘准入

系统会自动检查：

- 新 Key 未命中已暴露指纹
- Gate 私有 API 可认证
- IP 白名单已配置
- 单笔限额已配置
- 每日亏损熔断已配置
- 手动确认签名已配置

全部通过后，才能进入手动确认实盘候选。无人值守自动实盘保持关闭。
