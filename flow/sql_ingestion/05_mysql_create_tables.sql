-- =====================================================
-- MYSQL TABLES FOR TELECOM ANALYTICAL DATA
-- =====================================================
-- These tables complement the star schema
-- Designed for maximum-speed production MySQL ingestion from Spark
-- Auto-increment IDs restored; duplicate handling disabled.
-- =====================================================

-- =====================================================
-- 1. CURATED USAGE TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS curated_usage (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL,
    grid_id INT NOT NULL,
    country_code VARCHAR(255),
    sms_in_count DOUBLE DEFAULT 0,
    sms_out_count DOUBLE DEFAULT 0,
    call_in_count DOUBLE DEFAULT 0,
    call_out_count DOUBLE DEFAULT 0,
    internet_usage DOUBLE DEFAULT 0,
    date DATE NOT NULL,
    hour INT NOT NULL,
    day_of_week INT,
    total_sms DOUBLE DEFAULT 0,
    total_calls DOUBLE DEFAULT 0,
    total_activity DOUBLE DEFAULT 0,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date_grid (date, grid_id),
    INDEX idx_timestamp (timestamp),
    INDEX idx_grid_id (grid_id),
    INDEX idx_date (date),
    INDEX idx_hour (hour)
);

-- =====================================================
-- 2. QUARANTINE TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS quarantine (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME,
    grid_id VARCHAR(50),
    country_code VARCHAR(255),
    sms_in_count DOUBLE,
    sms_out_count DOUBLE,
    call_in_count DOUBLE,
    call_out_count DOUBLE,
    internet_usage DOUBLE,
    date DATE,
    quarantine_reason VARCHAR(255) NOT NULL,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date_reason (date, quarantine_reason),
    INDEX idx_reason (quarantine_reason),
    INDEX idx_timestamp (timestamp)
);

-- =====================================================
-- 3. HOURLY GRID SUMMARY
-- =====================================================
CREATE TABLE IF NOT EXISTS hourly_grid_summary (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL,
    hour INT NOT NULL,
    grid_id INT NOT NULL,
    sms_in DOUBLE DEFAULT 0,
    sms_out DOUBLE DEFAULT 0,
    call_in DOUBLE DEFAULT 0,
    call_out DOUBLE DEFAULT 0,
    internet_activity DOUBLE DEFAULT 0,
    total_activity DOUBLE DEFAULT 0,
    record_count INT DEFAULT 0,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (date),
    INDEX idx_grid_id (grid_id),
    INDEX idx_hour (hour),
    INDEX idx_total_activity (total_activity DESC)
);

-- =====================================================
-- 4. DAILY SUMMARY
-- =====================================================
CREATE TABLE IF NOT EXISTS daily_summary (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL,
    total_sms DOUBLE DEFAULT 0,
    total_calls DOUBLE DEFAULT 0,
    internet_usage DOUBLE DEFAULT 0,
    total_activity DOUBLE DEFAULT 0,
    active_grids INT DEFAULT 0,
    total_records BIGINT DEFAULT 0,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (date)
);

-- =====================================================
-- 5. GRID SUMMARY
-- =====================================================
CREATE TABLE IF NOT EXISTS grid_summary (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL,
    grid_id INT NOT NULL,
    total_sms DOUBLE DEFAULT 0,
    total_calls DOUBLE DEFAULT 0,
    internet_usage DOUBLE DEFAULT 0,
    total_activity DOUBLE DEFAULT 0,
    active_hours INT DEFAULT 0,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (date),
    INDEX idx_grid_id (grid_id),
    INDEX idx_total_activity (total_activity DESC)
);

-- =====================================================
-- 6. ENRICHED SPATIAL HOURLY
-- =====================================================
CREATE TABLE IF NOT EXISTS enriched_spatial_hourly (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    date DATE NOT NULL,
    hour INT NOT NULL,
    grid_id INT NOT NULL,
    sms_in DOUBLE DEFAULT 0,
    sms_out DOUBLE DEFAULT 0,
    call_in DOUBLE DEFAULT 0,
    call_out DOUBLE DEFAULT 0,
    internet_activity DOUBLE DEFAULT 0,
    total_activity DOUBLE DEFAULT 0,
    geometry LONGTEXT,
    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_date (date),
    INDEX idx_grid_id (grid_id),
    INDEX idx_hour (hour)
);

-- =====================================================
-- 7. AUDIT LOG
-- =====================================================
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    status VARCHAR(20),
    filename VARCHAR(255),
    row_count BIGINT,
    error_message TEXT,
    duration_seconds FLOAT,
    processed_at DATETIME NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_event_type (event_type),
    INDEX idx_status (status),
    INDEX idx_processed_at (processed_at)
);