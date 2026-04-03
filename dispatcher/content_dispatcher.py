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

    def generate_from_topic(self, topic: str, count: int = 8) -> Dict[str, Any]:
        """根据话题生成素材（LLM直接生成，无需爬取）"""
        self.log_section(f"话题生成: {topic}")

        prompt = f"""你是一个自动化内容官，根据给定话题生成高质量原始素材。

话题：{topic}

【约束要求 - 必须严格遵守】
1. 数量：生成5-10条独立的原子素材
2. 每条素材必须同时包含三个维度：
   - 认知(Cognition)：提供深度洞察、逻辑底层或独特思考视角
   - 金句(Golden Sentence)：极具传播力、朗朗上口的总结性短句
   - 行动(Action)：具体可执行、可操作的步骤或建议
3. 素材之间不能重复，覆盖面要广

【每条原始素材格式】
{{
  "platform": "微博/抖音/小红书/今日头条",
  "author": "拟人化作者名（如九边、职场大叔）",
  "title": "吸引人的标题（15-30字）",
  "content": "详细内容（300-800字），必须同时包含：认知洞察+金句+可执行建议",
  "cognition": "本条的核心认知或独特视角（50-150字）",
  "golden_sentence": "传播金句（20字内）",
  "action": "可执行建议或步骤（50-150字）",
  "tags": ["标签1", "标签2", "标签3"]
}}

【风格要求】
- 内容要有深度，不是浮于表面
- 有反常识观点或独特视角
- 情感共鸣强（焦虑/希望/认同/惊讶）
- 实用性强，能给人启发

请生成{count}条素材，输出JSON数组格式："""

        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.config.llm.api_key,
                base_url=self.config.llm.base_url
            )

            response = client.chat.completions.create(
                model=self.config.llm.model_id,
                messages=[
                    {"role": "system", "content": "你是内容策划专家，擅长创作引发共鸣的深度内容。"},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=4000,
                temperature=0.8
            )

            result_text = response.choices[0].message.content.strip()

            # 解析JSON
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
                result_text = result_text.strip()

            materials = json.loads(result_text)
            added_count = 0

            for m in materials:
                self.pool.add_raw_material(
                    platform=m.get("platform", "微博"),
                    author=m.get("author", "未知"),
                    title=m.get("title", ""),
                    content=m.get("content", ""),
                    url="",
                    tags=m.get("tags", [topic])
                )
                added_count += 1

            self.log(f"✅ 已生成 {added_count} 条素材")
            return {"generated": added_count, "topic": topic}

        except Exception as e:
            self.log(f"❌ 素材生成失败: {e}", "ERROR")
            return {"generated": 0, "error": str(e)}

    def run_full_flow(self, topic: str, platforms: List[str] = None) -> Dict[str, Any]:
        """从话题到发布的完整流程"""
        if platforms is None:
            platforms = ["微博", "小红书", "抖音", "今日头条"]

        self.log_section(f"完整流程: {topic} → 多平台发布")

        results = {}

        # Step 1: 话题生成素材
        gen = self.generate_from_topic(topic)
        results["generate"] = gen
        if gen.get("generated", 0) == 0:
            return results

        # Step 2: 提炼原子
        refine = self.run_refine(raw_limit=gen["generated"])
        results["refine"] = refine

        # Step 3: 多平台改写
        rewrite = self.run_rewrite(atom_limit=10, target_platforms=platforms)
        results["rewrite"] = rewrite

        # Step 4: 加入待发布队列
        dispatch = self.run_dispatch(platforms=platforms, auto=False)
        results["dispatch"] = dispatch

        self.log_section("流程完成")
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    📊 执行结果汇总                          ║
╠══════════════════════════════════════════════════════════════╣
║  话题: {topic}
║  生成素材: {gen.get('generated', 0)} 条
║  提炼原子: {refine.get('atoms_created', 0)} 个
║  改写平台: {rewrite.get('rewritten', 0)} 条
║  待发布队列: {sum(dispatch.get('platforms', {}).values())} 条
╚══════════════════════════════════════════════════════════════╝
""")
        return results

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
        """从原始素材提炼原子 - 高转化版"""
        prompt = f"""你是知识管理专家，使用Zettelkasten方法处理内容。

任务：从以下素材中提炼「高价值原子笔记」——目标是产出能引爆曝光、带来粉丝转化的内容。

【素材信息】
- 来源：{raw_material['platform']}
- 作者：{raw_material['author']}
- 标题：{raw_material['title']}
- 内容：
{raw_material['content'][:2000]}

【原子提炼约束 - 必须严格遵守】
每条原子必须同时包含以下四个维度：

1. 认知 (Cognition) - 必须包含"反常识"或"痛点扎心"视角，触发用户点击欲望
2. 金句 (Golden Sentence) - 易传播 + 具备"身份认同感"，让用户觉得"这就是我想说的"
3. 行动 (Action) - 升级为"即得利益"：告诉用户照做后立刻能获得的具体好处
4. 情绪锚点 (Emotional Hook) - 挖掘能引起焦虑、共鸣或爽感的点，这是曝光核心驱动

【每条原子必须包含的字段】
1. type: "cognition"(认知) / "quote"(金句) / "action"(行动) / "case"(案例)
2. cognition: 反常识/痛点洞察（50-150字），让人"哇"的观点
3. golden_sentence: 身份认同金句（20字内），用户看完想说"太对了"
4. action: 即得利益（50-150字），明确告诉用户"做完这件事，你会获得XX"
5. emotional_hook: 情绪锚点（20字内），如"焦虑感/共鸣感/爽感"
6. thinking_model: 思维模型（认知偏差/复利效应/人性本质/职场策略等）
7. emotional_resonance: 情感共鸣（焦虑/希望/认同/惊讶/好奇/赋能）
8. target_audience: 目标受众
9. tags: 标签数组（3-5个）
10. risk_level: 0(安全)/1(需语境)
11. shelf_life: "long"/"medium"

【高转化质量自检 - 输出前必须全部检查】
1. 选题度：该内容是否蹭到了当前热点关键词？
2. 获得感：用户看完后是否觉得自己学到了"带得走"的干货？
3. 互动欲：文案中是否有留给用户评论的"槽点"？
4. 转化链：文案结尾是否清晰地告诉了用户下一步该干什么？

【输出格式】
只输出JSON数组，每条原子必须同时包含cognition/golden_sentence/action/emotional_hook四个字段。
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
        """将原子改写为特定平台格式 - 高转化版"""
        prompts = {
            "微博": f"""你是一位百万粉丝微博大V，目标是产出能引爆社交裂变的高转化内容。

【素材】
{atom.get('content', '')}
情绪锚点：{atom.get('emotional_hook', '')}
金句：{atom.get('golden_sentence', '')}
思维模型：{atom.get('thinking_model', '')}
情感共鸣：{', '.join(atom.get('emotional_resonance', []))}

【微博爆款公式 - 严格遵守】
- 篇幅：约300字
- 目标：社交裂变 + 涨粉 + 引导评论区互动

【结构约束】
1. 开头钩子（情绪吸引）：用"反常识/痛点/数据冲击"前3秒抓住用户
2. 核心观点：逻辑清晰、有独到见解，不是网上烂大街的鸡汤
3. 金句收尾：郎朗上口，具备身份认同感
4. 【必须】结尾抛出有争议性问题，引导粉丝在评论区站队讨论，提高权重获得系统推流
   例如："你觉得XXX是对的还是错的？评论区说说"

【标签约束】
- 必须有话题标签(#话题名)
- 结尾CTA：引导点赞/关注/评论

直接输出内容，不要前缀。""",

            "小红书": f"""你是一位百万粉丝小红书博主，目标是产出高收藏、高转化的爆款内容。

【素材】
{atom.get('content', '')}
情绪锚点：{atom.get('emotional_hook', '')}
金句：{atom.get('golden_sentence', '')}
目标受众：{', '.join(atom.get('target_audience', ['年轻人']))}
思维模型：{atom.get('thinking_model', '')}

【小红书爆款公式 - 严格遵守】
- 篇幅：约1000字
- 目标：高收藏量 + SEO搜索曝光 + 粉丝转化

【标题约束 - 生成5个爆款标题】
从以下格式中选择最合适的：
- 数字+利益点："5个让XX提升300%的秘诀"
- 惊叹号+好奇心："99%的人都踩过的坑！"
- 避坑指南："XX人必看！别再被割韭菜了"
- 疑问句："为什么你XX？答案出乎意料"

【正文结构约束】
1. 前3行：必须完成"情绪吸引"，让人想点进来
2. 中间：清单式排版，有表格/步骤/对比等可视化元素
3. 干货密度：让用户觉得"收藏=学会"
4. 【必须】结尾强引导关注CTA，例如：
   "如果你也觉得XX有用，评论区扣'想要'，我发你全套方案"
   "关注我，下期教你如何XX"

【标签约束】
- 5-8个#话题标签，包含SEO关键词

直接输出内容，先输出5个标题供选择，再输出正文。""",

            "抖音": f"""你是一位抖音百万粉丝知识博主，目标是产出高完播率、高转化的口播脚本。

【素材】
{atom.get('content', '')}
情绪锚点：{atom.get('emotional_hook', '')}
金句：{atom.get('golden_sentence', '')}
即得利益：{atom.get('action', '')[:100]}
适用场景：{', '.join(atom.get('applicable_scenarios', ['短视频']))}

【抖音爆款公式 - 严格遵守】
- 篇幅：约150字（约1分钟语速）
- 目标：高完播率 + 高互动 + 粉丝转化

【黄金3秒约束 - 开头必须用强钩子】
从以下格式中选择（任选其一）：
- "你敢相信吗？XX竟然..."
- "这绝对是XX界的潜规则"
- "为什么XX？真相让你想不到"
- "看完这个视频，你会XX"

【节奏约束】
- 每30秒设置一个信息点翻转（让人"哇"的信息）
- 语速：快节奏，短句为主
- 中间有案例/故事/金句

【结尾CTA - 必须包含】
- 引导收藏："收藏防走丢，下次想用找不到"
- 引导关注："想看更多XX干货，点关注"
- 引导评论："你觉得XX吗？评论区聊聊"

直接输出口播脚本。""",

            "今日头条": f"""你是一位今日头条资深深度作者，目标是产出高阅读量、高转化的专业长文。

【素材】
{atom.get('content', '')}
情绪锚点：{atom.get('emotional_hook', '')}
金句：{atom.get('golden_sentence', '')}
思维模型：{atom.get('thinking_model', '')}
情感共鸣：{', '.join(atom.get('emotional_resonance', []))}

【今日头条爆款公式 - 严格遵守】
- 篇幅：约1500字
- 目标：高阅读量 + 专业度信任 + 高净值粉丝转化

【逻辑结构约束】
采用"提出问题-深度拆解-解决方案"的硬核长文逻辑：
1. 开头（100字内）：热点引入，用数据/悬念/争议抓住注意力
2. 背景分析：该现象产生的原因
3. 核心观点（3-4个）：每个观点要有深度，不是表面分析
4. 案例解读：有实际案例或故事支撑
5. 解决方案：给用户一个可操作的路径

【标题约束】
疑问句/数字/对比，例如：
"XX的真相：为什么越努力越穷？"
"年薪百万的人，都在用这个底层逻辑"

【人设约束】
建立专家人设，提高高净值粉丝转化：
- 用数据和案例支撑观点
- 逻辑严密，不说废话
- 结尾有思考引导，不做总结式说教

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

    parser.add_argument("--mode", choices=["full", "crawl", "refine", "rewrite", "dispatch", "report", "menu", "topic"],
                        default="menu", help="运行模式")
    parser.add_argument("--skip-crawl", action="store_true", help="跳过爬取阶段")
    parser.add_argument("--auto", action="store_true", help="开启自动发布")
    parser.add_argument("--status", action="store_true", help="显示当前状态")
    parser.add_argument("--queue", metavar="PLATFORM", help="查看待发布队列")
    parser.add_argument("--platforms", nargs="+", default=["微博"], help="目标平台")
    parser.add_argument("--topic", type=str, help="输入话题，自动跑完整流程")

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
    elif args.mode == "topic" or args.topic:
        topic = args.topic or input("请输入话题: ").strip()
        if topic:
            dispatcher.run_full_flow(topic, platforms=args.platforms)
        else:
            print("❌ 话题不能为空")


if __name__ == "__main__":
    main()