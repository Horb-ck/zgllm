# 用户数据看板说明

本文档说明 `/dev/analytics` 用户数据看板当前版本中每个数据项的定义、数据来源、统计意义和实现口径。

以当前代码为准的主要文件：

- 路由与 FastGPT 统计逻辑：[app.py](/home/zgllm/workspace/elite_server/app.py)
- 平台行为统计逻辑：[utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)
- 页面模板：[templates/dashboard/usage_analytics.html](/home/zgllm/workspace/elite_server/templates/dashboard/usage_analytics.html)

## 1. 数据总览

当前看板的数据来自三部分：

1. MongoDB `education2`
   - `usage_events`
   - `usage_online_users`
   - `usage_daily_peaks`
2. MySQL `zgllm`
   - `student`
3. FastGPT MongoDB `fastgpt`
   - `chatitems`
   - `outlinks`
   - `chat_input_guides` 仅作为结构判断参考，不直接参与计数

它们分别承担的职责是：

- `education2.usage_events`：平台请求、登录、注册、页面访问、智能体打开等行为埋点
- `education2.usage_online_users`：当前在线用户状态
- `zgllm.student`：系统注册用户总量
- `fastgpt.chatitems`：FastGPT 中真实发生的用户提问消息
- `fastgpt.outlinks`：FastGPT `shareId -> appId` 映射

## 2. 当前看板里有哪些指标

当前页面分为四块：

1. 顶部统计卡片
2. 趋势图
3. 榜单卡片
4. 明细表

当前页面实际展示的核心字段有：

- 顶部卡片
  - `analytics.today.dau`
  - `analytics.today.registrations`
  - `analytics.super_teacher_questions.total_questions`
  - `analytics.today.requests`
  - `analytics.today.current_online`
  - `analytics.selected_period.active_users`
  - `analytics.total_registered_users`
  - `analytics.super_teacher_questions.total_questions_all_time`
- 趋势图
  - `analytics.daily_trend[*].dau`
  - `analytics.daily_trend[*].requests`
  - `analytics.daily_trend[*].registrations`
  - `analytics.daily_trend[*].chats`
- 榜单
  - `analytics.top_agents`
  - `analytics.top_pages`
  - `analytics.top_users`
- 明细表
  - `analytics.selected_period.active_users`
  - `analytics.selected_period.logins`
  - `analytics.selected_period.registrations`
  - `analytics.selected_period.chats`
  - `analytics.selected_period.requests`
  - `analytics.daily_trend[*].day`
  - `analytics.daily_trend[*].dau`
  - `analytics.daily_trend[*].logins`
  - `analytics.daily_trend[*].registrations`
  - `analytics.daily_trend[*].chats`
  - `analytics.daily_trend[*].requests`

## 3. 平台埋点数据是怎么记录的

### 3.1 请求埋点入口

所有请求进入 Flask 后，会先经过：

- [app.py](/home/zgllm/workspace/elite_server/app.py:66)

逻辑顺序是：

1. 判断这个请求是否需要记录
2. 如果用户已登录，刷新在线状态
3. 写入一条 `request` 事件到 `usage_events`

### 3.2 `usage_events` 的基础字段

由 `track_event()` 写入：

- `event_type`
- `username`
- `role`
- `occurred_at`
- `day`
- `meta`

如果传入了 `request`，还会写入：

- `path`
- `endpoint`
- `method`
- `ip`
- `user_agent`

实现位置：

- [utils/usage_analytics.py](/home/zgllm/workspace/elite_server/utils/usage_analytics.py)

### 3.3 当前已定义的事件类型

- `request`
- `heartbeat`
- `login_success`
- `register_success`
- `agent_open`
- `kg_page_view`
- `mcp_chat`

注意：

- 当前页面上的“对话数”已经不再主要依赖 `mcp_chat`
- 现在“对话数”主要来自 FastGPT 的 `chatitems`

