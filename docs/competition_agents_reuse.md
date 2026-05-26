# 比赛智能体复用说明

## 目标

当前 `Robocon` 和 `Robotac` 已整理为一套通用页面和一份集中配置，后续可以继续复用这套模式管理更多“页面布局相近、只是在链接和资料来源上有差异”的比赛智能体。

## 现在的结构

- 通用详情页模板：`templates/dashboard/competition_chat.html`
- 智能体注册表：`competition_agents.py`
- 路由入口：`app_comp.py` 中的 `/dashboard/kd` 和 `/dashboard/kds/<int:agent_id>`
- 比赛资料加载器：
  - `get_robocon_main_resources()`
  - `get_robotac_resources()`

## 配置源

`competition_agents.py` 是当前的参数总入口。每个智能体定义包含：

- `id`
  页面入口使用的整数 ID。
- `key`
  智能体唯一标识，建议后续一直保持稳定。
- `name`
  页面标题和广场卡片名称。
- `description`
  页面副标题和广场卡片描述。
- `url`
  智能体 iframe 地址。
- `image_url`
  广场卡片图片。
- `template_name`
  使用的页面模板。当前同类比赛智能体统一使用 `dashboard/competition_chat.html`。
- `resource_loader_key`
  资源加载器标识，用来映射到服务端抓取函数。
- `assistant_title`
  预留给页面或后续扩展使用的智能体标题。
- `official_link_label`
  页面中“官网入口”按钮的文案。
- `site_urls`
  该智能体相关的网站参数，例如 `home_url`、`news_url`、`intro_url`。
- `resource_snapshot`
  抓取失败时用于兜底展示的静态资料快照。

## 新增一个同类智能体的推荐步骤

1. 在 `competition_agents.py` 里新增一个配置项。
2. 给它分配新的 `id` 和稳定的 `key`。
3. 填写页面层参数：
   - `name`
   - `description`
   - `url`
   - `image_url`
   - `official_link_label`
   - `site_urls`
4. 如果页面仍然是“资料区 + 聊天区”结构，继续复用 `dashboard/competition_chat.html`。
5. 在 `app_comp.py` 的 `COMPETITION_RESOURCE_LOADERS` 中补一个加载器映射。
6. 如果抓取逻辑和现有比赛接近，可以复用已有模式；如果差异较大，新增一组抓取函数。
7. 准备一份最小可用的 `resource_snapshot`，确保官网抓取失败时页面仍能打开。

## 建议的职责边界

- `competition_agents.py`
  只放“配置型参数”和静态快照，不放复杂抓取逻辑。
- `app_comp.py`
  保留抓取、缓存、FastGPT 同步、路由组装。
- `competition_chat.html`
  只负责展示，不写死某个比赛名称。

## 当前已经完成的复用点

- `Robocon` 和 `Robotac` 共用同一个详情页模板。
- 广场列表不再手写 `agents_kd`，而是从注册表生成。
- 详情页不再通过 `if agent_id == 1/2` 手工分支拼上下文，而是通过注册表自动装配。
- 官网链接等易变参数已从 `app_comp.py` 抽到注册表。
- `Robocon` 和 `Robotac` 的静态资源快照已从主业务文件抽离。

## 当前仍保留在代码里的差异

下面这些差异还在 `app_comp.py` 中，用代码维护比写进配置更稳：

- 官网页面抓取规则
- 标题分类规则
- 附件筛选规则
- 本地缓存与下载逻辑
- FastGPT 上传策略
- 定时同步策略

这是有意保留的边界。页面参数适合配置化，但抓取规则通常会越来越复杂，继续用 Python 代码维护更安全。

## 后续可以继续优化的方向

- 把抓取逻辑进一步拆成 `adapter` 模式，例如 `RoboconAdapter`、`RobotacAdapter`。
- 把 FastGPT dataset id、同步开关、同步频率也收拢到注册表。
- 如果后续非技术同学也要维护参数，可以再把注册表从 Python 迁移到 `YAML/JSON`。
