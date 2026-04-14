"""
跨实例记忆同步插件 (Memory Sync Bridge) - v1.1.0
功能：监控本地 learnings 目录，将新增或变更的经验记录通过 A2A 协议同步到远程 AstrBot 实例。
改进：增加内容 Hash 去重、重试机制、优雅退出、过滤规则。
"""

import os
import time
import asyncio
import hashlib
import aiohttp
from astrbot.api.all import *

logger = logging.getLogger("AstrBot.memory_sync_bridge")

# 默认配置
DEFAULT_CONFIG = {
    "remote_a2a_url": "http://192.168.100.1:6185/api/plug/astrbot_plugin_a2a_gateway/api/a2a/proxy",
    "remote_token": "my_secure_token_2026",
    "learnings_dir": "/AstrBot/data/learnings/",
    "sync_interval": 30,
    "file_filter": "*.md",
    "content_max_length": 3000,
    "retry_count": 3
}

@register("astrbot_plugin_memory_sync", "记忆同步桥接", "1.1.0", "door")
class MemorySyncBridge(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.context = context
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        
        self.learnings_dir = self.config["learnings_dir"]
        self.remote_a2a_url = self.config["remote_a2a_url"]
        self.remote_token = self.config["remote_token"]
        self.sync_interval = int(self.config["sync_interval"])
        self.retry_count = int(self.config["retry_count"])
        
        # 记录 {filepath: {"mtime": float, "hash": str}}
        self.watched_files = {} 
        self.running = True
        self.sync_task = None
        
        # 确保监控目录存在
        if not os.path.exists(self.learnings_dir):
            os.makedirs(self.learnings_dir, exist_ok=True)
            
        logger.info(f"🕊️ 记忆同步桥接 v1.1.0 启动。目标: {self.remote_a2a_url}")
        
        # 启动后台轮询任务
        self.sync_task = asyncio.create_task(self.sync_loop())

    async def terminate(self):
        """插件卸载/重载时的清理逻辑"""
        logger.info("🛑 正在停止记忆同步任务...")
        self.running = False
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass

    async def sync_loop(self):
        logger.info(f"⏳ 轮询循环启动 (间隔 {self.sync_interval}s)。")
        await self._scan_current_files()
        
        while self.running:
            try:
                await self.check_for_new_memories()
            except Exception as e:
                logger.error(f"同步循环异常: {e}")
            await asyncio.sleep(self.sync_interval)

    def _calc_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    async def _scan_current_files(self):
        if not os.path.exists(self.learnings_dir): return
        import fnmatch
        all_files = os.listdir(self.learnings_dir)
        
        for f in all_files:
            if fnmatch.fnmatch(f, self.config.get("file_filter", "*.md")):
                path = os.path.join(self.learnings_dir, f)
                try:
                    with open(path, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    self.watched_files[path] = {
                        "mtime": os.path.getmtime(path),
                        "hash": self._calc_hash(content)
                    }
                except Exception as e:
                    logger.warning(f"扫描 {f} 失败: {e}")
        logger.info(f"📂 已索引 {len(self.watched_files)} 个文件指纹。")

    async def check_for_new_memories(self):
        if not os.path.exists(self.learnings_dir): return
        import fnmatch

        try:
            current_files = os.listdir(self.learnings_dir)
        except Exception as e:
            logger.warning(f"扫描目录失败: {e}")
            return

        for f in current_files:
            if not fnmatch.fnmatch(f, self.config.get("file_filter", "*.md")):
                continue
                
            path = os.path.join(self.learnings_dir, f)
            try:
                mtime = os.path.getmtime(path)
                last_record = self.watched_files.get(path, {})
                last_mtime = last_record.get("mtime", 0)
                
                # 如果修改时间变新了，再算 Hash 确认内容是否真的变了
                if mtime > last_mtime:
                    with open(path, 'r', encoding='utf-8') as fp:
                        content = fp.read()
                    
                    current_hash = self._calc_hash(content)
                    last_hash = last_record.get("hash", "")
                    
                    if current_hash != last_hash:
                        logger.info(f"📝 发现真实变更: {f}")
                        # 发送成功后才更新记录，失败则下次重试
                        if await self.process_and_send(path, content):
                            self.watched_files[path] = {"mtime": mtime, "hash": current_hash}
            except Exception as e:
                logger.warning(f"检查 {f} 时出错: {e}")

    async def process_and_send(self, file_path: str, content: str) -> bool:
        filename = os.path.basename(file_path)
        summary = content.split('\n')[0][:100] + "..." if content else "无标题"
        
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
                        f"📄 **Content**:\n```markdown\n{content[:self.config['content_max_length']]}\n```\n\n"
                        f"[指令] 请 Pinna 接收此记忆并归档。"
                    )
                }
            }
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.remote_token}"
        }
        
        # 重试机制
        for attempt in range(self.retry_count):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.remote_a2a_url, json=payload, headers=headers, timeout=10) as resp:
                        if resp.status == 200:
                            logger.info(f"✅ 同步成功: {filename}")
                            return True
                        else:
                            text = await resp.text()
                            logger.error(f"❌ 远端拒绝: {resp.status} - {text}")
                            return False # 远端明确拒绝，不重试
            except Exception as e:
                logger.warning(f"⏳ 同步失败 (尝试 {attempt+1}/{self.retry_count}): {e}")
                await asyncio.sleep(2 ** attempt) # 指数退避
        
        logger.error(f"💀 同步彻底失败: {filename}")
        return False

    @command("sync_test")
    async def cmd_sync_test(self, event: AstrMessageEvent):
        yield event.make_result().message("🧪 开始同步测试...")
        test_file = os.path.join(self.learnings_dir, "SYNC_TEST_TEMP.md")
        content = f"# Sync Test\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n手动测试"
        with open(test_file, 'w') as f:
            f.write(content)
            
        success = await self.process_and_send(test_file, content)
        if os.path.exists(test_file): os.remove(test_file)
        
        yield event.make_result().message("✅ 测试完成。" if success else "❌ 测试失败，请检查日志。")