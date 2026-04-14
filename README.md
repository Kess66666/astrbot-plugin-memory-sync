# 🕊️ AstrBot 跨实例记忆同步插件 (Memory Sync Bridge)

通过 [A2A 协议](https://github.com/door/astrbot-plugin-a2a-gateway) 将本地 `learnings/` 目录中的经验记录自动同步到远程 AstrBot 实例。

## ✨ 功能特性

- **自动监听**: 后台轮询监控本地 `learnings/` 目录的文件变更
- **智能去重**: 基于 SHA-256 内容指纹，仅同步内容真正变更的文件
- **蒸馏同步**: 只同步 `.md` 格式的经验总结，不传输原始对话记录
- **A2A 集成**: 无缝对接现有的 A2A Gateway 通信链路
- **可配置**: 支持自定义目标地址、Token、轮询间隔、文件过滤规则
- **生产级健壮性**: 重试机制、指数退避、优雅退出、黑白名单支持

## 📦 安装

1. 将此插件文件夹放入 AstrBot 的 `data/plugins/` 目录
2. 在 AstrBot 管理面板中重载/安装插件
3. 配置 `config.yaml`（见下方说明）

## ⚙️ 配置

在 AstrBot 面板的插件配置中，或手动创建 `config.yaml`：

```yaml
# 远程 A2A 接收地址
remote_a2a_url: "http://<PINNA_IP>:6185/api/plug/astrbot_plugin_a2a_gateway/api/a2a/proxy"

# 认证 Token（需与 A2A Gateway 配置的 Token 一致）
remote_token: "your_secure_token_here"

# 本地监控目录（默认路径）
learnings_dir: "/AstrBot/data/learnings/"

# 轮询间隔（秒）
sync_interval: 30

# 文件过滤规则（支持通配符）
file_filter: "*.md"

# 内容最大长度（截断）
content_max_length: 3000

# 网络重试次数
retry_count: 3
```

## 🧪 使用

### 自动同步
插件启动后会自动在后台运行，每 30 秒扫描一次 `learnings/` 目录。
当有新的 `.md` 文件或文件内容发生变更时，会自动打包并通过 A2A 发送到远程实例。

### 手动测试
发送指令 `/sync_test` 可手动触发一次同步测试，验证链路是否通畅。

## 🔍 同步内容格式

发送到远程实例的消息格式：
```markdown
🚨 **[SYSTEM_SYNC: MEMORY_UPDATE]**
👤 **Source**: Door (N100 Debian)
📂 **File**: ERR-20260407-001.md
📝 **Summary**: 热重载环境变量未开启导致代码未生效...

📄 **Content**:
[文件完整内容，截断至 3000 字符]
```

远程实例接收到此消息后，可通过 `self-improving-agent` 等记忆插件自动归档。

## 🏗️ 架构说明

```
[Door 实例]                     [Pinna 实例]
    │                               │
    ├── learnings/                  │
    │   └── *.md (经验记录)         │
    │                               │
    ├── Memory Sync Bridge ────────▶│ A2A Gateway
    │   (监听 + 发送)               │   (接收 + 处理)
    │                               │
    └── SHA-256 去重                └── 自动归档到本地记忆库
    └── 重试 + 指数退避
```

## 📝 更新日志

- **v1.1.0** (2026-04-14)
  - ✨ 新增 SHA-256 内容指纹去重
  - ✨ 新增网络重试 + 指数退避策略
  - ✨ 新增 `terminate()` 优雅退出
  - ✨ 新增文件过滤规则（黑白名单支持）
  - 🐛 修复插件卸载后僵尸任务问题
  - 🐛 修复内容未变却重复发送的问题

- **v1.0.0** (2026-04-14)
  - 初始版本发布
  - 支持基础的文件监听与 A2A 同步
  - 提供 `/sync_test` 测试指令

## ⚠️ 注意事项

1. **单向同步**: 当前版本仅支持从 Door → Pinna 的单向同步
2. **冲突处理**: 采用 Last-Write-Wins 策略，以最新内容指纹为准
3. **文件大小**: 单个文件超过 3000 字符的内容会被截断
4. **网络依赖**: 需要 Door 实例能够网络访问 Pinna 的 A2A 接口

## 🤝 贡献

欢迎提交 Issue 或 PR！

## 📄 License

MIT
