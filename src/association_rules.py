"""
关联规则挖掘（Market Basket Analysis）
======================================
使用Apriori算法挖掘品类/商品间的购买关联
输出捆绑推荐策略
业务域数据挖掘、数据建模
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine, text
from mlxtend.frequent_patterns import apriori, association_rules
import os, sys, warnings
warnings.filterwarnings('ignore')

try:
    from config import DB_CONFIG, FIGURE_DIR
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


def load_purchase_baskets():
    """
    构建购买篮数据
    每个用户购买的品类集合作为一次"购物篮"
    """
    query = """
    SELECT 
        user_id,
        category_code
    FROM events
    WHERE event_type = 'purchase'
      AND category_code IS NOT NULL
      AND category_code != ''
    """
    df = pd.read_sql(query, engine)
    print(f"购买记录数: {len(df):,}")
    print(f"购买用户数: {df['user_id'].nunique():,}")
    
    # 按用户聚合为购物篮（跨会话，捕获全周期关联）
    baskets = df.groupby('user_id')['category_code'].apply(lambda x: list(set(x))).reset_index()
    baskets = baskets[baskets['category_code'].apply(len) >= 2]  # 至少买过2个不同品类
    print(f"多品类用户购物篮数: {len(baskets):,}")
    
    return baskets


def build_onehot_matrix(baskets):
    """将购物篮列表转为One-Hot编码矩阵"""
    from mlxtend.preprocessing import TransactionEncoder
    
    te = TransactionEncoder()
    te_ary = te.fit_transform(baskets['category_code'].values)
    df_onehot = pd.DataFrame(te_ary, columns=te.columns_)
    
    # 过滤只包含1个品类的篮（无法形成关联规则）
    basket_sizes = df_onehot.sum(axis=1)
    df_onehot = df_onehot[basket_sizes >= 2]
    print(f"多品类购物篮数: {len(df_onehot):,}")
    
    return df_onehot


def mine_association_rules(df_onehot):
    """挖掘关联规则"""
    # 频繁项集
    print("挖掘频繁项集...")
    frequent_itemsets = apriori(
        df_onehot, 
        min_support=0.003,  # 支持度阈值：至少0.5%的购物篮包含该组合
        use_colnames=True,
        max_len=3,          # 最多3项组合
    )
    print(f"频繁项集数: {len(frequent_itemsets)}")
    
    if len(frequent_itemsets) == 0:
        print("⚠ 未找到频繁项集，请降低min_support阈值")
        return None
    
    # 关联规则
    print("生成关联规则...")
    rules = association_rules(
        frequent_itemsets, 
        metric="lift",
        min_threshold=1.0,  # 提升度>1（比随机同时购买概率高）
    )
    
    # 过滤：置信度>20%
    rules = rules[rules['confidence'] >= 0.10]
    rules = rules.sort_values('lift', ascending=False)
    
    print(f"关联规则数: {len(rules)}")
    return rules


def display_top_rules(rules, top_n=15):
    """输出Top N关联规则"""
    if rules is None or len(rules) == 0:
        print("无关联规则可展示")
        return
    
    print(f"\n{'='*80}")
    print(f"Top {top_n} 品类关联规则（按提升度排序）")
    print(f"{'='*80}")
    print(f"{'前项':<30s} {'后项':<30s} {'支持度':>8s} {'置信度':>8s} {'提升度':>8s}")
    print("-"*80)
    
    for _, row in rules.head(top_n).iterrows():
        ant = ', '.join(list(row['antecedents']))[:28]
        con = ', '.join(list(row['consequents']))[:28]
        print(f"{ant:<30s} {con:<30s} {row['support']:>8.4f} {row['confidence']:>8.4f} {row['lift']:>8.3f}")
    
    return rules.head(top_n)


def plot_association_heatmap(rules, top_n=10):
    """关联规则热力图"""
    if rules is None or len(rules) == 0:
        return
    
    top_rules = rules.head(top_n)
    
    # 构建矩阵
    antecedents = top_rules['antecedents'].apply(lambda x: ', '.join(list(x)))
    consequents = top_rules['consequents'].apply(lambda x: ', '.join(list(x)))
    
    all_items = sorted(set(antecedents) | set(consequents))
    matrix = pd.DataFrame(0.0, index=all_items, columns=all_items)
    
    for _, row in top_rules.iterrows():
        ant = ', '.join(list(row['antecedents']))
        con = ', '.join(list(row['consequents']))
        matrix.loc[ant, con] = row['lift']
    
    # 只保留非零行/列
    matrix = matrix.loc[(matrix.sum(axis=1) > 0), (matrix.sum(axis=0) > 0)]
    
    if matrix.shape[0] < 2:
        print("⚠ 规则太少，无法生成热力图")
        return
    
    fig, ax = plt.subplots(figsize=(max(8, matrix.shape[1]*1.2), max(6, matrix.shape[0]*0.8)))
    sns.heatmap(matrix, annot=True, fmt='.2f', cmap='YlOrRd',
                linewidths=0.5, cbar_kws={'label': '提升度(Lift)'}, ax=ax)
    ax.set_title('品类关联规则热力图（提升度）', fontsize=14, fontweight='bold')
    ax.set_xlabel('后项')
    ax.set_ylabel('前项')
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '09_association_heatmap.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


def plot_top_rules_bar(rules, top_n=10):
    """关联规则柱状图"""
    if rules is None or len(rules) == 0:
        return
    
    top = rules.head(top_n).iloc[::-1]
    
    labels = []
    for _, row in top.iterrows():
        ant = ', '.join(list(row['antecedents']))
        con = ', '.join(list(row['consequents']))
        labels.append(f"{ant} → {con}")
    
    fig, ax = plt.subplots(figsize=(10, 6))
    y_pos = range(len(labels))
    
    ax.barh(y_pos, top['lift'].values, color='#fc8d62', alpha=0.8)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.set_xlabel('提升度 (Lift)')
    ax.set_title('Top品类关联规则（提升度越高=关联越强）', fontsize=13, fontweight='bold')
    ax.axvline(x=1, color='gray', linestyle='--', alpha=0.5, label='Lift=1 (随机)')
    ax.legend()
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '10_association_rules_bar.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


if __name__ == "__main__":
    print("加载购买数据...")
    baskets = load_purchase_baskets()
    
    print("\n构建One-Hot矩阵...")
    df_onehot = build_onehot_matrix(baskets)
    
    print("\n挖掘关联规则...")
    rules = mine_association_rules(df_onehot)
    
    if rules is not None:
        display_top_rules(rules, top_n=15)
        plot_association_heatmap(rules, top_n=10)
        plot_top_rules_bar(rules, top_n=10)
    
    print("\n✓ 关联规则分析完成！")
