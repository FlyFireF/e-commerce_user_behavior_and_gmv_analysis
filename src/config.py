"""
数据库与应用配置
===============
数据库与应用配置，运行前请修改为实际值
"""

# MySQL 连接
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "1234",
    "database": "ec_analysis",
    "charset": "utf8mb4",
}

# 数据文件路径
DATA_DIR = "../data"

# 输出目录
FIGURE_DIR = "../figures"
REPORT_DIR = "../reports"

# 分析参数
ANALYSIS_START_DATE = "2019-10-01"
ANALYSIS_END_DATE = "2019-11-30"

# RFM分群日期参考点（通常取数据最后一天）
RFM_REFERENCE_DATE = "2019-12-01"

# 异常用户检测阈值
ANOMALY_DAILY_VIEW_THRESHOLD = 200   # 单日浏览超此次数标记为异常
ANOMALY_HOURLY_VIEW_THRESHOLD = 50   # 单小时浏览超此次数标记为异常

# 数据加载（大文件分批读取）
CHUNK_SIZE = 100000  # 每次读取行数
