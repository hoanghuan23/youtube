-- =========================================================
-- YOUTUBE DATABASE SCHEMA
-- Không dùng bảng sessions/accounts
-- =========================================================


-- bảng task_logs lưu lịch sử thực thi các tác vụ định kỳ
CREATE TABLE task_logs (
    id INTEGER NOT NULL,
    task_name VARCHAR(100) NOT NULL,
    status VARCHAR(20),
    started_at DATETIME,
    completed_at DATETIME,
    duration_seconds FLOAT,
    items_processed INTEGER,
    errors_count INTEGER,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
);

CREATE INDEX idx_task_logs_name_date 
ON task_logs (task_name, created_at);


-- bảng sources lưu nguồn dữ liệu YouTube cần theo dõi
-- source_type:
--   channel  : crawl theo kênh
--   keyword  : crawl theo từ khóa tìm kiếm
CREATE TABLE sources (
    id INTEGER NOT NULL,

    source_type VARCHAR(20) NOT NULL,
    identifier VARCHAR(255) NOT NULL,

    display_name VARCHAR(255),
    youtube_url VARCHAR(500),
    subscriber_count INTEGER,
    view_count INTEGER,

    is_active BOOLEAN DEFAULT 1,
    is_accessible BOOLEAN,

    max_days_old INTEGER,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_scraped DATETIME,
    next_scrape DATETIME,

    schedule_tier INTEGER DEFAULT NULL,
    schedule_override_minutes INTEGER DEFAULT NULL,

    PRIMARY KEY (id),

    CONSTRAINT uq_youtube_source_url UNIQUE (youtube_url),
    CONSTRAINT ck_youtube_sources_type 
        CHECK (source_type IN ('channel', 'keyword', 'playlist'))
);

CREATE INDEX idx_youtube_sources_active 
ON sources (is_active);

CREATE INDEX idx_youtube_sources_accessible 
ON sources (is_accessible);

CREATE INDEX idx_youtube_sources_next_scrape 
ON sources (next_scrape);


