#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材池管理模块 v2.0 (material_pool.py)
=====================================
整合了 ip-arsenal 的最佳实践：
- ThinkingModel 思维模型分类体系
- EmotionalResonance 情感共鸣标注
- MaterialQualityChecker 质量评分与路由

核心数据结构：
- 原始素材 (RawMaterial): 从各平台爬取/抓取的原始内容
- 原子素材 (AtomMaterial): 经过LLM提炼的最小可复用单元
- 产品 (Product): 打包好的电子书/报告等

使用示例：
    pool = MaterialPool()
    pool.add_raw_material("微博", "九边", "今天聊聊认知升级...")
    pool.query_atoms(tags=["认知"], thinking_models=["认知偏差"])
    pool.list_products()
"""

import json
import sqlite3
import uuid
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum
from difflib import SequenceMatcher

# Windows UTF-8 支持
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


# ═══════════════════════════════════════════════════════════════════════════
# 分类枚举 - 来自 ip-arsenal
# ═══════════════════════════════════════════════════════════════════════════

class ThinkingModel(Enum):
    """思维模型 - 跨学科分类（来自查理·芒格方法论）"""
    # 心理学
    COGNITIVE_BIAS = "认知偏差"         # 现状偏差/幸存者偏差/确认偏误
    BEHAVIORAL_PSYCHOLOGY = "行为心理学" # 激励/强化/习惯
    EMOTIONAL_INTELLIGENCE = "情商"      # 情绪管理/人际关系
    # 社会
    SOCIAL_DYNAMICS = "社会动力学"       # 从众/群体压力/社会认同
    GROUP_BEHAVIOR = "群体行为"          # 群体思维/羊群效应
    POWER_RELATIONS = "权力关系"         # 上下级/影响力/谈判
    # 人性
    HUMAN_NATURE = "人性本质"            # 自私/恐惧/贪婪/虚荣
    MOTIVATION = "动机驱动"              # 内在动机/外在动机/X理论
    SELF_DECEPTION = "自我欺骗"          # 合理化/自我服务偏差
    # 职场
    CAREER_STRATEGY = "职场策略"         # 晋升/跳槽/办公室政治
    COMMUNICATION = "沟通技巧"            # 汇报/说服/倾听
    LEADERSHIP = "领导力"               # 授权/决策/担当
    # 情感
    RELATIONSHIP_DYNAMICS = "关系动力学" # 亲密关系/边界/依赖
    ATTACHMENT_THEORY = "依恋理论"       # 安全型/焦虑型/回避型
    CONFLICT_RESOLUTION = "冲突解决"     # 谈判/妥协/共赢
    # 底层逻辑
    SYSTEMS_THINKING = "系统思维"        # 反馈回路/延迟效应/非线性
    FIRST_PRINCIPLES = "第一性原理"      # 从头推理/物理思维
    OPPORTUNITY_COST = "机会成本"        # 权衡/选择成本/放弃价值
    COMPOUND_EFFECT = "复利效应"         # 指数增长/积累/长期主义


class EmotionalResonance(Enum):
    """情感共鸣点 - 内容传播的底层驱动力"""
    ANXIETY = "焦虑"           # 引发焦虑（问题意识）- "35岁失业怎么办"
    HOPE = "希望"              # 给予希望（解决方案）- "这样做就行了"
    ANGER = "愤怒"             # 愤怒（不公现象）- "老板就是PUA你"
    RECOGNITION = "认同"       # 认同（共鸣）- "我也是这样"
    SURPRISE = "惊讶"          # 反常识（惊讶）- "原来一直都错了"
    CURIOSITY = "好奇"         # 悬念钩子 - "你绝对想不到"
    EMPOWERMENT = "赋能"       # 能力感 - "原来我也可以"


class RiskLevel(Enum):
    """风险等级"""
    SAFE = 0          # 安全，可直接使用
    NEED_CONTEXT = 1  # 需语境，谨慎使用
    FORBIDDEN = 2     # 禁用，不可用


class ShelfLife(Enum):
    """时效性"""
    LONG = "long"       # 长效，几年内不过期
    MEDIUM = "medium"   # 中效，几个月内有效
    SHORT = "short"     # 短效，热点需快速使用


# ═══════════════════════════════════════════════════════════════════════════
# 质量评分模块 - 来自 ip-arsenal/quality_control.py
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class QualityScore:
    """质量评分结果"""
    completeness: float   # 完整度 0-1
    uniqueness: float     # 唯一性 0-1
    ip_fit: float         # IP契合度 0-1
    actionable: float     # 可执行性 0-1
    emotional_score: float  # 情感共鸣度 0-1
    risk_level: str       # risk/safe
    overall: float        # 综合得分 0-1

    def to_dict(self) -> Dict:
        return {
            "completeness": round(self.completeness, 3),
            "uniqueness": round(self.uniqueness, 3),
            "ip_fit": round(self.ip_fit, 3),
            "actionable": round(self.actionable, 3),
            "emotional_score": round(self.emotional_score, 3),
            "risk_level": self.risk_level,
            "overall": round(self.overall, 3)
        }


class MaterialQualityChecker:
    """素材质量检查器"""

    # IP方向关键词
    IP_KEYWORDS = {
        "职场认知升级": ["职场", "工作", "职业", "升职", "加薪", "领导", "同事", "沟通", "汇报", "面试", "简历", "跳槽", "转行", "成长", "晋升"],
        "人性洞察": ["人性", "心理", "情绪", "关系", "社交", "影响力", "说服", "认知", "偏见", "行为", "动机", "需求", "欲望", "恐惧"],
        "个人成长破局": ["成长", "突破", "改变", "习惯", "自律", "学习", "思考", "认知升级", "思维", "格局", "视野", "目标", "执行力"],
        "情感关系": ["情感", "恋爱", "婚姻", "分手", "依赖", "亲密", "边界", "安全感", "沟通"],
        "商业思维": ["商业", "赚钱", "副业", "创业", "变现", "流量", "产品", "用户", "市场", "竞争"]
    }

    # 情感关键词映射
    EMOTION_KEYWORDS = {
        "焦虑": ["焦虑", "担心", "害怕", "恐惧", "压力", "怎么办", "如何应对"],
        "希望": ["希望", "相信", "可以", "能够", "方法", "技巧", "秘诀"],
        "愤怒": ["愤怒", "气死了", "不公平", "凭什么", "恶心", "无语"],
        "认同": ["我也是", "说的太对了", "确实", "深有体会", "感同身受"],
        "惊讶": ["没想到", "居然", "竟然", "原来", "其实", "一直错了"],
        "好奇": ["为什么", "想知道", "揭秘", "秘密", "真相", "内幕"],
        "赋能": ["你也可以", "能够", "学会", "掌握", "做到", "突破"]
    }

    # 风险关键词
    RISK_KEYWORDS = {
        "danger": ["政治", "共产党", "政府", "领导人", "色情", "暴力", "赌博", "毒品"],
        "warning": ["自杀", "抑郁", "死亡", "失败", "失业"],
        "caution": ["竞争", "斗争", "权谋", "操控"]
    }

    def __init__(self, ip_direction: str = "职场认知升级 / 人性洞察 / 个人成长破局"):
        self.ip_direction = ip_direction
        self._existing_materials: List[Dict] = []

    def set_existing_materials(self, materials: List[Dict]):
        self._existing_materials = materials

    def check(self, atom: Dict) -> Tuple[QualityScore, List[str]]:
        """完整质量检查"""
        suggestions = []

        completeness = self._check_completeness(atom, suggestions)
        uniqueness = self._check_uniqueness(atom, suggestions)
        ip_fit = self._check_ip_fit(atom, suggestions)
        actionable = self._check_actionable(atom, suggestions)
        emotional = self._check_emotional(atom, suggestions)
        risk_level, risk_suggestions = self._check_risk(atom, suggestions)
        suggestions.extend(risk_suggestions)

        risk_weight = 1.0 if risk_level == "safe" else 0.5 if risk_level == "caution" else 0.0

        overall = (
            completeness * 0.20 +
            uniqueness * 0.15 +
            ip_fit * 0.20 +
            actionable * 0.15 +
            emotional * 0.30
        ) * risk_weight

        score = QualityScore(
            completeness=completeness,
            uniqueness=uniqueness,
            ip_fit=ip_fit,
            actionable=actionable,
            emotional_score=emotional,
            risk_level=risk_level,
            overall=overall
        )

        return score, suggestions

    def _check_completeness(self, atom: Dict, suggestions: List[str]) -> float:
        content = atom.get("content", "")
        score = 1.0
        if len(content) < 30:
            score -= 0.3
            suggestions.append("内容过短")
        elif len(content) > 500:
            score -= 0.1
        if not atom.get("tags"):
            score -= 0.2
            suggestions.append("缺少标签")
        return max(0, score)

    def _check_uniqueness(self, atom: Dict, suggestions: List[str]) -> float:
        if not self._existing_materials:
            return 1.0
        content = atom.get("content", "").lower()
        max_sim = max(
            SequenceMatcher(None, content, m.get("content", "").lower()).ratio()
            for m in self._existing_materials
        ) if self._existing_materials else 0
        if max_sim > 0.85:
            suggestions.append(f"与已有素材高度相似({max_sim:.0%})")
            return 0.2
        elif max_sim > 0.6:
            suggestions.append(f"轻度相似({max_sim:.0%})")
            return 0.8
        return 1.0

    def _check_ip_fit(self, atom: Dict, suggestions: List[str]) -> float:
        content = (atom.get("content", "") + " " + " ".join(atom.get("tags", []))).lower()
        matched = sum(1 for kw in self.IP_KEYWORDS.get(self.ip_direction, []) if kw in content)
        score = min(1.0, 0.3 + matched * 0.15)
        if score < 0.5:
            suggestions.append("IP契合度较低")
        return score

    def _check_actionable(self, atom: Dict, suggestions: List[str]) -> float:
        content = atom.get("content", "")
        has_action = any(k in content for k in ["方法", "技巧", "步骤", "如何", "可以", "应该"])
        has_step = bool(re.search(r'\d+[.、]', content))
        score = 0.9 if (has_action and has_step) else 0.7 if has_action else 0.5
        if score < 0.7:
            suggestions.append("缺少行动指引")
        return score

    def _check_emotional(self, atom: Dict, suggestions: List[str]) -> float:
        content = (atom.get("content", "") + " ".join(atom.get("tags", []))).lower()
        matched_emotions = [e for e, kws in self.EMOTION_KEYWORDS.items() if any(k in content for k in kws)]
        score = min(1.0, len(matched_emotions) * 0.25 + 0.25)
        if matched_emotions:
            atom["emotions"] = matched_emotions
        return score

    def _check_risk(self, atom: Dict, suggestions: List[str]) -> Tuple[str, List[str]]:
        content = (atom.get("content", "") + " ".join(atom.get("tags", []))).lower()
        for level, keywords in self.RISK_KEYWORDS.items():
            if any(kw in content for kw in keywords):
                suggestions.append(f"含风险关键词: {level}")
                return "caution" if level == "caution" else "danger", suggestions
        return "safe", suggestions


class MaterialRouter:
    """素材路由 - 根据质量评分决定处理方式"""
    THRESHOLDS = {"auto_approve": 0.75, "human_review": 0.50, "auto_discard": 0.25}

    def route(self, atom: Dict, score: QualityScore) -> Tuple[str, str]:
        if score.risk_level == "danger":
            return "discard", "高风险内容"
        if score.overall >= self.THRESHOLDS["auto_approve"]:
            return "approve", f"优秀({score.overall:.2f})"
        if score.overall >= self.THRESHOLDS["human_review"]:
            return "review", f"待审核({score.overall:.2f})"
        return "discard", f"不合格({score.overall:.2f})"


# ═══════════════════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class AtomMaterial:
    """原子化素材 - 增强版"""
    id: str
    raw_id: str             # 原始素材ID
    type: str               # quote/case/cognition/action
    content: str             # 核心内容

    # 增强字段
    thinking_model: str = ""     # 思维模型分类
    emotional_resonance: List[str] = field(default_factory=list)  # 情感共鸣点
    target_audience: List[str] = field(default_factory=list)    # 目标受众
    applicable_scenarios: List[str] = field(default_factory=list)  # 适用场景

    # 原有字段
    platform_tags: Dict[str, str] = field(default_factory=dict)  # 各平台改写版本
    tags: List[str] = field(default_factory=list)              # 标签
    risk_level: int = 0                                        # RiskLevel
    shelf_life: str = "long"                                   # ShelfLife
    hot_score: float = 0.0                                     # 热度评分
    quality_score: float = 0.0                                 # 质量评分
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    used_count: int = 0                                        # 被使用次数


# ═══════════════════════════════════════════════════════════════════════════
# 素材池管理器
# ═══════════════════════════════════════════════════════════════════════════

class MaterialPool:
    """素材池管理器"""

    def __init__(self, db_path: str = None):
        script_dir = Path(__file__).parent.resolve()
        if db_path is None:
            db_path = str(script_dir / "content_pool" / "materials.db")

        self.db_path = db_path
        self.raw_dir = script_dir / "content_pool" / "raw"
        self.refined_dir = script_dir / "content_pool" / "refined"
        self.products_dir = script_dir / "content_pool" / "products"
        self.quality_checker = MaterialQualityChecker()
        self.router = MaterialRouter()

        for d in [self.raw_dir, self.refined_dir, self.products_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS raw_materials (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                author TEXT,
                title TEXT,
                content TEXT,
                url TEXT,
                tags TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'pending',
                file_path TEXT
            )
        """)

        # 增强的原子素材表
        c.execute("""
            CREATE TABLE IF NOT EXISTS atom_materials (
                id TEXT PRIMARY KEY,
                raw_id TEXT,
                type TEXT,
                content TEXT,
                thinking_model TEXT DEFAULT '',
                emotional_resonance TEXT DEFAULT '[]',
                target_audience TEXT DEFAULT '[]',
                applicable_scenarios TEXT DEFAULT '[]',
                platform_tags TEXT DEFAULT '{}',
                tags TEXT DEFAULT '[]',
                risk_level INTEGER DEFAULT 0,
                shelf_life TEXT DEFAULT 'long',
                hot_score REAL DEFAULT 0.0,
                quality_score REAL DEFAULT 0.0,
                created_at TEXT,
                used_count INTEGER DEFAULT 0,
                FOREIGN KEY (raw_id) REFERENCES raw_materials(id)
            )
        """)

        # 迁移：为已有数据库添加新字段
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN thinking_model TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 字段已存在
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN emotional_resonance TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN target_audience TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN applicable_scenarios TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN platform_tags TEXT DEFAULT '{}'")
        except sqlite3.OperationalError:
            pass
        try:
            c.execute("ALTER TABLE atom_materials ADD COLUMN quality_score REAL DEFAULT 0.0")
        except sqlite3.OperationalError:
            pass

        c.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                price REAL,
                content TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT,
                published_at TEXT
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS product_atoms (
                product_id TEXT,
                atom_id TEXT,
                PRIMARY KEY (product_id, atom_id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (atom_id) REFERENCES atom_materials(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS dispatch_log (
                id TEXT PRIMARY KEY,
                atom_id TEXT,
                platform TEXT,
                dispatched_at TEXT,
                status TEXT,
                FOREIGN KEY (atom_id) REFERENCES atom_materials(id)
            )
        """)

        conn.commit()
        conn.close()

    # ========== 原始素材操作 ==========

    def add_raw_material(self, platform: str, author: str, title: str, content: str,
                         url: str = "", tags: List[str] = None) -> str:
        if tags is None:
            tags = []
        material_id = str(uuid.uuid4())[:8]

        safe_name = f"{platform}_{author}_{material_id}.txt"
        file_path = self.raw_dir / safe_name
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n来源：{platform} / {author}\n链接：{url}\n标签：{', '.join(tags)}\n时间：{datetime.now().isoformat()}\n---\n\n{content}")

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO raw_materials (id, platform, author, title, content, url, tags, created_at, status, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (material_id, platform, author, title, content, url, json.dumps(tags, ensure_ascii=False),
              datetime.now().isoformat(), "pending", str(file_path)))
        conn.commit()
        conn.close()

        print(f"✅ 添加原始素材: {title} ({material_id})")
        return material_id

    def get_raw_materials(self, status: str = None, platform: str = None, limit: int = 100) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM raw_materials WHERE 1=1"
        params = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if platform:
            query += " AND platform = ?"
            params.append(platform)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        c.execute(query, params)
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_raw_status(self, material_id: str, status: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE raw_materials SET status = ? WHERE id = ?", (status, material_id))
        conn.commit()
        conn.close()

    # ========== 原子素材操作 ==========

    def add_atom_material(self, raw_id: str, atom_type: str, content: str,
                          tags: List[str] = None, risk_level: int = 0, shelf_life: str = "long",
                          thinking_model: str = "", emotional_resonance: List[str] = None,
                          target_audience: List[str] = None, applicable_scenarios: List[str] = None) -> str:
        if tags is None:
            tags = []
        if emotional_resonance is None:
            emotional_resonance = []
        if target_audience is None:
            target_audience = []
        if applicable_scenarios is None:
            applicable_scenarios = []

        atom_id = str(uuid.uuid4())[:8]

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO atom_materials
            (id, raw_id, type, content, thinking_model, emotional_resonance, target_audience,
             applicable_scenarios, platform_tags, tags, risk_level, shelf_life, quality_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (atom_id, raw_id, atom_type, content, thinking_model,
              json.dumps(emotional_resonance, ensure_ascii=False),
              json.dumps(target_audience, ensure_ascii=False),
              json.dumps(applicable_scenarios, ensure_ascii=False),
              "{}", json.dumps(tags, ensure_ascii=False), risk_level, shelf_life, 0.0,
              datetime.now().isoformat()))
        conn.commit()
        conn.close()

        self.update_raw_status(raw_id, "processed")
        print(f"✅ 添加原子素材: [{atom_type}] {content[:30]}... ({atom_id})")
        return atom_id

    def update_atom_platform_tags(self, atom_id: str, platform: str, content: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT platform_tags FROM atom_materials WHERE id = ?", (atom_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        platform_tags = json.loads(row[0] or "{}")
        platform_tags[platform] = content
        c.execute("UPDATE atom_materials SET platform_tags = ? WHERE id = ?",
                  (json.dumps(platform_tags, ensure_ascii=False), atom_id))
        conn.commit()
        conn.close()

    def query_atoms(self, tags: List[str] = None, atom_types: List[str] = None,
                   thinking_models: List[str] = None, emotional_resonance: List[str] = None,
                   risk_max: int = 1, limit: int = 50) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM atom_materials WHERE risk_level <= ? AND quality_score >= 0.3"
        params = [risk_max]

        if atom_types:
            query += f" AND type IN ({','.join('?' * len(atom_types))})"
            params.extend(atom_types)

        if tags:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f"%{tag}%")

        if thinking_models:
            for tm in thinking_models:
                query += " AND thinking_model LIKE ?"
                params.append(f"%{tm}%")

        if emotional_resonance:
            for er in emotional_resonance:
                query += " AND emotional_resonance LIKE ?"
                params.append(f"%{er}%")

        query += " ORDER BY quality_score DESC, hot_score DESC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        atoms = []
        for row in rows:
            atom = dict(row)
            atom["platform_tags"] = json.loads(atom["platform_tags"] or "{}")
            atom["tags"] = json.loads(atom["tags"] or "[]")
            atom["emotional_resonance"] = json.loads(atom["emotional_resonance"] or "[]")
            atom["target_audience"] = json.loads(atom["target_audience"] or "[]")
            atom["applicable_scenarios"] = json.loads(atom["applicable_scenarios"] or "[]")
            atoms.append(atom)
        return atoms

    def check_atom_quality(self, atom: Dict) -> Tuple[QualityScore, str]:
        """检查原子素材质量并返回评分和路由决策"""
        score, suggestions = self.quality_checker.check(atom)
        decision, reason = self.router.route(atom, score)

        # 更新质量评分
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE atom_materials SET quality_score = ? WHERE id = ?",
                  (score.overall, atom["id"]))
        conn.commit()
        conn.close()

        return score, decision

    def increment_used_count(self, atom_id: str):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE atom_materials SET used_count = used_count + 1 WHERE id = ?", (atom_id,))
        conn.commit()
        conn.close()

    # ========== 产品操作 ==========

    def create_product(self, name: str, product_type: str, price: float, content: str,
                      atom_ids: List[str] = None) -> str:
        if atom_ids is None:
            atom_ids = []
        product_id = str(uuid.uuid4())[:8]

        file_path = self.products_dir / f"{product_id}_{name}.md"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO products (id, name, type, price, content, status, created_at, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (product_id, name, product_type, price, content, "draft", datetime.now().isoformat(), str(file_path)))

        for atom_id in atom_ids:
            c.execute("INSERT INTO product_atoms (product_id, atom_id) VALUES (?, ?)", (product_id, atom_id))
            self.increment_used_count(atom_id)

        conn.commit()
        conn.close()
        print(f"✅ 创建产品: {name} ({product_id})")
        return product_id

    def publish_product(self, product_id: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE products SET status = 'published', published_at = ? WHERE id = ?",
                  (datetime.now().isoformat(), product_id))
        conn.commit()
        affected = c.rowcount
        conn.close()
        return affected > 0

    def list_products(self, status: str = None) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        query = "SELECT * FROM products"
        if status:
            c.execute(query + " WHERE status = ? ORDER BY created_at DESC", (status,))
        else:
            c.execute(query + " ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ========== 分发记录 ==========

    def log_dispatch(self, atom_id: str, platform: str, status: str = "success"):
        dispatch_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("INSERT INTO dispatch_log (id, atom_id, platform, dispatched_at, status) VALUES (?, ?, ?, ?, ?)",
                   (dispatch_id, atom_id, platform, datetime.now().isoformat(), status))
        conn.commit()
        conn.close()

    def get_dispatch_stats(self, days: int = 7) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT platform, COUNT(*) FROM dispatch_log WHERE dispatched_at >= ? GROUP BY platform",
                   (datetime.now().isoformat(),))
        stats = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return stats

    # ========== 统计 ==========

    def get_pool_stats(self) -> Dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        stats = {}
        c.execute("SELECT COUNT(*), status FROM raw_materials GROUP BY status")
        stats["raw_by_status"] = {row[1]: row[0] for row in c.fetchall()}
        stats["raw_total"] = sum(stats["raw_by_status"].values())

        c.execute("SELECT COUNT(*) FROM atom_materials")
        stats["atoms_total"] = c.fetchone()[0]

        c.execute("SELECT type, COUNT(*) FROM atom_materials GROUP BY type")
        stats["atoms_by_type"] = {row[0]: row[1] for row in c.fetchall()}

        c.execute("SELECT thinking_model, COUNT(*) FROM atom_materials WHERE thinking_model != '' GROUP BY thinking_model")
        stats["atoms_by_model"] = {row[0]: row[1] for row in c.fetchall()}

        c.execute("SELECT COUNT(*), status FROM products GROUP BY status")
        stats["products_by_status"] = {row[1]: row[0] for row in c.fetchall()}
        stats["products_total"] = sum(stats["products_by_status"].values())

        conn.close()
        return stats


if __name__ == "__main__":
    pool = MaterialPool()
    print("\n📊 素材池统计:")
    stats = pool.get_pool_stats()
    print(f"   原始素材: {stats['raw_total']} (待处理: {stats['raw_by_status'].get('pending', 0)})")
    print(f"   原子素材: {stats['atoms_total']}")
    if "atoms_by_type" in stats:
        for t, c in stats["atoms_by_type"].items():
            print(f"      - {t}: {c}")
    if "atoms_by_model" in stats:
        print(f"   思维模型分布:")
        for m, c in list(stats["atoms_by_model"].items())[:5]:
            print(f"      - {m}: {c}")