#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
素材池管理模块 (material_pool.py)
=================================
用途：管理所有原始素材和原子化内容的存储、查询、标注

核心数据结构：
- 原始素材 (RawMaterial): 从各平台爬取/抓取的原始内容
- 原子素材 (AtomMaterial): 经过LLM提炼的最小可复用单元
- 产品 (Product): 打包好的电子书/报告等

使用示例：
    pool = MaterialPool()
    pool.add_raw_material("微博", "九边", "今天聊聊认知升级...")
    pool.extract_atoms(material_id)
    pool.query_atoms(tags=["认知", "职场"], platforms=["微博"])
    pool.list_products()
"""

import json
import sqlite3
import uuid
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict, field
from enum import Enum

# Windows UTF-8 支持
if sys.platform == "win32":
    try:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass


class MaterialType(Enum):
    """素材类型"""
    RAW = "raw"                    # 原始素材
    ATOM = "atom"                  # 原子化素材
    PRODUCT = "product"          # 成品

class AtomType(Enum):
    """原子素材类型"""
    QUOTE = "quote"               # 金句
    CASE = "case"                 # 案例
    COGNITION = "cognition"       # 认知观点
    ACTION = "action"            # 行动指南

class Platform(Enum):
    """内容平台"""
    DOUYIN = "douyin"
    WEIBO = "weibo"
    TOUTIAO = "toutiao"
    WECHAT = "wechat"
    XIAOHONGSHU = "xiaohongshu"
    BILIBILI = "bilibili"
    BOOK = "book"                 # 书籍PDF
    OTHER = "other"

class RiskLevel(Enum):
    """风险等级"""
    SAFE = 0          # 安全
    NEED_CONTEXT = 1  # 需语境
    FORBIDDEN = 2     # 禁用

class ShelfLife(Enum):
    """时效性"""
    LONG = "long"       # 长效
    MEDIUM = "medium"   # 中效
    SHORT = "short"     # 短效

@dataclass
class RawMaterial:
    """原始素材"""
    id: str
    platform: str           # 平台
    author: str             # 作者/来源
    title: str              # 标题
    content: str            # 原文内容
    url: str = ""           # 原文链接
    tags: List[str] = field(default_factory=list)  # 标签
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    status: str = "pending"  # pending/processing/processed

@dataclass
class AtomMaterial:
    """原子化素材"""
    id: str
    raw_id: str             # 原始素材ID
    type: str               # AtomType
    content: str             # 核心内容
    platform_tags: Dict[str, str] = field(default_factory=dict)  # 各平台改写版本 {"微博": "...", "抖音": "..."}
    tags: List[str] = field(default_factory=list)
    risk_level: int = 0     # RiskLevel
    shelf_life: str = "long"
    hot_score: float = 0.0  # 热度评分
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    used_count: int = 0     # 被使用次数

@dataclass
class Product:
    """知识产品"""
    id: str
    name: str               # 产品名称
    type: str               # ebook/report/collection
    price: float            # 价格
    content: str            # Markdown内容
    atoms: List[str] = field(default_factory=list)  # 包含的原子素材ID
    status: str = "draft"   # draft/published
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    published_at: Optional[str] = None


class MaterialPool:
    """素材池管理器"""

    def __init__(self, db_path: str = None):
        # 默认使用脚本所在目录
        script_dir = Path(__file__).parent.resolve()
        if db_path is None:
            db_path = str(script_dir / "content_pool" / "materials.db")

        self.db_path = db_path
        self.raw_dir = script_dir / "content_pool" / "raw"
        self.refined_dir = script_dir / "content_pool" / "refined"
        self.products_dir = script_dir / "content_pool" / "products"

        # 确保目录存在
        for d in [self.raw_dir, self.refined_dir, self.products_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 原始素材表
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

        # 原子素材表
        c.execute("""
            CREATE TABLE IF NOT EXISTS atom_materials (
                id TEXT PRIMARY KEY,
                raw_id TEXT,
                type TEXT,
                content TEXT,
                platform_tags TEXT,
                tags TEXT,
                risk_level INTEGER DEFAULT 0,
                shelf_life TEXT DEFAULT 'long',
                hot_score REAL DEFAULT 0.0,
                created_at TEXT,
                used_count INTEGER DEFAULT 0,
                FOREIGN KEY (raw_id) REFERENCES raw_materials(id)
            )
        """)

        # 产品表
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

        # 产品-原子素材关联表
        c.execute("""
            CREATE TABLE IF NOT EXISTS product_atoms (
                product_id TEXT,
                atom_id TEXT,
                PRIMARY KEY (product_id, atom_id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (atom_id) REFERENCES atom_materials(id)
            )
        """)

        # 分发记录表
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

    def add_raw_material(
        self,
        platform: str,
        author: str,
        title: str,
        content: str,
        url: str = "",
        tags: List[str] = None
    ) -> str:
        """添加原始素材"""
        if tags is None:
            tags = []

        material_id = str(uuid.uuid4())[:8]

        # 保存原始内容到文件
        safe_name = f"{platform}_{author}_{material_id}.txt"
        file_path = self.raw_dir / safe_name
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n")
            f.write(f"来源：{platform} / {author}\n")
            f.write(f"链接：{url}\n")
            f.write(f"标签：{', '.join(tags)}\n")
            f.write(f"时间：{datetime.now().isoformat()}\n")
            f.write("---\n\n")
            f.write(content)

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO raw_materials
            (id, platform, author, title, content, url, tags, created_at, status, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (material_id, platform, author, title, content, url,
              json.dumps(tags, ensure_ascii=False), datetime.now().isoformat(),
              "pending", str(file_path)))
        conn.commit()
        conn.close()

        print(f"✅ 添加原始素材: {title} ({material_id})")
        return material_id

    def get_raw_materials(self, status: str = None, platform: str = None, limit: int = 100) -> List[Dict]:
        """获取原始素材列表"""
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
        """更新原始素材状态"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE raw_materials SET status = ? WHERE id = ?", (status, material_id))
        conn.commit()
        conn.close()

    # ========== 原子素材操作 ==========

    def add_atom_material(
        self,
        raw_id: str,
        atom_type: str,
        content: str,
        tags: List[str] = None,
        risk_level: int = 0,
        shelf_life: str = "long"
    ) -> str:
        """添加原子化素材"""
        if tags is None:
            tags = []

        atom_id = str(uuid.uuid4())[:8]

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO atom_materials
            (id, raw_id, type, content, platform_tags, tags, risk_level, shelf_life, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (atom_id, raw_id, atom_type, content, "{}", json.dumps(tags, ensure_ascii=False),
              risk_level, shelf_life, datetime.now().isoformat()))
        conn.commit()
        conn.close()

        # 更新原始素材状态
        self.update_raw_status(raw_id, "processed")

        print(f"✅ 添加原子素材: [{atom_type}] {content[:30]}... ({atom_id})")
        return atom_id

    def update_atom_platform_tags(self, atom_id: str, platform: str, content: str):
        """更新原子素材的某平台改写版本"""
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

    def query_atoms(
        self,
        tags: List[str] = None,
        atom_types: List[str] = None,
        platforms: List[str] = None,
        risk_max: int = 1,
        limit: int = 50
    ) -> List[Dict]:
        """查询原子素材"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM atom_materials WHERE risk_level <= ?"
        params = [risk_max]

        if atom_types:
            placeholders = ",".join("?" * len(atom_types))
            query += f" AND type IN ({placeholders})"
            params.extend(atom_types)

        if tags:
            for tag in tags:
                query += " AND tags LIKE ?"
                params.append(f"%{tag}%")

        query += " ORDER BY hot_score DESC, used_count ASC LIMIT ?"
        params.append(limit)

        c.execute(query, params)
        rows = c.fetchall()
        conn.close()

        atoms = []
        for row in rows:
            atom = dict(row)
            atom["platform_tags"] = json.loads(atom["platform_tags"] or "{}")
            atom["tags"] = json.loads(atom["tags"] or "[]")

            # 如果指定了平台过滤，只返回有对应平台改写的素材
            if platforms:
                has_platform = any(p in atom["platform_tags"] for p in platforms)
                if has_platform:
                    atoms.append(atom)
            else:
                atoms.append(atom)

        return atoms

    def increment_used_count(self, atom_id: str):
        """增加使用计数"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE atom_materials SET used_count = used_count + 1 WHERE id = ?", (atom_id,))
        conn.commit()
        conn.close()

    # ========== 产品操作 ==========

    def create_product(
        self,
        name: str,
        product_type: str,
        price: float,
        content: str,
        atom_ids: List[str] = None
    ) -> str:
        """创建知识产品"""
        if atom_ids is None:
            atom_ids = []

        product_id = str(uuid.uuid4())[:8]

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        # 保存产品内容到文件
        safe_name = f"{product_id}_{name}.md"
        file_path = self.products_dir / safe_name
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        c.execute("""
            INSERT INTO products (id, name, type, price, content, status, created_at, file_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (product_id, name, product_type, price, content, "draft",
              datetime.now().isoformat(), str(file_path)))

        # 关联原子素材
        for atom_id in atom_ids:
            c.execute("INSERT INTO product_atoms (product_id, atom_id) VALUES (?, ?)",
                      (product_id, atom_id))
            self.increment_used_count(atom_id)

        conn.commit()
        conn.close()

        print(f"✅ 创建产品: {name} ({product_id})")
        return product_id

    def publish_product(self, product_id: str) -> bool:
        """发布产品"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            UPDATE products
            SET status = 'published', published_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), product_id))
        conn.commit()
        affected = c.rowcount
        conn.close()
        return affected > 0

    def list_products(self, status: str = None) -> List[Dict]:
        """列出产品"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        query = "SELECT * FROM products"
        if status:
            query += " WHERE status = ?"
            c.execute(query + " ORDER BY created_at DESC", (status,))
        else:
            c.execute(query + " ORDER BY created_at DESC")

        rows = c.fetchall()
        conn.close()
        return [dict(row) for row in rows]

    # ========== 分发记录 ==========

    def log_dispatch(self, atom_id: str, platform: str, status: str = "success"):
        """记录分发日志"""
        dispatch_id = str(uuid.uuid4())[:8]
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""
            INSERT INTO dispatch_log (id, atom_id, platform, dispatched_at, status)
            VALUES (?, ?, ?, ?, ?)
        """, (dispatch_id, atom_id, platform, datetime.now().isoformat(), status))
        conn.commit()
        conn.close()

    def get_dispatch_stats(self, days: int = 7) -> Dict:
        """获取分发统计"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        since = datetime.now().isoformat()
        c.execute("""
            SELECT platform, COUNT(*) as count
            FROM dispatch_log
            WHERE dispatched_at >= ?
            GROUP BY platform
        """, (since,))

        stats = {row[0]: row[1] for row in c.fetchall()}
        conn.close()
        return stats

    # ========== 统计与报告 ==========

    def get_pool_stats(self) -> Dict:
        """获取素材池统计"""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()

        stats = {}

        # 原始素材统计
        c.execute("SELECT COUNT(*), status FROM raw_materials GROUP BY status")
        stats["raw_by_status"] = {row[1]: row[0] for row in c.fetchall()}
        stats["raw_total"] = sum(stats["raw_by_status"].values())

        # 原子素材统计
        c.execute("SELECT COUNT(*) FROM atom_materials")
        stats["atoms_total"] = c.fetchone()[0]

        c.execute("SELECT type, COUNT(*) FROM atom_materials GROUP BY type")
        stats["atoms_by_type"] = {row[0]: row[1] for row in c.fetchall()}

        # 产品统计
        c.execute("SELECT COUNT(*), status FROM products GROUP BY status")
        stats["products_by_status"] = {row[1]: row[0] for row in c.fetchall()}
        stats["products_total"] = sum(stats["products_by_status"].values())

        conn.close()
        return stats


def init_sample_data(pool: MaterialPool):
    """初始化示例数据"""
    # 添加一条示例原始素材
    pool.add_raw_material(
        platform="微博",
        author="九边",
        title="关于认知升级的一些思考",
        content="""
认知升级不是让你知道更多，而是让你能做出更好的决策。

大多数人的问题是：学了很多，但从来不用。他们把学习当成一种安慰剂，而不是工具。

真正有效的学习是：
1. 遇到具体问题
2. 找到相关知识
3. 立刻应用到决策中
4. 复盘效果

这才是「知行合一」。

另外有个很重要的点：你要建立自己的「决策清单」，而不是记住一堆道理。
清单是显性的、可执行的。道理是模糊的、容易遗忘的。
        """,
        url="https://weibo.com/jiubian",
        tags=["认知升级", "学习", "决策"]
    )

    # 添加一条原子素材
    atoms = pool.query_atoms(tags=["认知"])
    if atoms:
        print(f"\n📊 素材池统计: {pool.get_pool_stats()}")


if __name__ == "__main__":
    pool = MaterialPool()

    # 如果素材池为空，添加示例数据
    if pool.get_pool_stats()["raw_total"] == 0:
        print("📦 初始化示例数据...")
        init_sample_data(pool)

    print("\n📊 素材池统计:")
    stats = pool.get_pool_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")

    print("\n🔍 测试查询原子素材:")
    atoms = pool.query_atoms(limit=5)
    print(f"   找到 {len(atoms)} 条原子素材")