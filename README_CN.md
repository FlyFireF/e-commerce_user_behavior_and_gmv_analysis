# 电商用户行为与GMV数据分析

[English](./README.md)

从原始CSV到业务洞察的完整数据分析流水线。

**数据集**：[eCommerce Behavior Data from Multi Category Store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)（Kaggle）  
**规模**：约1100万条用户行为事件（2019年10-11月）  
**技术栈**：MySQL 8.0、Python 3.10+（Pandas、Scikit-learn、Matplotlib、Seaborn、mlxtend）

## 项目结构

```
ec_project/
├── README.md
├── README_CN.md
├── requirements.txt
├── data/                           # 原始CSV数据（需单独下载）
│   ├── 2019-Oct.csv
│   └── 2019-Nov.csv
├── sql/
│   ├── 01_create_tables.sql        # 建表语句 + 索引定义
│   └── 02_analysis_queries.sql     # 14条分析SQL查询
├── src/
│   ├── config.py                   # 数据库和路径配置
│   ├── data_preparation.py         # CSV分批导入、清洗、聚合
│   ├── eda.py                      # 探索性数据分析（5张图表）
│   ├── rfm_analysis.py             # RFM用户分群（3张图表）
│   ├── conversion_analysis.py      # 漏斗分析 + 逻辑回归归因（2张图表）
│   ├── association_rules.py        # Apriori关联规则挖掘（2张图表）
│   └── visualization.py            # 综合仪表盘（1张看板）
└── figures/                        # 生成的图表（PNG）

```

## 快速开始

### 1. 环境要求

- Python 3.10+
- MySQL 8.0+（InnoDB引擎）
- 约35 GB空闲磁盘空间（14 GB CSV + 约20 GB MySQL）
- 建议内存：16 GB+

### 2. 环境搭建

```bash
# 进入项目目录
cd ec_project

# 创建虚拟环境
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 3. 下载数据

从Kaggle下载数据集，将CSV文件放入 `data/` 目录：

- [2019-Oct.csv](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)
- [2019-Nov.csv](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)

### 4. 配置数据库

编辑 `src/config.py`，填入你的MySQL连接信息：

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "你的密码",
    "database": "ec_analysis",
    "charset": "utf8mb4",
}
```

### 5. 创建数据库

连接MySQL执行：

```sql
CREATE DATABASE IF NOT EXISTS ec_analysis CHARACTER SET utf8mb4;
```

或直接执行SQL脚本：`sql/01_create_tables.sql`

### 6. 运行分析流水线

按顺序执行：

```bash
python src/data_preparation.py    # CSV导入MySQL（约2-5小时+）
python src/eda.py                 # 探索性分析
python src/rfm_analysis.py        # 用户分群
python src/conversion_analysis.py # 漏斗与归因
python src/association_rules.py   # 关联规则挖掘
python src/visualization.py       # 综合仪表盘
```

**注意**：`data_preparation.py` 会将约14 GB的CSV数据导入MySQL。处理时间取决于硬件配置。建议将MySQL的 `innodb_buffer_pool_size` 设置为512 MB以上以获得最佳性能。如果遇到"lock table size exceeded"错误，脚本会自动尝试增大缓冲池；如无权限则用较小批次替代。

### 7. 产出物

- **图表**：`figures/` 目录（11张PNG）
- **RFM分群结果**：`rfm_segments.csv`
- **控制台输出**：关键统计数据

## 分析流程

| 步骤 | 脚本 | 功能说明 |
|:-----|:-----|:---------|
| 数据入库 | `data_preparation.py` | 分批导入1100万行CSV数据到MySQL，生成 `users` 和 `products` 聚合维度表，创建索引 |
| 探索性分析 | `eda.py` | 事件分布饼图、每日GMV趋势、品类对比、时段热力图、用户活跃度分布 |
| RFM分群 | `rfm_analysis.py` | 对用户进行R（最近购买）/F（购买频次）/M（消费金额）三维评分，分为5个层级，输出CSV |
| 转化分析 | `conversion_analysis.py` | 浏览→加购→购买漏斗分析，逻辑回归模型量化各行为特征对转化概率的贡献 |
| 关联规则 | `association_rules.py` | Apriori算法挖掘跨品类购买关联，输出捆绑推荐规则 |
| 可视化 | `visualization.py` | 2×2综合仪表盘（事件饼图、Top品类GMV、转化漏斗、每日GMV趋势） |

## SQL分析查询说明

`sql/02_analysis_queries.sql` 包含14条查询，按主题分为六部分：

- **数据概览**（Q1-Q3）：总数据量、事件分布、月度趋势
- **漏斗分析**（Q4-Q5）：浏览→加购→购买各环节转化率
- **品类分析**（Q6-Q7）：品类GMV排名、子类目下钻
- **用户行为**（Q8-Q10）：活跃度分层、行为序列、会话分析
- **GMV分析**（Q11-Q12）：每日GMV走势、用户终身价值分布
- **异常检测**（Q13-Q14）：高频用户识别、价格异常检测

涵盖的SQL技术：CTE公共表表达式、窗口函数（ROW_NUMBER、LAG、SUM OVER）、条件聚合、多表JOIN。

## 依赖清单

```
pandas>=2.0.0
numpy>=1.24.0
matplotlib>=3.7.0
seaborn>=0.12.0
scikit-learn>=1.3.0
sqlalchemy>=2.0.0
pymysql>=1.1.0
mlxtend>=0.23.0
tqdm>=4.65.0
```

## 常见问题

**Q: data_preparation.py 报 "lock table size exceeded" 错误怎么办？**

将 `src/data_preparation.py` 中的 `AGG_BATCH_SIZE` 调小（如从5000降到2000），或者增大MySQL的 `innodb_buffer_pool_size` 至512MB以上。

**Q: 中文图表显示方框或乱码？**

脚本会自动加载系统字体 SimHei（黑体）。如果仍乱码，检查 `C:/Windows/Fonts/simhei.ttf` 是否存在；如果不存在，安装中文字体或将代码中的字体路径改为系统已有的中文字体路径。

**Q: 可以只跑部分分析吗？**

可以。`data_preparation.py` 是前置依赖（必须跑），之后的5个分析脚本各自独立，可按需运行。

## 许可证

MIT
