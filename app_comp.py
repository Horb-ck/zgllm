import copy
import hashlib
import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import unquote, urljoin, urlparse

import requests
from flask import Blueprint, flash, redirect, render_template, session, url_for
from bs4 import BeautifulSoup
from requests.packages.urllib3.exceptions import InsecureRequestWarning

app_comp = Blueprint("app_comp", __name__)

ROBOCON_HOME_URL = "https://robocon.org.cn/"
ROBOCON_NEWS_URL = "https://robocon.org.cn/h-col-104.html"
ROBOCON_REQUEST_TIMEOUT = 12
ROBOCON_VERIFY_SSL = False
ROBOCON_SYNC_INTERVAL_DAYS = 2
ROBOCON_SYNC_HOUR = 3
ROBOCON_SYNC_MINUTE = 0
ROBOCON_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROBOCON_DOC_DIR = os.path.join(
    ROBOCON_BASE_DIR,
    "static",
    "robocon_docs",
    "national",
    "official_monitor"
)
ROBOCON_STATE_PATH = os.path.join(ROBOCON_DOC_DIR, "resources_state.json")
ROBOCON_REQUIRED_TITLE_KEYWORDS = ("第二十五届", "ROBOCON")
ROBOCON_RULE_CORE_KEYWORDS = ("竞技赛规则", "规则书", "比赛规则", "规则V", "补充规则", "规则修订")
ROBOCON_FIGURE_CORE_KEYWORDS = ("图册", "场地图", "尺寸图", "结构图", "附件图")
ROBOCON_FAQ_CORE_KEYWORDS = ("FAQ", "答疑", "补充说明", "裁判说明", "问题解答")
ROBOCON_IMPORTANT_NOTICE_KEYWORDS = ("赛程", "时间安排", "中期检查", "技术交流", "测试安排", "参赛说明", "现场说明")
ROBOCON_GENERAL_NOTICE_KEYWORDS = ("通知", "报名", "公示", "名单", "会议", "举办", "资格", "结果", "章程")
ROBOCON_DOWNLOADABLE_CATEGORIES = {"rule_core", "figure_core", "faq_core"}
ROBOCON_ATTACHMENT_ALLOW_KEYWORDS = ("规则", "rule", "图册", "faq", "答疑", "武林探秘", "补充说明")
ROBOCON_ATTACHMENT_BLOCK_KEYWORDS = ("报名表", "回执", "盖章", "汇总表", "名单", "签到", "申请表", "说明会")
ROBOCON_CATEGORY_LABELS = {
    "rule_core": "核心规则",
    "figure_core": "图册",
    "faq_core": "FAQ",
    "important_notice": "重要通知",
    "general_notice": "通知"
}
ROBOCON_SCHEDULER_STATE = {
    "started": False,
    "lock": threading.Lock(),
    "thread": None
}

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

def strip_html(value):
    cleaned = re.sub(r"<[^>]+>", " ", value or "")
    cleaned = cleaned.replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").strip())


def sanitize_filename(filename):
    safe_name = re.sub(r"[\\/:*?\"<>|]+", "_", filename or "")
    safe_name = re.sub(r"\s+", "_", safe_name).strip("._")
    return safe_name or f"file_{int(time.time())}"


def parse_date_value(value):
    if not value:
        return None

    date_match = re.search(r"([0-9]{4})[-/.年]([0-9]{1,2})[-/.月]([0-9]{1,2})", value)
    if not date_match:
        return None

    year, month, day = date_match.groups()
    try:
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    except ValueError:
        return None


def requests_get_robocon(url):
    kwargs = {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        },
        "timeout": ROBOCON_REQUEST_TIMEOUT
    }
    if url.startswith(ROBOCON_HOME_URL) and not ROBOCON_VERIFY_SSL:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        kwargs["verify"] = False
    return requests.get(url, **kwargs)


def is_relevant_robocon_title(title):
    text = normalize_text(title)
    if not text:
        return False

    return all(keyword in text for keyword in ROBOCON_REQUIRED_TITLE_KEYWORDS)


