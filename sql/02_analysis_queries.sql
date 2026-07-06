-- ============================================================
-- 电商用户行为分析 — 分析SQL查询集
-- ============================================================

-- ============================================================
-- 第一部分：数据概览（快速了解数据全貌）
-- ============================================================

-- Q1. 总体数据量
-- 目的：确认数据规模
SELECT 
    COUNT(*) AS total_events,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT product_id) AS unique_products,
    COUNT(DISTINCT user_session) AS unique_sessions,
    MIN(event_date) AS date_from,
    MAX(event_date) AS date_to
FROM events;

-- Q2. 事件类型分布
-- 目的：了解用户行为结构，这是转化漏斗的基础
SELECT 
    event_type,
    COUNT(*) AS event_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM events
GROUP BY event_type
ORDER BY event_count DESC;

-- Q3. 月度数据量趋势
SELECT 
    DATE_FORMAT(event_date, '%Y-%m') AS month,
    COUNT(*) AS monthly_events,
    COUNT(DISTINCT user_id) AS monthly_active_users
FROM events
GROUP BY month
ORDER BY month;

-- ============================================================
-- 第二部分：漏斗分析（转化率——数分最核心的指标之一）
-- ============================================================

-- Q4. 整体转化漏斗（从浏览到购买）
-- 目的：量化各环节转化率，定位用户流失关键节点
WITH user_funnel AS (
    SELECT 
        user_id,
        MAX(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) AS has_view,
        MAX(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) AS has_cart,
        MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS has_purchase
    FROM events
    GROUP BY user_id
)
SELECT 
    '浏览(view)' AS stage,
    COUNT(*) AS user_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(ORDER BY (SELECT NULL) ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING), 2) AS overall_pct
FROM user_funnel WHERE has_view = 1
UNION ALL
SELECT 
    '加购(cart)' AS stage,
    COUNT(*) AS user_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM user_funnel WHERE has_view = 1), 2) AS view_to_cart_rate
FROM user_funnel WHERE has_cart = 1
UNION ALL
SELECT 
    '购买(purchase)' AS stage,
    COUNT(*) AS user_count,
    ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM user_funnel WHERE has_cart = 1), 2) AS cart_to_purchase_rate
FROM user_funnel WHERE has_purchase = 1;

-- Q5. 加购→购买转化率（按月查看趋势）
-- 目的：监控核心转化指标的时间变化
SELECT 
    DATE_FORMAT(event_date, '%Y-%m') AS month,
    COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN user_id END) AS cart_users,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) AS purchase_users,
    ROUND(
        COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) * 100.0 
        / NULLIF(COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN user_id END), 0), 
        2
    ) AS cart_to_purchase_rate
FROM events
GROUP BY month
ORDER BY month;

-- ============================================================
-- 第三部分：品类分析（多维度拆解）
-- ============================================================

-- Q6. 一级品类核心指标一览
-- 目的：识别高GMV品类、高转化品类、高客单价品类
SELECT 
    category_l1 AS 品类,
    COUNT(DISTINCT product_id) AS 商品数,
    COUNT(*) AS 总事件数,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS 购买事件数,
    ROUND(
        SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) * 100.0 
        / NULLIF(SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END), 0), 
        2
    ) AS 浏览转化率,
    ROUND(AVG(CASE WHEN event_type = 'purchase' THEN price END), 2) AS 平均客单价,
    ROUND(SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END), 2) AS GMV
FROM events
WHERE category_l1 IS NOT NULL AND category_l1 != ''
GROUP BY category_l1
HAVING 总事件数 > 1000
ORDER BY GMV DESC;

-- Q7. 品类内子类目转化对比
-- 目的：深入一级品类内部，找出高/低转化的子类目
SELECT 
    SUBSTRING_INDEX(category_code, '.', 2) AS sub_category,
    COUNT(*) AS total_events,
    SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS purchases,
    ROUND(
        SUM(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) * 100.0 
        / NULLIF(COUNT(*), 0), 
        3
    ) AS conversion_rate
FROM events
WHERE category_l1 = 'electronics'  -- 为实际最大品类名
  AND category_code IS NOT NULL
GROUP BY sub_category
ORDER BY purchases DESC
LIMIT 20;

-- ============================================================
-- 第四部分：用户行为分析
-- ============================================================

