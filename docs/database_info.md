# 数据库信息说明

本文档根据 `/home/zgllm/workspace/elite_server` 当前代码、配置文件和项目内说明整理而成。

说明：

- 已从代码中确认项目实际连接了 `MySQL` 和 `MongoDB`。
- 当前环境下未能直接连上本机数据库服务，因此 `MySQL` 的表结构主要来自项目自带 SQL/README，`MongoDB` 的集合字段主要来自代码访问路径推断。
- 对于 MongoDB，这里记录的是“代码中明确使用过的字段”，不保证等于线上文档的完整结构。

## 1. 已确认连接的数据库

### 1.1 MySQL

来源：

- [config.py](/home/zgllm/workspace/elite_server/config.py)
- [app.py](/home/zgllm/workspace/elite_server/app.py)
- [utils/email_verify.py](/home/zgllm/workspace/elite_server/utils/email_verify.py)
- [readme.md](/home/zgllm/workspace/elite_server/readme.md)
- [utils/readme.md](/home/zgllm/workspace/elite_server/utils/readme.md)

连接信息：

- host: `localhost`
- user: `root`
- password: `123456`
- database: `zgllm`
- charset: `utf8mb4`

### 1.2 MongoDB

来源：

- [config.py](/home/zgllm/workspace/elite_server/config.py)
- [app.py](/home/zgllm/workspace/elite_server/app.py)
- [utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)

连接信息：

- host: `localhost`
- port: `27027`
- user: `root`
- password: `123456`
- authSource: `admin`
- database: `education2`

## 2. MySQL 数据库 `zgllm`

目前在项目中能明确确认的表如下。

### 2.1 `student`

来源：[readme.md](/home/zgllm/workspace/elite_server/readme.md)

表作用：

- 用户账号表