def title_contains_any_keyword(title, keywords):
    text = normalize_text(title)
    lowered = text.lower()
    for keyword in keywords:
        if keyword.lower() in lowered:
            return True
    return False


def classify_robocon_entry(title):
    if not is_relevant_robocon_title(title):
        return None
    if title_contains_any_keyword(title, ROBOCON_RULE_CORE_KEYWORDS):
        return "rule_core"
    if title_contains_any_keyword(title, ROBOCON_FIGURE_CORE_KEYWORDS):
        return "figure_core"
    if title_contains_any_keyword(title, ROBOCON_FAQ_CORE_KEYWORDS):
        return "faq_core"
    if title_contains_any_keyword(title, ROBOCON_IMPORTANT_NOTICE_KEYWORDS):
        return "important_notice"
    if title_contains_any_keyword(title, ROBOCON_GENERAL_NOTICE_KEYWORDS):
        return "general_notice"
    return None


def should_download_robocon_entry(category):
    return category in ROBOCON_DOWNLOADABLE_CATEGORIES


def infer_robocon_doc_type(title, category=None):
    if category in ROBOCON_CATEGORY_LABELS:
        return ROBOCON_CATEGORY_LABELS[category]
    if "图册" in title:
        return "图册"
    if "FAQ" in title or "答疑" in title:
        return "FAQ"
    if "规则" in title:
        return "规则"
    if "通知" in title:
        return "通知"
    return "官网资料"


def relative_static_path(local_path):
    static_root = os.path.join(ROBOCON_BASE_DIR, "static")
    if not local_path or not local_path.startswith(static_root):
        return None
    relative_path = os.path.relpath(local_path, static_root).replace(os.sep, "/")
    return f"/static/{relative_path}"


def ensure_robocon_storage():
    os.makedirs(ROBOCON_DOC_DIR, exist_ok=True)


def download_robocon_file(file_url, file_name):
    ensure_robocon_storage()
    response = requests_get_robocon(file_url)
    response.raise_for_status()
    file_bytes = response.content
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    parsed_path = urlparse(file_url).path
    suffix = os.path.splitext(parsed_path)[1] or os.path.splitext(file_name)[1] or ".pdf"
    local_filename = f"{sanitize_filename(os.path.splitext(file_name)[0])}_{file_hash[:12]}{suffix}"
    local_path = os.path.join(ROBOCON_DOC_DIR, local_filename)
    if not os.path.exists(local_path):
        with open(local_path, "wb") as file_obj:
            file_obj.write(file_bytes)
    return {
        "file_hash": file_hash,
        "local_path": local_path,
        "local_url": relative_static_path(local_path)
    }


def extract_robocon_news_entries(html):
    soup = BeautifulSoup(html, "lxml")
    container = soup.select_one(".news_list_wrap")
    if not container:
        return []

    entries = []
    seen_urls = set()
    for link in container.select("a[href]"):
        href = normalize_text(link.get("href"))
        if not href:
            continue
        detail_url = urljoin(ROBOCON_HOME_URL, href)
        if detail_url in seen_urls:
            continue

        title = normalize_text(link.get_text(" ", strip=True)) or normalize_text(link.get("title"))
        if not title:
            continue
        category = classify_robocon_entry(title)
        if not category:
            continue

        block = link.find_parent(["li", "div", "article", "section"]) or link.parent
        block_text = normalize_text(block.get_text(" ", strip=True)) if block else ""
        publish_date = parse_date_value(block_text) or parse_date_value(title)

        entries.append(
            {
                "title": title,
                "detail_url": detail_url,
                "publish_date": publish_date,
                "type": infer_robocon_doc_type(title, category),
                "category": category
            }
        )
        seen_urls.add(detail_url)
    return entries


