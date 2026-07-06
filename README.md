# E-commerce User Behavior & GMV Analysis

[简体中文](./README_CN.md)

A complete data analysis pipeline for e-commerce user behavior data: from raw CSV ingestion to business insights.

**Dataset**: [eCommerce Behavior Data from Multi Category Store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store) (Kaggle)  
**Scale**: ~11 million user behavior events (Oct-Nov 2019)  
**Tech Stack**: MySQL 8.0, Python 3.10+ (Pandas, Scikit-learn, Matplotlib, Seaborn, mlxtend)

## Project Structure

```
ec_project/
├── README.md
├── README_CN.md
├── requirements.txt
├── data/                           # Raw CSV files (download separately)
│   ├── 2019-Oct.csv
│   └── 2019-Nov.csv
├── sql/
│   ├── 01_create_tables.sql        # Database schema + indexes
│   └── 02_analysis_queries.sql     # 14 analytical SQL queries
├── src/
│   ├── config.py                   # Database and path configuration
│   ├── data_preparation.py         # CSV ingestion, cleaning, aggregation
│   ├── eda.py                      # Exploratory data analysis (5 charts)
│   ├── rfm_analysis.py             # RFM user segmentation (3 charts)
│   ├── conversion_analysis.py      # Funnel analysis + logistic regression (2 charts)
│   ├── association_rules.py        # Apriori market basket analysis (2 charts)
│   └── visualization.py            # Summary dashboard (1 dashboard)
├── figures/                        # Generated charts (PNG)
└── reports/
    └── analysis_report.md          # Analysis report template
```

## Quick Start

### 1. Prerequisites

- Python 3.10+
- MySQL 8.0+ (with InnoDB engine)
- ~35 GB free disk space (14 GB CSV + ~20 GB MySQL)
- Recommended: 16 GB+ RAM

### 2. Setup

```bash
# Clone and enter project
cd ec_project

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt
```

### 3. Download Data

Download the dataset from Kaggle and place the CSV files in `data/`:

- [2019-Oct.csv](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)
- [2019-Nov.csv](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)

### 4. Configure

Edit `src/config.py` with your MySQL credentials:

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "your_password",
    "database": "ec_analysis",
    "charset": "utf8mb4",
}
```

### 5. Create Database

Connect to MySQL and run:

```sql
CREATE DATABASE IF NOT EXISTS ec_analysis CHARACTER SET utf8mb4;
```

Or use the SQL script: `sql/01_create_tables.sql`

### 6. Run Pipeline

Execute scripts in order:

```bash
python src/data_preparation.py    # CSV to MySQL (~2-5+ hours)
python src/eda.py                 # Exploratory analysis
python src/rfm_analysis.py        # User segmentation
python src/conversion_analysis.py # Funnel and attribution
python src/association_rules.py   # Market basket analysis
python src/visualization.py       # Summary dashboard
```

**Note**: `data_preparation.py` imports ~14 GB of CSV data into MySQL. Processing time depends on your hardware. For best performance, set MySQL `innodb_buffer_pool_size` to at least 512 MB.

### 7. Output

- **Charts**: `figures/` directory (11 PNG files)
- **RFM segments**: `rfm_segments.csv`
- **Console output**: Key statistics

## Analysis Flow

| Step | Script | What It Does |
|:-----|:-------|:-------------|
| Data Ingestion | `data_preparation.py` | Batch-loads 11M CSV rows into MySQL, creates aggregate tables (`users`, `products`), builds indexes |
| EDA | `eda.py` | Event distribution, daily GMV trends, category comparison, hourly heatmap, user activity distribution |
| RFM Segmentation | `rfm_analysis.py` | Scores users on Recency/Frequency/Monetary, segments into 5 tiers, outputs CSV |
| Conversion Analysis | `conversion_analysis.py` | Funnel analysis (view -> cart -> purchase), logistic regression to quantify conversion drivers |
| Association Rules | `association_rules.py` | Apriori algorithm for cross-category purchase associations |
| Dashboard | `visualization.py` | 2x2 summary dashboard (event pie, top categories, funnel, daily GMV) |

## SQL Analysis Queries

The `sql/02_analysis_queries.sql` file contains 14 queries organized by topic:

- **Data Overview** (Q1-Q3): Total scale, event distribution, monthly trends
- **Funnel Analysis** (Q4-Q5): View to Cart to Purchase conversion rates
- **Category Analysis** (Q6-Q7): Category GMV ranking, sub-category drill-down
- **User Behavior** (Q8-Q10): Activity segmentation, behavior sequences, session analysis
- **GMV Analysis** (Q11-Q12): Daily GMV trends, user LTV distribution
- **Anomaly Detection** (Q13-Q14): High-frequency users, price outliers

Key SQL techniques demonstrated: CTEs, window functions (ROW_NUMBER, LAG, SUM OVER), conditional aggregation, multi-table JOINs.

## Dependencies

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

## License

MIT