## 4. 请求量是怎么统计的

### 4.1 定义

`请求量` 统计的是 `usage_events` 中 `event_type = "request"` 的记录数。

### 4.2 数据来源

- MongoDB `education2.usage_events`

### 4.3 统计意义

- 表示后端收到的业务请求总次数
- 反映页面访问和接口调用热度
- 不是“页面打开次数”

### 4.4 统计规则

满足以下条件的请求会被记入：

- 通过 `should_track_request()`
- 非静态资源
- 非心跳请求
- 非被排除的内部路径

常见会计入请求量的访问包括：

- 首页 `/`
- 登录页 `/login`
- 注册页 `/register`
- 首页问答 `/dashboard/new-chat`
- 课程广场、个人知识库、学情分析页面
- 页面里的业务 `fetch` 请求

### 4.5 不会被计入的请求

以下路径不写入 `request`：

- `/favicon.ico`
- `/get_session`
- `/usage/heartbeat`
- `/dev/analytics`
- `/dev/analytics/login`
- `/dev/analytics/logout`
- `/static/` 开头
- `/js/` 开头
- `/KG/static/output/` 开头

说明：

- 开发者统计页自身不会再污染请求量

## 5. 顶部卡片说明

当前顶部卡片共有 8 个。

### 5.1 今日活跃用户数（DAU）

定义：

- 今日活跃去重用户数

来源：

- `education2.usage_events`

统计规则：

- 今天 `day = 今日`
- 事件类型属于活跃事件集合
- `username` 非空
- 对 `username` 去重

统计意义：

- 表示今天实际活跃过的不同用户数量
- 反映平台日活规模

### 5.2 今日注册数

定义：

- 今日成功注册次数

来源：

- `education2.usage_events`

统计规则：

- `event_type = "register_success"`
- `day = 今日`

统计意义：

- 表示今天新增注册行为的次数
- 用于看新增用户增长

### 5.3 所选时段对话数

定义：

- 当前筛选日期范围内，FastGPT 真实用户提问总数

来源：

- FastGPT `fastgpt.chatitems`

统计范围包含：

1. 课程智能体中的超级教师问答
2. 首页 `/dashboard/new-chat` 的通用问答
3. 学情分析中的问答
   - 教师端
   - 学生端

统计规则：

- 先从项目中的分享链接提取 `shareId`
- 再通过 `fastgpt.outlinks` 找到对应 `appId`
- 在 `fastgpt.chatitems` 中筛选：
  - `appId` 属于上述目标应用
  - `obj = "Human"`
  - `time` 落在所选日期范围内

统计意义：

- 表示当前时间范围内，用户在 FastGPT 问答入口实际发出的提问次数
- 这是当前页面里“对话数”的主要标准口径

### 5.4 今日请求量

定义：

- 今日被埋点记录的请求次数

来源：

- `education2.usage_events`

统计规则：

- `event_type = "request"`
- `day = 今日`

统计意义：

- 表示今天平台收到的业务请求量
- 可用于评估平台访问负载和活跃程度

### 5.5 当前在线

定义：

- 最近 5 分钟内有活动的在线用户数

来源：

- `education2.usage_online_users`

统计规则：

- 登录用户发生有效请求时刷新 `last_seen_at`
- 统计最近 5 分钟内去重用户名数量

统计意义：

- 表示当前近实时在线人数
- 反映平台瞬时活跃情况

### 5.6 所选时段活跃用户数

定义：

- 当前日期筛选范围内的去重活跃用户数

来源：

- `education2.usage_events`

统计规则：

- 查询所选日期范围
- 事件类型属于活跃事件集合
- `username` 非空
- 对 `username` 去重

统计意义：

- 表示这一时间段内触达过平台的不同用户数量

### 5.7 总注册人数

定义：

- 当前系统注册用户总数

来源：

- MySQL `zgllm.student`

统计规则：

