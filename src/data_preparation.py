"""
数据准备：CSV → MySQL 入库
=========================
处理大型CSV文件的分批读取、清洗、入库，并生成聚合维度表。
两个CSV文件约14GB，建议在内存≥16GB的机器上运行。
"""
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime
from tqdm import tqdm
import os, sys

try:
    from config import DB_CONFIG, DATA_DIR, CHUNK_SIZE
except ImportError:
    print("ERROR: 请先填写 src/config.py 中的配置")
    sys.exit(1)

DB_URL = (
    f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    f"?charset={DB_CONFIG['charset']}"
)
engine = create_engine(DB_URL, pool_size=5, max_overflow=10)

# 尝试增大 InnoDB 缓冲池以加速聚合
try:
    with engine.connect() as conn:
        conn.execute(text("SET GLOBAL innodb_buffer_pool_size = 536870912"))
        conn.commit()
        print("InnoDB 缓冲池已调至 512MB")
except Exception:
    pass  # 无权限则跳过，以较小批次替代

# 聚合批次大小：可根据MySQL缓冲池大小调整
AGG_BATCH_SIZE = 5000

# ── 辅助函数 ────────────────────────────────────────────
def safe_float(val):
    """安全转换为float，空值返回NaN"""
    try:
        return float(val) if pd.notna(val) and val != '' else np.nan
    except (ValueError, TypeError):
        return np.nan

def parse_category(category_code):
    """解析层级类目码，提取三级类目"""
    if pd.isna(category_code) or category_code == '':
        return (None, None, None)
    parts = str(category_code).split('.')
    l1 = parts[0] if len(parts) >= 1 else None
    l2 = parts[1] if len(parts) >= 2 else None
    l3 = parts[2] if len(parts) >= 3 else None
    return (l1, l2, l3)

# ── CSV导入 ──────────────────────────────────────────────
def process_csv(filepath, engine, chunksize=CHUNK_SIZE):
    """分批读取CSV并写入MySQL events表"""
    fname = os.path.basename(filepath)
    print(f"\n{'='*60}")
    print(f"处理文件: {fname}")
    print(f"{'='*60}")

    print("统计总行数...")
    total_rows = sum(1 for _ in open(filepath, 'r', encoding='utf-8')) - 1
    print(f"总行数: {total_rows:,}")

    reader = pd.read_csv(
        filepath,
        chunksize=chunksize,
        dtype={
            'event_type': 'category',
            'product_id': 'Int64',
            'category_id': 'Int64',
            'category_code': 'string',
            'brand': 'string',
            'user_id': 'Int64',
            'user_session': 'string',
        },
        parse_dates=['event_time'],
        low_memory=False,
    )

    total_loaded = 0
    for chunk in tqdm(reader, total=total_rows//chunksize + 1, desc=fname):
        chunk['event_date'] = chunk['event_time'].dt.date
        chunk['event_hour'] = chunk['event_time'].dt.hour

        cat_parts = chunk['category_code'].apply(parse_category)
        chunk['category_l1'] = [p[0] for p in cat_parts]

        chunk['price'] = chunk['price'].apply(safe_float)
        chunk['is_purchase'] = (chunk['event_type'] == 'purchase').astype(int)

        events_cols = [
            'event_time', 'event_type', 'product_id', 'category_id',
            'category_code', 'category_l1', 'brand', 'price',
            'user_id', 'user_session', 'event_date', 'event_hour', 'is_purchase'
        ]
        chunk = chunk[events_cols]

        chunk.to_sql(
            'events', engine, if_exists='append', index=False,
            method='multi', chunksize=10000,
        )
        total_loaded += len(chunk)

    print(f"  {fname} 导入完成: {total_loaded:,} 行")
    return total_loaded

# ── 建索引 ──────────────────────────────────────────────
def create_indexes(engine):
    """创建索引（入库后执行）。TEXT/BLOB列使用前缀索引"""
    print("\n创建索引...")
    indexes = [
        # 单列索引
        ("CREATE INDEX idx_events_user_id ON events(user_id)", None),
        ("CREATE INDEX idx_events_event_date ON events(event_date)", None),
        ("CREATE INDEX idx_events_event_type ON events(event_type(10))", None),
        ("CREATE INDEX idx_events_product_id ON events(product_id)", None),
        ("CREATE INDEX idx_events_category_l1 ON events(category_l1(50))", None),
        # 复合索引
        ("CREATE INDEX idx_events_user_date_type ON events(user_id, event_date, event_type(10))", None),
        ("CREATE INDEX idx_events_purchase ON events(is_purchase, event_date)", None),
    ]
    with engine.connect() as conn:
        for idx_sql, _ in indexes:
            try:
                conn.execute(text(idx_sql))
                conn.commit()
                idx_name = idx_sql.split('ON')[0].replace('CREATE INDEX ', '').strip()
                print(f"  OK {idx_name}")
            except Exception as e:
                print(f"  跳过（可能已存在）: {str(e)[:80]}")
    print("索引创建完成")

# ── 创建维度表 ──────────────────────────────────────────
def create_dimension_tables(engine):
    """创建users和products空表（events表已由to_sql自动创建）"""
    print("\n创建维度表...")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         BIGINT NOT NULL PRIMARY KEY,
                first_seen      DATETIME,
                last_seen       DATETIME,
                total_events    INT DEFAULT 0,
                total_purchases INT DEFAULT 0,
                lifetime_value  DECIMAL(12,2) DEFAULT 0.00
            ) ENGINE=InnoDB
        """))
        conn.commit()
        print("  OK users 表就绪")

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS products (
                product_id      BIGINT NOT NULL PRIMARY KEY,
                category_id     BIGINT,
                category_code   VARCHAR(255),
                category_l1     VARCHAR(100),
                brand           VARCHAR(255),
                avg_price       DECIMAL(10,2),
                total_views     INT DEFAULT 0,
                total_carts     INT DEFAULT 0,
                total_purchases INT DEFAULT 0
            ) ENGINE=InnoDB
        """))
        conn.commit()
        print("  OK products 表就绪")

