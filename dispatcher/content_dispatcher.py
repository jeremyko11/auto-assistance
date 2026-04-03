#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容分发调度中心 v2.0 (content_dispatcher.py)
==============================================
核心功能：
  1. 素材池管理 - 爬取 → 提炼 → 改写 → 分发全流程
  2. 智能调度 - 根据平台特性和内容质量自动匹配
  3. 多平台发布 - 微博/小红书/抖音/公众号
  4. 运营统计 - 每日/周/月报表

使用示例：
    dispatcher = ContentDispatcher()
    dispatcher.run_full_pipeline()          # 完整流水线
    dispatcher.show_status()               # 查看状态
    dispatcher.interactive_menu()          # 交互式菜单
"""

import os
import sys
import json
import time
import subprocess
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

# Windows UTF-8 支持 (仅在直接运行时生效)
if sys.platform == "win32":
    try:
        import io
        # 只在未包装时包装
        if not isinstance(sys.stdout, io.TextIOWrapper):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        if not isinstance(sys.stderr, io.TextIOWrapper):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from material_pool import MaterialPool


# ========== 配置 ==========

@dataclass
class LLMConfig:
    """LLM配置"""
    api_key: str = "d25220d05c80686af77fcc163c6fe92a:MmRkNjk3MzQ2MGQzMDllNzAyZjM3Mzg0"
    base_url: str = "https://maas-coding-api.cn-huabei-1.xf-yun.com/v2"
    model_id: str = "astron-code-latest"
    max_tokens: int = 4000
    temperature: float = 0.7


@dataclass
class PlatformConfig:
    """平台配置"""
    weibo_cookies: str = ""           # 微博Cookie
    xiaohongshu_cookies: str = ""    # 小红书Cookie
    feishu_app_id: str = "cli_a924ac2afc789bb5"
    feishu_app_secret: str = "rNbgYTiSXcYbUJZ4P4VeYf5DhyoUVllE"


@dataclass
class DispatchConfig:
    """分发配置"""
    llm: LLMConfig = field(default_factory=LLMConfig)
    platform: PlatformConfig = field(default_factory=PlatformConfig)

    # 流水线开关
    auto_crawl: bool = True
    auto_refine: bool = True
    auto_rewrite: bool = True
    auto_dispatch: bool = False       # 默认关闭，需要手动确认

    # 数量限制
    crawl_per_platform: int = 20
    refine_batch_size: int = 10
    rewrite_batch_size: int = 15
    dispatch_per_platform: int = 10


class ContentDispatcher:
    """内容分发调度中心"""

    def __init__(self, config: DispatchConfig = None):
        self.config = config or DispatchConfig()
        self.pool = MaterialPool()
        self.project_root = PROJECT_ROOT
        self.logs: List[str] = []

    # ========== 日志 ==========

    def log(self, msg: str, level: str = "INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {msg}"
        self.logs.append(log_line)
        print(log_line)

    def log_section(self, title: str):
        """分段日志"""
        print(f"\n{'='*55}")
        print(f"  {title}")
        print(f"{'='*55}")

    # ========== 爬取阶段 ==========

    def run_crawl(self, platforms: List[str] = None) -> Dict[str, Any]:
        """触发各平台爬虫"""
        if platforms is None:
            platforms = ["douyin", "weibo", "toutiao"]

        self.log_section("阶段1: 爬取")

        results = {}
        crawler_map = {
            "douyin": ("抖音", "douyin_crawler.py"),
            "weibo": ("微博", "weibo_crawler.py"),
            "toutiao": ("今日头条", "toutiao_crawler.py"),
        }

        for platform in platforms:
            if platform not in crawler_map:
                continue

            name, script = crawler_map[platform]
            self.log(f"触发{name}爬虫: {script}")

            result = self._run_crawler(script)
            results[platform] = result

            if result["status"] == "success":
                self.log(f"✅ {name}爬虫完成", "SUCCESS")
            else:
                self.log(f"❌ {name}爬虫失败: {result.get('message', '未知错误')}", "ERROR")

        # 导入爬取结果到素材池
        imported = self._import_crawl_results()
        self.log(f"导入 {imported} 条素材到素材池")

        return results

    def _run_crawler(self, script_name: str) -> Dict[str, Any]:
        """运行爬虫脚本"""
        script_path = self.project_root / script_name

        if not script_path.exists():
            return {"status": "error", "message": f"脚本不存在: {script_name}"}

        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,
                cwd=str(self.project_root)
            )
            return {
                "status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode,
                "stdout": result.stdout[-300:] if result.stdout else "",
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "执行超时(5分钟)"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _import_crawl_results(self) -> int:
        """从爬虫输出导入素材"""
        count = 0

        # 抖音视频列表
        douyin_files = list(self.project_root.glob("douyin_videos_*.json"))
        if douyin_files:
            latest = max(douyin_files, key=lambda p: p.stat().st_mtime)
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    videos = json.load(f)
                    for video in videos[:self.config.crawl_per_platform]:
                        self.pool.add_raw_material(
                            platform="抖音",
                            author=video.get("author", "未知"),
                            title=video.get("title", ""),
                            content=video.get("desc", ""),
                            url=video.get("url", ""),
                            tags=["短视频", "热门", "抖音"]
                        )
                        count += 1
            except Exception as e:
                self.log(f"导入抖音素材失败: {e}", "WARN")

        # 微博内容
        weibo_files = list(self.project_root.glob("weibo_pygz*.json"))
        if weibo_files:
            latest = max(weibo_files, key=lambda p: p.stat().st_mtime)
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    posts = json.load(f)
                    for post in posts[:self.config.crawl_per_platform]:
                        self.pool.add_raw_material(
                            platform="微博",
                            author=post.get("user", "未知"),
                            title=post.get("text", "")[:50],
                            content=post.get("text", ""),
                            url=post.get("url", ""),
                            tags=["微博", "观点", "热门"]
                        )
                        count += 1
            except Exception as e:
                self.log(f"导入微博素材失败: {e}", "WARN")

        return count

    # ========== 提炼阶段 ==========

    def run_refine(self, raw_limit: int = None) -> Dict[str, Any]:
        """LLM原子化提炼"""
        if raw_limit is None:
            raw_limit = self.config.refine_batch_size

        self.log_section("阶段2: 提炼")

        raw_materials = self.pool.get_raw_materials(status="pending", limit=raw_limit)

        if not raw_materials:
            self.log("没有待处理的素材", "WARN")
            return {"processed": 0, "atoms_created": 0}

        self.log(f"待处理 {len(raw_materials)} 条原始素材")

        results = {"processed": 0, "atoms_created": 0, "failed": []}

        for i, raw in enumerate(raw_materials, 1):
            self.log(f"[{i}/{len(raw_materials)}] 提炼: {raw['title'][:30]}...")
            try:
                atom_ids = self._extract_atoms_from_raw(raw)
                results["atoms_created"] += len(atom_ids)
                results["processed"] += 1
                self.pool.update_raw_status(raw["id"], "processed")
                self.log(f"  ✅ 创建 {len(atom_ids)} 个原子素材", "SUCCESS")
            except Exception as e:
                self.log(f"  ❌ 提炼失败: {e}", "ERROR")
                results["failed"].append({"id": raw["id"], "error": str(e)})

            time.sleep(0.5)  # 避免API过载

        self.log(f"提炼完成: 处理 {results['processed']} 条, 创建 {results['atoms_created']} 个原子")
        return results

    def _extract_atoms_from_raw(self, raw_material: Dict) -> List[str]:
        """从原始素材提炼原子 - 增强版（集成 ip-arsenal 方法论）"""
        prompt = f"""你是知识管理专家，使用Zettelkasten方法处理内容。