-- bảng channels lưu thông tin kênh YouTube
-- Tách riêng để tránh lặp lại channel_title, subscriber_count ở nhiều video
CREATE TABLE channels (
    id INTEGER NOT NULL,

    youtube_channel_id VARCHAR(100) NOT NULL,
    channel_handle VARCHAR(255),
    channel_title VARCHAR(255),
    channel_url VARCHAR(500),

    thumbnail_url VARCHAR(500),

    subscriber_count INTEGER,
    video_count INTEGER,
    view_count INTEGER,

    is_verified BOOLEAN,
    description TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_updated DATETIME,

    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_channels_youtube_channel_id 
ON channels (youtube_channel_id);

CREATE INDEX idx_channels_handle 
ON channels (channel_handle);

CREATE INDEX idx_channels_title 
ON channels (channel_title);


-- bảng videos lưu thông tin video YouTube
CREATE TABLE videos (
    id INTEGER NOT NULL,

    source_id INTEGER NOT NULL,
    channel_id INTEGER,

    youtube_video_id VARCHAR(100) NOT NULL,
    youtube_url VARCHAR(500) NOT NULL,

    title VARCHAR(500),
    description TEXT,

    categories TEXT,

    published_at DATETIME NOT NULL,

    duration_seconds INTEGER,

    -- phân loại video
    -- long  : video dài
    -- short : YouTube Shorts
    video_type VARCHAR(20) DEFAULT 'long'
        CHECK (video_type IN ('long', 'short')),

    thumbnail_url VARCHAR(500),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    is_tracked BOOLEAN DEFAULT 1,
    tracking_until DATETIME,

    is_deleted BOOLEAN DEFAULT 0,

    last_metric_update DATETIME,
    next_metric_update DATETIME,

    metric_tier VARCHAR(20) NOT NULL DEFAULT 'bootstrap',
    last_engagement_velocity FLOAT,

    cold_check_count INTEGER NOT NULL DEFAULT 0,
    metric_scan_miss_count INTEGER NOT NULL DEFAULT 0,

    PRIMARY KEY (id),

    FOREIGN KEY (source_id) REFERENCES sources (id),
    FOREIGN KEY (channel_id) REFERENCES channels (id),

    CONSTRAINT ck_youtube_video_metric_tier
        CHECK (metric_tier IN (
            'bootstrap',
            'very_low',
            'low',
            'medium',
            'high',
            'viral'
        ))
);

CREATE UNIQUE INDEX ix_videos_youtube_video_id 
ON videos (youtube_video_id);

CREATE INDEX idx_videos_source 
ON videos (source_id);

CREATE INDEX idx_videos_channel 
ON videos (channel_id);

CREATE INDEX idx_videos_published_at 
ON videos (published_at);

CREATE INDEX idx_videos_metric_due 
ON videos (is_tracked, next_metric_update);

CREATE INDEX idx_videos_last_metric_update 
ON videos (last_metric_update);

CREATE INDEX idx_videos_video_type 
ON videos (video_type);


-- bảng video_metrics lưu lịch sử metric của video theo thời gian
CREATE TABLE video_metrics (
    id INTEGER NOT NULL,

    video_id INTEGER NOT NULL,

    views_count INTEGER,
    likes_count INTEGER,
    comments_count INTEGER,

    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,

    PRIMARY KEY (id),

    FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE
);

CREATE INDEX ix_video_metrics_recorded_at 
ON video_metrics (recorded_at);

CREATE INDEX idx_video_metrics_video_date 
ON video_metrics (video_id, recorded_at);

CREATE INDEX idx_video_metrics_job_time 
ON video_metrics (job_id, recorded_at);


-- bảng comments lưu bình luận YouTube nếu sau này cần crawl comment
CREATE TABLE comments (
    id INTEGER NOT NULL,

    video_id INTEGER NOT NULL,
    youtube_comment_id VARCHAR(100) NOT NULL,

    commenter_id VARCHAR(100),
    commenter_name VARCHAR(255),
    commenter_channel_url VARCHAR(500),

    comment_text TEXT,

    likes_count INTEGER,

    published_at DATETIME,
    updated_at DATETIME,

    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    FOREIGN KEY (video_id) REFERENCES videos (id) ON DELETE CASCADE,

    UNIQUE (youtube_comment_id)
);

CREATE INDEX idx_comments_youtube_comment_id 
ON comments (youtube_comment_id);

CREATE INDEX idx_comments_video 
ON comments (video_id);



-- bảng analytics_cache lưu tổng hợp chỉ số theo source/ngày
CREATE TABLE analytics_cache (
    id INTEGER NOT NULL,

    source_id INTEGER NOT NULL,
    date DATETIME NOT NULL,

    total_videos INTEGER,
    total_views INTEGER,
    total_likes INTEGER,
    total_comments INTEGER,

    avg_views_per_video FLOAT,
    avg_likes_per_video FLOAT,
    avg_comments_per_video FLOAT,

    top_video_id VARCHAR(100),

    growth_rate FLOAT,

    cached_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    CONSTRAINT uq_youtube_analytics_cache UNIQUE (source_id, date),

    FOREIGN KEY (source_id) REFERENCES sources (id) ON DELETE CASCADE
);

CREATE INDEX idx_analytics_source_date 
ON analytics_cache (source_id, date);


-- bảng pipeline_jobs theo dõi pipeline crawl/update metric/analytics
CREATE TABLE pipeline_jobs (
    id INTEGER PRIMARY KEY,

    job_type VARCHAR(30) NOT NULL DEFAULT 'scraper_job'
        CHECK (job_type IN (
            'scrape_24h',
            'scraper_job',
            'update_metric',
            'analytics',
            'crawl_comments'
        )),

    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'done', 'failed')),

    videos_found INTEGER NOT NULL DEFAULT 0,
    videos_new INTEGER NOT NULL DEFAULT 0,

    items_total INTEGER NOT NULL DEFAULT 0,
    items_updated INTEGER NOT NULL DEFAULT 0,
    items_failed INTEGER NOT NULL DEFAULT 0,

    error_message TEXT,

    started_at DATETIME,
    finished_at DATETIME
);

CREATE INDEX idx_pipeline_jobs_source_time 
ON pipeline_jobs (source_id, started_at);

CREATE INDEX idx_pipeline_jobs_type_status 
ON pipeline_jobs (job_type, status, started_at);


-- bảng pipeline_logs chỉ lưu log lỗi cho từng pipeline job để debug
CREATE TABLE pipeline_logs (
    id INTEGER PRIMARY KEY,

    job_id INTEGER REFERENCES pipeline_jobs(id) ON DELETE SET NULL,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,

    log_level VARCHAR(20) NOT NULL DEFAULT 'ERROR'
        CHECK (log_level IN ('ERROR', 'WARNING')),

    message TEXT NOT NULL,

    error_type VARCHAR(100),
    error_details TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_logs_job 
ON pipeline_logs (job_id, created_at);

CREATE INDEX idx_pipeline_logs_source 
ON pipeline_logs (source_id, created_at);

CREATE INDEX idx_pipeline_logs_level 
ON pipeline_logs (log_level, created_at);
