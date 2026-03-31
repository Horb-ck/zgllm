# 验证码数据库持久化
- 建表
CREATE TABLE email_verification_code (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    scene VARCHAR(32) NOT NULL COMMENT '业务场景，如 register/reset_password/login/test',
    account VARCHAR(64) NOT NULL COMMENT '账号，如学号/工号/用户名',
    email VARCHAR(255) NOT NULL COMMENT '邮箱地址，统一存小写',
    code VARCHAR(16) NOT NULL COMMENT '验证码，通常6位',
    purpose_key VARCHAR(255) NOT NULL COMMENT '业务键，scene:account:email_lower',
    status TINYINT NOT NULL DEFAULT 0 COMMENT '状态：0未使用，1已使用，2已过期，3作废',
    fail_count INT NOT NULL DEFAULT 0 COMMENT '验证码校验失败次数',
    ip_addr VARCHAR(64) DEFAULT NULL COMMENT '请求来源IP',
    user_agent VARCHAR(255) DEFAULT NULL COMMENT '请求UA，可选',
    expires_at DATETIME NOT NULL COMMENT '过期时间',
    used_at DATETIME DEFAULT NULL COMMENT '使用时间',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    PRIMARY KEY (id),
    KEY idx_purpose_key_status_created (purpose_key, status, created_at),
    KEY idx_account_scene_created (account, scene, created_at),
    KEY idx_email_scene_created (email, scene, created_at),
    KEY idx_expires_at (expires_at),
    KEY idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='邮箱验证码表';

CREATE TABLE email_send_log (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    scene VARCHAR(32) NOT NULL COMMENT '业务场景',
    account VARCHAR(64) NOT NULL COMMENT '账号',
    email VARCHAR(255) NOT NULL COMMENT '邮箱地址，统一存小写',
    code_id BIGINT UNSIGNED DEFAULT NULL COMMENT '关联验证码表ID',
    ip_addr VARCHAR(64) DEFAULT NULL COMMENT '请求来源IP',
    user_agent VARCHAR(255) DEFAULT NULL COMMENT '请求UA，可选',
    send_status TINYINT NOT NULL DEFAULT 0 COMMENT '发送状态：0失败，1成功',
    error_message VARCHAR(500) DEFAULT NULL COMMENT '失败原因',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发送时间',
    PRIMARY KEY (id),
    KEY idx_account_scene_created (account, scene, created_at),
    KEY idx_email_scene_created (email, scene, created_at),
    KEY idx_ip_scene_created (ip_addr, scene, created_at),
    KEY idx_created_at (created_at),
    CONSTRAINT fk_email_send_log_code_id
        FOREIGN KEY (code_id) REFERENCES email_verification_code(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='邮件发送日志表';