任务：从以下素材中提炼「原子笔记」——每个观点一张卡片，独立完整。

【素材信息】
- 来源：{raw_material['platform']}
- 作者：{raw_material['author']}
- 标题：{raw_material['title']}
- 内容：
{raw_material['content'][:2000]}

【提炼要求】
每个原子必须包含：
1. type: "quote"(金句) / "case"(案例) / "cognition"(认知) / "action"(行动)
2. content: 核心观点（50-200字，用自己的话表达）
3. thinking_model: 思维模型（认知偏差/复利效应/人性本质/职场策略等）
4. emotional_resonance: 情感共鸣点（焦虑/希望/认同/惊讶/好奇/赋能）
5. target_audience: 目标受众（职场人/创业者/情感困惑者等）
6. applicable_scenarios: 适用场景（短视频/文章/直播/金句）
7. tags: 标签数组（3-5个）
8. risk_level: 0(安全)/1(需语境)
9. shelf_life: "long"(长效)/"medium"(中效)

【重要】
- 只输出JSON数组，不要其他文字
- 优先提取有情感共鸣的实用观点
- 保留反常识洞察，放弃陈词滥调
- 每条content必须是完整的独立观点

请以JSON数组格式输出："""

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url
            )

            response = client.chat.completions.create(
                model=self.config.llm.model_id,
                messages=[
                    {"role": "system", "content": "你是内容提炼专家。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=self.config.llm.max_tokens,
                temperature=self.config.llm.temperature
            )

            result_text = response.choices[0].message.content

            # 解析JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            atoms_data = json.loads(result_text.strip())
            atom_ids = []

            for atom in atoms_data:
                atom_id = self.pool.add_atom_material(
                    raw_id=raw_material["id"],
                    atom_type=atom.get("type", "quote"),
                    content=atom.get("content", ""),
                    tags=atom.get("tags", []),
                    risk_level=atom.get("risk_level", 0),
                    shelf_life=atom.get("shelf_life", "long"),
                    thinking_model=atom.get("thinking_model", ""),
                    emotional_resonance=atom.get("emotional_resonance", []),
                    target_audience=atom.get("target_audience", []),
                    applicable_scenarios=atom.get("applicable_scenarios", [])
                )
                atom_ids.append(atom_id)

            return atom_ids

        except Exception as e:
            raise Exception(f"LLM调用失败: {e}")

    # ========== 改写阶段 ==========

    def run_rewrite(self, atom_limit: int = None, target_platforms: List[str] = None) -> Dict[str, Any]:
        """多平台改写"""
        if atom_limit is None:
            atom_limit = self.config.rewrite_batch_size
        if target_platforms is None:
            target_platforms = ["微博", "小红书", "抖音", "今日头条"]

        self.log_section("阶段3: 改写")

        atoms = self.pool.query_atoms(risk_max=1, limit=atom_limit)

        if not atoms:
            self.log("没有待改写的素材", "WARN")
            return {"rewritten": 0, "platforms": {}}

        self.log(f"待改写 {len(atoms)} 条原子素材 → {', '.join(target_platforms)}")

        results = {"rewritten": 0, "platforms": {p: 0 for p in target_platforms}}

        for i, atom in enumerate(atoms, 1):
            for platform in target_platforms:
                # 检查是否已有改写
                existing = atom.get("platform_tags", {})
                if platform in existing and existing[platform]:
                    continue  # 跳过已有改写

                self.log(f"[{i}/{len(atoms)}] {atom['type']}:{atom['content'][:20]}... → {platform}")
                try:
                    rewrite = self._rewrite_for_platform(atom, platform)
                    if rewrite:
                        self.pool.update_atom_platform_tags(atom["id"], platform, rewrite)
                        results["platforms"][platform] += 1
                        results["rewritten"] += 1
                except Exception as e:
                    self.log(f"  改写失败: {e}", "ERROR")

            time.sleep(0.3)

        for platform, count in results["platforms"].items():
            self.log(f"  {platform}: {count} 条", "SUCCESS")

        return results

    def _rewrite_for_platform(self, atom: Dict, platform: str) -> Optional[str]:
        """将原子改写为特定平台格式 - 增强版"""
        prompts = {
            "微博": f"""你是一位微博大V，擅长创作引发共鸣的深度短内容。