def extract_detail_main_node(soup):
    selectors = [
        ".article_content",
        ".rich-text",
        ".news_detail_wrap",
        ".nd_content",
        ".text",
        ".content"
    ]
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def extract_robocon_attachment_links(main_node, page_url):
    attachments = []
    seen_urls = set()
    for anchor in main_node.select("a[href]"):
        href = normalize_text(anchor.get("href"))
        if not href:
            continue
        full_url = urljoin(page_url, href)
        parsed_path = urlparse(full_url).path.lower()
        is_attachment = any(
            parsed_path.endswith(ext)
            for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
        )
        if not is_attachment and "/upload/" not in parsed_path and "/file/" not in parsed_path:
            continue
        if full_url in seen_urls:
            continue

        anchor_text = normalize_text(anchor.get_text(" ", strip=True))
        file_name = anchor_text or os.path.basename(unquote(urlparse(full_url).path)) or "attachment"
        attachments.append({"file_name": file_name, "file_url": full_url})
        seen_urls.add(full_url)
    return attachments


def is_downloadable_robocon_attachment(file_name):
    normalized_name = normalize_text(file_name)
    if not normalized_name:
        return False
    if title_contains_any_keyword(normalized_name, ROBOCON_ATTACHMENT_BLOCK_KEYWORDS):
        return False
    return title_contains_any_keyword(normalized_name, ROBOCON_ATTACHMENT_ALLOW_KEYWORDS)


def fetch_robocon_detail_resource(entry):
    response = requests_get_robocon(entry["detail_url"])
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "lxml")

    title_node = soup.select_one("h1")
    title = normalize_text(title_node.get_text(" ", strip=True)) if title_node else entry["title"]
    body_text = normalize_text(strip_html(html))
    publish_date = parse_date_value(body_text) or entry.get("publish_date") or "官网当前页面"
    main_node = extract_detail_main_node(soup)
    attachments = extract_robocon_attachment_links(main_node, entry["detail_url"])

    doc = {
        "title": title,
        "type": infer_robocon_doc_type(title, entry.get("category")),
        "date": publish_date,
        "url": entry["detail_url"],
        "preview_url": entry["detail_url"],
        "source": "ROBOCON 官网赛事动态",
        "category": entry.get("category"),
        "download_policy": "download" if should_download_robocon_entry(entry.get("category")) else "metadata_only"
    }

    if should_download_robocon_entry(entry.get("category")):
        filtered_attachments = [
            attachment for attachment in attachments
            if is_downloadable_robocon_attachment(attachment["file_name"])
        ]
        if filtered_attachments:
            primary_attachment = filtered_attachments[0]
        else:
            primary_attachment = None

        if primary_attachment:
            try:
                download_result = download_robocon_file(
                    primary_attachment["file_url"],
                    primary_attachment["file_name"]
                )
                doc["url"] = primary_attachment["file_url"]
                doc["preview_url"] = download_result["local_url"] or primary_attachment["file_url"]
                doc["source"] = f"{doc['source']} / 本地副本"
                doc["downloaded_attachment"] = primary_attachment["file_name"]
            except Exception as exc:
                print(f"下载 Robocon 附件失败: {primary_attachment['file_url']} -> {exc}")
        else:
            print(f"Robocon 条目命中可下载分类，但未找到符合规则的附件: {title}")
    else:
        try:
            summary_text = normalize_text(main_node.get_text(" ", strip=True))
            if summary_text:
                doc["summary"] = summary_text[:180]
        except Exception:
            pass

    return doc


def build_robocon_dynamic_resources(docs, synced_at):
    resources = get_robocon_main_resources_snapshot()
    if docs:
        resources["national"]["docs"] = docs
        resources["national"]["updated_at"] = docs[0]["date"]
        resources["national"]["update_note"] = (
            f"后台定时任务已在 {synced_at} 完成最近一次官网同步，"
            "当前仅对规则、图册、FAQ 等规则资产下载附件，通知类内容只记录详情。"
        )
    return resources


