import copy
import os
import re
import threading
import time

import requests
from flask import Blueprint, flash, redirect, render_template, session, url_for

app_comp = Blueprint("app_comp", __name__)

ROBOTAC_HOME_URL = "https://www.robotac.cn/"
ROBOTAC_INTRO_URL = "https://www.robotac.cn/h-col-141.html"
ROBOTAC_CACHE_TTL_SECONDS = 6 * 60 * 60
ROBOTAC_REQUEST_TIMEOUT = 12


agents_kd = [
    {
        "id": 1,
        "name": "Robocon-主赛",
        "description": "Robocon 主赛智能体，聚焦赛题解析、方案设计与实战复盘。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=invnfCJLBhZmIM8fLdj0E0SN",
        "image_url": "/static/img/robocon_logo.png"
    },
    {
        "id": 2,
        "name": "Robotac",
        "description": "Robotac 智能体，聚焦对抗赛、挑战赛与备赛资料梳理。",
        "url": "http://180.85.206.30:3000/chat/share?shareId=mmvR2bCNNp9pHH3ngkx1ODwo",
        "image_url": "/static/img/robotac-logo.png"
    }
]

ROBOCON_MAIN_RESOURCES = {
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

ROBOTAC_RESOURCES_SNAPSHOT = {
    "notices": {
        "key": "notices",
        "label": "通知公告",
        "description": "ROBOTAC 官网当前公开的章程、办赛通知与赛季规则文件。",
        "official_url": ROBOTAC_HOME_URL,
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
        "official_url": ROBOTAC_HOME_URL,
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
                "url": ROBOTAC_INTRO_URL,
                "preview_url": ROBOTAC_INTRO_URL,
                "source": "ROBOTAC 官网"
            }
        ]
    }
}

ROBOTAC_CACHE = {
    "data": None,
    "fetched_at": 0.0,
    "lock": threading.Lock()
}


def require_login():
    if "username" not in session:
        flash("请先登录")
        return redirect(url_for("login"))
    return None


def build_resources_with_local_overrides(resources, local_path_map=None):
    resource_copy = copy.deepcopy(resources)
    local_path_map = local_path_map or {}
    base_dir = os.path.dirname(os.path.abspath(__file__))

    for section_key, section in resource_copy.items():
        title_to_path = local_path_map.get(section_key, {})
        for doc in section["docs"]:
            relative_path = title_to_path.get(doc["title"])
            if not relative_path:
                continue

            absolute_path = os.path.join(base_dir, relative_path)
            if os.path.exists(absolute_path):
                local_url = f"/{relative_path}"
                doc["url"] = local_url
                doc["preview_url"] = local_url
                doc["source"] = f"{doc['source']} / 本地副本"

    return resource_copy


def get_robocon_main_resources():
    return build_resources_with_local_overrides(
        ROBOCON_MAIN_RESOURCES,
        {
            "national": {
                "第二十五届全国大学生机器人大赛ROBOCON“武林探秘”竞技赛规则V4": "static/robocon_docs/national/national_rule_v4.pdf",
                "第二十五届全国大学生机器人大赛ROBOCON武林探秘图册V3": "static/robocon_docs/national/national_figure_v3.pdf",
                "第二十五届全国大学生机器人大赛ROBOCON“武林探秘”竞技赛规则V3": "static/robocon_docs/national/national_rule_v3.pdf"
            },
            "international": {
                "ABU ROBOCON 2025 Rule Book": "static/robocon_docs/international/international_rulebook_2025.pdf",
                "ABU ROBOCON 2025 FAQ": "static/robocon_docs/international/international_faq_20250805.pdf",
                "Appendix 1. Game field - Structure": "static/robocon_docs/international/international_appendix_1.pdf",
                "Appendix 2. Game field - Dimensions (Top view)": "static/robocon_docs/international/international_appendix_2.pdf"
            }
        }
    )


def strip_html(value):
    cleaned = re.sub(r"<[^>]+>", " ", value or "")
    cleaned = cleaned.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def classify_robotac_doc(title):
    notice_keywords = (
        "规则",
        "章程",
        "对抗赛",
        "挑战赛",
        "设计赛",
        "任务赛"
    )
    if any(keyword in title for keyword in notice_keywords):
        return "notices"
    return "competition"


def infer_robotac_doc_type(title):
    if "章程" in title:
        return "章程"
    if "规则" in title and "挑战赛" in title:
        return "挑战赛规则"
    if "规则" in title and "对抗赛" in title:
        return "对抗赛规则"
    if "规则" in title:
        return "规则"
    if "通知" in title or "报名" in title:
        return "办赛通知"
    if "简介" in title:
        return "赛事介绍"
    return "官网资料"


def extract_robotac_article_links(html):
    hrefs = re.findall(r'href=["\'](/sys-nd/\d+\.html)["\']', html)
    results = []
    seen = set()
    for href in hrefs:
        full_url = f"https://www.robotac.cn{href}"
        if full_url in seen:
            continue
        seen.add(full_url)
        results.append(full_url)
    return results


