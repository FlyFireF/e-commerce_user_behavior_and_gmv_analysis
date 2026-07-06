"""
综合可视化脚本
===============
汇总生成用于分析报告的关键图表
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
import os, sys

try:
    from config import DB_CONFIG, FIGURE_DIR
except ImportError:
    print("ERROR: 请先填写 src/config.py")
    sys.exit(1)

sns.set_style("whitegrid")

# ── 中文字体：绝对路径强绑，须在 seaborn 初始化之后 ──
import matplotlib.font_manager as fm
FONT_PATH = 'C:/Windows/Fonts/simhei.ttf'
fm.fontManager.addfont(FONT_PATH)
_font_prop = fm.FontProperties(fname=FONT_PATH)
_font_name = _font_prop.get_name()
plt.rcParams['font.family'] = _font_name
plt.rcParams['axes.unicode_minus'] = False

DB_URL = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
engine = create_engine(DB_URL)
os.makedirs(FIGURE_DIR, exist_ok=True)


def plot_summary_dashboard():
    """综合分析仪表盘 —— 四合一图"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # ── 左上：事件分布饼图 ──
    events = pd.read_sql(
        "SELECT event_type, COUNT(*) AS cnt FROM events GROUP BY event_type", engine
    )
    colors = ['#66c2a5', '#fc8d62', '#8da0cb']
    axes[0, 0].pie(events['cnt'], labels=events['event_type'], autopct='%1.1f%%',
                   startangle=90, colors=colors)
    axes[0, 0].set_title('事件类型分布', fontsize=12, fontweight='bold')
    
    # ── 右上：Top5品类GMV柱状图 ──
    cat_gmv = pd.read_sql("""
        SELECT category_l1, SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END) AS gmv
        FROM events WHERE category_l1 IS NOT NULL AND category_l1 != '' AND event_type='purchase'
        GROUP BY category_l1 ORDER BY gmv DESC LIMIT 5
    """, engine)
    axes[0, 1].bar(cat_gmv['category_l1'], cat_gmv['gmv'], color='#66c2a5')
    axes[0, 1].set_title('Top5品类GMV', fontsize=12, fontweight='bold')
    axes[0, 1].set_ylabel('GMV')
    axes[0, 1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    axes[0, 1].tick_params(axis='x', rotation=30)
    
    # ── 左下：转化漏斗 ──
    funnel = pd.read_sql("""
        SELECT 
            COUNT(DISTINCT CASE WHEN event_type='view' THEN user_id END) AS view_users,
            COUNT(DISTINCT CASE WHEN event_type='cart' THEN user_id END) AS cart_users,
            COUNT(DISTINCT CASE WHEN event_type='purchase' THEN user_id END) AS purchase_users
        FROM events
    """, engine)
    stages = ['浏览', '加购', '购买']
    counts = [funnel.iloc[0,0], funnel.iloc[0,1], funnel.iloc[0,2]]
    max_c = max(counts)
    widths = [c/max_c for c in counts]
    colors_f = ['#66c2a5', '#fc8d62', '#8da0cb']
    for i, (stage, count, w, c) in enumerate(zip(stages, counts, widths, colors_f)):
        axes[1, 0].barh(i, w, left=(1-w)/2, height=0.6, color=c, alpha=0.85)
        axes[1, 0].text(0.5, i, f'{stage}: {count:,}人', ha='center', va='center', fontsize=11, fontweight='bold')
    axes[1, 0].set_yticks([])
    axes[1, 0].set_xlim(0, 1)
    axes[1, 0].set_title('用户转化漏斗', fontsize=12, fontweight='bold')
    
    # ── 右下：每日GMV趋势 ──
    daily = pd.read_sql("""
        SELECT event_date, SUM(CASE WHEN event_type='purchase' THEN price ELSE 0 END) AS gmv
        FROM events WHERE event_type='purchase' GROUP BY event_date ORDER BY event_date
    """, engine)
    axes[1, 1].plot(range(len(daily)), daily['gmv'], color='#fc8d62', linewidth=1.5)
    axes[1, 1].fill_between(range(len(daily)), 0, daily['gmv'], alpha=0.2, color='#fc8d62')
    axes[1, 1].set_title('每日GMV趋势', fontsize=12, fontweight='bold')
    axes[1, 1].set_xlabel('日期序号')
    axes[1, 1].set_ylabel('GMV')
    axes[1, 1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f'{x:,.0f}'))
    
    plt.suptitle('电商用户行为分析 — 综合仪表盘', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '00_summary_dashboard.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 仪表盘已保存: {fp}")


if __name__ == "__main__":
    plot_summary_dashboard()
    print("\n✓ 可视化完成！")