# ── 分批聚合：users表 ────────────────────────────────────
def batch_build_users(engine, batch_size=AGG_BATCH_SIZE):
    """按实际user_id游标分页，分批聚合写入users表"""
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(DISTINCT user_id) FROM events")).scalar()
    print(f"\n填充 users 表 (去重用户: {total:,}, 每批 {batch_size:,})")

    last_id = 0
    batch_no = 0
    inserted = 0

    while True:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT user_id FROM events
                WHERE user_id > :last_id
                ORDER BY user_id
                LIMIT :limit
            """), {"last_id": last_id, "limit": batch_size}).fetchall()

        if not rows:
            break

        batch_no += 1
        lo, hi = rows[0][0], rows[-1][0]

        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO users (user_id, first_seen, last_seen, total_events, total_purchases, lifetime_value)
                SELECT user_id,
                    MIN(event_time), MAX(event_time), COUNT(*),
                    SUM(is_purchase),
                    COALESCE(SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END), 0)
                FROM events
                WHERE user_id BETWEEN :lo AND :hi
                GROUP BY user_id
            """), {"lo": lo, "hi": hi})
            conn.commit()
            inserted += result.rowcount

        last_id = hi
        if batch_no % 20 == 0 or batch_no == 1:
            print(f"  批次 {batch_no}: {inserted:,} 用户")

    print(f"  users 表完成: {inserted:,} 行")

# ── 分批聚合：products表 ──────────────────────────────────
def batch_build_products(engine, batch_size=AGG_BATCH_SIZE):
    """按实际product_id游标分页，分批聚合写入products表"""
    with engine.connect() as conn:
        total = conn.execute(text("SELECT COUNT(DISTINCT product_id) FROM events")).scalar()
    print(f"\n填充 products 表 (去重商品: {total:,}, 每批 {batch_size:,})")

    last_id = 0
    batch_no = 0
    inserted = 0

    while True:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT product_id FROM events
                WHERE product_id > :last_id
                ORDER BY product_id
                LIMIT :limit
            """), {"last_id": last_id, "limit": batch_size}).fetchall()

        if not rows:
            break

        batch_no += 1
        lo, hi = rows[0][0], rows[-1][0]

        with engine.connect() as conn:
            result = conn.execute(text("""
                INSERT INTO products (product_id, category_id, category_code, category_l1, brand, avg_price, total_views, total_carts, total_purchases)
                SELECT product_id,
                    MAX(category_id), MAX(category_code), MAX(category_l1), MAX(brand),
                    AVG(price),
                    SUM(CASE WHEN event_type='view' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type='cart' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type='purchase' THEN 1 ELSE 0 END)
                FROM events
                WHERE product_id BETWEEN :lo AND :hi
                GROUP BY product_id
            """), {"lo": lo, "hi": hi})
            conn.commit()
            inserted += result.rowcount

        last_id = hi
        if batch_no % 10 == 0 or batch_no == 1:
            print(f"  批次 {batch_no}: {inserted:,} 商品")

    print(f"  products 表完成: {inserted:,} 行")

# ── 质量检查 ────────────────────────────────────────────
def check_data_quality(engine):
    """数据质量检查"""
    print("\n" + "="*40 + " 数据质量 " + "="*40)
    with engine.connect() as conn:
        for label, sql in [
            ("events 总行数", "SELECT COUNT(*) FROM events"),
            ("去重用户数", "SELECT COUNT(DISTINCT user_id) FROM events"),
            ("去重商品数", "SELECT COUNT(DISTINCT product_id) FROM events"),
            ("users 表行数", "SELECT COUNT(*) FROM users"),
            ("products 表行数", "SELECT COUNT(*) FROM products"),
        ]:
            val = conn.execute(text(sql)).scalar()
            print(f"  {label}: {val:,}")

        result = conn.execute(text(
            "SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC"
        ))
        print("  事件类型分布:")
        for row in result:
            print(f"    {row[0]}: {row[1]:,}")
    print("="*91)

# ── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    # Step 1: 导入CSV数据
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv')]
    if not files:
        print(f"ERROR: {DATA_DIR} 中没有找到CSV文件")
        sys.exit(1)

    print(f"找到 {len(files)} 个CSV文件: {files}")
    for f in files:
        process_csv(os.path.join(DATA_DIR, f), engine)

    # Step 2: 创建维度表
    create_dimension_tables(engine)

    # Step 3: 建索引
    create_indexes(engine)

    # Step 4: 分批聚合users
    batch_build_users(engine)

    # Step 5: 分批聚合products
    batch_build_products(engine)

    # Step 6: 质量检查
    check_data_quality(engine)

    print("\n数据准备全部完成，可以运行分析脚本。")