def fetch_robotac_article(url):
    response = requests.get(url, timeout=ROBOTAC_REQUEST_TIMEOUT)
    response.raise_for_status()
    html = response.text

    title_match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    raw_title = strip_html(title_match.group(1)) if title_match else url
    title = raw_title.split(" - 全国大学生机器人大赛ROBOTAC官网")[0].strip()

    date_match = re.search(r"发表时间[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", strip_html(html))
    published_at = date_match.group(1) if date_match else "官网当前页面"

    return {
        "title": title,
        "type": infer_robotac_doc_type(title),
        "date": published_at,
        "url": url,
        "preview_url": url,
        "source": "ROBOTAC 官网动态页",
        "category": classify_robotac_doc(title)
    }


def scrape_robotac_resources():
    response = requests.get(ROBOTAC_HOME_URL, timeout=ROBOTAC_REQUEST_TIMEOUT)
    response.raise_for_status()
    links = extract_robotac_article_links(response.text)

    notices = []
    competition = [
        {
            "title": "ROBOTAC 大赛简介",
            "type": "赛事介绍",
            "date": "官网当前页面",
            "url": ROBOTAC_INTRO_URL,
            "preview_url": ROBOTAC_INTRO_URL,
            "source": "ROBOTAC 官网"
        }
    ]

    for article_url in links[:18]:
        try:
            article = fetch_robotac_article(article_url)
        except Exception as exc:
            print(f"抓取 ROBOTAC 文章失败: {article_url} -> {exc}")
            continue

        doc = {
            "title": article["title"],
            "type": article["type"],
            "date": article["date"],
            "url": article["url"],
            "preview_url": article["preview_url"],
            "source": article["source"]
        }

        if article["category"] == "notices":
            notices.append(doc)
        else:
            if all(existing["url"] != doc["url"] for existing in competition):
                competition.append(doc)

    notices = notices[:8]
    competition = competition[:6]
    latest_date = notices[0]["date"] if notices else "官网当前页面"
    event_date = competition[1]["date"] if len(competition) > 1 else competition[0]["date"]

    return {
        "notices": {
            "key": "notices",
            "label": "通知公告",
            "description": "ROBOTAC 官网实时抓取的通知、规则与章程。",
            "official_url": ROBOTAC_HOME_URL,
            "updated_at": latest_date,
            "update_note": "当前页面数据由服务端定期从 ROBOTAC 官网抓取，并带缓存兜底。",
            "docs": notices or copy.deepcopy(ROBOTAC_RESOURCES_SNAPSHOT["notices"]["docs"])
        },
        "competition": {
            "key": "competition",
            "label": "赛事说明",
            "description": "ROBOTAC 官网实时抓取的赛事介绍与办赛动态。",
            "official_url": ROBOTAC_HOME_URL,
            "updated_at": event_date,
            "update_note": "当前页面数据由服务端定期从 ROBOTAC 官网抓取，并带缓存兜底。",
            "docs": competition
        }
    }


def get_robotac_resources(force_refresh=False):
    now = time.time()
    with ROBOTAC_CACHE["lock"]:
        cached_data = ROBOTAC_CACHE["data"]
        fetched_at = ROBOTAC_CACHE["fetched_at"]
        cache_is_fresh = cached_data and (now - fetched_at) < ROBOTAC_CACHE_TTL_SECONDS
        if cache_is_fresh and not force_refresh:
            return copy.deepcopy(cached_data)

        try:
            fresh_data = scrape_robotac_resources()
            ROBOTAC_CACHE["data"] = fresh_data
            ROBOTAC_CACHE["fetched_at"] = now
            return copy.deepcopy(fresh_data)
        except Exception as exc:
            print(f"抓取 ROBOTAC 官网失败，回退缓存/快照: {exc}")
            if cached_data:
                return copy.deepcopy(cached_data)
            fallback = build_resources_with_local_overrides(ROBOTAC_RESOURCES_SNAPSHOT)
            ROBOTAC_CACHE["data"] = fallback
            ROBOTAC_CACHE["fetched_at"] = now
            return copy.deepcopy(fallback)


@app_comp.route('/dashboard/kd')
def course_kd():
    login_response = require_login()
    if login_response:
        return login_response

    return render_template(
        'dashboard/kd.html',
        agents=agents_kd,
        username=session.get('username', '用户'),
        role=session.get('role', 'student')
    )


@app_comp.route('/dashboard/kds/<int:agent_id>')
def view_kd(agent_id):
    login_response = require_login()
    if login_response:
        return login_response

    agent = next((a for a in agents_kd if a['id'] == agent_id), None)
    if not agent:
        flash('找不到该知识库智能体', 'error')
        return redirect(url_for('app_comp.course_kd'))

    template_name = 'dashboard/new_chat.html'
    extra_context = {}
    if agent_id == 1:
        template_name = 'dashboard/competition_chat.html'
        extra_context['competition_resources'] = get_robocon_main_resources()
        extra_context['official_link_label'] = 'ROBOCON 官网入口'
        extra_context['assistant_title'] = '主赛智能问答'
    elif agent_id == 2:
        template_name = 'dashboard/competition_chat.html'
        extra_context['competition_resources'] = get_robotac_resources()
        extra_context['official_link_label'] = 'ROBOTAC 官网入口'
        extra_context['assistant_title'] = 'Robotac 智能问答'

    return render_template(
        template_name,
        embed_url=agent['url'],
        agent=agent,
        username=session.get('username', '用户'),
        role=session.get('role', 'student'),
        **extra_context
    )