def save_robocon_resources_state(resources):
    ensure_robocon_storage()
    with open(ROBOCON_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(resources, file_obj, ensure_ascii=False, indent=2)


def load_robocon_resources_state():
    if not os.path.exists(ROBOCON_STATE_PATH):
        return None
    try:
        with open(ROBOCON_STATE_PATH, "r", encoding="utf-8") as file_obj:
            return json.load(file_obj)
    except Exception as exc:
        print(f"读取 Robocon 本地缓存失败: {exc}")
        return None


def sync_robocon_main_resources():
    print(f"开始同步 Robocon 官网规则: {ROBOCON_NEWS_URL}")
    response = requests_get_robocon(ROBOCON_NEWS_URL)
    response.raise_for_status()
    entries = extract_robocon_news_entries(response.text)
    print(f"Robocon 列表页抓取成功，发现候选条目 {len(entries)} 条")

    docs = []
    for entry in entries:
        try:
            doc = fetch_robocon_detail_resource(entry)
            docs.append(doc)
            print(
                "同步 Robocon 条目成功: "
                f"{doc['title']} "
                f"[category={doc.get('category')}, policy={doc.get('download_policy')}]"
            )
        except Exception as exc:
            print(f"同步 Robocon 条目失败: {entry.get('detail_url')} -> {exc}")

    docs.sort(key=lambda item: item.get("date") or "", reverse=True)
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resources = build_robocon_dynamic_resources(docs, synced_at)
    save_robocon_resources_state(resources)
    print(f"Robocon 官网同步完成，本次处理条目 {len(docs)} 条")
    return resources


def get_robocon_main_resources_snapshot():
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


def get_robocon_main_resources():
    cached_resources = load_robocon_resources_state()
    if cached_resources:
        return cached_resources
    return get_robocon_main_resources_snapshot()


def compute_next_robocon_sync(now=None):
    now = now or datetime.now()
    anchor = datetime(now.year, 1, 1, ROBOCON_SYNC_HOUR, ROBOCON_SYNC_MINUTE, 0)
    if now <= anchor:
        return anchor

    days_since_anchor = (now.date() - anchor.date()).days
    next_offset = days_since_anchor if days_since_anchor % ROBOCON_SYNC_INTERVAL_DAYS == 0 else days_since_anchor + 1
    candidate = anchor + timedelta(days=next_offset)
    if candidate <= now:
        candidate += timedelta(days=ROBOCON_SYNC_INTERVAL_DAYS)
    while (candidate.date() - anchor.date()).days % ROBOCON_SYNC_INTERVAL_DAYS != 0:
        candidate += timedelta(days=1)
    return candidate


def robocon_scheduler_loop():
    print(
        "Robocon 定时同步已启动，"
        f"计划每 {ROBOCON_SYNC_INTERVAL_DAYS} 天 {ROBOCON_SYNC_HOUR:02d}:{ROBOCON_SYNC_MINUTE:02d} 执行一次"
    )

    if not os.path.exists(ROBOCON_STATE_PATH):
        try:
            print("未发现 Robocon 本地缓存，启动后先执行一次初始化同步")
            sync_robocon_main_resources()
        except Exception as exc:
            print(f"初始化同步 Robocon 官网失败: {exc}")

    while True:
        next_run = compute_next_robocon_sync()
        wait_seconds = max(30, int((next_run - datetime.now()).total_seconds()))
        print(f"下一次 Robocon 定时同步时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        try:
            sync_robocon_main_resources()
        except Exception as exc:
            print(f"Robocon 定时同步失败: {exc}")
        time.sleep(1)


def should_start_background_scheduler():
    werkzeug_run_main = os.environ.get("WERKZEUG_RUN_MAIN")
    if werkzeug_run_main is not None:
        return werkzeug_run_main == "true"
    return True


def start_robocon_scheduler():
    if not should_start_background_scheduler():
        return

    with ROBOCON_SCHEDULER_STATE["lock"]:
        if ROBOCON_SCHEDULER_STATE["started"]:
            return

        scheduler_thread = threading.Thread(
            target=robocon_scheduler_loop,
            name="robocon-sync-scheduler",
            daemon=True
        )
        scheduler_thread.start()
        ROBOCON_SCHEDULER_STATE["thread"] = scheduler_thread
        ROBOCON_SCHEDULER_STATE["started"] = True


@app_comp.record_once
def on_app_comp_registered(state):
    start_robocon_scheduler()


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
