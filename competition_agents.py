import copy


COMPETITION_AGENT_DEFINITIONS = [
    {
        "id": 1,
        "key": "robocon_main",
        "route_name": "Robocon",
        "competition_name": "Robocon",
        "name": "Robocon-主赛",
        "description": "Robocon 主赛智能体，聚焦赛题解析、方案设计与实战复盘。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=pjSRSIwb4iudHQu7T7OeVm7s",
        "image_url": "/static/img/robocon_logo.png",
        "template_name": "dashboard/competition_chat.html",
        "resource_loader_key": "robocon_main",
        "default_category": "national",
        "assistant_title": "Robocon 智能体",
        "official_link_label": "ROBOCON 官网入口",
        "site_urls": {
            "home_url": "https://robocon.org.cn/",
            "news_url": "https://robocon.org.cn/h-col-104.html",
        },
        "resource_snapshot": {
            "national": {
                "key": "national",
                "label": "国赛",
                "description": "全国大学生机器人大赛 ROBOCON 主赛官方规则资料。",
                "official_url": "https://robocon.org.cn/",
                "updated_at": "2026-02-27",
                "update_note": "官网赛事动态页显示最新主赛规则已更新到 V4。",
                "docs": [
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOCON“武林探秘”竞技赛规则V4",
                        "type": "最新规则",
                        "date": "2026-02-27",
                        "url": "https://robocon.org.cn/h-col-104.html",
                        "preview_url": "https://robocon.org.cn/h-col-104.html",
                        "source": "ROBOCON 官网赛事动态页"
                    },
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOCON武林探秘图册V3",
                        "type": "图册",
                        "date": "2026-01-08",
                        "url": "https://robocon.org.cn/sys-nd/77.html",
                        "preview_url": "https://robocon.org.cn/sys-nd/77.html",
                        "source": "ROBOCON 官网文章页"
                    },
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOCON“武林探秘”竞技赛规则V3",
                        "type": "历史版本",
                        "date": "2026-01-08",
                        "url": "https://robocon.org.cn/sys-nd/76.html",
                        "preview_url": "https://robocon.org.cn/sys-nd/76.html",
                        "source": "ROBOCON 官网文章页"
                    }
                ]
            },
            "international": {
                "key": "international",
                "label": "国际赛",
                "description": "ABU Robocon 官方规则资料。当前最新资料实际发布在 2025 主办方官网，aburobocon.net 主页仍显示 2017 页面。",
                "official_url": "https://aburobocon2025.mnb.mn/en",
                "updated_at": "2025-08-05",
                "update_note": "按当前可访问的官方站点，最新规则资料来自 ABU Robocon 2025 Ulaanbaatar 官网。",
                "docs": [
                    {
                        "title": "ABU ROBOCON 2025 Rule Book",
                        "type": "最新规则",
                        "date": "2024-11-21",
                        "url": "https://aburobocon2025.mnb.mn/uploads/file/ABU_ROBOCON_2025_Rulebook_20241121.pdf",
                        "preview_url": "https://aburobocon2025.mnb.mn/uploads/file/ABU_ROBOCON_2025_Rulebook_20241121.pdf",
                        "source": "ABU Robocon 2025 官网"
                    },
                    {
                        "title": "ABU ROBOCON 2025 FAQ",
                        "type": "FAQ",
                        "date": "2025-08-05",
                        "url": "https://aburobocon2025.mnb.mn/uploads/file/ABU_ROBOCON_2025_FAQ_20250805.pdf",
                        "preview_url": "https://aburobocon2025.mnb.mn/uploads/file/ABU_ROBOCON_2025_FAQ_20250805.pdf",
                        "source": "ABU Robocon 2025 官网"
                    },
                    {
                        "title": "Appendix 1. Game field - Structure",
                        "type": "Figures",
                        "date": "2024-08-08",
                        "url": "https://aburobocon2025.mnb.mn/uploads/file/Appendix-1.pdf",
                        "preview_url": "https://aburobocon2025.mnb.mn/uploads/file/Appendix-1.pdf",
                        "source": "ABU Robocon 2025 官网"
                    },
                    {
                        "title": "Appendix 2. Game field - Dimensions (Top view)",
                        "type": "Figures",
                        "date": "2024-08-08",
                        "url": "https://aburobocon2025.mnb.mn/uploads/file/Appendix-2.pdf",
                        "preview_url": "https://aburobocon2025.mnb.mn/uploads/file/Appendix-2.pdf",
                        "source": "ABU Robocon 2025 官网"
                    }
                ]
            }
        }
    },
    {
        "id": 2,
        "key": "robotac",
        "route_name": "Robotac",
        "competition_name": "Robotac",
        "name": "Robotac",
        "description": "Robotac 智能体，聚焦对抗赛、挑战赛与备赛资料梳理。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=op71UGEW28SkdhD9NVAGVens",
        "image_url": "/static/img/robotac-logo.png",
        "template_name": "dashboard/competition_chat.html",
        "resource_loader_key": "robotac",
        "default_category": "notices",
        "assistant_title": "Robotac 智能问答",
        "official_link_label": "ROBOTAC 官网入口",
        "site_urls": {
            "home_url": "https://www.robotac.cn/",
            "news_url": "https://www.robotac.cn/h-col-104.html",
            "intro_url": "https://www.robotac.cn/h-col-141.html",
        },
        "resource_snapshot": {
            "notices": {
                "key": "notices",
                "label": "通知公告",
                "description": "ROBOTAC 官网当前公开的章程、办赛通知与赛季规则文件。",
                "official_url": "https://www.robotac.cn/",
                "updated_at": "2026-01-10",
                "update_note": "静态备份：抓取失败时继续展示这份最近一次整理的官网资料。",
                "docs": [
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOTAC 侦察任务挑战赛比赛规则（1.0)",
                        "type": "最新规则",
                        "date": "2026-01-10",
                        "url": "https://www.robotac.cn/sys-nd/1317.html",
                        "preview_url": "https://www.robotac.cn/sys-nd/1317.html",
                        "source": "ROBOTAC 官网通知公告"
                    },
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOTAC挑战赛比赛规则——能量球灌篮挑战赛（V1.0）",
                        "type": "挑战赛规则",
                        "date": "2026-01-07",
                        "url": "https://www.robotac.cn/sys-nd/1316.html",
                        "preview_url": "https://www.robotac.cn/sys-nd/1316.html",
                        "source": "ROBOTAC 官网通知公告"
                    },
                    {
                        "title": "第二十五届全国大学生机器人大赛ROBOTAC挑战赛比赛规则——足式机器人挑战赛（V1.0）",
                        "type": "挑战赛规则",
                        "date": "2026-01-06",
                        "url": "https://www.robotac.cn/sys-nd/1315.html",
                        "preview_url": "https://www.robotac.cn/sys-nd/1315.html",
                        "source": "ROBOTAC 官网通知公告"
                    },
                    {
                        "title": "全国大学生机器人大赛ROBOTAC章程",
                        "type": "章程",
                        "date": "2025-12-30",
                        "url": "https://www.robotac.cn/sys-nd/1313.html",
                        "preview_url": "https://www.robotac.cn/sys-nd/1313.html",
                        "source": "ROBOTAC 官网通知公告"
                    }
                ]
            },
            "competition": {
                "key": "competition",
                "label": "赛事说明",
                "description": "ROBOTAC 官方赛事简介与赛事通知。",
                "official_url": "https://www.robotac.cn/",
                "updated_at": "2025-11-14",
                "update_note": "静态备份：官网抓取不可用时回退到这份整理数据。",
                "docs": [
                    {
                        "title": "关于举办第二十五届全国大学生机器人大赛ROBOTAC的通知",
                        "type": "办赛通知",
                        "date": "2025-11-14",
                        "url": "https://www.robotac.cn/sys-nd/1307.html",
                        "preview_url": "https://www.robotac.cn/sys-nd/1307.html",
                        "source": "ROBOTAC 官网赛事动态"
                    },
                    {
                        "title": "ROBOTAC 大赛简介",
                        "type": "赛事介绍",
                        "date": "官网当前页面",
                        "url": "https://www.robotac.cn/h-col-141.html",
                        "preview_url": "https://www.robotac.cn/h-col-141.html",
                        "source": "ROBOTAC 官网"
                    }
                ]
            }
        }
    },
    {
        "id": 3,
        "key": "robomaster",
        "route_name": "Robomaster",
        "competition_name": "Robomaster",
        "name": "Robomaster",
        "description": "Robomaster 战队智能体，聚焦 Robomaster 赛题解析、战队方案设计与实战复盘。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=o3BBx3j5FNohHbNH8WjUDaGQ",
        "image_url": "/static/img/robomaster_logo.jpg",
        "template_name": "dashboard/competition_chat.html",
        "resource_loader_key": "robomaster",
        "default_category": "rmuc",
        "assistant_title": "Robomaster 战队智能体",
        "official_link_label": "ROBOMASTER 资料入口",
        "site_urls": {
            "home_url": "https://www.robomaster.com/zh-CN",
            "news_url": "https://bbs.robomaster.com/wiki/20204847"
        },
        "resource_snapshot": {
            "rmuc": {
                "key": "rmuc",
                "label": "RMUC",
                "description": "Robomaster RMUC 官方规则与公告资料。",
                "official_url": "https://bbs.robomaster.com/wiki/20204847/809871?source=7",
                "updated_at": "2026-06-17",
                "update_note": "服务端将按 Robocon 主赛相同标准抓取 RMUC 规则页附件并同步到本地与 FastGPT。",
                "docs": []
            },
            "rmul": {
                "key": "rmul",
                "label": "RMUL",
                "description": "Robomaster RMUL 官方规则与公告资料。",
                "official_url": "https://bbs.robomaster.com/wiki/20204847/809872?source=7",
                "updated_at": "2026-06-17",
                "update_note": "服务端将按 Robocon 主赛相同标准抓取 RMUL 规则页附件并同步到本地与 FastGPT。",
                "docs": []
            },
            "rmua": {
                "key": "rmua",
                "label": "RMUA",
                "description": "Robomaster RMUA 官方规则与公告资料。",
                "official_url": "https://bbs.robomaster.com/wiki/20204847/809873?source=7",
                "updated_at": "2026-06-17",
                "update_note": "服务端将按 Robocon 主赛相同标准抓取 RMUA 规则页附件并同步到本地与 FastGPT。",
                "docs": []
            },
            "rmu": {
                "key": "rmu",
                "label": "RMU",
                "description": "Robomaster RMU 官方规则与公告资料。",
                "official_url": "https://bbs.robomaster.com/wiki/20204847/811363?source=7",
                "updated_at": "2026-06-17",
                "update_note": "服务端将按 Robocon 主赛相同标准抓取 RMU 规则页附件并同步到本地与 FastGPT。",
                "docs": []
            }
        }
    },
    {
        "id": 4,
        "key": "robocon_bionic_legged",
        "route_name": "RoboconBionicLegged",
        "competition_name": "Robocon",
        "name": "Robocon-仿生足式机器人",
        "description": "Robocon 仿生足式机器人战队智能体，聚焦仿生足式机器人赛题的专项资料与问答。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=cy2uRFeYVahpoEdETXoisAfo",
        "image_url": "/static/img/robocon_logo.png",
        "template_name": "dashboard/competition_chat.html",
        "resource_loader_key": "robocon_bionic_legged",
        "default_category": "national",
        "assistant_title": "Robocon-仿生足式机器人",
        "official_link_label": "ROBOCON 官网入口",
        "site_urls": {
            "home_url": "https://robocon.org.cn/",
            "news_url": "https://robocon.org.cn/h-col-104.html",
        },
        "resource_snapshot": {
            "national": {
                "key": "national",
                "label": "国赛",
                "description": "Robocon 仿生足式机器人方向的官方规则资料。",
                "official_url": "https://robocon.org.cn/",
                "updated_at": "2026-06-10",
                "update_note": "当前资料区用于展示 Robocon 官网中的仿生足式机器人相关规则，服务端会独立抓取并同步到足式知识库。",
                "docs": []
            },
            "international": {
                "key": "international",
                "label": "国际赛",
                "description": "当前未单独维护 Robocon 仿生足式机器人国际赛资料。",
                "official_url": "https://robocon.org.cn/",
                "updated_at": "2026-06-10",
                "update_note": "当前仅维护国赛足式规则，国际赛资料后续可按实际来源扩展。",
                "docs": []
            }
        }
    }
]

