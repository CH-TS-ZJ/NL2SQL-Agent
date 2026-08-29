SET NAMES utf8mb4;
CREATE DATABASE meta DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
GRANT ALL PRIVILEGES ON meta.* TO 'lossts'@'%';

USE meta;

DROP TABLE IF EXISTS table_info;
CREATE TABLE table_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '表编号',
    name        VARCHAR(128) COMMENT '表名称',
    role        VARCHAR(32) COMMENT '表类型(fact/dim)',
    description TEXT COMMENT '表描述'
);



DROP TABLE IF EXISTS column_info;
CREATE TABLE column_info
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '列编号',
    name        VARCHAR(128) COMMENT '列名称',
    type        VARCHAR(64) COMMENT '数据类型',
    role        VARCHAR(32) COMMENT '列类型(primary_key,foreign_key,measure,dimension)',
    examples    JSON COMMENT '数据示例',
    description TEXT COMMENT '列描述',
    alias       JSON COMMENT '列别名',
    table_id    VARCHAR(64) COMMENT '所属表编号'
);

DROP TABLE IF EXISTS metric_info;
CREATE TABLE metric_info
(
    id               VARCHAR(64) PRIMARY KEY COMMENT '指标编码',
    name             VARCHAR(128) COMMENT '指标名称',
    description      TEXT COMMENT '指标描述',
    relevant_columns JSON COMMENT '关联的列',
    alias            JSON COMMENT '指标别名'
);


DROP TABLE IF EXISTS column_metric;
CREATE TABLE column_metric
(
    column_id VARCHAR(64) COMMENT '列编号',
    metric_id VARCHAR(64) COMMENT '指标编号',
    PRIMARY KEY (column_id, metric_id)
);


CREATE TABLE IF NOT EXISTS chat_session
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '会话编号',
    title       VARCHAR(255) COMMENT '会话标题(取首个问题)',
    created_at  DATETIME COMMENT '创建时间',
    updated_at  DATETIME COMMENT '最近更新时间'
);

CREATE TABLE IF NOT EXISTS chat_message
(
    id          VARCHAR(64) PRIMARY KEY COMMENT '消息编号',
    session_id  VARCHAR(64) NOT NULL COMMENT '所属会话编号',
    role        VARCHAR(16) NOT NULL COMMENT '角色 user/assistant',
    content     TEXT COMMENT '消息文本',
    query       TEXT COMMENT '指代消解后的完整问题',
    sql         TEXT COMMENT '生成的SQL',
    result      JSON COMMENT '查询结果',
    error       TEXT COMMENT '错误信息',
    detail      TEXT COMMENT '错误详情(校验错误)',
    created_at  DATETIME COMMENT '创建时间',
    KEY idx_session_id (session_id)
);
