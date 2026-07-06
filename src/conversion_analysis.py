"""
转化漏斗分析与归因建模
======================
分析用户从浏览→加购→购买的转化链路
使用逻辑回归量化各行为特征对转化的贡献
业务归因分析、数据建模
"""

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
from sqlalchemy import create_engine, text
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
import os, sys, warnings
warnings.filterwarnings('ignore')

try:
    from config import DB_CONFIG, FIGURE_DIR, ANALYSIS_START_DATE, ANALYSIS_END_DATE
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


def build_user_features():
    """
    从events表构建用户行为特征宽表
    每个用户一行，包含行为特征和是否购买的标签
    这是转化归因分析的核心——特征工程
    """
    query = f"""
    SELECT 
        u.user_id,
        -- 行为数量特征
        SUM(CASE WHEN e.event_type = 'view' THEN 1 ELSE 0 END) AS view_count,
        SUM(CASE WHEN e.event_type = 'cart' THEN 1 ELSE 0 END) AS cart_count,
        -- 购买行为
        CASE WHEN SUM(e.is_purchase) > 0 THEN 1 ELSE 0 END AS has_purchased,
        -- 品类多样性（浏览了多少个不同品类）
        COUNT(DISTINCT CASE WHEN e.event_type = 'view' THEN e.category_l1 END) AS distinct_categories,
        -- 活跃天数
        COUNT(DISTINCT e.event_date) AS active_days,
        -- 总消费金额
        COALESCE(SUM(CASE WHEN e.event_type = 'purchase' THEN e.price ELSE 0 END), 0) AS total_spent,
        -- 平均浏览价格
        AVG(CASE WHEN e.event_type = 'view' THEN e.price END) AS avg_viewed_price,
        -- 会话数
        COUNT(DISTINCT e.user_session) AS session_count,
        -- 首次和最后活跃日期
        MIN(e.event_date) AS first_active,
        MAX(e.event_date) AS last_active
    FROM users u
    JOIN events e ON u.user_id = e.user_id
    WHERE e.event_date BETWEEN '{ANALYSIS_START_DATE}' AND '{ANALYSIS_END_DATE}'
    GROUP BY u.user_id
    HAVING view_count >= 1
    """
    df = pd.read_sql(query, engine)
    print(f"构建了 {len(df):,} 个用户的特征宽表")
    
    # 派生特征
    df['view_to_cart_ratio'] = np.where(df['view_count'] > 0, df['cart_count'] / df['view_count'], 0)
    df['avg_events_per_day'] = np.where(df['active_days'] > 0, 
                                         (df['view_count'] + df['cart_count']) / df['active_days'], 0)
    
    # 处理无穷和NaN
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.fillna(0)
    
    return df


def run_logistic_regression(df):
    """逻辑回归归因分析——量化各特征的转化贡献"""
    feature_cols = [
        'view_count', 'cart_count', 'distinct_categories',
        'active_days', 'session_count', 'avg_viewed_price',
        'view_to_cart_ratio', 'avg_events_per_day'
    ]
    
    # 过滤掉极少浏览的用户（可能是噪声）
    df_model = df[df['view_count'] >= 2].copy()
    print(f"建模样本: {len(df_model):,} 用户")
    print(f"其中购买用户: {df_model['has_purchased'].sum():,} "
          f"({df_model['has_purchased'].mean()*100:.2f}%)")
    
    X = df_model[feature_cols].values
    y = df_model['has_purchased'].values
    
    # 标准化
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    # 划分训练/测试集
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.3, random_state=42, stratify=y
    )
    
    # 训练逻辑回归
    model = LogisticRegression(
        max_iter=1000,
        class_weight='balanced',  # 处理类别不平衡
        random_state=42,
    )
    model.fit(X_train, y_train)
    
    # 评估
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]
    
    print(f"\n模型评估:")
    print(f"  AUC: {roc_auc_score(y_test, y_prob):.4f}")
    print(f"  准确率: {(y_pred == y_test).mean():.4f}")
    
    # 特征重要性（Odds Ratio）
    odds_ratios = np.exp(model.coef_[0])
    feature_importance = pd.DataFrame({
        '特征': feature_cols,
        '系数': model.coef_[0],
        'OR(优势比)': odds_ratios,
        'abs_coef': np.abs(model.coef_[0]),
    }).sort_values('abs_coef', ascending=False)
    
    # 特征名中文映射
    name_map = {
        'view_count': '浏览次数',
        'cart_count': '加购次数',
        'distinct_categories': '浏览品类数',
        'active_days': '活跃天数',
        'session_count': '会话数',
        'avg_viewed_price': '平均浏览价格',
        'view_to_cart_ratio': '浏览→加购比',
        'avg_events_per_day': '日均事件数',
    }
    feature_importance['特征名'] = feature_importance['特征'].map(name_map)
    
    print(f"\n特征重要性排名（按OR绝对值的对数）:")
    print(f"{'特征名':<16s} {'系数':>8s} {'OR':>8s} {'解读'}")
    print("-" * 65)
    for _, row in feature_importance.iterrows():
        if row['OR(优势比)'] > 1:
            interp = f"每增加1单位，购买概率提升{(row['OR(优势比)']-1)*100:.0f}%"
        else:
            interp = f"每增加1单位，购买概率降低{(1-row['OR(优势比)'])*100:.0f}%"
        print(f"{row['特征名']:<16s} {row['系数']:>+8.4f} {row['OR(优势比)']:>8.3f} {interp}")
    
    return feature_importance