【素材】
{atom.get('content', '')}
思维模型：{atom.get('thinking_model', '')}
情感共鸣：{', '.join(atom.get('emotional_resonance', []))}

【要求】
- 200-400字的长微博（比传统140字更长但保持精炼）
- 必须有话题标签(如 #{atom.get('tags', ['认知'])[0]}#)
- 结构：开头钩子→核心观点展开→金句收尾→互动引导
- 开头3秒必须抓住注意力（痛点/反常识/数据冲击）
- 有2-3个分段，逻辑清晰
- 结尾引导评论互动
- 符合微博传播规律：有态度、有价值、有槽点

直接输出内容，不要前缀。""",

            "小红书": f"""你是一位小红书爆款博主，擅长创作高收藏量内容。

【素材】
{atom.get('content', '')}
目标受众：{', '.join(atom.get('target_audience', ['年轻人']))}
思维模型：{atom.get('thinking_model', '')}

【要求】
- 800-1200字深度内容（知识干货类）
- 使用丰富的emoji（💡🔥✨❌✅💬📌）
- 结构：开头痛点共鸣→3-5个核心要点（分段）→实用建议→结尾金句
- 开头钩子：痛点共鸣或反常识
- 中间有表格、清单、步骤等可视化元素
- 结尾引导收藏（"收藏这篇下次用"）+ 关注引导
- 标签丰富（5-8个）

直接输出内容。""",

            "抖音": f"""你是一位抖音知识博主，擅长创作高完播率口播稿。

【素材】
{atom.get('content', '')}
适用场景：{', '.join(atom.get('applicable_scenarios', ['短视频']))}

【要求】
- 60秒口播稿（约150-200字）
- 开头3秒必须留人（提问/反常识/悬念）
- 中间逻辑清晰，有案例或金句
- 结尾引导评论（"认同的扣1"）
- 语言口语化，像在和人聊天
- 有节奏感，短句为主

直接输出口播稿。""",

            "今日头条": f"""你是一位今日头条深度作者，擅长创作高阅读量长文。

【素材】
{atom.get('content', '')}
思维模型：{atom.get('thinking_model', '')}
情感共鸣：{', '.join(atom.get('emotional_resonance', []))}

【要求】
- 1200-1800字深度文章
- 结构：热点引入→背景分析→核心观点（3-4个）→案例解读→总结升华
- 开头100字必须抓住注意力（悬念/争议/数据）
- 标题有吸引力：疑问句/数字/对比
- 中间分段清晰，每段有独立小标题或序号
- 有2-3个实际案例或故事
- 结尾有思考引导，不做总结式说教
- 配图建议（可选，用括号标注）

直接输出文章内容和标题。""",

            "公众号": f"""你是一位公众号深度文章作者，擅长写有深度的长文。

【素材】
{atom.get('content', '')}
思维模型：{atom.get('thinking_model', '')}
情感共鸣：{', '.join(atom.get('emotional_resonance', []))}

【要求】
- 1500-2500字深度文章
- 结构：问题引入→理论解读→案例分析→行动建议
- 有独特观点，不是资料搬运
- 结尾引导点在看/转发
- 逻辑严密，论证充分

直接输出文章。"""
        }

        prompt = prompts.get(platform, f"改写为适合{platform}的内容，直接输出。")

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url
            )

            # 根据平台调整max_tokens
            token_map = {
                "微博": 800,
                "小红书": 2500,
                "抖音": 600,
                "今日头条": 3500,
                "公众号": 4000
            }
            max_tokens = token_map.get(platform, 2000)

            response = client.chat.completions.create(
                model=self.config.llm.model_id,
                messages=[
                    {"role": "system", "content": f"你是{platform}内容创作专家。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=max_tokens,
                temperature=0.8
            )

            return response.choices[0].message.content.strip()

        except Exception as e:
            self.log(f"LLM改写失败: {e}", "ERROR")
            return None

    # ========== 分发阶段 ==========

    def run_dispatch(self, platforms: List[str] = None, auto: bool = None) -> Dict[str, Any]:
        """分发内容到各平台"""
        if platforms is None:
            platforms = ["微博"]
        if auto is None:
            auto = self.config.auto_dispatch

        self.log_section("阶段4: 分发")

        if not auto:
            self.log("⚠️ 自动发布已禁用，仅生成待发布队列", "WARN")
            self.log("使用 --auto 参数开启自动发布")

        results = {"dispatched": 0, "queued": 0, "platforms": {p: {"dispatched": 0, "queued": 0} for p in platforms}}

        # 获取待分发内容
        atoms = self.pool.query_atoms(risk_max=0, limit=self.config.dispatch_per_platform * len(platforms))

        if not atoms:
            self.log("没有可分发的安全内容", "WARN")
            return results

        self.log(f"待分发 {len(atoms)} 条原子素材")

        for atom in atoms:
            platform_content = atom.get("platform_tags", {})

            for platform in platforms:
                if platform not in platform_content or not platform_content[platform]:
                    continue

                content = platform_content[platform]

                if auto:
                    # 调用平台发布接口
                    success = self._post_to_platform(platform, content)
                    if success:
                        self.pool.log_dispatch(atom["id"], platform, "success")
                        results["platforms"][platform]["dispatched"] += 1
                        results["dispatched"] += 1
                        self.log(f"✅ 已发布 {platform}: {content[:30]}...", "SUCCESS")
                    else:
                        self.pool.log_dispatch(atom["id"], platform, "failed")
                else:
                    # 加入待发布队列
                    self._add_to_queue(platform, atom, content)
                    results["platforms"][platform]["queued"] += 1
                    results["queued"] += 1

        # 打印待发布队列
        if not auto and results["queued"] > 0:
            self.log("\n📋 待发布队列：")
            for platform, counts in results["platforms"].items():
                if counts["queued"] > 0:
                    self.log(f"  {platform}: {counts['queued']} 条")

        return results

    def _post_to_platform(self, platform: str, content: str) -> bool:
        """调用平台API发布内容"""
        # 自动发帖需要运行独立的poster脚本
        # 当前版本：内容已加入待发布队列
        # 使用以下命令手动触发自动发帖：
        #   python dispatcher/weibo_poster.py --file content_pool/queue_微博.json
        #   python dispatcher/xiaohongshu_poster.py --file content_pool/queue_小红书.json
        self.log(f"已加入 {platform} 待发布队列，请手动运行poster发布", "WARN")
        return False

    def _add_to_queue(self, platform: str, atom: Dict, content: str):
        """加入待发布队列"""
        queue_file = self.project_root / "content_pool" / f"queue_{platform}.json"
        queue = []

        if queue_file.exists():
            try:
                queue = json.loads(queue_file.read_text(encoding="utf-8"))
            except:
                queue = []

        queue.append({
            "atom_id": atom["id"],
            "content": content,
            "tags": atom.get("tags", []),
            "queued_at": datetime.now().isoformat()
        })

        queue_file.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")

    # ========== 状态显示 ==========

    def show_status(self, detailed: bool = False):
        """显示当前状态"""
        stats = self.pool.get_pool_stats()
        dispatch_stats = self.pool.get_dispatch_stats(days=7)

        print(f"""
╔══════════════════════════════════════════════════════════════╗
║              📊 内容分发中心 — 运营状态                        ║
║              {datetime.now().strftime('%Y-%m-%d %H:%M')}                              ║
╠══════════════════════════════════════════════════════════════╣""")

        print(f"║  📦 素材池                                                   ║")
        print(f"║     原始素材: {stats.get('raw_total', 0):>4}  (待处理: {stats.get('raw_by_status', {}).get('pending', 0):>3})               ║")
        print(f"║     原子素材: {stats.get('atoms_total', 0):>4}  (金句:{stats.get('atoms_by_type', {}).get('quote', 0):>3} 案例:{stats.get('atoms_by_type', {}).get('case', 0):>3} 认知:{stats.get('atoms_by_type', {}).get('cognition', 0):>3})   ║")

        # 显示思维模型分布
        if stats.get('atoms_by_model'):
            model_sample = list(stats['atoms_by_model'].items())[:3]
            model_str = " / ".join([f"{m[:4]}:{c}" for m, c in model_sample])
            print(f"║     💡思维模型: {model_str}            ║")

        print(f"║     产品: {stats.get('products_total', 0):>4}  (已发布: {stats.get('products_by_status', {}).get('published', 0):>3})              ║")

        print(f"║                                                              ║")
        print(f"║  📤 近7日分发                                                ║")
        for platform, count in dispatch_stats.items():
            print(f"║     {platform}: {count:>3} 条                                              ║")

        # 检查待发布队列
        for platform in ["微博", "小红书", "抖音", "今日头条"]:
            queue_file = self.project_root / "content_pool" / f"queue_{platform}.json"
            if queue_file.exists():
                try:
                    queue = json.loads(queue_file.read_text(encoding="utf-8"))
                    if queue:
                        print(f"║     📋 {platform}待发布: {len(queue):>3} 条                                    ║")
                except:
                    pass

        print(f"║                                                              ║")
        print(f"╚══════════════════════════════════════════════════════════════╝""")

        if detailed:
            print("\n📋 最近添加的原子素材:")
            atoms = self.pool.query_atoms(limit=5)
            for atom in atoms:
                print(f"  [{atom['type']}] {atom['content'][:40]}...")

    def show_queue(self, platform: str = None):
        """显示待发布队列"""
        platforms = [platform] if platform else ["微博", "小红书", "抖音", "今日头条"]

        for p in platforms:
            queue_file = self.project_root / "content_pool" / f"queue_{p}.json"
            if not queue_file.exists():
                continue

            try:
                queue = json.loads(queue_file.read_text(encoding="utf-8"))
                if not queue:
                    continue

                print(f"\n📋 {p} 待发布队列 ({len(queue)} 条):")
                for i, item in enumerate(queue[:5], 1):
                    print(f"  [{i}] {item['content'][:50]}...")
                if len(queue) > 5:
                    print(f"  ... 还有 {len(queue) - 5} 条")
            except:
                pass

    # ========== 一键运行 ==========

    def run_full_pipeline(self, skip_crawl: bool = False):
        """运行完整流水线"""
        self.logs.clear()
        self.log_section("🚀 启动内容分发流水线")
        self.log(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        start_time = time.time()

        # 1. 爬取
        if not skip_crawl and self.config.auto_crawl:
            self.run_crawl()
        else:
            self.log("跳过爬取阶段")

        # 2. 提炼
        if self.config.auto_refine:
            self.run_refine()
        else:
            self.log("跳过提炼阶段")

        # 3. 改写
        if self.config.auto_rewrite:
            self.run_rewrite()
        else:
            self.log("跳过改写阶段")

        # 4. 分发
        if self.config.auto_dispatch:
            self.run_dispatch(auto=True)
        else:
            self.run_dispatch(auto=False)

        elapsed = time.time() - start_time
        self.log_section("✅ 流水线执行完成")
        self.log(f"总耗时: {elapsed:.1f} 秒")
        self.show_status()

    # ========== 交互式菜单 ==========

    def interactive_menu(self):
        """交互式菜单"""
        while True:
            self.show_status()

            print("""
╔══════════════════════════════════════════════════════════════╗
║                    📋 内容分发中心 — 操作菜单                   ║
╠══════════════════════════════════════════════════════════════╣
║  [1] 完整流水线     [2] 仅爬取      [3] 仅提炼     [4] 仅改写   ║
║  [5] 分发内容      [6] 查看队列    [7] 查看状态   [8] 生成报告  ║
║  [0] 退出                                                       ║
╚══════════════════════════════════════════════════════════════╝""")

            try:
                choice = input("\n请输入选项 [0-8]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n退出...")
                break

            if choice == "1":
                self.run_full_pipeline()
            elif choice == "2":
                self.run_crawl()
            elif choice == "3":
                self.run_refine()
            elif choice == "4":
                self.run_rewrite()
            elif choice == "5":
                self.run_dispatch(auto=False)
            elif choice == "6":
                self.show_queue()
            elif choice == "7":
                self.show_status(detailed=True)
            elif choice == "8":
                print(self.get_daily_report())
            elif choice == "0":
                print("\n退出...")
                break
            else:
                print("无效选项，请重新输入")

            input("\n按回车继续...")

    # ========== 报告 ==========

    def get_daily_report(self) -> str:
        """生成每日工作报告"""
        stats = self.pool.get_pool_stats()
        dispatch_stats = self.pool.get_dispatch_stats(days=1)

        return f"""
╔══════════════════════════════════════════════════════════════╗
║              📊 虚拟资料项目 — 每日工作报告                     ║
║              {datetime.now().strftime('%Y-%m-%d %H:%M')}                              ║
╠══════════════════════════════════════════════════════════════╣
║  📦 素材池概况                                               ║
║     原始素材总数：{stats.get('raw_total', 0):>4}                                      ║
║     待处理：{stats.get('raw_by_status', {}).get('pending', 0):>4}  |  已处理：{stats.get('raw_by_status', {}).get('processed', 0):>4}                   ║
║     原子素材总数：{stats.get('atoms_total', 0):>4}                                      ║
║                                                              ║
║  📤 今日分发                                                  ║
║     微博：{dispatch_stats.get('微博', 0):>4}  |  小红书：{dispatch_stats.get('小红书', 0):>4}  |  抖音：{dispatch_stats.get('抖音', 0):>4}          ║
║                                                              ║
║  📚 产品概况                                                  ║
║     产品总数：{stats.get('products_total', 0):>4}  |  已发布：{stats.get('products_by_status', {}).get('published', 0):>4}  |  草稿：{stats.get('products_by_status', {}).get('draft', 0):>4}            ║
╚══════════════════════════════════════════════════════════════╝
"""


# ========== CLI 入口 ==========

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="内容分发调度中心 v2.0",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python content_dispatcher.py                    # 交互式菜单
  python content_dispatcher.py --mode full       # 完整流水线
  python content_dispatcher.py --mode refine      # 仅提炼
  python content_dispatcher.py --status          # 查看状态
  python content_dispatcher.py --queue 微博       # 查看待发布队列
        """
    )

    parser.add_argument("--mode", choices=["full", "crawl", "refine", "rewrite", "dispatch", "report", "menu"],
                        default="menu", help="运行模式")
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬取阶段")
    parser.add_argument("--auto", action="store_true", help="开启自动发布")
    parser.add_argument("--status", action="store_true", help="显示当前状态")
    parser.add_argument("--queue", metavar="PLATFORM", help="查看待发布队列")
    parser.add_argument("--platforms", nargs="+", default=["微博"], help="目标平台")

    args = parser.parse_args()

    dispatcher = ContentDispatcher()

    if args.status:
        dispatcher.show_status(detailed=True)
        return

    if args.queue:
        dispatcher.show_queue(args.queue)
        return

    if args.mode == "menu":
        dispatcher.interactive_menu()
    elif args.mode == "full":
        dispatcher.run_full_pipeline(skip_crawl=args.skip_crawl)
    elif args.mode == "crawl":
        dispatcher.run_crawl()
    elif args.mode == "refine":
        print(dispatcher.run_refine())
    elif args.mode == "rewrite":
        print(dispatcher.run_rewrite(target_platforms=args.platforms))
    elif args.mode == "dispatch":
        print(dispatcher.run_dispatch(platforms=args.platforms, auto=args.auto))
    elif args.mode == "report":
        print(dispatcher.get_daily_report())


if __name__ == "__main__":
    main()