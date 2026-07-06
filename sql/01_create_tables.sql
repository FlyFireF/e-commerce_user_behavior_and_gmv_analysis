-- ============================================================
-- 电商用户行为分析 — 建库建表 + 索引
-- 数据集: eCommerce Behavior Data (Kaggle)
-- 数据量: ~1100万行 (Oct+Nov 2019)
-- ============================================================

CREATE DATABASE IF NOT EXISTS ec_analysis  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ec_analysis;


-- -----------------------------------------------------------
-- 1. 用户维度表（从events表中提取去重user_id）
-- -----------------------------------------------------------
CREATE TABLE users (
    user_id         BIGINT NOT NULL PRIMARY KEY,
    first_seen      DATETIME COMMENT '首次出现时间',
    last_seen       DATETIME COMMENT '最后出现时间',
    total_events    INT DEFAULT 0 COMMENT '总事件数',
    total_purchases INT DEFAULT 0 COMMENT '总购买次数',
    lifetime_value  DECIMAL(12,2) DEFAULT 0.00 COMMENT '累计消费金额'
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 2. 商品维度表
-- -----------------------------------------------------------
CREATE TABLE products (
    product_id      BIGINT NOT NULL PRIMARY KEY,
    category_id     BIGINT,
    category_code   VARCHAR(255) COMMENT '类目编码，如 electronics.smartphone',
    category_l1     VARCHAR(100) COMMENT '一级类目',
    category_l2     VARCHAR(100) COMMENT '二级类目',
    category_l3     VARCHAR(100) COMMENT '三级类目',
    brand           VARCHAR(255),
    avg_price       DECIMAL(10,2) COMMENT '平均价格',
    total_views     INT DEFAULT 0,
    total_carts     INT DEFAULT 0,
    total_purchases INT DEFAULT 0
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 3. 事件表（主表，千万级）
-- -----------------------------------------------------------
CREATE TABLE events (
    id              BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    event_time      DATETIME NOT NULL,
    event_type      ENUM('view', 'cart', 'purchase') NOT NULL,
    product_id      BIGINT NOT NULL,
    category_id     BIGINT,
    category_code   VARCHAR(255),
    category_l1     VARCHAR(100),
    brand           VARCHAR(255),
    price           DECIMAL(10,2),
    user_id         BIGINT NOT NULL,
    user_session    VARCHAR(64),
    -- 派生字段（方便后续查询）
    event_date      DATE NOT NULL,
    event_hour      TINYINT,
    is_purchase     TINYINT DEFAULT 0 COMMENT '是否购买事件: 1=是'
) ENGINE=InnoDB;

-- -----------------------------------------------------------
-- 4. 索引（对千万级表至关重要）
-- -----------------------------------------------------------
-- 主查询索引
CREATE INDEX idx_events_user_id ON events(user_id);
CREATE INDEX idx_events_event_date ON events(event_date);
CREATE INDEX idx_events_event_type ON events(event_type);
CREATE INDEX idx_events_product_id ON events(product_id);
CREATE INDEX idx_events_category_l1 ON events(category_l1);

-- 复合索引（转化漏斗分析核心查询）
CREATE INDEX idx_events_user_date_type ON events(user_id, event_date, event_type);

-- 会话分析索引
CREATE INDEX idx_events_session ON events(user_session);

-- 购买行为索引
CREATE INDEX idx_events_purchase ON events(is_purchase, event_date);

-- 数据导入请使用 Python 脚本: python src/data_preparation.py
