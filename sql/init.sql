-- Optional PostgreSQL schema. The crawler process does not open this database.
CREATE SCHEMA IF NOT EXISTS crawler;

-- Main crawl results table
CREATE TABLE IF NOT EXISTS crawler.crawl_results (
    id SERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    status_code INTEGER NOT NULL,
    title TEXT,
    links_count INTEGER DEFAULT 0,
    error TEXT,
    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    response_time FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Link relationships table
CREATE TABLE IF NOT EXISTS crawler.crawled_links (
    id SERIAL PRIMARY KEY,
    parent_url TEXT NOT NULL,
    child_url TEXT NOT NULL,
    UNIQUE(parent_url, child_url),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Crawl sessions (track separate crawl runs)
CREATE TABLE IF NOT EXISTS crawler.crawl_sessions (
    id SERIAL PRIMARY KEY,
    session_id UUID UNIQUE NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    status VARCHAR(20) DEFAULT 'RUNNING',
    urls_total INTEGER DEFAULT 0,
    urls_crawled INTEGER DEFAULT 0,
    urls_failed INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Performance metrics
CREATE TABLE IF NOT EXISTS crawler.metrics (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES crawler.crawl_sessions(session_id),
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_crawl_results_url ON crawler.crawl_results(url);
CREATE INDEX IF NOT EXISTS idx_crawl_results_crawled_at ON crawler.crawl_results(crawled_at);
CREATE INDEX IF NOT EXISTS idx_crawl_results_status ON crawler.crawl_results(status_code);
CREATE INDEX IF NOT EXISTS idx_crawled_links_parent ON crawler.crawled_links(parent_url);
CREATE INDEX IF NOT EXISTS idx_crawled_links_child ON crawler.crawled_links(child_url);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON crawler.crawl_sessions(status);
CREATE INDEX IF NOT EXISTS idx_metrics_session ON crawler.metrics(session_id);

-- Views for common queries
CREATE OR REPLACE VIEW crawler.v_crawl_summary AS
SELECT
    COUNT(*) as total_urls,
    SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as successful,
    SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed,
    AVG(response_time) as avg_response_time,
    MAX(response_time) as max_response_time,
    MIN(response_time) as min_response_time
FROM crawler.crawl_results;

CREATE OR REPLACE VIEW crawler.v_domain_summary AS
SELECT
    SUBSTRING(url FROM 'https?://([^/]+)') as domain,
    COUNT(*) as url_count,
    AVG(response_time) as avg_response_time,
    SUM(links_count) as total_links
FROM crawler.crawl_results
GROUP BY domain
ORDER BY url_count DESC;

-- Grant permissions
GRANT USAGE ON SCHEMA crawler TO crawler_user;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA crawler TO crawler_user;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA crawler TO crawler_user;