def plot_conversion_funnel(df):
    """转化漏斗可视化"""
    # 直接从原始数据构建漏斗
    total_users = len(df)
    has_view = total_users
    has_cart = (df['cart_count'] > 0).sum()
    has_purchase = df['has_purchased'].sum()
    
    stages = ['浏览(view)', '加购(cart)', '购买(purchase)']
    counts = [has_view, has_cart, has_purchase]
    rates = [100, has_cart/has_view*100, has_purchase/has_cart*100 if has_cart > 0 else 0]
    
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # 漏斗图
    colors = ['#66c2a5', '#fc8d62', '#8da0cb']
    y_pos = range(len(stages))
    max_w = max(counts)
    widths = [c/max_w for c in counts]
    
    for i, (stage, count, w, c) in enumerate(zip(stages, counts, widths, colors)):
        left = (1 - w) / 2
        axes[0].barh(y_pos[i], w, left=left, height=0.6, color=c, alpha=0.85)
        axes[0].text(0.5, y_pos[i], f'{stage}\n{count:,}人 ({rates[i]:.1f}%)',
                    ha='center', va='center', fontsize=11, fontweight='bold')
    
    axes[0].set_yticks([])
    axes[0].set_xlim(0, 1)
    axes[0].set_title('用户转化漏斗', fontsize=14, fontweight='bold')
    
    # 特征重要性柱状图
    importance = run_logistic_regression(df)
    
    top_features = importance.head(6).iloc[::-1]
    axes[1].barh(range(len(top_features)), top_features['OR(优势比)'].values, color='#8da0cb')
    axes[1].set_yticks(range(len(top_features)))
    axes[1].set_yticklabels(top_features['特征名'].values)
    axes[1].axvline(x=1, color='red', linestyle='--', alpha=0.7, label='OR=1 (无影响)')
    axes[1].set_xlabel('优势比 (OR > 1 = 正向影响)')
    axes[1].set_title('转化影响因素优势比 (OR)', fontsize=14, fontweight='bold')
    axes[1].legend()
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '07_conversion_funnel.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


def plot_feature_importance_detail(feature_importance):
    """详细特征重要性图"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    top = feature_importance.head(8).iloc[::-1]
    colors = ['#2ecc71' if v > 1 else '#e74c3c' for v in top['OR(优势比)'].values]
    
    ax.barh(range(len(top)), top['系数'].values, color=colors)
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top['特征名'].values)
    ax.set_xlabel('逻辑回归系数')
    ax.set_title('转化影响因素系数（正→促进购买，负→抑制购买）', fontsize=13, fontweight='bold')
    ax.axvline(x=0, color='black', linewidth=0.8)
    
    for i, (coef, or_val) in enumerate(zip(top['系数'].values, top['OR(优势比)'].values)):
        ax.text(coef, i, f' OR={or_val:.2f}', va='center', fontsize=9, 
                ha='left' if coef > 0 else 'right')
    
    plt.tight_layout()
    fp = os.path.join(FIGURE_DIR, '08_feature_importance.png')
    fig.savefig(fp, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"✓ 已保存: {fp}")


if __name__ == "__main__":
    print("构建用户行为特征...")
    df = build_user_features()
    
    print(f"\n数据概览:")
    print(f"  总用户数: {len(df):,}")
    print(f"  有加购行为的用户: {(df['cart_count']>0).sum():,} ({(df['cart_count']>0).mean()*100:.1f}%)")
    print(f"  有购买行为的用户: {df['has_purchased'].sum():,} ({df['has_purchased'].mean()*100:.1f}%)")
    print(f"  人均浏览商品数: {df['view_count'].mean():.1f}")
    print(f"  人均浏览品类数: {df['distinct_categories'].mean():.1f}")
    
    print("\n" + "="*60)
    print("逻辑回归归因分析")
    print("="*60)
    importance = run_logistic_regression(df)
    
    print("\n生成可视化...")
    plot_conversion_funnel(df)
    plot_feature_importance_detail(importance)
    
    print("\n✓ 转化分析完成！")
