"""
跨实例记忆同步插件 (Memory Sync Bridge)。
功能：监控本地 learnings 目录，将新增或变更的经验记录通过 A2A 协议同步到远程 AstrBot 实例。

配置项 (config.yaml):
  - remote_a2a_url: 远程 A2A 接收地址 (默认: http://192.168.100.1:6185/api/plug/astrbot_plugin_a2a_gateway/api/a2a/proxy)
  - remote_token: 认证 Token (默认: my_secure_token_2026)
  - learnings_dir: 本地监控目录 (默认: /AstrBot/data/learnings/)
  - sync_interval: 轮询间隔秒数 (默认: 30)
"""

import os
import time
import asyncio
import aiohttp
from astrbot.api.all import *

logger = logging.getLogger("AstrBot.memory_sync_bridge")


@register("astrbot_plugin_memory_sync", "记忆同步桥接", "1.0.0", "door")
class MemorySyncBridge(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.context = context
        self.config = config or {}
        
        # 从配置读取参数，或使用默认值
        self.learnings_dir = self.config.get("learnings_dir", "/AstrBot/data/learnings/")
        self.remote_a2a_url = self.config.get("remote_a2a_url", "http://192.168.100.1:6185/api/plug/astrbot_plugin_a2a_gateway/api/a2a/proxy")
        self.remote_token = self.config.get("remote_token", "my_secure_token_2026")
        self.sync_interval = int(self.config.get("sync_interval", 30))
        
        self.watched_files = {}  # 记录 {filepath: mtime}，用于去重
        
        # 确保监控目录存在
        if not os.path.exists(self.learnings_dir):
            os.makedirs(self.learnings_dir, exist_ok=True)
            
        logger.info(f"🕊️ 记忆同步桥接插件已启动。监控目录: {self.learnings_dir}，目标地址: {self.remote_a2a_url}，间隔: {self.sync_interval}s")
        
        # 启动后台轮询任务
        asyncio.create_task(self.sync_loop())

    async def sync_loop(self):
        logger.info(f"⏳ 记忆同步轮询循环已启动 (间隔 {self.sync_interval}s)。")
        # 初始化当前状态，避免启动时全量轰炸
        await self._scan_current_files()
        
        while True:
            try:
                await self.check_for_new_memories()
            except Exception as e:
                logger.error(f"同步循环异常: {e}")
            await asyncio.sleep(self.sync_interval)

    async def _scan_current_files(self):
        """扫描现有文件并记录时间戳"""
        if not os.path.exists(self.learnings_dir): return
        for f in os.listdir(self.learnings_dir):
            if f.endswith(".md"):
                path = os.path.join(self.learnings_dir, f)
                self.watched_files[path] = os.path.getmtime(path)
        logger.info(f"📂 已索引 {len(self.watched_files)} 个现有记忆文件。")

    async def check_for_new_memories(self):
        """检查新增或修改的文件"""
        if not os.path.exists(self.learnings_dir): return

        current_files = {}
        try:
            for f in os.listdir(self.learnings_dir):
                if f.endswith(".md"):
                    path = os.path.join(self.learnings_dir, f)
                    current_files[path] = os.path.getmtime(path)
        except Exception as e:
            logger.warning(f"扫描目录失败: {e}")
            return

        for path, mtime in current_files.items():
            last_mtime = self.watched_files.get(path, 0)
            
            # 如果修改时间变新了
            if mtime > last_mtime:
                logger.info(f"📝 发现记忆变更: {os.path.basename(path)}")
                await self.process_and_send(path)
                self.watched_files[path] = mtime

    async def process_and_send(self, file_path):
        """读取文件并通过 A2A 发送"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            filename = os.path.basename(file_path)
            # 提取摘要（取前 100 字或第一行）
            summary = content.split('\n')[0] if content else "无标题"
            if len(summary) > 100: summary = summary[:100] + "..."
            
            # 构造 A2A Payload
            payload = {
                "jsonrpc": "2.0",
                "id": f"mem-sync-{int(time.time())}",
                "method": "message",
                "params": {
                    "message": {
                        "role": "user",
                        "content": (
                            f"🚨 **[SYSTEM_SYNC: MEMORY_UPDATE]**\n"
                            f"👤 **Source**: Door (N100 Debian)\n"
                            f"📂 **File**: {filename}\n"
                            f"📝 **Summary**: {summary}\n\n"
                            f"📄 **Content**:\n```markdown\n{content[:3000]}\n```\n\n"
                            f"[指令] 请接收此记忆并归档到你的本地知识库中。"
                        )
                    }
                }
            }
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.remote_token}"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(self.remote_a2a_url, json=payload, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        logger.info(f"✅ 记忆已成功同步: {filename}")
                    else:
                        text = await resp.text()
                        logger.error(f"❌ 同步失败: {resp.status} - {text}")
                        
        except Exception as e:
            logger.error(f"处理文件 {file_path} 失败: {e}")

    @command("sync_test")
    async def cmd_sync_test(self, event: AstrMessageEvent):
        """手动触发一次同步测试"""
        yield event.make_result().message("🧪 开始同步测试... 请观察日志。")
        test_file = os.path.join(self.learnings_dir, "SYNC_TEST_TEMP.md")
        with open(test_file, 'w') as f:
            f.write("# Sync Test\n这是一次手动触发的同步测试。")
        
        await self.process_and_send(test_file)
        os.remove(test_file)
        yield event.make_result().message("✅ 测试完成。")