COMPETITION_AGENT_BY_ID = {
    agent["id"]: agent for agent in COMPETITION_AGENT_DEFINITIONS
}

COMPETITION_AGENT_BY_KEY = {
    agent["key"]: agent for agent in COMPETITION_AGENT_DEFINITIONS
}

COMPETITION_AGENT_BY_ROUTE_NAME = {
    agent["route_name"].lower(): agent for agent in COMPETITION_AGENT_DEFINITIONS
}


def list_kd_agents():
    return [
        {
            "id": agent["id"],
            "key": agent["key"],
            "route_name": agent["route_name"],
            "competition_name": agent["competition_name"],
            "name": agent["name"],
            "description": agent["description"],
            "url": agent["url"],
            "image_url": agent["image_url"]
        }
        for agent in COMPETITION_AGENT_DEFINITIONS
    ]


def get_competition_agent_by_id(agent_id):
    return COMPETITION_AGENT_BY_ID.get(agent_id)


def get_competition_agent_by_key(agent_key):
    return COMPETITION_AGENT_BY_KEY.get(agent_key)


def get_competition_agent_by_route_name(route_name):
    if not route_name:
        return None
    return COMPETITION_AGENT_BY_ROUTE_NAME.get(route_name.lower())


def get_competition_agent_snapshot(agent_key):
    agent = get_competition_agent_by_key(agent_key)
    if not agent:
        return {}
    return copy.deepcopy(agent["resource_snapshot"])