-- Q8. 用户活跃度分层
-- 目的：按总事件数将用户分层，看核心用户占比
SELECT 
    CASE 
        WHEN event_count = 1 THEN '1次(过客)'
        WHEN event_count BETWEEN 2 AND 5 THEN '2-5次(轻度)'
        WHEN event_count BETWEEN 6 AND 20 THEN '6-20次(中度)'
        WHEN event_count BETWEEN 21 AND 100 THEN '21-100次(重度)'
        ELSE '100+次(超级用户)'
    END AS user_segment,
    COUNT(*) AS user_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct
FROM (
    SELECT user_id, COUNT(*) AS event_count
    FROM events
    GROUP BY user_id
) t
GROUP BY user_segment
ORDER BY MIN(event_count);

-- Q9. 用户平均行为序列分析（加购前的浏览数、购买前的加购数）
-- 目的：量化用户决策路径长度，用窗口函数实现
WITH user_behavior_seq AS (
    SELECT 
        user_id,
        event_type,
        event_time,
        ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY event_time) AS seq_num,
        SUM(CASE WHEN event_type = 'view' THEN 1 ELSE 0 END) 
            OVER (PARTITION BY user_id ORDER BY event_time) AS cumulative_views,
        SUM(CASE WHEN event_type = 'cart' THEN 1 ELSE 0 END) 
            OVER (PARTITION BY user_id ORDER BY event_time) AS cumulative_carts
    FROM events
    WHERE user_id IN (
        -- 只分析有购买行为的用户
        SELECT DISTINCT user_id FROM events WHERE event_type = 'purchase'
    )
)
SELECT 
    ROUND(AVG(cumulative_views), 1) AS avg_views_before_purchase,
    ROUND(AVG(cumulative_carts), 1) AS avg_carts_before_purchase
FROM user_behavior_seq
WHERE event_type = 'purchase' AND cumulative_views > 0;

-- Q10. 用户会话内行为分析（单次会话的行为模式）
-- 目的：识别高质量会话的特征
SELECT 
    user_session,
    COUNT(*) AS events_in_session,
    COUNT(DISTINCT event_type) AS distinct_event_types,
    MAX(CASE WHEN event_type = 'purchase' THEN 1 ELSE 0 END) AS has_purchase,
    COUNT(DISTINCT category_l1) AS categories_browsed
FROM events
WHERE user_session IS NOT NULL
GROUP BY user_session
HAVING events_in_session >= 5
ORDER BY events_in_session DESC
LIMIT 1000;

-- ============================================================
-- 第五部分：GMV与营收分析
-- ============================================================

-- Q11. 每日GMV趋势
SELECT 
    event_date,
    SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS daily_gmv,
    COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) AS paying_users,
    COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS order_count
FROM events
GROUP BY event_date
ORDER BY event_date;

-- Q12. 用户终身价值(LTV)分布（用于RFM分群的输入）
SELECT 
    user_id,
    COUNT(CASE WHEN event_type = 'purchase' THEN 1 END) AS purchase_count,
    SUM(CASE WHEN event_type = 'purchase' THEN price ELSE 0 END) AS total_spent,
    MIN(CASE WHEN event_type = 'purchase' THEN event_date END) AS first_purchase,
    MAX(CASE WHEN event_type = 'purchase' THEN event_date END) AS last_purchase,
    DATEDIFF(MAX(CASE WHEN event_type = 'purchase' THEN event_date END), 
             MIN(CASE WHEN event_type = 'purchase' THEN event_date END)) AS purchase_span_days
FROM events
WHERE user_id IN (SELECT DISTINCT user_id FROM events WHERE event_type = 'purchase')
GROUP BY user_id
HAVING purchase_count >= 1
ORDER BY total_spent DESC
LIMIT 1000;

-- ============================================================
-- 第六部分：异常检测
-- ============================================================

-- Q13. 异常高频用户检测（疑似爬虫/刷量）
-- 单日浏览>200次或单小时>50次，标记为异常
SELECT 
    user_id,
    event_date,
    COUNT(*) AS daily_events,
    COUNT(CASE WHEN event_type = 'view' THEN 1 END) AS daily_views
FROM events
GROUP BY user_id, event_date
HAVING daily_views > 200
ORDER BY daily_views DESC;

-- Q14. 价格异常检测（免费商品或天价商品）
SELECT 
    product_id,
    brand,
    category_code,
    MIN(price) AS min_price,
    MAX(price) AS max_price
FROM events
WHERE price IS NOT NULL
GROUP BY product_id, brand, category_code
HAVING MIN(price) <= 0 OR MAX(price) > 10000
ORDER BY MAX(price) DESC;