- 执行 `SELECT COUNT(*) FROM student`

统计意义：

- 表示账号库当前总规模
- 是实时总量，不依赖埋点

### 5.8 系统总对话数

定义：

- FastGPT 问答入口的累计用户提问总数

来源：

- FastGPT `fastgpt.chatitems`

统计范围：

- 与“所选时段对话数”相同
- 但不受日期筛选影响

统计规则：

- `appId` 属于目标问答应用
- `obj = "Human"`
- 统计全历史条数

统计意义：

- 表示系统问答能力长期累计的使用规模

## 6. 为什么“对话数”不是 `chat_input_guides`

这是一个当前实现里非常重要的细节。

### 6.1 `chat_input_guides` 的实际含义

FastGPT 中的 `chat_input_guides` 存的是“输入引导文案配置”，例如：

- “请给我一份课程大纲”
- “请给我规划定量工程设计方法的学习路径”

它的结构更像：

- `appId`
- `text`

这表示：

- 某个应用有哪些推荐引导问题
- 不是用户实际点击了多少次
- 也不是用户真正发出了多少次消息

### 6.2 当前为什么不直接把它加到对话数

因为它本身不是点击日志。

如果用户真的点击了引导，并把这条问题发送出去，最终会在：

- `fastgpt.chatitems`

里留下真实的 `Human` 消息。

所以当前系统采用的是：

- 不直接给 `chat_input_guides` 加次数
- 只统计最终真实发送成功的用户消息

这样做的好处是：

- 不会重复计数
- 不会把“只是展示了引导文案”误算成对话
- 更符合“真实提问次数”的定义

## 7. 趋势图说明

当前趋势图展示 4 条数据：

- `DAU`
- `请求量`
- `注册人数`
- `对话数`

页面位置：

- [templates/dashboard/usage_analytics.html](/home/zgllm/workspace/elite_server/templates/dashboard/usage_analytics.html)

### 7.1 数据来源

- `analytics.daily_trend`

### 7.2 每日趋势项包含的字段

- `day`
- `dau`
- `requests`
- `logins`
- `registrations`
- `chats`
- `peak_online`

说明：

- 虽然 `peak_online` 还保留在后端结构中，但前端页面不再展示
- `chats` 在当前页面中已经被 FastGPT 的按天提问数覆盖

### 7.3 对话数曲线的口径

趋势图中的“对话数”曲线，和顶部“所选时段对话数”、底部明细中的“对话数”口径一致，都是：

- FastGPT 目标问答应用中
- `chatitems.obj = "Human"`
- 按天聚合后的真实用户提问数

统计意义：

- 可以观察问答功能的日使用走势
- 适合和请求量、注册数一起对比变化

## 8. 热门课程智能体

### 8.1 卡片位置与布局

当前页面中：

- 左侧：热门课程智能体
- 右侧：热门页面
- 两张卡片平分页面宽度

### 8.2 展示字段

- 智能体
- 打开次数
- 对话数
- UV

### 8.3 打开次数

来源：

- `education2.usage_events`

统计规则：

- `event_type = "agent_open"`
- 按 `meta.agent_id + meta.agent_name` 分组

统计意义：

- 表示这个课程智能体被打开了多少次

### 8.4 UV

来源：

- `education2.usage_events`

统计规则：

- 对打开该智能体的 `username` 去重

统计意义：

- 表示有多少不同用户使用过这个智能体

### 8.5 对话数

来源：

- FastGPT `fastgpt.chatitems`

统计规则：

- 先用该课程智能体的 `shareId` 找到 `appId`
- 再统计所选日期范围内：
  - `appId = 当前课程智能体`
  - `obj = "Human"`

统计意义：

- 表示这个课程智能体在当前筛选时间范围内，被用户真实提问了多少次
- 和“打开次数”不同，它只统计真正的问答输入

## 9. 热门页面

### 9.1 来源

- `education2.usage_events`