字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT` | 主键，自增 |
| `sid` | `VARCHAR(50)` | 学号，唯一，非空 |
| `email` | `VARCHAR(100)` | 邮箱，唯一 |
| `password` | `VARCHAR(255)` | 密码 |

项目文档中的建表 SQL：

```sql
CREATE TABLE student (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sid VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE,
    password VARCHAR(255)
);
```

### 2.2 `email_verification_code`

来源：[utils/readme.md](/home/zgllm/workspace/elite_server/utils/readme.md)

表作用：

- 邮箱验证码持久化表

字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | 主键 ID，自增 |
| `scene` | `VARCHAR(32)` | 业务场景，如 `register/reset_password/login/test` |
| `account` | `VARCHAR(64)` | 账号，如学号/工号/用户名 |
| `email` | `VARCHAR(255)` | 邮箱地址，统一存小写 |
| `code` | `VARCHAR(16)` | 验证码 |
| `purpose_key` | `VARCHAR(255)` | 业务键，格式 `scene:account:email_lower` |
| `status` | `TINYINT` | 状态：`0未使用`、`1已使用`、`2已过期`、`3作废` |
| `fail_count` | `INT` | 验证码校验失败次数 |
| `ip_addr` | `VARCHAR(64)` | 请求来源 IP |
| `user_agent` | `VARCHAR(255)` | 请求 UA |
| `expires_at` | `DATETIME` | 过期时间 |
| `used_at` | `DATETIME` | 使用时间 |
| `created_at` | `DATETIME` | 创建时间 |
| `updated_at` | `DATETIME` | 更新时间 |

索引：

- `idx_purpose_key_status_created (purpose_key, status, created_at)`
- `idx_account_scene_created (account, scene, created_at)`
- `idx_email_scene_created (email, scene, created_at)`
- `idx_expires_at (expires_at)`
- `idx_created_at (created_at)`

### 2.3 `email_send_log`

来源：[utils/readme.md](/home/zgllm/workspace/elite_server/utils/readme.md)

表作用：

- 邮件发送日志表

字段：

| 字段名 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `BIGINT UNSIGNED` | 主键 ID，自增 |
| `scene` | `VARCHAR(32)` | 业务场景 |
| `account` | `VARCHAR(64)` | 账号 |
| `email` | `VARCHAR(255)` | 邮箱地址，统一存小写 |
| `code_id` | `BIGINT UNSIGNED` | 关联验证码表 `email_verification_code.id` |
| `ip_addr` | `VARCHAR(64)` | 请求来源 IP |
| `user_agent` | `VARCHAR(255)` | 请求 UA |
| `send_status` | `TINYINT` | 发送状态：`0失败`、`1成功` |
| `error_message` | `VARCHAR(500)` | 失败原因 |
| `created_at` | `DATETIME` | 发送时间 |

索引与约束：

- `idx_account_scene_created (account, scene, created_at)`
- `idx_email_scene_created (email, scene, created_at)`
- `idx_ip_scene_created (ip_addr, scene, created_at)`
- `idx_created_at (created_at)`
- 外键：`code_id -> email_verification_code(id)`，`ON DELETE SET NULL`

## 3. MongoDB 数据库 `education2`

以下集合名和字段来自代码实际访问记录。

### 3.1 `courses`

来源：[app.py](/home/zgllm/workspace/elite_server/app.py)

代码中明确使用过的字段：

| 字段名 | 说明 |
| --- | --- |
| `id` | 课程 ID |
| `course_id` | 课程 ID，代码中出现过 |
| `course_name` | 课程名称 |
| `name` | 课程名称的另一种字段名 |
| `knowledge_count` | 知识点总数 |
| `knowledge_list` | 课程知识点列表 |
| `enrollment_term_id` | 学期 ID |
| `sis_course_id` | SIS 课程 ID |
| `workflow_state` | 课程状态 |
| `enrollment_status` | 选课状态 |
| `student_list` | 课程下学生列表，代码中有出现 |
| `courses_list` | 嵌套课程列表 |

推断出的嵌套结构：

```json
{
  "id": 123,
  "course_name": "xxx",
  "knowledge_count": 10,
  "knowledge_list": [
    {
      "knowledge_id": 1,
      "knowledge_name": "xxx",
      "state": "learned/in_progress/not_learned/review_needed"
    }
  ],
  "courses_list": [
    {
      "course_code": "CS101",
      "class_list": [
        {
          "id": 1001,
          "sis_course_id": "xxx",
          "enrollment_term_id": "xxx"
        }
      ]
    }
  ]
}
```

### 3.2 `classes`

来源：[app.py](/home/zgllm/workspace/elite_server/app.py)

代码中明确使用过的字段：

| 字段名 | 说明 |
| --- | --- |
| `id` | 班级或课程实例 ID |
| `course_code` | 课程代码 |
| `course_name` | 课程名称 |
| `sis_course_id` | SIS 课程 ID |
| `enrollment_term_id` | 学期 ID |
| `student_list` | 班级学生列表 |

推断出的 `student_list` 元素字段：

| 字段名 | 说明 |
| --- | --- |
| `id` | 学生 ID |
| `sis_user_id` | SIS 学生 ID |
| `student_name` | 学生姓名 |
| `name` | 学生姓名，另一种字段名 |

推断结构示例：

```json
{
  "id": 1001,
  "course_code": "CS101",
  "course_name": "xxx",
  "sis_course_id": "xxx",
  "enrollment_term_id": "xxx",
  "student_list": [
    {
      "id": 2001,
      "sis_user_id": "20240001",
      "student_name": "张三"
    }
  ]
}
```

### 3.3 `students`

来源：[app.py](/home/zgllm/workspace/elite_server/app.py)

代码中明确使用过的字段：

| 字段名 | 说明 |
| --- | --- |
| `id` | 学生 ID |
| `user_id` | 用户 ID |
| `sis_user_id` | SIS 学号/用户 ID |
| `student_name` | 学生姓名 |
| `name` | 姓名 |
| `sortable_name` | 可排序姓名 |
| `display_name` | 展示姓名 |
| `anonymous_id` | 匿名 ID |
| `fake_student` | 是否为假学生/测试账号 |
| `grades` | 成绩信息对象 |
| `user` | 用户对象 |
| `enrolled_courses` | 选课列表 |

推断出的嵌套结构：

```json
{
  "id": 2001,
  "user_id": 2001,
  "sis_user_id": "20240001",
  "student_name": "张三",
  "sortable_name": "张三",
  "display_name": "张三",
  "anonymous_id": "xxx",
  "fake_student": false,
  "grades": {
    "current_score": 95.5
  },
  "user": {
    "id": 2001
  },
  "enrolled_courses": [
    {
      "id": 1001,
      "enrollment_status": "active",
      "knowledge_list": [
        {
          "knowledge_id": 1,
          "state": "learned"
        }
      ]
    }
  ]
}
```

### 3.4 `knowledges`

来源：[app.py](/home/zgllm/workspace/elite_server/app.py)

代码中明确使用过的字段：

| 字段名 | 说明 |
| --- | --- |
| `knowledge_id` | 知识点 ID |
| `knowledge_name` | 知识点名称 |
| `course_code` | 所属课程代码 |
| `state` | 知识点状态，代码中出现过 |
| `access_records` | 知识点访问记录 |

推断出的 `access_records` 元素字段：

| 字段名 | 说明 |
| --- | --- |
| `sis_user_id` | 访问学生的 SIS ID |
| `access_time` | 访问时间 |

推断结构示例：

```json
{
  "knowledge_id": 1,
  "knowledge_name": "函数极限",
  "course_code": "MATH101",
  "access_records": [
    {
      "sis_user_id": "20240001",
      "access_time": "2026-04-13T10:00:00Z"
    }
  ]
}
```

### 3.5 `usage_events`

来源：[utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)

表作用：

- 平台请求与用户行为埋点

代码中明确写入的字段：

| 字段名 | 说明 |
| --- | --- |
| `event_type` | 事件类型 |
| `username` | 用户名 |
| `role` | 角色 |
| `occurred_at` | 发生时间 |
| `day` | 日期，格式 `YYYY-MM-DD` |
| `meta` | 扩展信息 |
| `path` | 请求路径 |
| `endpoint` | Flask endpoint |
| `method` | HTTP 方法 |
| `ip` | 请求 IP |
| `user_agent` | 请求 UA |

代码中创建的索引：

- `("occurred_at", -1)`
- `("event_type", 1), ("day", 1)`
- `("username", 1), ("occurred_at", -1)`
- `("path", 1), ("occurred_at", -1)`

### 3.6 `usage_online_users`

来源：[utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)

表作用：

- 在线用户状态

代码中明确写入的字段：

| 字段名 | 说明 |
| --- | --- |
| `username` | 用户名，唯一索引 |
| `role` | 角色 |
| `last_seen_at` | 最近在线时间 |
| `updated_at` | 更新时间 |
| `first_seen_at` | 首次出现时间 |
| `last_path` | 最近访问路径 |
| `ip` | 请求 IP |

代码中创建的索引：

- `username` 唯一索引
- `("last_seen_at", -1)`

### 3.7 `usage_daily_peaks`

来源：[utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)

表作用：

- 每日在线峰值统计

代码中明确写入的字段：

| 字段名 | 说明 |
| --- | --- |
| `day` | 日期，唯一索引 |
| `peak_online` | 当日峰值在线人数 |
| `updated_at` | 更新时间 |
| `created_at` | 创建时间 |

代码中创建的索引：

- `day` 唯一索引

## 4. 代码中出现但未确认启用的 ORM 模型

来源：[models.py](/home/zgllm/workspace/elite_server/models.py)

当前项目里还存在 `Flask-SQLAlchemy` 模型，但在 `app.py` 中未发现对应数据库初始化、`db.init_app()`、`create_all()` 或实际查询调用，因此暂时不能判断它们是否正在使用。

### 4.1 `User`

字段：

| 字段名 | 类型 |
| --- | --- |
| `id` | `Integer` |
| `username` | `String(80)` |
| `password` | `String(200)` |
| `created_at` | `DateTime` |

### 4.2 `LLModel`

字段：

| 字段名 | 类型 |
| --- | --- |
| `id` | `Integer` |
| `name` | `String(100)` |
| `description` | `Text` |
| `image_path` | `String(200)` |
| `detail_url` | `String(100)` |

## 5. 本次核查结论

当前目录下，从代码层面可确认的数据库有：

1. MySQL：`zgllm`
2. MongoDB：`education2`

其中：

- `zgllm` 可明确确认的表有：`student`、`email_verification_code`、`email_send_log`
- `education2` 可明确确认的集合有：`courses`、`classes`、`students`、`knowledges`、`usage_events`、`usage_online_users`、`usage_daily_peaks`

如果后面你希望我继续做两件事，我也可以直接接着补：

1. 进一步扫描 `app.py`，把 Mongo 各集合字段补成更完整的“字段字典”
2. 如果你能提供可连接数据库的环境，我可以直接导出真实的 `SHOW TABLES / DESC` 和 Mongo `sample document`，把这份文档改成“实库版”
