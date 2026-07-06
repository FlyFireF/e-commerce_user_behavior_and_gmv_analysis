"""
探索性数据分析 (EDA)
=====================
数据可视化、指标体系搭建、品类分析
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')

# ── 导入但不设置，等 seaborn 初始化完 ──
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.font_manager as fm
import seaborn as sns

# ── seaborn 先初始化 ──
sns.set_style("whitegrid")
sns.set_palette("Set2")

# ── 用绝对路径注册 SimHei，绕过所有缓存/名称匹配 ──
FONT_PATH = 'C:/Windows/Fonts/simhei.ttf'
fm.fontManager.addfont(FONT_PATH)
_font_prop = fm.FontProperties(fname=FONT_PATH)
_font_name = _font_prop.get_name()

# 用注册回来的真实名称设置默认字体
plt.rcParams['font.family'] = _font_name
plt.rcParams['axes.unicode_minus'] = False

# 验证
print(f"字体注册为: {_font_name}")

from sqlalchemy import create_engine, text
import os, sys

try:
    from config import DB_CONFIG, FIGURE_DIR, ANALYSIS_START_DATE, ANALYSIS_END_DATE
except ImportError:
    print("ERROR: 请先填写 src/config.py")
    sys.exit(1)

# 中文字体设置
# plt.rcParams['font.sans-serif'] = ['SimHei']
# plt.rcParams['axes.unicode_minus'] = False
# sns.set_style("whitegrid")
# sns.set_palette("Set2")

DB_URL = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
engine = create_engine(DB_URL)

os.makedirs(FIGURE_DIR, exist_ok=True)


def load_main_data():
    """从MySQL加载events表数据（聚合级别，避免OOM）"""
    # 按天+品类聚合，而不是加载全表
    query = f"""
    SELECT 
        event_date,
        event_type,
        category_l1,
        event_hour,
        COUNT(*) AS event_count,
        COUNT(DISTINCT user_id) AS unique_users,
        SUM(CASE WHEN is_purchase = 1 THEN price ELSE 0 END) AS gmv,
        COUNT(CASE WHEN is_purchase = 1 THEN 1 END) AS purchase_count
    FROM events
    WHERE event_date BETWEEN '{ANALYSIS_START_DATE}' AND '{ANALYSIS_END_DATE}'
    GROUP BY event_date, event_type, category_l1, event_hour
    """
    return pd.read_sql(query, engine)


def load_user_summary():
    """加载用户级摘要（用于分布分析）"""
    query = """
    SELECT 
        user_id,
        total_events,
        total_purchases,
        lifetime_value
    FROM users
    WHERE total_events > 0
    """
    return pd.read_sql(query, engine)


# ── 1. 事件类型分布 ─────────────────────────────────────
def plot_event_distribution(df):
    """饼图：view/cart/purchase事件占比"""
    event_counts = df.groupby('event_type')['event_count'].sum().sort_values()
    
    fig, ax = plt.subplots(figsize=(8, 6))
    colors = ['#66c2a5', '#fc8d62', '#8da0cb']
    wedges, texts, autotexts = ax.pie(
        event_counts.values, labels=event_counts.index,
        autopct='%1.1f%%', startangle=90, colors=colors,
        explode=(0, 0, 0.05)
    )
    ax.set_title('用户行为事件分布', fontsize=14, fontweight='bold')
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '01_event_distribution.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")
    return event_counts


# ── 2. 每日GMV趋势 ──────────────────────────────────────
def plot_daily_gmv(df):
    """折线图：每日GMV + 购买用户数"""
    daily = df[df['event_type'] == 'purchase'].groupby('event_date').agg(
        gmv=('gmv', 'sum'),
        purchase_count=('purchase_count', 'sum'),
        paying_users=('unique_users', 'sum')
    ).reset_index()
    
    fig, ax1 = plt.subplots(figsize=(14, 6))
    
    ax1.bar(daily['event_date'], daily['gmv'], alpha=0.6, color='#66c2a5', label='GMV')
    ax1.set_ylabel('GMV', fontsize=12)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    
    ax2 = ax1.twinx()
    ax2.plot(daily['event_date'], daily['paying_users'], color='#fc8d62', 
             linewidth=2, marker='o', markersize=3, label='购买用户数')
    ax2.set_ylabel('购买用户数', fontsize=12)
    
    ax1.set_title('每日GMV与购买用户数趋势', fontsize=14, fontweight='bold')
    ax1.set_xlabel('日期')
    fig.autofmt_xdate()
    
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '02_daily_gmv.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")
    
    # 输出关键统计
    print(f"  日均GMV: {daily['gmv'].mean():,.0f}")
    print(f"  最高GMV日: {daily.loc[daily['gmv'].idxmax(), 'event_date']} ({daily['gmv'].max():,.0f})")
    print(f"  日均购买用户: {daily['paying_users'].mean():,.0f}")


# ── 3. 品类GMV对比 ──────────────────────────────────────
def plot_category_gmv(df):
    """柱状图：一级品类GMV + 转化率双轴"""
    cat = df.groupby('category_l1').agg(
        gmv=('gmv', 'sum'),
        total_events=('event_count', 'sum'),
        purchase_count=('purchase_count', 'sum')
    ).reset_index()
    
    cat = cat[cat['category_l1'].notna() & (cat['category_l1'] != '')]
    cat = cat[cat['total_events'] > 1000]  # 过滤极小品类
    cat['conversion_rate'] = cat['purchase_count'] / cat['total_events'] * 100
    cat = cat.sort_values('gmv', ascending=True)
    
    fig, ax1 = plt.subplots(figsize=(12, 7))
    
    bars = ax1.barh(range(len(cat)), cat['gmv'], color='#66c2a5', alpha=0.8)
    ax1.set_yticks(range(len(cat)))
    ax1.set_yticklabels(cat['category_l1'])
    ax1.set_xlabel('GMV', fontsize=12)
    ax1.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    
    ax2 = ax1.twiny()
    ax2.scatter(cat['conversion_rate'], range(len(cat)), color='#fc8d62', 
                s=100, zorder=5, marker='D')
    ax2.set_xlabel('浏览→购买转化率 (%)', fontsize=12, color='#fc8d62')
    ax2.tick_params(axis='x', labelcolor='#fc8d62')
    
    ax1.set_title('一级品类GMV与转化率对比', fontsize=14, fontweight='bold')
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '03_category_gmv.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")
    
    # 输出品类排名
    for _, row in cat.sort_values('gmv', ascending=False).head(7).iterrows():
        print(f"  {row['category_l1']:20s} GMV={row['gmv']:>12,.0f}  转化率={row['conversion_rate']:.2f}%")


# ── 4. 时段热力图 ───────────────────────────────────────
def plot_hourly_heatmap(df):
    """热力图：每周各天的每小时活跃度"""
    df['dow'] = pd.to_datetime(df['event_date']).dt.dayofweek  # 0=Mon
    hourly = df.groupby(['dow', 'event_hour'])['event_count'].sum().unstack(fill_value=0)
    
    dow_labels = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
    hourly.index = [dow_labels[i] for i in hourly.index]
    
    fig, ax = plt.subplots(figsize=(14, 5))
    sns.heatmap(hourly, cmap='YlOrRd', annot=True, fmt=',.0f',
                linewidths=0.5, cbar_kws={'label': '事件数'}, ax=ax)
    ax.set_title('用户活跃时段热力图（周一~周日）', fontsize=14, fontweight='bold')
    ax.set_xlabel('小时')
    ax.set_ylabel('')
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '04_hourly_heatmap.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


# ── 5. 用户活跃度分布 ───────────────────────────────────
def plot_user_activity(user_df):
    """直方图：用户事件数分布（对数坐标）"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # 事件数分布
    event_counts = user_df['total_events']
    axes[0].hist(event_counts.clip(upper=100), bins=50, color='#8da0cb', edgecolor='white')
    axes[0].set_xlabel('事件数（≥100截断）')
    axes[0].set_ylabel('用户数')
    axes[0].set_title('用户事件数分布')
    
    # 购买次数分布
    purchase_counts = user_df[user_df['total_purchases'] > 0]['total_purchases']
    axes[1].hist(purchase_counts.clip(upper=20), bins=20, color='#fc8d62', edgecolor='white')
    axes[1].set_xlabel('购买次数（≥20截断）')
    axes[1].set_ylabel('用户数')
    axes[1].set_title('购买用户购买次数分布')
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '05_user_activity.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")
    
    # 分段统计
    bins = [0, 1, 2, 5, 10, 20, 50, 100, float('inf')]
    labels = ['1次', '2次', '3-5次', '6-10次', '11-20次', '21-50次', '51-100次', '100+次']
    user_df['activity_segment'] = pd.cut(event_counts, bins=bins, labels=labels, right=True)
    print("用户活跃度分段:")
    print(user_df['activity_segment'].value_counts().sort_index().to_string())


# ── 入口 ────────────────────────────────────────────────
if __name__ == "__main__":
    print("加载数据...")
    df = load_main_data()
    print(f"加载了 {len(df):,} 行聚合数据")
    
    user_df = load_user_summary()
    print(f"加载了 {len(user_df):,} 个用户")
    
    print("\n" + "="*60)
    print("1. 事件类型分布")
    plot_event_distribution(df)
    
    print("\n2. 每日GMV趋势")
    plot_daily_gmv(df)
    
    print("\n3. 品类GMV对比")
    plot_category_gmv(df)
    
    print("\n4. 时段热力图")
    plot_hourly_heatmap(df)
    
    print("\n5. 用户活跃度分布")
    plot_user_activity(user_df)
    
    print("\n✓ EDA 完成！图表已保存到", FIGURE_DIR)