### 9.2 统计规则

- 在所选时间范围内筛选 `event_type = "request"`
- 仅统计 `username` 非空记录
- 按 `path` 分组
- `views` 为访问次数
- `uv` 为去重用户名数量

### 9.3 统计意义

- 反映平台中最常被访问的业务页面和接口

## 10. 活跃用户 Top 10

### 10.1 来源

- `education2.usage_events`

### 10.2 统计规则

- 在所选日期范围内
- 事件类型属于活跃事件集合
- `username` 非空
- 按 `username` 聚合
- `events` 为事件总次数
- 按次数降序取前 10

### 10.3 统计意义

- 表示当前时间范围内最活跃的用户名
- 在当前系统里通常等于学号

## 11. 明细表说明

当前明细表展示这些列：

- 日期
- DAU
- 登录数
- 注册数
- 对话数
- 请求量

### 11.1 第一行汇总

第一行固定为：

- `所选时段汇总`

含义：

- 对整个筛选日期区间做一次汇总统计

### 11.2 第二行开始的日期顺序

从第二行开始：

- 按日期倒序展示
- 最新日期排在最上面

### 11.3 每日对话数的来源

这里的 `item.chats` 已经不是旧的 `usage_events.mcp_chat` 口径，而是被 FastGPT 日提问数覆盖后的结果。

也就是说：

- 顶部对话数
- 趋势图对话数
- 明细表对话数

现在是同一套口径。

## 12. 日期范围规则

日期范围由 `resolve_date_range()` 处理。

规则如下：

- 不传开始和结束日期时，默认取“当月 1 日到今天”
- 只传一个日期时，开始和结束都用这个日期
- 如果开始日期晚于结束日期，会自动交换
- 查询时实际区间为：
  - `start_at = 开始日期 00:00:00`
  - `end_at = 结束日期 + 1 天`

因此：

- 结束日期当天会被包含在统计中

## 13. 当前在线相关说明

虽然页面已不展示“峰值在线”，但后端仍保留相关逻辑。

当前机制：

- 登录用户发起有效请求时刷新 `usage_online_users`
- 最近 5 分钟内有活动则认为在线
- 每日最大在线人数仍会写入 `usage_daily_peaks`

统计意义：

- 支持当前在线人数统计
- 为以后恢复在线峰值展示保留后端基础

## 14. 当前系统中“登录数”和“DAU”的区别

### 14.1 登录数

- 含义：成功登录行为的次数
- 口径：`event_type = "login_success"` 的记录条数
- 特点：不去重，同一个用户登录多次会累计多次

### 14.2 DAU

- 含义：当天活跃去重用户数
- 口径：活跃事件集合中的 `username` 去重数
- 特点：同一个用户当天无论触发多少次行为，只算 1 个活跃用户

## 15. 维护建议

### 15.1 如果以后再新增 FastGPT 对话入口

推荐做法：

1. 在项目中找到新的 FastGPT 分享链接
2. 从链接中提取 `shareId`
3. 加入 [app.py](/home/zgllm/workspace/elite_server/app.py) 里的 `_fastgpt_dialogue_targets()`
4. 让它自动参与：
   - 顶部对话数
   - 趋势图对话数
   - 明细表对话数
   - 系统总对话数

### 15.2 如果以后要统计“课程智能体点击引导提问次数”

当前 `chat_input_guides` 不是点击日志，所以如果以后要统计“用户点了引导按钮多少次”，需要：

1. 在前端点击引导时新增埋点
2. 或在 FastGPT 侧单独落点击日志

否则不能仅凭 `chat_input_guides` 直接得出“点击次数”。

### 15.3 环境安全建议

FastGPT MongoDB 建议：

- 使用只读账号
- 通过环境变量 `FASTGPT_MONGO_URI` 注入
- 不要把真实 URI 写入代码仓库
- 最好限制为仅允许应用服务器访问
