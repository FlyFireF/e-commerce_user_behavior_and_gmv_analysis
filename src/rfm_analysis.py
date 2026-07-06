"""
RFM用户分群分析
================
基于 最近购买时间(R) / 购买频次(F) / 消费金额(M) 的三维用户分层
数据建模与挖掘、业务归因、指标体系
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine, text
import os, sys

try:
    from config import DB_CONFIG, FIGURE_DIR, RFM_REFERENCE_DATE
except ImportError:
    print("ERROR: 请先填写 src/config.py")
    sys.exit(1)

# ── 中文字体：绝对路径强绑，绕过缓存/名称匹配 ──
import matplotlib.font_manager as fm
FONT_PATH = 'C:/Windows/Fonts/simhei.ttf'
fm.fontManager.addfont(FONT_PATH)
_font_prop = fm.FontProperties(fname=FONT_PATH)
_font_name = _font_prop.get_name()
plt.rcParams['font.family'] = _font_name
plt.rcParams['axes.unicode_minus'] = False

DB_URL = f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}?charset={DB_CONFIG['charset']}"
engine = create_engine(DB_URL)


def load_rfm_data():
    """从users表提取RFM原始数据"""
    query = f"""
    SELECT 
        user_id,
        DATEDIFF('{RFM_REFERENCE_DATE}', last_seen) AS recency,
        total_purchases AS frequency,
        lifetime_value AS monetary
    FROM users
    WHERE total_purchases > 0
      AND lifetime_value > 0
    """
    df = pd.read_sql(query, engine)
    print(f"有购买行为的用户数: {len(df):,}")
    return df


def rfm_scoring(df):
    """
    RFM评分：每个维度按分位数分为5档（1-5分）
    R: 越小越好 → 分值反转
    F: 越大越好
    M: 越大越好
    """
    # Recency: 天数越小越好 → 反转打分
    r_labels = [5, 4, 3, 2, 1]
    df['R_score'] = pd.qcut(df['recency'], q=5, labels=r_labels).astype(int)
    
    # Frequency: 次数越多越好
    try:
        df['F_score'] = pd.qcut(df['frequency'], q=5, labels=[1, 2, 3, 4, 5]).astype(int)
    except ValueError:
        # 如果购买次数分布集中在少数值，用cut降级
        df['F_score'] = pd.cut(df['frequency'], bins=5, labels=[1, 2, 3, 4, 5]).astype(int)
    
    # Monetary: 金额越高越好
    df['M_score'] = pd.qcut(df['monetary'], q=5, labels=[1, 2, 3, 4, 5]).astype(int)
    
    # 综合RFM分数
    df['RFM_score'] = df['R_score'] + df['F_score'] + df['M_score']
    
    return df


def segment_users(df):
    """根据RFM分数进行用户分层"""
    conditions = [
        (df['RFM_score'] >= 13),
        (df['RFM_score'].between(10, 12)),
        (df['RFM_score'].between(7, 9)),
        (df['RFM_score'].between(5, 6)),
        (df['RFM_score'] <= 4),
    ]
    labels = [
        '高价值用户',     # R高+F高+M高
        '潜力用户',       # 中等偏高
        '需激活用户',     # 中等
        '流失预警用户',   # 偏低
        '已流失用户',     # 低
    ]
    df['segment'] = np.select(conditions, labels, default='未分类')
    return df


def plot_rfm_summary(df):
    """可视化RFM分群结果"""
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    
    # 1. 饼图：各层用户占比
    seg_counts = df['segment'].value_counts()
    colors_map = {
        '高价值用户': '#2ecc71',
        '潜力用户': '#3498db',
        '需激活用户': '#f39c12',
        '流失预警用户': '#e74c3c',
        '已流失用户': '#95a5a6',
    }
    colors = [colors_map.get(s, '#bdc3c7') for s in seg_counts.index]
    
    axes[0].pie(seg_counts.values, labels=seg_counts.index, autopct='%1.1f%%',
                startangle=90, colors=colors)
    axes[0].set_title('RFM用户分层占比', fontsize=13, fontweight='bold')
    
    # 2. 柱状图：各层GMV贡献
    gmv_by_seg = df.groupby('segment')['monetary'].sum().sort_values(ascending=True)
    bars = axes[1].barh(range(len(gmv_by_seg)), gmv_by_seg.values, 
                        color=[colors_map.get(s, '#bdc3c7') for s in gmv_by_seg.index])
    axes[1].set_yticks(range(len(gmv_by_seg)))
    axes[1].set_yticklabels(gmv_by_seg.index)
    axes[1].set_xlabel('GMV贡献')
    axes[1].set_title('各层用户GMV贡献', fontsize=13, fontweight='bold')
    
    # 3. 散点图：R vs F，颜色=分层
    for seg in df["segment"].unique():
        subset = df[df['segment'] == seg]
        axes[2].scatter(subset['recency'], subset['frequency'], 
                        c=colors_map.get(seg, '#bdc3c7'), label=seg,
                        alpha=0.4, s=10)
    axes[2].set_xlabel('最近购买距今天数 (Recency)')
    axes[2].set_ylabel('购买次数 (Frequency)')
    axes[2].set_title('R-F 散点图（颜色=分层）', fontsize=13, fontweight='bold')
    axes[2].legend(markerscale=3, fontsize=8)
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '06_rfm_segmentation.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


def output_segment_stats(df):
    """输出各层详细统计"""
    print("\n" + "="*70)
    print("RFM用户分层详细统计")
    print("="*70)
    
    stats = df.groupby('segment').agg(
        用户数=('user_id', 'count'),
        用户占比=('user_id', lambda x: f'{len(x)/len(df)*100:.1f}%'),
        平均R=('recency', 'mean'),
        平均F=('frequency', 'mean'),
        平均M=('monetary', 'mean'),
        GMV贡献=('monetary', 'sum'),
        GMV占比=('monetary', lambda x: f'{x.sum()/df["monetary"].sum()*100:.1f}%'),
    )
    
    # 排序
    seg_order = ['高价值用户', '潜力用户', '需激活用户', '流失预警用户', '已流失用户']
    stats = stats.reindex(seg_order)
    
    for idx, row in stats.iterrows():
        print(f"\n{'─'*50}")
        print(f"【{idx}】")
        print(f"  用户数: {row['用户数']:>8,}  占比: {row['用户占比']}")
        print(f"  平均R(天): {row['平均R']:>7.1f}  |  平均F(次): {row['平均F']:>6.1f}  |  平均M: {row['平均M']:>10,.1f}")
        print(f"  GMV贡献: {row['GMV贡献']:>12,.0f}  占比: {row['GMV占比']}")
    
    return stats


if __name__ == "__main__":
    print("加载RFM数据...")
    df = load_rfm_data()
    
    print("计算RFM评分...")
    df = rfm_scoring(df)
    
    print("用户分层...")
    df = segment_users(df)
    
    # 可视化
    plot_rfm_summary(df)
    
    # 详细统计
    stats = output_segment_stats(df)
    
    # 保存分层结果到CSV（供后续使用）
    out_path = os.path.join(os.path.dirname(FIGURE_DIR), 'rfm_segments.csv')
    df[['user_id', 'recency', 'frequency', 'monetary', 'R_score', 'F_score', 'M_score', 'RFM_score', 'segment']].to_csv(
        out_path, index=False, encoding='utf-8-sig'
    )
    print(f"\n✓ 分层结果已保存: {out_path}")
