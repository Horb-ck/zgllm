import copy
import hashlib
import json
import mimetypes
import os
import re
import threading
import time
from datetime import datetime, timedelta
from urllib.parse import quote, unquote, urljoin, urlparse

import requests
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry
from urllib3.fields import RequestField
from urllib3.filepost import encode_multipart_formdata

from competition_agents import (
    get_competition_agent_by_id,
    get_competition_agent_by_key,
    get_competition_agent_by_route_name,
    get_competition_agent_snapshot,
    list_kd_agents,
)

from config import FASTGPT_URL

app_comp = Blueprint("app_comp", __name__)

ROBOCON_AGENT_CONFIG = get_competition_agent_by_key("robocon_main") or {}
ROBOCON_BIONIC_AGENT_CONFIG = get_competition_agent_by_key("robocon_bionic_legged") or {}
ROBOCON_SITE_URLS = ROBOCON_AGENT_CONFIG.get("site_urls", {})
ROBOCON_BIONIC_SITE_URLS = ROBOCON_BIONIC_AGENT_CONFIG.get("site_urls", {})
ROBOCON_HOME_URL = ROBOCON_SITE_URLS.get("home_url", "https://robocon.org.cn/")
ROBOCON_NEWS_URL = ROBOCON_SITE_URLS.get("news_url", "https://robocon.org.cn/h-col-104.html")
ROBOCON_BIONIC_HOME_URL = ROBOCON_BIONIC_SITE_URLS.get("home_url", ROBOCON_HOME_URL)
ROBOCON_BIONIC_NEWS_URL = ROBOCON_BIONIC_SITE_URLS.get("news_url", ROBOCON_NEWS_URL)
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
ROBOCON_FASTGPT_SYNC_STATE_PATH = os.path.join(ROBOCON_DOC_DIR, "fastgpt_sync_state.json")
ROBOCON_BIONIC_DOC_DIR = os.path.join(
    ROBOCON_BASE_DIR,
    "static",
    "robocon_docs",
    "bionic_legged",
    "official_monitor"
)
ROBOCON_BIONIC_STATE_PATH = os.path.join(ROBOCON_BIONIC_DOC_DIR, "resources_state.json")
ROBOCON_BIONIC_FASTGPT_SYNC_STATE_PATH = os.path.join(ROBOCON_BIONIC_DOC_DIR, "fastgpt_sync_state.json")
ROBOCON_REQUIRED_TITLE_KEYWORDS = ("第二十五届", "ROBOCON")
ROBOCON_RULE_CORE_KEYWORDS = ("竞技赛规则", "规则书", "比赛规则", "规则V", "补充规则", "规则修订")
ROBOCON_FIGURE_CORE_KEYWORDS = ("图册", "场地图", "尺寸图", "结构图", "附件图")
ROBOCON_FAQ_CORE_KEYWORDS = ("FAQ", "答疑", "补充说明", "裁判说明", "问题解答")
ROBOCON_IMPORTANT_NOTICE_KEYWORDS = ("赛程", "时间安排", "中期检查", "技术交流", "测试安排", "参赛说明", "现场说明")
ROBOCON_GENERAL_NOTICE_KEYWORDS = ("通知", "报名", "公示", "名单", "会议", "举办", "资格", "结果", "章程")
ROBOCON_DOWNLOADABLE_CATEGORIES = {"rule_core", "figure_core", "faq_core"}
ROBOCON_ATTACHMENT_ALLOW_KEYWORDS = ("规则", "rule", "图册", "faq", "答疑", "武林探秘", "补充说明")
ROBOCON_ATTACHMENT_BLOCK_KEYWORDS = ("报名表", "回执", "盖章", "汇总表", "名单", "签到", "申请表", "说明会")
ROBOCON_BIONIC_TRACK_KEYWORDS = ("仿生足式", "仿生足式机器人", "足式机器人", "足式比赛")
ROBOCON_BIONIC_ATTACHMENT_ALLOW_KEYWORDS = ROBOCON_ATTACHMENT_ALLOW_KEYWORDS + ROBOCON_BIONIC_TRACK_KEYWORDS
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
ROBOCON_FASTGPT_API_URL = os.environ.get("FASTGPT_API_URL", FASTGPT_URL+"api").rstrip("/")
ROBOCON_FASTGPT_DATASET_ID = os.environ.get(
    "FASTGPT_ROBOCON_DATASET_ID",
    "69c23d555a95f8059e185c36"
)
ROBOCON_BIONIC_FASTGPT_DATASET_ID = os.environ.get(
    "FASTGPT_ROBOCON_BIONIC_LEGGED_DATASET_ID",
    "6a32b5c8e2eeb153edc0a4ae"
)
ROBOCON_FASTGPT_TIMEOUT = 120

ROBOTAC_AGENT_CONFIG = get_competition_agent_by_key("robotac") or {}
ROBOTAC_SITE_URLS = ROBOTAC_AGENT_CONFIG.get("site_urls", {})
ROBOTAC_HOME_URL = ROBOTAC_SITE_URLS.get("home_url", "https://www.robotac.cn/")
ROBOTAC_NEWS_URL = ROBOTAC_SITE_URLS.get("news_url", "https://www.robotac.cn/h-col-104.html")
ROBOTAC_INTRO_URL = ROBOTAC_SITE_URLS.get("intro_url", "https://www.robotac.cn/h-col-141.html")
ROBOTAC_CACHE_TTL_SECONDS = 6 * 60 * 60
ROBOTAC_REQUEST_TIMEOUT = 12
ROBOTAC_VERIFY_SSL = False
ROBOTAC_BASE_DIR = ROBOCON_BASE_DIR
ROBOTAC_DOC_DIR = os.path.join(
    ROBOTAC_BASE_DIR,
    "static",
    "robotac_docs",
    "national",
    "official_monitor"
)
ROBOTAC_STATE_PATH = os.path.join(ROBOTAC_DOC_DIR, "resources_state.json")
ROBOTAC_FASTGPT_SYNC_STATE_PATH = os.path.join(ROBOTAC_DOC_DIR, "fastgpt_sync_state.json")
ROBOTAC_FASTGPT_DATASET_ID = os.environ.get(
    "FASTGPT_ROBOTAC_DATASET_ID",
    "69ba94c8799878a22bcaf349"
)
ROBOTAC_FASTGPT_TIMEOUT = 120
ROBOTAC_SCHEDULER_STATE = {
    "started": False,
    "lock": threading.Lock(),
    "thread": None
}

ROBOMASTER_AGENT_CONFIG = get_competition_agent_by_key("robomaster") or {}
ROBOMASTER_SITE_URLS = ROBOMASTER_AGENT_CONFIG.get("site_urls", {})
ROBOMASTER_HOME_URL = ROBOMASTER_SITE_URLS.get("home_url", "https://www.robomaster.com/zh-CN")
ROBOMASTER_NEWS_URL = ROBOMASTER_SITE_URLS.get("news_url", "https://bbs.robomaster.com/wiki/20204847")
ROBOMASTER_REQUEST_TIMEOUT = 12
ROBOMASTER_VERIFY_SSL = True
ROBOMASTER_BASE_DIR = ROBOCON_BASE_DIR
ROBOMASTER_DOC_DIR = os.path.join(
    ROBOMASTER_BASE_DIR,
    "static",
    "robomaster_docs",
    "official_monitor"
)
ROBOMASTER_STATE_PATH = os.path.join(ROBOMASTER_DOC_DIR, "resources_state.json")
ROBOMASTER_FASTGPT_SYNC_STATE_PATH = os.path.join(ROBOMASTER_DOC_DIR, "fastgpt_sync_state.json")
ROBOMASTER_FASTGPT_DATASET_ID = os.environ.get("FASTGPT_ROBOMASTER_DATASET_ID", "").strip()
ROBOMASTER_FASTGPT_TIMEOUT = 120
ROBOMASTER_API_BASE_URL = "https://bbs.robomaster.com/developers-server"
ROBOMASTER_TRACK_DEFINITIONS = {
    "rmuc": {
        "key": "rmuc",
        "label": "RMUC",
        "posts_id": "809871",
        "page_url": "https://bbs.robomaster.com/wiki/20204847/809871?source=7",
        "fastgpt_folder_id": "6a3293a35339ba6c28181a9b",
        "fastgpt_dataset_id": "6a32ae84e2eeb153edc04c5d",
        "fastgpt_dataset_name": "RMUC比赛规则知识库",
        "description": "Robomaster RMUC 官方规则资料"
    },
    "rmul": {
        "key": "rmul",
        "label": "RMUL",
        "posts_id": "809872",
        "page_url": "https://bbs.robomaster.com/wiki/20204847/809872?source=7",
        "fastgpt_folder_id": "6a3293ad5339ba6c28181bfc",
        "fastgpt_dataset_id": "6a32af39e2eeb153edc05cf1",
        "fastgpt_dataset_name": "RMUL比赛规则知识库",
        "description": "Robomaster RMUL 官方规则资料"
    },
    "rmua": {
        "key": "rmua",
        "label": "RMUA",
        "posts_id": "809873",
        "page_url": "https://bbs.robomaster.com/wiki/20204847/809873?source=7",
        "fastgpt_folder_id": "6a3293b55339ba6c28181dd8",
        "fastgpt_dataset_id": "6a32af48e2eeb153edc0668c",
        "fastgpt_dataset_name": "RMUA比赛规则知识库",
        "description": "Robomaster RMUA 官方规则资料"
    },
    "rmu": {
        "key": "rmu",
        "label": "RMU",
        "posts_id": "811363",
        "page_url": "https://bbs.robomaster.com/wiki/20204847/811363?source=7",
        "fastgpt_folder_id": "6a3293bc5339ba6c28181e9a",
        "fastgpt_dataset_id": "6a32af49e2eeb153edc06786",
        "fastgpt_dataset_name": "RMU比赛规则知识库",
        "description": "Robomaster RMU 官方规则资料"
    }
}
ROBOMASTER_ATTACHMENT_ALLOW_KEYWORDS = (
    "规则", "rule", "手册", "manual", "图册", "场地", "附录", "appendix",
    "faq", "答疑", "公告", "裁判", "判罚"
)
ROBOMASTER_ATTACHMENT_BLOCK_KEYWORDS = (
    "报名", "报名表", "回执", "名单", "成绩", "签到", "授权书", "盖章", "申请表"
)
ROBOMASTER_CATEGORY_LABELS = {
    "rule_core": "核心规则",
    "figure_core": "图册",
    "faq_core": "FAQ",
    "important_notice": "重要通知",
    "general_notice": "通知"
}
ROBOMASTER_SCHEDULER_STATE = {
    "started": False,
    "lock": threading.Lock(),
    "thread": None
}


agents_kd = list_kd_agents()
ROBOCON_MAIN_RESOURCES = get_competition_agent_snapshot("robocon_main")
ROBOCON_BIONIC_RESOURCES_SNAPSHOT = get_competition_agent_snapshot("robocon_bionic_legged")
ROBOTAC_RESOURCES_SNAPSHOT = get_competition_agent_snapshot("robotac")
ROBOMASTER_RESOURCES_SNAPSHOT = get_competition_agent_snapshot("robomaster")

ROBOTAC_CACHE = {
    "data": None,
    "fetched_at": 0.0,
    "lock": threading.Lock()
}
FASTGPT_SESSION = None
FASTGPT_SESSION_LOCK = threading.Lock()


def require_login():
    if "username" not in session:
        flash("请先登录")
        return redirect(url_for("login"))
    return None


def require_teacher_json():
    if "username" not in session:
        return jsonify({"success": False, "error": "请先登录"}), 401
    if session.get("role") != "teacher":
        return jsonify({"success": False, "error": "仅教师可执行该操作"}), 403
    return None


def get_fastgpt_http_session():
    global FASTGPT_SESSION
    if FASTGPT_SESSION is not None:
        return FASTGPT_SESSION

    with FASTGPT_SESSION_LOCK:
        if FASTGPT_SESSION is not None:
            return FASTGPT_SESSION
        session_obj = requests.Session()
        session_obj.trust_env = False
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=frozenset(["GET", "POST", "PUT", "DELETE"])
        )
        adapter = HTTPAdapter(max_retries=retry)
        session_obj.mount("http://", adapter)
        session_obj.mount("https://", adapter)
        FASTGPT_SESSION = session_obj
    return FASTGPT_SESSION


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


def extract_sync_timestamp_from_text(text):
    match = re.search(r"([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})", text or "")
    return match.group(1) if match else ""


def format_file_mtime(file_path):
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ""


def apply_resource_sync_metadata(resources, *, state_path=None, default_synced_at=""):
    resource_copy = copy.deepcopy(resources or {})
    fallback_synced_at = default_synced_at or format_file_mtime(state_path)

    for section in resource_copy.values():
        if not isinstance(section, dict):
            continue
        section["synced_at"] = (
            section.get("synced_at")
            or extract_sync_timestamp_from_text(section.get("update_note", ""))
            or fallback_synced_at
            or section.get("updated_at", "")
        )

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


def requests_get_robotac(url):
    kwargs = {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        },
        "timeout": ROBOTAC_REQUEST_TIMEOUT
    }
    if (
        url.startswith("https://www.robotac.cn/")
        or url.startswith("http://www.robotac.cn/")
        or url.startswith("https://robotac.cn/")
        or url.startswith("http://robotac.cn/")
    ) and not ROBOTAC_VERIFY_SSL:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        kwargs["verify"] = False
    return requests.get(url, **kwargs)


def requests_get_robomaster(url):
    kwargs = {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        },
        "timeout": ROBOMASTER_REQUEST_TIMEOUT
    }
    if not ROBOMASTER_VERIFY_SSL:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        kwargs["verify"] = False
    return requests.get(url, **kwargs)


def requests_post_robomaster_api(path, payload=None, referer=""):
    kwargs = {
        "headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
            ,
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://bbs.robomaster.com",
            "Referer": referer or ROBOMASTER_NEWS_URL
        },
        "timeout": ROBOMASTER_REQUEST_TIMEOUT
    }
    if not ROBOMASTER_VERIFY_SSL:
        requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
        kwargs["verify"] = False
    return requests.post(
        f"{ROBOMASTER_API_BASE_URL}{path}",
        json=payload if payload is not None else {},
        **kwargs
    )


def is_relevant_robocon_title(title):
    text = normalize_text(title)
    if not text:
        return False

    return all(keyword in text for keyword in ROBOCON_REQUIRED_TITLE_KEYWORDS)


def contains_any_robocon_track_keyword(text, keywords):
    return title_contains_any_keyword(text, keywords)


def is_relevant_robocon_bionic_title(title):
    text = normalize_text(title)
    if not is_relevant_robocon_title(text):
        return False
    return contains_any_robocon_track_keyword(text, ROBOCON_BIONIC_TRACK_KEYWORDS)


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


def classify_robocon_bionic_entry(title):
    if not is_relevant_robocon_bionic_title(title):
        return None
    return classify_robocon_entry(title)


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


def ensure_robocon_bionic_storage():
    os.makedirs(ROBOCON_BIONIC_DOC_DIR, exist_ok=True)


def ensure_robotac_storage():
    os.makedirs(ROBOTAC_DOC_DIR, exist_ok=True)


def ensure_robomaster_storage():
    os.makedirs(ROBOMASTER_DOC_DIR, exist_ok=True)


def ensure_robomaster_track_storage(track_key):
    ensure_robomaster_storage()
    os.makedirs(os.path.join(ROBOMASTER_DOC_DIR, track_key), exist_ok=True)


def load_robomaster_resources_state():
    if not os.path.exists(ROBOMASTER_STATE_PATH):
        return None
    try:
        with open(ROBOMASTER_STATE_PATH, "r", encoding="utf-8") as file_obj:
            return apply_resource_sync_metadata(json.load(file_obj), state_path=ROBOMASTER_STATE_PATH)
    except Exception as exc:
        print(f"读取 Robomaster 本地缓存失败: {exc}")
        return None


def save_robomaster_resources_state(resources):
    ensure_robomaster_storage()
    with open(ROBOMASTER_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(resources, file_obj, ensure_ascii=False, indent=2)


def load_robomaster_fastgpt_sync_state():
    if not os.path.exists(ROBOMASTER_FASTGPT_SYNC_STATE_PATH):
        return {"dataset_id": ROBOMASTER_FASTGPT_DATASET_ID, "items": []}
    try:
        with open(ROBOMASTER_FASTGPT_SYNC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            if not isinstance(data, dict):
                return {"dataset_id": ROBOMASTER_FASTGPT_DATASET_ID, "items": []}
            data.setdefault("dataset_id", ROBOMASTER_FASTGPT_DATASET_ID)
            data.setdefault("items", [])
            return data
    except Exception as exc:
        print(f"读取 Robomaster FastGPT 同步状态失败: {exc}")
        return {"dataset_id": ROBOMASTER_FASTGPT_DATASET_ID, "items": []}


def save_robomaster_fastgpt_sync_state(state):
    ensure_robomaster_storage()
    with open(ROBOMASTER_FASTGPT_SYNC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(state, file_obj, ensure_ascii=False, indent=2)


def load_robotac_resources_state():
    if not os.path.exists(ROBOTAC_STATE_PATH):
        return None
    try:
        with open(ROBOTAC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            return apply_resource_sync_metadata(json.load(file_obj), state_path=ROBOTAC_STATE_PATH)
    except Exception as exc:
        print(f"读取 Robotac 本地缓存失败: {exc}")
        return None


def save_robotac_resources_state(resources):
    ensure_robotac_storage()
    with open(ROBOTAC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(resources, file_obj, ensure_ascii=False, indent=2)


def load_robotac_fastgpt_sync_state():
    if not os.path.exists(ROBOTAC_FASTGPT_SYNC_STATE_PATH):
        return {"dataset_id": ROBOTAC_FASTGPT_DATASET_ID, "items": []}
    try:
        with open(ROBOTAC_FASTGPT_SYNC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            if not isinstance(data, dict):
                return {"dataset_id": ROBOTAC_FASTGPT_DATASET_ID, "items": []}
            data.setdefault("dataset_id", ROBOTAC_FASTGPT_DATASET_ID)
            data.setdefault("items", [])
            return data
    except Exception as exc:
        print(f"读取 Robotac FastGPT 同步状态失败: {exc}")
        return {"dataset_id": ROBOTAC_FASTGPT_DATASET_ID, "items": []}


def save_robotac_fastgpt_sync_state(state):
    ensure_robotac_storage()
    with open(ROBOTAC_FASTGPT_SYNC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(state, file_obj, ensure_ascii=False, indent=2)


def normalize_robotac_filename(filename):
    return normalize_text((filename or "").strip())


def download_robotac_file(file_url, file_name):
    ensure_robotac_storage()
    response = requests_get_robotac(file_url)
    response.raise_for_status()
    file_bytes = response.content
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    parsed_path = urlparse(file_url).path
    suffix = os.path.splitext(parsed_path)[1] or os.path.splitext(file_name)[1] or ".pdf"
    local_filename = f"{sanitize_filename(os.path.splitext(file_name)[0])}_{file_hash[:12]}{suffix}"
    local_path = os.path.join(ROBOTAC_DOC_DIR, local_filename)
    if not os.path.exists(local_path):
        with open(local_path, "wb") as file_obj:
            file_obj.write(file_bytes)
    return {
        "file_hash": file_hash,
        "local_path": local_path,
        "local_url": relative_static_path(local_path)
    }


def normalize_robomaster_filename(filename):
    return normalize_text((filename or "").strip())


def infer_robomaster_doc_category(title):
    text = normalize_text(title)
    if not text:
        return "general_notice"
    lowered = text.lower()
    if "faq" in lowered or "答疑" in text or "qa" in lowered:
        return "faq_core"
    if "图册" in text or "场地" in text or "附录" in text or "appendix" in lowered:
        return "figure_core"
    if "规则" in text or "rule" in lowered or "手册" in text or "manual" in lowered:
        return "rule_core"
    if "公告" in text or "通知" in text or "赛程" in text:
        return "important_notice"
    return "general_notice"


def infer_robomaster_doc_type(title, category=None):
    if category in ROBOMASTER_CATEGORY_LABELS:
        return ROBOMASTER_CATEGORY_LABELS[category]
    if "图册" in title or "场地" in title or "附录" in title:
        return "图册"
    if "FAQ" in title or "答疑" in title:
        return "FAQ"
    if "规则" in title or "手册" in title:
        return "规则"
    if "公告" in title or "通知" in title:
        return "通知"
    return "官网资料"


def should_download_robomaster_doc(category):
    return True


def is_downloadable_robomaster_attachment(file_name):
    normalized_name = normalize_text(file_name)
    if not normalized_name:
        return False
    return True


def infer_robomaster_file_extension(file_name, file_url=""):
    normalized_name = normalize_text(file_name)
    parsed_path = urlparse(file_url or "").path
    suffix = os.path.splitext(normalized_name)[1] or os.path.splitext(parsed_path)[1]
    return (suffix or "").lower()


def infer_robomaster_doc_type_from_file(file_name, file_url="", category=None):
    extension = infer_robomaster_file_extension(file_name, file_url)
    if extension in {".pdf"}:
        return infer_robomaster_doc_type(file_name, category)
    if extension in {".doc", ".docx"}:
        return "文档"
    if extension in {".xls", ".xlsx", ".csv"}:
        return "表格"
    if extension in {".ppt", ".pptx"}:
        return "演示文稿"
    if extension in {".zip", ".rar", ".7z"}:
        return "压缩包"
    if extension in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg"}:
        return "图片"
    return infer_robomaster_doc_type(file_name, category)


def download_robomaster_file(file_url, file_name, track_key):
    ensure_robomaster_track_storage(track_key)
    response = requests_get_robomaster(file_url)
    response.raise_for_status()
    file_bytes = response.content
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    parsed_path = urlparse(file_url).path
    suffix = os.path.splitext(parsed_path)[1] or os.path.splitext(file_name)[1] or ".pdf"
    local_filename = f"{sanitize_filename(os.path.splitext(file_name)[0])}_{file_hash[:12]}{suffix}"
    local_path = os.path.join(ROBOMASTER_DOC_DIR, track_key, local_filename)
    if not os.path.exists(local_path):
        with open(local_path, "wb") as file_obj:
            file_obj.write(file_bytes)
    return {
        "file_hash": file_hash,
        "local_path": local_path,
        "local_url": relative_static_path(local_path)
    }


def save_robomaster_track_manifest(track_key, docs):
    ensure_robomaster_track_storage(track_key)
    manifest_path = os.path.join(ROBOMASTER_DOC_DIR, track_key, "manifest.json")
    manifest_payload = {
        "track_key": track_key,
        "track_label": ROBOMASTER_TRACK_DEFINITIONS.get(track_key, {}).get("label", track_key),
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "doc_count": len(docs or []),
        "docs": docs or []
    }
    with open(manifest_path, "w", encoding="utf-8") as file_obj:
        json.dump(manifest_payload, file_obj, ensure_ascii=False, indent=2)


def fetch_robomaster_post_detail(track_config):
    response = requests_post_robomaster_api(
        f"/rest/posts/info/{track_config['posts_id']}",
        payload={},
        referer=track_config.get("page_url", "")
    )
    response.raise_for_status()
    result = response.json()
    if result.get("code") not in (0, 200) or not result.get("data"):
        raise RuntimeError(result.get("message", f"获取 Robomaster 帖子详情失败: {track_config['posts_id']}"))
    return result["data"]


def extract_robomaster_attachment_links_from_html(raw_html):
    attachments = []
    seen_urls = set()
    anchor_pattern = re.compile(r'<a\b[^>]*\bhref=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    for match in anchor_pattern.finditer(raw_html or ""):
        full_tag = match.group(0)
        file_url = normalize_text(match.group(1))
        if not file_url or file_url in seen_urls:
            continue

        is_attachment = (
            'data-w-e-type="attachment"' in full_tag
            or "data-w-e-type='attachment'" in full_tag
            or any(file_url.lower().endswith(ext) for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar", ".7z"))
        )
        if not is_attachment:
            continue

        file_name = ""
        name_match = re.search(r'data-file-name=["\']([^"\']+)["\']', full_tag, flags=re.IGNORECASE)
        if name_match:
            file_name = normalize_text(unquote(name_match.group(1)))
        if not file_name:
            file_name = normalize_text(strip_html(match.group(2)))
        if not file_name:
            file_name = os.path.basename(unquote(urlparse(file_url).path)) or "attachment"

        item = {
            "file_name": file_name,
            "file_url": file_url
        }
        md5_match = re.search(r'data-file-md5=["\']([^"\']+)["\']', full_tag, flags=re.IGNORECASE)
        len_match = re.search(r'data-file-len=["\']([^"\']+)["\']', full_tag, flags=re.IGNORECASE)
        if md5_match:
            item["file_md5"] = md5_match.group(1)
        if len_match:
            try:
                item["file_len"] = int(len_match.group(1))
            except ValueError:
                pass
        attachments.append(item)
        seen_urls.add(file_url)
    return attachments


def extract_robomaster_post_attachments(detail):
    attachments = []
    seen_urls = set()

    def append_attachment(item):
        if not isinstance(item, dict):
            return
        file_url = normalize_text(item.get("src") or item.get("url") or item.get("href"))
        if not file_url or file_url in seen_urls:
            return
        file_name = normalize_robomaster_filename(
            item.get("name")
            or item.get("fileName")
            or os.path.basename(unquote(urlparse(file_url).path))
        )
        if not file_name:
            return
        attachment = {
            "file_name": file_name,
            "file_url": file_url
        }
        if item.get("md5"):
            attachment["file_md5"] = item.get("md5")
        if item.get("len"):
            attachment["file_len"] = item.get("len")
        attachments.append(attachment)
        seen_urls.add(file_url)

    for item in detail.get("fileItems") or []:
        append_attachment(item)
    for item in detail.get("attachments") or []:
        append_attachment(item)
    for item in extract_robomaster_attachment_links_from_html(detail.get("htmlContent") or ""):
        append_attachment(item)

    return attachments


def extract_robomaster_attachment_links(main_node, page_url, raw_html=""):
    attachments = []
    seen_urls = set()
    search_roots = [main_node]
    if hasattr(main_node, "select_one"):
        attach_box = main_node.select_one(".attachBox")
        if attach_box:
            search_roots.insert(0, attach_box)

    for search_root in search_roots:
        if not search_root:
            continue
        for anchor in search_root.select("a[href]"):
            href = normalize_text(anchor.get("href"))
            if not href:
                continue
            full_url = urljoin(page_url, href)
            parsed_path = urlparse(full_url).path.lower()
            anchor_text = normalize_text(anchor.get_text(" ", strip=True))
            title_text = normalize_text(anchor.get("title"))
            is_attachment = any(
                parsed_path.endswith(ext)
                for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".rar")
            )
            looks_download = (
                "download" in full_url.lower()
                or "/attachment/" in parsed_path
                or "/attachments/" in parsed_path
                or "下载" in anchor_text
                or "附件" in anchor_text
            )
            if not is_attachment and not looks_download:
                continue
            if full_url in seen_urls:
                continue

            file_name = title_text or anchor_text or os.path.basename(unquote(urlparse(full_url).path)) or "attachment"
            attachments.append({"file_name": file_name, "file_url": full_url})
            seen_urls.add(full_url)

    url_pattern = re.compile(r'https?://[^\\s"\'<>]+?\.(?:pdf|doc|docx|xls|xlsx|ppt|pptx|zip|rar)(?:\?[^\\s"\'<>]*)?', re.IGNORECASE)
    for match in url_pattern.findall(raw_html or ""):
        full_url = match.strip()
        if full_url in seen_urls:
            continue
        file_name = os.path.basename(unquote(urlparse(full_url).path)) or "attachment"
        attachments.append({"file_name": file_name, "file_url": full_url})
        seen_urls.add(full_url)

    return attachments


def extract_robomaster_semantic_tags(filename, title="", doc_type="", track_key=""):
    base_name = os.path.splitext(filename or "")[0]
    base_name = re.sub(r'_[0-9a-f]{8,}$', '', base_name, flags=re.IGNORECASE)
    base_name = normalize_text(base_name).replace("“", "").replace("”", "").replace('"', "")
    merged_text = " ".join(
        part for part in (
            ROBOMASTER_TRACK_DEFINITIONS.get(track_key, {}).get("label", ""),
            base_name,
            normalize_text(title),
            normalize_text(doc_type)
        ) if part
    )

    tags = ["ROBOMASTER"]
    track_label = ROBOMASTER_TRACK_DEFINITIONS.get(track_key, {}).get("label")
    if track_label:
        tags.append(track_label)

    for label in ("规则", "图册", "FAQ", "答疑", "公告", "附录", "手册", "裁判"):
        if label in merged_text and label not in tags:
            tags.append(label)

    version_text, version_parts = parse_robocon_version(merged_text)
    if version_text and version_text not in tags:
        tags.append(version_text)

    family_parts = [track_label] if track_label else []
    for label in ("规则", "图册", "FAQ", "答疑", "公告", "附录", "手册"):
        if label in merged_text:
            family_parts.append(label)
            break

    family_key = "|".join(part for part in family_parts if part) or (base_name or track_key or "未分类")

    return {
        "base_name": base_name,
        "tags": tags,
        "family_key": family_key,
        "version_text": version_text,
        "version_parts": version_parts
    }


def extract_robomaster_page_docs(track_key, track_config):
    detail = fetch_robomaster_post_detail(track_config)
    page_title = normalize_text(detail.get("title")) or track_config["label"]
    html = detail.get("htmlContent") or ""
    markdown = detail.get("markdownContent") or ""
    page_text = normalize_text(strip_html(html or markdown))
    publish_date = (
        parse_date_value(detail.get("updateAt"))
        or parse_date_value(detail.get("createAt"))
        or parse_date_value(page_text)
        or datetime.now().strftime("%Y-%m-%d")
    )
    attachments = extract_robomaster_post_attachments(detail)

    docs = []
    seen_file_urls = set()
    for attachment in attachments:
        file_name = normalize_robomaster_filename(attachment["file_name"])
        file_url = attachment["file_url"]
        if file_url in seen_file_urls:
            continue
        seen_file_urls.add(file_url)
        if not is_downloadable_robomaster_attachment(file_name):
            continue

        category = infer_robomaster_doc_category(file_name or page_title)
        doc = {
            "title": file_name or page_title,
            "type": infer_robomaster_doc_type_from_file(file_name or page_title, file_url, category),
            "date": publish_date,
            "url": file_url,
            "preview_url": file_url,
            "source": f"ROBOMASTER {track_config['label']} 官方规则页",
            "category": category,
            "track_key": track_key,
            "download_policy": "download" if should_download_robomaster_doc(category) else "metadata_only",
            "metadata_source": f"robomaster_{track_key}_official_monitor",
            "official_page_url": track_config["page_url"],
            "page_title": page_title,
            "file_url": file_url,
            "file_name": file_name or page_title,
            "file_ext": infer_robomaster_file_extension(file_name or page_title, file_url),
            "file_md5": attachment.get("file_md5", ""),
            "file_len": attachment.get("file_len", 0)
        }
        if doc["download_policy"] == "download":
            try:
                download_result = download_robomaster_file(
                    file_url,
                    file_name or page_title,
                    track_key
                )
                doc["preview_url"] = download_result["local_url"] or attachment["file_url"]
                doc["source"] = f"{doc['source']} / 本地副本"
                doc["downloaded_attachment"] = file_name or page_title
                doc["file_hash"] = download_result["file_hash"]
                doc["local_relative_path"] = (download_result["local_url"] or "").lstrip("/")
            except Exception as exc:
                print(f"下载 Robomaster 附件失败: {attachment['file_url']} -> {exc}")
        docs.append(doc)

    if not docs:
        category = infer_robomaster_doc_category(page_title)
        docs.append({
            "title": page_title,
            "type": infer_robomaster_doc_type(page_title, category),
            "date": publish_date,
            "url": track_config["page_url"],
            "preview_url": track_config["page_url"],
            "source": f"ROBOMASTER {track_config['label']} 官方规则页",
            "category": category,
            "track_key": track_key,
            "download_policy": "metadata_only",
            "metadata_source": f"robomaster_{track_key}_official_monitor",
            "summary": page_text[:240] if page_text else ""
        })

    docs.sort(key=lambda item: (item.get("date") or "", item.get("title") or ""), reverse=True)
    save_robomaster_track_manifest(track_key, docs)
    return docs


def extract_robotac_attachment_links(main_node, page_url):
    attach_box = None
    if hasattr(main_node, "select_one"):
        attach_box = main_node.select_one(".attachBox")
    search_root = attach_box or main_node

    attachments = []
    seen_urls = set()
    for anchor in search_root.select("a[href]"):
        href = normalize_text(anchor.get("href"))
        if not href:
            continue
        full_url = urljoin(page_url, href)
        parsed_path = urlparse(full_url).path.lower()
        is_attachment = any(
            parsed_path.endswith(ext)
            for ext in (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".rar")
        )
        if not is_attachment and not any(token in parsed_path for token in ("/upload/", "/uploads/", "/file/", "/_upload/")):
            continue
        if full_url in seen_urls:
            continue

        anchor_text = normalize_text(anchor.get_text(" ", strip=True))
        title_text = normalize_text(anchor.get("title"))
        file_name = title_text or anchor_text or os.path.basename(unquote(urlparse(full_url).path)) or "attachment"
        attachments.append({"file_name": file_name, "file_url": full_url})
        seen_urls.add(full_url)
    return attachments


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


def download_robocon_bionic_file(file_url, file_name):
    ensure_robocon_bionic_storage()
    response = requests_get_robocon(file_url)
    response.raise_for_status()
    file_bytes = response.content
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    parsed_path = urlparse(file_url).path
    suffix = os.path.splitext(parsed_path)[1] or os.path.splitext(file_name)[1] or ".pdf"
    local_filename = f"{sanitize_filename(os.path.splitext(file_name)[0])}_{file_hash[:12]}{suffix}"
    local_path = os.path.join(ROBOCON_BIONIC_DOC_DIR, local_filename)
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


def extract_robocon_bionic_news_entries(html):
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
        detail_url = urljoin(ROBOCON_BIONIC_HOME_URL, href)
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


def is_downloadable_robocon_bionic_attachment(file_name):
    normalized_name = normalize_text(file_name)
    if not normalized_name:
        return False
    if title_contains_any_keyword(normalized_name, ROBOCON_ATTACHMENT_BLOCK_KEYWORDS):
        return False
    if not title_contains_any_keyword(normalized_name, ROBOCON_BIONIC_TRACK_KEYWORDS):
        return False
    return title_contains_any_keyword(normalized_name, ROBOCON_BIONIC_ATTACHMENT_ALLOW_KEYWORDS)


def infer_robocon_bionic_doc_type(file_name, fallback_title="", category=None):
    normalized_name = normalize_text(file_name or fallback_title)
    if "图册" in normalized_name:
        return "图册"
    if "FAQ" in normalized_name or "答疑" in normalized_name:
        return "FAQ"
    if "规则" in normalized_name:
        return "核心规则"
    return infer_robocon_doc_type(fallback_title or normalized_name, category)


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


def fetch_robocon_bionic_detail_resources(entry):
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
    filtered_attachments = [
        attachment for attachment in attachments
        if is_downloadable_robocon_bionic_attachment(attachment["file_name"])
    ]
    docs = []

    for attachment in filtered_attachments:
        try:
            download_result = download_robocon_bionic_file(
                attachment["file_url"],
                attachment["file_name"]
            )
            docs.append({
                "title": normalize_text(attachment["file_name"]) or title,
                "type": infer_robocon_bionic_doc_type(
                    attachment["file_name"],
                    fallback_title=title,
                    category=entry.get("category")
                ),
                "date": publish_date,
                "url": attachment["file_url"],
                "preview_url": download_result["local_url"] or attachment["file_url"],
                "source": "ROBOCON 官网赛事动态 / 本地副本",
                "category": entry.get("category"),
                "download_policy": "download",
                "metadata_source": "robocon_bionic_legged_official_monitor",
                "downloaded_attachment": attachment["file_name"]
            })
        except Exception as exc:
            print(f"下载 Robocon 仿生足式附件失败: {attachment['file_url']} -> {exc}")

    if not docs and contains_any_robocon_track_keyword(title, ROBOCON_BIONIC_TRACK_KEYWORDS):
        print(f"Robocon 仿生足式条目未找到符合规则的附件: {title}")

    return docs


def build_robocon_dynamic_resources(docs, synced_at):
    resources = get_robocon_main_resources_snapshot()
    if docs:
        resources["national"]["docs"] = docs
        resources["national"]["updated_at"] = docs[0]["date"]
        resources["national"]["synced_at"] = synced_at
        resources["national"]["update_note"] = (
            f"后台定时任务已在 {synced_at} 完成最近一次官网同步，"
            "当前仅对规则、图册、FAQ 等规则资产下载附件，通知类内容只记录详情。"
        )
    return resources


def build_robocon_bionic_dynamic_resources(docs, synced_at):
    resources = get_robocon_bionic_resources_snapshot()
    resources["national"]["synced_at"] = synced_at
    resources["national"]["update_note"] = (
        f"后台定时任务已在 {synced_at} 完成最近一次官网同步，"
        "当前仅抓取标题或附件明确包含“仿生足式机器人/足式比赛”的规则、图册、FAQ 资料。"
    )
    if docs:
        resources["national"]["docs"] = docs
        resources["national"]["updated_at"] = docs[0]["date"]
    return resources


def save_robocon_resources_state(resources):
    ensure_robocon_storage()
    with open(ROBOCON_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(resources, file_obj, ensure_ascii=False, indent=2)


def save_robocon_bionic_resources_state(resources):
    ensure_robocon_bionic_storage()
    with open(ROBOCON_BIONIC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(resources, file_obj, ensure_ascii=False, indent=2)


def load_robocon_resources_state():
    if not os.path.exists(ROBOCON_STATE_PATH):
        return None
    try:
        with open(ROBOCON_STATE_PATH, "r", encoding="utf-8") as file_obj:
            return apply_resource_sync_metadata(json.load(file_obj), state_path=ROBOCON_STATE_PATH)
    except Exception as exc:
        print(f"读取 Robocon 本地缓存失败: {exc}")
        return None


def load_robocon_bionic_resources_state():
    if not os.path.exists(ROBOCON_BIONIC_STATE_PATH):
        return None
    try:
        with open(ROBOCON_BIONIC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            return apply_resource_sync_metadata(json.load(file_obj), state_path=ROBOCON_BIONIC_STATE_PATH)
    except Exception as exc:
        print(f"读取 Robocon 仿生足式本地缓存失败: {exc}")
        return None


def load_robocon_fastgpt_sync_state():
    if not os.path.exists(ROBOCON_FASTGPT_SYNC_STATE_PATH):
        return {"dataset_id": ROBOCON_FASTGPT_DATASET_ID, "items": []}
    try:
        with open(ROBOCON_FASTGPT_SYNC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            if not isinstance(data, dict):
                return {"dataset_id": ROBOCON_FASTGPT_DATASET_ID, "items": []}
            data.setdefault("dataset_id", ROBOCON_FASTGPT_DATASET_ID)
            data.setdefault("items", [])
            return data
    except Exception as exc:
        print(f"读取 Robocon FastGPT 同步状态失败: {exc}")
        return {"dataset_id": ROBOCON_FASTGPT_DATASET_ID, "items": []}


def load_robocon_bionic_fastgpt_sync_state():
    if not os.path.exists(ROBOCON_BIONIC_FASTGPT_SYNC_STATE_PATH):
        return {"dataset_id": ROBOCON_BIONIC_FASTGPT_DATASET_ID, "items": []}
    try:
        with open(ROBOCON_BIONIC_FASTGPT_SYNC_STATE_PATH, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
            if not isinstance(data, dict):
                return {"dataset_id": ROBOCON_BIONIC_FASTGPT_DATASET_ID, "items": []}
            data.setdefault("dataset_id", ROBOCON_BIONIC_FASTGPT_DATASET_ID)
            data.setdefault("items", [])
            return data
    except Exception as exc:
        print(f"读取 Robocon 仿生足式 FastGPT 同步状态失败: {exc}")
        return {"dataset_id": ROBOCON_BIONIC_FASTGPT_DATASET_ID, "items": []}


def save_robocon_fastgpt_sync_state(state):
    ensure_robocon_storage()
    with open(ROBOCON_FASTGPT_SYNC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(state, file_obj, ensure_ascii=False, indent=2)


def save_robocon_bionic_fastgpt_sync_state(state):
    ensure_robocon_bionic_storage()
    with open(ROBOCON_BIONIC_FASTGPT_SYNC_STATE_PATH, "w", encoding="utf-8") as file_obj:
        json.dump(state, file_obj, ensure_ascii=False, indent=2)


def get_robocon_fastgpt_api_key():
    api_key = os.environ.get("FASTGPT_API_KEY", "").strip()
    if api_key:
        return api_key
    try:
        from config_fastgpt import FASTGPT_API_KEY as fallback_api_key
        return (fallback_api_key or "").strip()
    except Exception:
        return ""


def get_robocon_fastgpt_headers():
    return {
        "Authorization": f"Bearer {get_robocon_fastgpt_api_key()}",
        "Content-Type": "application/json"
    }


def get_robocon_fastgpt_upload_headers():
    return {
        "Authorization": f"Bearer {get_robocon_fastgpt_api_key()}"
    }


def normalize_robocon_filename(filename):
    return normalize_text((filename or "").strip())


def parse_robocon_version(value):
    text = value or ""
    match = re.search(r'V\.?\s*([0-9]+(?:\.[0-9]+)*)', text, flags=re.IGNORECASE)
    if not match:
        return None, ()

    version_text = match.group(0).upper().replace(" ", "")
    parts = tuple(int(part) for part in match.group(1).split('.'))
    return version_text, parts


def extract_robocon_semantic_tags(filename):
    base_name = os.path.splitext(filename or "")[0]
    base_name = re.sub(r'_[0-9a-f]{8,}$', '', base_name, flags=re.IGNORECASE)
    if "ROBOCON" in base_name:
        base_name = base_name.split("ROBOCON", 1)[1]
    base_name = normalize_text(base_name)
    base_name = base_name.replace("“", "").replace("”", "").replace('"', "")

    tags = []
    for label in ("武林探秘", "沙排之王", "仿生足式机器人", "仿生足式", "足式机器人", "足式比赛", "竞技赛", "技能挑战赛", "规则", "图册", "FAQ", "答疑"):
        if label in base_name and label not in tags:
            tags.append(label)

    version_text, version_parts = parse_robocon_version(base_name)
    if version_text:
        tags.append(version_text)

    if not tags:
        tags.append(base_name or "未分类")

    family_tags = [tag for tag in tags if not tag.upper().startswith("V")]
    family_key = "|".join(family_tags) if family_tags else (base_name or "未分类")

    return {
        "base_name": base_name,
        "tags": tags,
        "family_key": family_key,
        "version_text": version_text,
        "version_parts": version_parts
    }


def parse_robocon_date_key(date_text):
    try:
        return datetime.strptime(date_text or "", "%Y-%m-%d")
    except Exception:
        return datetime.min


def detect_robocon_content_type(filename):
    content_type, _ = mimetypes.guess_type(filename or "")
    return content_type or "application/octet-stream"


def extract_robotac_semantic_tags(filename, title="", doc_type=""):
    base_name = os.path.splitext(filename or "")[0]
    base_name = re.sub(r'_[0-9a-f]{8,}$', '', base_name, flags=re.IGNORECASE)
    base_name = normalize_text(base_name)
    base_name = base_name.replace("“", "").replace("”", "").replace('"', "")

    title_text = normalize_text(title or "")
    doc_type_text = normalize_text(doc_type or "")
    merged_text = " ".join(part for part in (base_name, title_text, doc_type_text) if part)

    track_labels = [
        "AIROBOTIC创新挑战赛",
        "数字仿真挑战赛",
        "侦察任务挑战赛",
        "能量球灌篮挑战赛",
        "足式机器人挑战赛",
        "三维数字设计赛",
        "竞技机器人方案设计赛",
        "人形功夫搏击赛（大型组）",
        "人形功夫搏击赛（小型组）",
        "人形功夫搏击赛大型组",
        "人形功夫搏击赛小型组",
        "深蓝使命",
        "长城烽火",
        "章程"
    ]

    tags = ["ROBOTAC"]
    family_parts = []
    for label in track_labels:
        if label in merged_text and label not in tags:
            tags.append(label)
            family_parts.append(label)

    for label in ("对抗赛", "挑战赛", "设计赛", "创新挑战赛", "数字仿真挑战赛", "规则", "章程"):
        if label in merged_text and label not in tags:
            tags.append(label)

    version_text, version_parts = parse_robocon_version(merged_text)
    if version_text and version_text not in tags:
        tags.append(version_text)

    if not family_parts:
        normalized_base = base_name
        if "ROBOTAC" in normalized_base:
            normalized_base = normalized_base.split("ROBOTAC", 1)[1]
        normalized_base = normalize_text(normalized_base).strip("-_ ")
        family_parts.append(normalized_base or doc_type_text or "未分类")

    family_key = "|".join(part for part in family_parts if part)

    return {
        "base_name": base_name,
        "tags": tags,
        "family_key": family_key,
        "version_text": version_text,
        "version_parts": version_parts
    }


def should_upload_robocon_rule_pdf_as_qa(candidate):
    """规则类 PDF 除了分块训练外，还需要额外按问答对提取方式训练一份。"""
    filename = (candidate or {}).get("filename", "") or ""
    if detect_robocon_content_type(filename) != "application/pdf":
        return False

    title = normalize_text((candidate or {}).get("title", "") or "")
    doc_type = normalize_text((candidate or {}).get("doc_type", "") or "")
    category = (candidate or {}).get("category", "")

    # 优先按标题判断；同时兼容 category/doc_type 归类
    return ("规则" in title) or (category == "rule_core") or ("规则" in doc_type)


def build_robocon_qa_collection_name(filename):
    filename = (filename or "").strip()
    return f"{filename}（问答对）" if filename else "规则（问答对）"


def upload_robocon_file_to_fastgpt_with_config(dataset_id, candidate, *, collection_name, training_type, config_overrides=None):
    url = f"{ROBOCON_FASTGPT_API_URL}/core/dataset/collection/create/localFile"
    filename = candidate["filename"]
    encoded_filename = quote(filename, safe="")
    content_type = detect_robocon_content_type(filename)
    is_pdf_file = content_type == "application/pdf"

    metadata_source = (candidate or {}).get("metadata_source") or "robocon_official_monitor"
    metadata = {
        "source": metadata_source,
        "title": candidate.get("title", ""),
        "publishDate": candidate.get("date", ""),
        "sourceUrl": candidate.get("source_url", ""),
        "docType": candidate.get("doc_type", ""),
        "category": candidate.get("category", ""),
        "originalName": filename,
        "encodedOriginalName": encoded_filename,
        "trackKey": candidate.get("track_key", ""),
        "versionText": candidate.get("version_text", ""),
        "semanticTags": candidate.get("semantic_tags", []),
        "isLatestVersion": candidate.get("is_latest_version", False),
        "recallPriority": candidate.get("recall_priority", "")
    }
    config_data = {
        "datasetId": dataset_id,
        "parentId": None,
        "filename": collection_name,
        "name": collection_name,
        "trainingType": training_type,
        "customPdfParse": is_pdf_file,
        "indexPrefixTitle": True,
        "chunkSize": 500 if is_pdf_file else 800,
        "chunkSplitter": "",
        "qaPrompt": "",
        "tags": candidate.get("effective_tags", []),
        "metadata": metadata
    }
    if config_overrides:
        config_data.update(config_overrides)

    with open(candidate["absolute_path"], "rb") as file_obj:
        file_bytes = file_obj.read()
        data_json = json.dumps(config_data, ensure_ascii=False)

        file_field = RequestField(name="file", data=file_bytes, filename=encoded_filename)
        file_field.make_multipart(content_type=content_type)
        file_field.headers["Content-Disposition"] = (
            f'form-data; name="file"; filename="{encoded_filename}"; '
            f"filename*=UTF-8''{encoded_filename}"
        )

        body, form_content_type = encode_multipart_formdata([
            ("data", data_json),
            file_field
        ])
        response = get_fastgpt_http_session().post(
            url,
            headers={
                "Authorization": f"Bearer {get_robocon_fastgpt_api_key()}",
                "Content-Type": form_content_type
            },
            data=body,
            timeout=ROBOCON_FASTGPT_TIMEOUT
        )

    response.raise_for_status()
    result = response.json()
    if result.get("code") != 200:
        raise RuntimeError(result.get("message", f"上传失败: {collection_name}"))

    data = result.get("data", {})
    collection_id = data.get("collectionId") or data.get("_id")
    if not collection_id:
        raise RuntimeError(f"上传成功但未返回 collectionId: {collection_name}")

    update_fastgpt_collection_name(collection_id, collection_name)
    return collection_id


def existing_robocon_name_matches(filename, existing_names):
    normalized_name = normalize_robocon_filename(filename)
    for existing_name in existing_names:
        if normalized_name == existing_name or normalized_name in existing_name:
            return True
    return False


def infer_fastgpt_training_type(item):
    raw_type = normalize_text(
        (item or {}).get("trainingType")
        or (item or {}).get("type")
        or (item or {}).get("mode")
    ).lower()
    if raw_type in {"qa", "chunk"}:
        return raw_type

    name = normalize_robocon_filename((item or {}).get("name", ""))
    if "问答对" in name:
        return "qa"
    return "chunk"


def list_fastgpt_collection_records(dataset_id, parent_id=None):
    records = []
    page_num = 1
    page_size = 50
    url = f"{ROBOCON_FASTGPT_API_URL}/core/dataset/collection/list"

    while True:
        payload = {
            "datasetId": dataset_id,
            "parentId": parent_id,
            "pageNum": page_num,
            "pageSize": page_size,
            "searchText": ""
        }
        response = get_fastgpt_http_session().post(
            url,
            headers=get_robocon_fastgpt_headers(),
            json=payload,
            timeout=ROBOCON_FASTGPT_TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 200:
            raise RuntimeError(result.get("message", "获取 FastGPT collection 列表失败"))

        data = result.get("data", {})
        if isinstance(data, dict):
            items = data.get("data", [])
            total = data.get("total", 0)
        elif isinstance(data, list):
            items = data
            total = len(items)
        else:
            items = []
            total = 0

        for item in items:
            name = normalize_robocon_filename(item.get("name", ""))
            if name:
                records.append({
                    "name": item.get("name", ""),
                    "normalized_name": name,
                    "training_type": infer_fastgpt_training_type(item)
                })

        if not items or len(records) >= total or len(items) < page_size:
            break
        page_num += 1

    return records


def list_fastgpt_collection_names(dataset_id, parent_id=None):
    existing_names = set()
    for item in list_fastgpt_collection_records(dataset_id, parent_id=parent_id):
        existing_names.add(item["normalized_name"])
    return existing_names


def update_fastgpt_collection_name(collection_id, filename):
    url = f"{ROBOCON_FASTGPT_API_URL}/core/dataset/collection/update"
    payload = {"id": collection_id, "name": filename}

    session_obj = get_fastgpt_http_session()
    for method in (session_obj.post, session_obj.put):
        response = method(
            url,
            headers=get_robocon_fastgpt_headers(),
            json=payload,
            timeout=ROBOCON_FASTGPT_TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 200:
            return

    raise RuntimeError(f"更新 Collection 名称失败: {filename}")


def build_robocon_fastgpt_upload_candidates(resources, *, base_dir=None, metadata_source="robocon_official_monitor"):
    national = (resources or {}).get("national", {})
    docs = national.get("docs", [])
    candidates = []
    base_dir = base_dir or ROBOCON_BASE_DIR

    for doc in docs:
        if doc.get("download_policy") != "download":
            continue

        preview_url = doc.get("preview_url", "")
        downloaded_attachment = doc.get("downloaded_attachment", "")
        if not preview_url.startswith("/static/") or not downloaded_attachment:
            continue

        relative_path = preview_url.lstrip("/")
        absolute_path = os.path.join(base_dir, relative_path)
        if not os.path.exists(absolute_path):
            print(f"Robocon 本地文件不存在，跳过 FastGPT 上传: {absolute_path}")
            continue

        filename = normalize_robocon_filename(downloaded_attachment)
        if not filename:
            continue

        candidates.append({
            "filename": filename,
            "absolute_path": absolute_path,
            "title": doc.get("title", ""),
            "date": doc.get("date", ""),
            "source_url": doc.get("url", ""),
            "doc_type": doc.get("type", ""),
            "category": doc.get("category", ""),
            "source": doc.get("source", ""),
            "metadata_source": doc.get("metadata_source") or metadata_source
        })

    latest_by_track = {}
    for candidate in candidates:
        if not candidate.get("semantic_tags"):
            semantic_info = extract_robocon_semantic_tags(candidate["filename"])
            candidate["semantic_tags"] = semantic_info["tags"]
            candidate["version_text"] = semantic_info["version_text"]
            candidate["version_parts"] = semantic_info["version_parts"]
            candidate["track_key"] = semantic_info["family_key"]
        candidate["version_text"] = candidate.get("version_text")
        candidate["version_parts"] = candidate.get("version_parts", ())
        candidate["track_key"] = candidate.get("track_key") or candidate["filename"]
        candidate["date_key"] = parse_robocon_date_key(candidate.get("date", ""))

        track_key = candidate["track_key"]
        current_best = latest_by_track.get(track_key)
        candidate_score = (candidate["version_parts"], candidate["date_key"], candidate["filename"])
        if current_best is None:
            latest_by_track[track_key] = candidate
            continue

        best_score = (
            current_best.get("version_parts", ()),
            current_best.get("date_key", datetime.min),
            current_best["filename"]
        )
        if candidate_score > best_score:
            latest_by_track[track_key] = candidate

    for candidate in candidates:
        if "is_latest_version" not in candidate:
            candidate["is_latest_version"] = latest_by_track.get(candidate["track_key"]) is candidate
        if "recall_priority" not in candidate:
            candidate["recall_priority"] = "latest" if candidate["is_latest_version"] else "history"
        if not candidate.get("effective_tags"):
            candidate["effective_tags"] = list(candidate.get("semantic_tags", []))
            candidate["effective_tags"].append("最新版本" if candidate["is_latest_version"] else "历史版本")

    candidates.sort(key=lambda item: (item.get("date") or "", item["filename"]), reverse=True)
    return candidates


def upload_robocon_file_to_fastgpt(dataset_id, candidate):
    filename = candidate["filename"]
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=filename,
        training_type="chunk"
    )


def upload_robocon_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate):
    """规则 PDF 额外上传为问答对训练方式。"""
    filename = candidate["filename"]
    collection_name = build_robocon_qa_collection_name(filename)

    # 按截图设置：PDF 增强解析 + 问答对提取 + 标题入索引 + 自定义（按段落分块）+ 最大分块大小 8000
    config_overrides = {
        "trainingType": "qa",
        "customPdfParse": True,
        "indexPrefixTitle": True,
        "chunkSettingMode": "custom",
        "chunkSplitMode": "size",
        "chunkSize": 8000,
        "chunkSplitter": "\n\n",
        "qaPrompt": ""
    }
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=collection_name,
        training_type="qa",
        config_overrides=config_overrides
    )


def sync_robocon_resources_to_fastgpt(resources=None, force_upload=False):
    api_key = get_robocon_fastgpt_api_key()
    dataset_id = ROBOCON_FASTGPT_DATASET_ID

    if not api_key:
        print("未配置 FASTGPT_API_KEY，跳过 Robocon FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_api_key"}

    if not dataset_id:
        print("未配置 FASTGPT_ROBOCON_DATASET_ID，跳过 Robocon FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_dataset_id"}

    resources = resources or load_robocon_resources_state() or get_robocon_main_resources_snapshot()
    candidates = build_robocon_fastgpt_upload_candidates(resources)
    if not candidates:
        print("Robocon FastGPT 同步：没有可上传的本地规则文件")
        return {"success": True, "uploaded": 0, "skipped": 0, "total": 0}

    print(f"开始同步 Robocon 规则到 FastGPT，候选文件 {len(candidates)} 个")
    existing_records = list_fastgpt_collection_records(dataset_id)
    existing_names = {item["normalized_name"] for item in existing_records}
    existing_name_type_pairs = {
        (item["normalized_name"], item["training_type"])
        for item in existing_records
    }
    print(f"FastGPT 知识库中已存在 {len(existing_names)} 个 collection 名称")

    sync_state = load_robocon_fastgpt_sync_state()
    sync_state["dataset_id"] = dataset_id
    sync_state["items"] = [
        item for item in sync_state.get("items", [])
        if isinstance(item, dict)
    ]
    sync_state_pairs = {
        (
            normalize_robocon_filename(item.get("filename", "")),
            item.get("training_type", "chunk")
        )
        for item in sync_state["items"]
        if normalize_robocon_filename(item.get("filename", ""))
    }

    uploaded = []
    skipped = []
    errors = []

    for candidate in candidates:
        filename = candidate["filename"]
        normalized_name = normalize_robocon_filename(filename)
        qa_collection_name = build_robocon_qa_collection_name(filename)
        qa_normalized_name = normalize_robocon_filename(qa_collection_name)

        has_chunk = force_upload or not (
            (normalized_name, "chunk") in sync_state_pairs
            or (normalized_name, "chunk") in existing_name_type_pairs
            or existing_robocon_name_matches(filename, existing_names)
        )
        has_qa = force_upload or not (
            (qa_normalized_name, "qa") in sync_state_pairs
            or (qa_normalized_name, "qa") in existing_name_type_pairs
            or existing_robocon_name_matches(qa_collection_name, existing_names)
        )

        if not has_chunk:
            print(f"FastGPT 已存在 chunk 版本，跳过上传: {filename}")
            skipped.append(filename)

        try:
            if has_chunk:
                collection_id = upload_robocon_file_to_fastgpt(dataset_id, candidate)
                existing_names.add(normalized_name)
                existing_name_type_pairs.add((normalized_name, "chunk"))
                sync_state_pairs.add((normalized_name, "chunk"))
                uploaded.append(filename)
                sync_state["items"] = [
                    item for item in sync_state["items"]
                    if normalize_robocon_filename(item.get("filename")) != normalized_name
                ]
                sync_state["items"].append({
                    "filename": filename,
                    "collection_id": collection_id,
                    "date": candidate.get("date", ""),
                    "title": candidate.get("title", ""),
                    "track_key": candidate.get("track_key", ""),
                    "version_text": candidate.get("version_text", ""),
                    "semantic_tags": candidate.get("semantic_tags", []),
                    "effective_tags": candidate.get("effective_tags", []),
                    "is_latest_version": candidate.get("is_latest_version", False),
                    "source_url": candidate.get("source_url", ""),
                    "training_type": "chunk",
                    "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_robocon_fastgpt_sync_state(sync_state)
                print(f"Robocon FastGPT 上传成功: {filename} -> {collection_id}")

            if should_upload_robocon_rule_pdf_as_qa(candidate):
                if has_qa:
                    qa_collection_id = upload_robocon_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate)
                    existing_names.add(qa_normalized_name)
                    existing_name_type_pairs.add((qa_normalized_name, "qa"))
                    sync_state_pairs.add((qa_normalized_name, "qa"))
                    uploaded.append(qa_collection_name)
                    sync_state["items"] = [
                        item for item in sync_state["items"]
                        if normalize_robocon_filename(item.get("filename")) != qa_normalized_name
                    ]
                    sync_state["items"].append({
                        "filename": qa_collection_name,
                        "source_filename": filename,
                        "collection_id": qa_collection_id,
                        "date": candidate.get("date", ""),
                        "title": candidate.get("title", ""),
                        "track_key": candidate.get("track_key", ""),
                        "version_text": candidate.get("version_text", ""),
                        "semantic_tags": candidate.get("semantic_tags", []),
                        "effective_tags": (candidate.get("effective_tags", []) or []) + ["问答对提取"],
                        "is_latest_version": candidate.get("is_latest_version", False),
                        "source_url": candidate.get("source_url", ""),
                        "training_type": "qa",
                        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_robocon_fastgpt_sync_state(sync_state)
                    print(f"Robocon FastGPT QA 上传成功: {qa_collection_name} -> {qa_collection_id}")
                else:
                    print(f"FastGPT 已存在 QA 版本，跳过上传: {qa_collection_name}")
                    skipped.append(qa_collection_name)
        except Exception as exc:
            error_text = f"{filename}: {exc}"
            print(f"Robocon FastGPT 上传失败: {error_text}")
            errors.append(error_text)

    return {
        "success": len(errors) == 0,
        "uploaded": len(uploaded),
        "skipped": len(skipped),
        "total": len(candidates),
        "uploaded_files": uploaded,
        "errors": errors
    }


def sync_robocon_bionic_resources_to_fastgpt(resources=None, force_upload=False):
    api_key = get_robocon_fastgpt_api_key()
    dataset_id = ROBOCON_BIONIC_FASTGPT_DATASET_ID

    if not api_key:
        print("未配置 FASTGPT_API_KEY，跳过 Robocon 仿生足式 FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_api_key"}

    if not dataset_id:
        print("未配置 FASTGPT_ROBOCON_BIONIC_LEGGED_DATASET_ID，跳过 Robocon 仿生足式 FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_dataset_id"}

    resources = resources or load_robocon_bionic_resources_state() or get_robocon_bionic_resources_snapshot()
    candidates = build_robocon_fastgpt_upload_candidates(
        resources,
        base_dir=ROBOCON_BASE_DIR,
        metadata_source="robocon_bionic_legged_official_monitor"
    )
    if not candidates:
        print("Robocon 仿生足式 FastGPT 同步：没有可上传的本地规则文件")
        return {"success": True, "uploaded": 0, "skipped": 0, "total": 0}

    print(f"开始同步 Robocon 仿生足式规则到 FastGPT，候选文件 {len(candidates)} 个")
    existing_records = list_fastgpt_collection_records(dataset_id)
    existing_names = {item["normalized_name"] for item in existing_records}
    existing_name_type_pairs = {
        (item["normalized_name"], item["training_type"])
        for item in existing_records
    }

    sync_state = load_robocon_bionic_fastgpt_sync_state()
    sync_state["dataset_id"] = dataset_id
    sync_state["items"] = [
        item for item in sync_state.get("items", [])
        if isinstance(item, dict)
    ]
    sync_state_pairs = {
        (
            normalize_robocon_filename(item.get("filename", "")),
            item.get("training_type", "chunk")
        )
        for item in sync_state["items"]
        if normalize_robocon_filename(item.get("filename", ""))
    }

    uploaded = []
    skipped = []
    errors = []

    for candidate in candidates:
        filename = candidate["filename"]
        normalized_name = normalize_robocon_filename(filename)
        qa_collection_name = build_robocon_qa_collection_name(filename)
        qa_normalized_name = normalize_robocon_filename(qa_collection_name)

        has_chunk = force_upload or not (
            (normalized_name, "chunk") in sync_state_pairs
            or (normalized_name, "chunk") in existing_name_type_pairs
            or existing_robocon_name_matches(filename, existing_names)
        )
        has_qa = force_upload or not (
            (qa_normalized_name, "qa") in sync_state_pairs
            or (qa_normalized_name, "qa") in existing_name_type_pairs
            or existing_robocon_name_matches(qa_collection_name, existing_names)
        )

        if not has_chunk:
            print(f"FastGPT 已存在 Robocon 仿生足式 chunk 版本，跳过上传: {filename}")
            skipped.append(filename)

        try:
            if has_chunk:
                collection_id = upload_robocon_file_to_fastgpt(dataset_id, candidate)
                existing_names.add(normalized_name)
                existing_name_type_pairs.add((normalized_name, "chunk"))
                sync_state_pairs.add((normalized_name, "chunk"))
                uploaded.append(filename)
                sync_state["items"] = [
                    item for item in sync_state["items"]
                    if normalize_robocon_filename(item.get("filename")) != normalized_name
                ]
                sync_state["items"].append({
                    "filename": filename,
                    "collection_id": collection_id,
                    "date": candidate.get("date", ""),
                    "title": candidate.get("title", ""),
                    "track_key": candidate.get("track_key", ""),
                    "version_text": candidate.get("version_text", ""),
                    "semantic_tags": candidate.get("semantic_tags", []),
                    "effective_tags": candidate.get("effective_tags", []),
                    "is_latest_version": candidate.get("is_latest_version", False),
                    "source_url": candidate.get("source_url", ""),
                    "training_type": "chunk",
                    "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_robocon_bionic_fastgpt_sync_state(sync_state)
                print(f"Robocon 仿生足式 FastGPT 上传成功: {filename} -> {collection_id}")

            if should_upload_robocon_rule_pdf_as_qa(candidate):
                if has_qa:
                    qa_collection_id = upload_robocon_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate)
                    existing_names.add(qa_normalized_name)
                    existing_name_type_pairs.add((qa_normalized_name, "qa"))
                    sync_state_pairs.add((qa_normalized_name, "qa"))
                    uploaded.append(qa_collection_name)
                    sync_state["items"] = [
                        item for item in sync_state["items"]
                        if normalize_robocon_filename(item.get("filename")) != qa_normalized_name
                    ]
                    sync_state["items"].append({
                        "filename": qa_collection_name,
                        "source_filename": filename,
                        "collection_id": qa_collection_id,
                        "date": candidate.get("date", ""),
                        "title": candidate.get("title", ""),
                        "track_key": candidate.get("track_key", ""),
                        "version_text": candidate.get("version_text", ""),
                        "semantic_tags": candidate.get("semantic_tags", []),
                        "effective_tags": (candidate.get("effective_tags", []) or []) + ["问答对提取"],
                        "is_latest_version": candidate.get("is_latest_version", False),
                        "source_url": candidate.get("source_url", ""),
                        "training_type": "qa",
                        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_robocon_bionic_fastgpt_sync_state(sync_state)
                    print(f"Robocon 仿生足式 FastGPT QA 上传成功: {qa_collection_name} -> {qa_collection_id}")
                else:
                    print(f"FastGPT 已存在 Robocon 仿生足式 QA 版本，跳过上传: {qa_collection_name}")
                    skipped.append(qa_collection_name)
        except Exception as exc:
            error_text = f"{filename}: {exc}"
            print(f"Robocon 仿生足式 FastGPT 上传失败: {error_text}")
            errors.append(error_text)

    return {
        "success": len(errors) == 0,
        "uploaded": len(uploaded),
        "skipped": len(skipped),
        "total": len(candidates),
        "uploaded_files": uploaded,
        "errors": errors
    }


def start_robocon_fastgpt_backfill():
    def run():
        try:
            resources = load_robocon_resources_state() or get_robocon_main_resources_snapshot()
            sync_robocon_resources_to_fastgpt(resources)
        except Exception as exc:
            print(f"Robocon FastGPT 启动回填失败: {exc}")

    thread = threading.Thread(
        target=run,
        name="robocon-fastgpt-backfill",
        daemon=True
    )
    thread.start()


def start_robocon_bionic_fastgpt_backfill():
    def run():
        try:
            resources = load_robocon_bionic_resources_state() or get_robocon_bionic_resources_snapshot()
            sync_robocon_bionic_resources_to_fastgpt(resources)
        except Exception as exc:
            print(f"Robocon 仿生足式 FastGPT 启动回填失败: {exc}")

    thread = threading.Thread(
        target=run,
        name="robocon-bionic-fastgpt-backfill",
        daemon=True
    )
    thread.start()


def sync_robotac_main_resources(force_refresh=False, force_upload=False):
    print(f"开始同步 Robotac 官网资料: {ROBOTAC_NEWS_URL}")
    resources = get_robotac_resources(force_refresh=force_refresh) if not force_refresh else scrape_robotac_resources()
    try:
        save_robotac_resources_state(resources)
    except Exception as exc:
        print(f"Robotac 保存本地缓存失败: {exc}")

    try:
        sync_result = sync_robotac_resources_to_fastgpt(resources, force_upload=force_upload)
        print(
            "Robotac FastGPT 同步完成: "
            f"uploaded={sync_result.get('uploaded', 0)}, "
            f"skipped={sync_result.get('skipped', 0)}, "
            f"errors={len(sync_result.get('errors', []))}"
        )
    except Exception as exc:
        print(f"Robotac FastGPT 自动同步失败: {exc}")
    return resources


def start_robotac_fastgpt_backfill():
    def run():
        try:
            resources = load_robotac_resources_state() or get_robotac_resources(force_refresh=True)
            sync_robotac_resources_to_fastgpt(resources)
        except Exception as exc:
            print(f"Robotac FastGPT 启动回填失败: {exc}")

    thread = threading.Thread(
        target=run,
        name="robotac-fastgpt-backfill",
        daemon=True
    )
    thread.start()


def robotac_scheduler_loop():
    print(
        "Robotac 定时同步已启动，"
        f"计划每 {ROBOCON_SYNC_INTERVAL_DAYS} 天 {ROBOCON_SYNC_HOUR:02d}:{ROBOCON_SYNC_MINUTE:02d} 执行一次"
    )

    if not os.path.exists(ROBOTAC_STATE_PATH):
        try:
            print("未发现 Robotac 本地缓存，启动后先执行一次初始化同步")
            sync_robotac_main_resources(force_refresh=True)
        except Exception as exc:
            print(f"初始化同步 Robotac 官网失败: {exc}")

    while True:
        next_run = compute_next_robocon_sync()
        wait_seconds = max(30, int((next_run - datetime.now()).total_seconds()))
        print(f"下一次 Robotac 定时同步时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        try:
            sync_robotac_main_resources(force_refresh=True)
        except Exception as exc:
            print(f"Robotac 定时同步失败: {exc}")
        time.sleep(1)

def sync_robocon_main_resources(force_upload=False):
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
    try:
        sync_result = sync_robocon_resources_to_fastgpt(resources, force_upload=force_upload)
        print(
            "Robocon FastGPT 同步完成: "
            f"uploaded={sync_result.get('uploaded', 0)}, "
            f"skipped={sync_result.get('skipped', 0)}, "
            f"errors={len(sync_result.get('errors', []))}"
        )
    except Exception as exc:
        print(f"Robocon FastGPT 自动同步失败: {exc}")

    try:
        print("Robocon 主赛同步完成，开始联动同步 Robomaster 官方规则")
        robomaster_sync_result = sync_robomaster_resources(force_upload=force_upload)
        print(
            "Robomaster 联动同步完成: "
            f"tracks={len(robomaster_sync_result.get('track_docs', {}))}, "
            f"uploaded={((robomaster_sync_result.get('fastgpt_sync') or {}).get('uploaded', 0))}, "
            f"errors={len(((robomaster_sync_result.get('fastgpt_sync') or {}).get('errors', [])))}"
        )
    except Exception as exc:
        print(f"Robomaster 联动同步失败: {exc}")

    print(f"Robocon 官网同步完成，本次处理条目 {len(docs)} 条")
    return resources


def sync_robocon_bionic_resources(force_upload=False):
    print(f"开始同步 Robocon 仿生足式规则: {ROBOCON_BIONIC_NEWS_URL}")
    response = requests_get_robocon(ROBOCON_BIONIC_NEWS_URL)
    response.raise_for_status()
    entries = extract_robocon_bionic_news_entries(response.text)
    print(f"Robocon 仿生足式列表页抓取成功，发现候选条目 {len(entries)} 条")

    docs = []
    for entry in entries:
        try:
            entry_docs = fetch_robocon_bionic_detail_resources(entry)
            if not entry_docs:
                continue
            docs.extend(entry_docs)
            for doc in entry_docs:
                print(
                    "同步 Robocon 仿生足式条目成功: "
                    f"{doc['title']} "
                    f"[category={doc.get('category')}, policy={doc.get('download_policy')}]"
                )
        except Exception as exc:
            print(f"同步 Robocon 仿生足式条目失败: {entry.get('detail_url')} -> {exc}")

    docs.sort(key=lambda item: ((item.get("date") or ""), (item.get("title") or "")), reverse=True)
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resources = build_robocon_bionic_dynamic_resources(docs, synced_at)
    save_robocon_bionic_resources_state(resources)
    try:
        sync_result = sync_robocon_bionic_resources_to_fastgpt(resources, force_upload=force_upload)
        print(
            "Robocon 仿生足式 FastGPT 同步完成: "
            f"uploaded={sync_result.get('uploaded', 0)}, "
            f"skipped={sync_result.get('skipped', 0)}, "
            f"errors={len(sync_result.get('errors', []))}"
        )
    except Exception as exc:
        print(f"Robocon 仿生足式 FastGPT 自动同步失败: {exc}")
    print(f"Robocon 仿生足式官网同步完成，本次处理条目 {len(docs)} 条")
    return resources


def get_robocon_main_resources_snapshot():
    return apply_resource_sync_metadata(build_resources_with_local_overrides(
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
    ))


def get_robocon_bionic_resources_snapshot():
    return apply_resource_sync_metadata(build_resources_with_local_overrides(
        ROBOCON_BIONIC_RESOURCES_SNAPSHOT
    ))


def get_robocon_main_resources():
    cached_resources = load_robocon_resources_state()
    if cached_resources:
        return cached_resources
    return get_robocon_main_resources_snapshot()


def get_robocon_bionic_resources():
    cached_resources = load_robocon_bionic_resources_state()
    if cached_resources:
        return cached_resources
    return get_robocon_bionic_resources_snapshot()


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
    if not os.path.exists(ROBOCON_BIONIC_STATE_PATH):
        try:
            print("未发现 Robocon 仿生足式本地缓存，启动后先执行一次初始化同步")
            sync_robocon_bionic_resources()
        except Exception as exc:
            print(f"初始化同步 Robocon 仿生足式官网失败: {exc}")

    while True:
        next_run = compute_next_robocon_sync()
        wait_seconds = max(30, int((next_run - datetime.now()).total_seconds()))
        print(f"下一次 Robocon 定时同步时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        try:
            sync_robocon_main_resources()
        except Exception as exc:
            print(f"Robocon 定时同步失败: {exc}")
        try:
            sync_robocon_bionic_resources()
        except Exception as exc:
            print(f"Robocon 仿生足式定时同步失败: {exc}")
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


def start_robotac_scheduler():
    if not should_start_background_scheduler():
        return

    with ROBOTAC_SCHEDULER_STATE["lock"]:
        if ROBOTAC_SCHEDULER_STATE["started"]:
            return

        scheduler_thread = threading.Thread(
            target=robotac_scheduler_loop,
            name="robotac-sync-scheduler",
            daemon=True
        )
        scheduler_thread.start()
        ROBOTAC_SCHEDULER_STATE["thread"] = scheduler_thread
        ROBOTAC_SCHEDULER_STATE["started"] = True


@app_comp.record_once
def on_app_comp_registered(state):
    start_robocon_scheduler()
    start_robotac_scheduler()
    start_robocon_fastgpt_backfill()
    start_robocon_bionic_fastgpt_backfill()
    start_robotac_fastgpt_backfill()


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
    hrefs = re.findall(
        r'href=["\']((?:https?://(?:www\.)?robotac\.cn)?/sys-nd/\d+\.html)["\']',
        html
    )
    results = []
    seen = set()
    for href in hrefs:
        full_url = urljoin(ROBOTAC_HOME_URL, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        results.append(full_url)
    return results


def fetch_robotac_article(url):
    response = requests_get_robotac(url)
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


def should_download_robotac_doc(title, doc_type=None):
    title = normalize_text(title or "")
    doc_type = normalize_text(doc_type or "")
    if "规则" in title or "规则" in doc_type:
        return True
    if "章程" in title or "章程" in doc_type:
        return True
    # 通知类通常只有正文，无附件时不强制下载
    return False


def fetch_robotac_detail_resource(article_url):
    response = requests_get_robotac(article_url)
    response.raise_for_status()
    html = response.text
    soup = BeautifulSoup(html, "lxml")

    title_match = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    raw_title = strip_html(title_match.group(1)) if title_match else article_url
    title = raw_title.split(" - 全国大学生机器人大赛ROBOTAC官网")[0].strip()
    doc_type = infer_robotac_doc_type(title)

    date_match = re.search(r"发表时间[:：]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", strip_html(html))
    published_at = date_match.group(1) if date_match else "官网当前页面"

    main_node = extract_detail_main_node(soup)
    attach_root = soup.select_one(".attachBox") or main_node
    attachments = extract_robotac_attachment_links(attach_root, article_url)

    doc = {
        "title": title,
        "type": doc_type,
        "date": published_at,
        "url": article_url,
        "preview_url": article_url,
        "source": "ROBOTAC 官网动态页",
        "category": classify_robotac_doc(title),
        "download_policy": "download" if should_download_robotac_doc(title, doc_type) else "metadata_only"
    }

    if doc["download_policy"] == "download" and attachments:
        # 优先 PDF，其次按出现顺序
        attachments.sort(
            key=lambda item: (0 if urlparse(item.get("file_url", "")).path.lower().endswith(".pdf") else 1, item.get("file_name", ""))
        )
        selected = attachments[0]
        try:
            downloaded = download_robotac_file(selected["file_url"], selected["file_name"])
            if downloaded.get("local_url"):
                doc["preview_url"] = downloaded["local_url"]
                doc["url"] = selected["file_url"]
                doc["source"] = f"{doc['source']} / 本地副本"
                # 与 Robocon 保持一致：用于 FastGPT collection 命名的是原始附件文件名
                doc["downloaded_attachment"] = selected["file_name"]
                doc["downloaded_hash"] = downloaded.get("file_hash")
        except Exception as exc:
            print(f"下载 ROBOTAC 附件失败: {selected.get('file_url')} -> {exc}")

    return doc


def scrape_robotac_resources():
    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    response = requests_get_robotac(ROBOTAC_NEWS_URL)
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
            article = fetch_robotac_detail_resource(article_url)
        except Exception as exc:
            print(f"抓取 ROBOTAC 文章失败: {article_url} -> {exc}")
            continue

        doc = {
            "title": article["title"],
            "type": article["type"],
            "date": article["date"],
            "url": article["url"],
            "preview_url": article["preview_url"],
            "source": article["source"],
            "category": article.get("category", ""),
            "download_policy": article.get("download_policy", "metadata_only"),
            "downloaded_attachment": article.get("downloaded_attachment", "")
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
            "official_url": ROBOTAC_NEWS_URL,
            "updated_at": latest_date,
            "synced_at": synced_at,
            "update_note": "当前页面数据由服务端定期从 ROBOTAC 官网抓取，并带缓存兜底。",
            "docs": notices or copy.deepcopy(ROBOTAC_RESOURCES_SNAPSHOT["notices"]["docs"])
        },
        "competition": {
            "key": "competition",
            "label": "赛事说明",
            "description": "ROBOTAC 官网实时抓取的赛事介绍与办赛动态。",
            "official_url": ROBOTAC_HOME_URL,
            "updated_at": event_date,
            "synced_at": synced_at,
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
            # 优先使用本地落盘缓存（若存在），避免每次页面访问都触发抓取
            local_state = load_robotac_resources_state()
            if local_state and not force_refresh:
                ROBOTAC_CACHE["data"] = local_state
                ROBOTAC_CACHE["fetched_at"] = now
                return copy.deepcopy(local_state)

            fresh_data = scrape_robotac_resources()
            try:
                save_robotac_resources_state(fresh_data)
            except Exception as exc:
                print(f"保存 ROBOTAC 本地缓存失败: {exc}")
            ROBOTAC_CACHE["data"] = fresh_data
            ROBOTAC_CACHE["fetched_at"] = now
            return copy.deepcopy(fresh_data)
        except Exception as exc:
            print(f"抓取 ROBOTAC 官网失败，回退缓存/快照: {exc}")
            if cached_data:
                return copy.deepcopy(cached_data)
            local_state = load_robotac_resources_state()
            if local_state:
                ROBOTAC_CACHE["data"] = local_state
                ROBOTAC_CACHE["fetched_at"] = now
                return copy.deepcopy(local_state)
            fallback = apply_resource_sync_metadata(build_resources_with_local_overrides(ROBOTAC_RESOURCES_SNAPSHOT))
            ROBOTAC_CACHE["data"] = fallback
            ROBOTAC_CACHE["fetched_at"] = now
            return copy.deepcopy(fallback)


def get_robomaster_resources_snapshot():
    return apply_resource_sync_metadata(build_resources_with_local_overrides(ROBOMASTER_RESOURCES_SNAPSHOT))


def build_robomaster_dynamic_resources(track_docs_map, synced_at):
    resources = get_robomaster_resources_snapshot()
    for track_key, track_config in ROBOMASTER_TRACK_DEFINITIONS.items():
        section = resources.get(track_key, {})
        docs = track_docs_map.get(track_key, [])
        section["synced_at"] = synced_at
        section["official_url"] = track_config["page_url"]
        section["description"] = track_config["description"]
        section["update_note"] = (
            f"后台定时任务已在 {synced_at} 完成最近一次官网同步，"
            f"当前抓取 {track_config['label']} 页面中可识别到的全部附件并按赛道落盘，同时同步上传到 FastGPT 对应目录。"
        )
        if docs:
            section["docs"] = docs
            section["updated_at"] = docs[0].get("date") or section.get("updated_at", "")
        resources[track_key] = section
    return resources


def get_robomaster_resources():
    cached_resources = load_robomaster_resources_state()
    if cached_resources:
        return cached_resources
    return get_robomaster_resources_snapshot()


def build_robomaster_fastgpt_upload_candidates(resources):
    candidates = []
    for track_key, section in (resources or {}).items():
        if track_key not in ROBOMASTER_TRACK_DEFINITIONS:
            continue
        docs = (section or {}).get("docs", [])
        track_config = ROBOMASTER_TRACK_DEFINITIONS[track_key]
        for doc in docs:
            preview_url = doc.get("preview_url", "")
            downloaded_attachment = doc.get("downloaded_attachment", "")
            if not preview_url.startswith("/static/") or not downloaded_attachment:
                continue

            relative_path = preview_url.lstrip("/")
            absolute_path = os.path.join(ROBOMASTER_BASE_DIR, relative_path)
            if not os.path.exists(absolute_path):
                print(f"Robomaster 本地文件不存在，跳过 FastGPT 上传: {absolute_path}")
                continue

            filename = normalize_robomaster_filename(downloaded_attachment)
            if not filename:
                continue

            candidates.append({
                "filename": filename,
                "absolute_path": absolute_path,
                "title": doc.get("title", ""),
                "date": doc.get("date", ""),
                "source_url": doc.get("url", ""),
                "doc_type": doc.get("type", ""),
                "category": doc.get("category", track_key),
                "source": doc.get("source", ""),
                "metadata_source": doc.get("metadata_source") or f"robomaster_{track_key}_official_monitor",
                "track_key": track_key,
                "track_label": track_config["label"],
                "dataset_id": track_config.get("fastgpt_dataset_id") or ROBOMASTER_FASTGPT_DATASET_ID,
                "parent_id": None
            })

    latest_by_track = {}
    for candidate in candidates:
        if not candidate.get("semantic_tags"):
            semantic_info = extract_robomaster_semantic_tags(
                candidate["filename"],
                candidate.get("title", ""),
                candidate.get("doc_type", ""),
                candidate.get("track_key", "")
            )
            candidate["semantic_tags"] = semantic_info["tags"]
            candidate["version_text"] = semantic_info["version_text"]
            candidate["version_parts"] = semantic_info["version_parts"]
            candidate["family_key"] = semantic_info["family_key"]
            candidate["track_group_key"] = f"{candidate.get('track_key')}|{semantic_info['family_key'] or candidate['filename']}"
        candidate["date_key"] = parse_robocon_date_key(candidate.get("date", ""))
        current_best = latest_by_track.get(candidate["track_group_key"])
        candidate_score = (candidate.get("version_parts", ()), candidate["date_key"], candidate["filename"])
        if current_best is None:
            latest_by_track[candidate["track_group_key"]] = candidate
            continue
        best_score = (
            current_best.get("version_parts", ()),
            current_best.get("date_key", datetime.min),
            current_best["filename"]
        )
        if candidate_score > best_score:
            latest_by_track[candidate["track_group_key"]] = candidate

    for candidate in candidates:
        candidate["is_latest_version"] = latest_by_track.get(candidate["track_group_key"]) is candidate
        candidate["recall_priority"] = "latest" if candidate["is_latest_version"] else "history"
        candidate["effective_tags"] = list(candidate.get("semantic_tags", []))
        candidate["effective_tags"].append(candidate.get("track_label", ""))
        candidate["effective_tags"].append("最新版本" if candidate["is_latest_version"] else "历史版本")
        candidate["effective_tags"] = [tag for tag in candidate["effective_tags"] if tag]

    candidates.sort(
        key=lambda item: (
            item.get("track_key") or "",
            item.get("date") or "",
            item["filename"]
        ),
        reverse=True
    )
    return candidates


def upload_robomaster_file_to_fastgpt(dataset_id, candidate):
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=candidate["filename"],
        training_type="chunk",
        config_overrides={"parentId": candidate.get("parent_id")}
    )


def upload_robomaster_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate):
    collection_name = build_robocon_qa_collection_name(candidate["filename"])
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=collection_name,
        training_type="qa",
        config_overrides={
            "parentId": candidate.get("parent_id"),
            "trainingType": "qa",
            "customPdfParse": True,
            "indexPrefixTitle": True,
            "chunkSettingMode": "custom",
            "chunkSplitMode": "size",
            "chunkSize": 8000,
            "chunkSplitter": "\n\n",
            "qaPrompt": ""
        }
    )


def should_upload_robomaster_rule_pdf_as_qa(candidate):
    filename = (candidate or {}).get("filename", "") or ""
    if detect_robocon_content_type(filename) != "application/pdf":
        return False
    title = normalize_text((candidate or {}).get("title", "") or "")
    doc_type = normalize_text((candidate or {}).get("doc_type", "") or "")
    return ("规则" in title) or ("规则" in doc_type) or ("手册" in title) or ("手册" in doc_type)


def sync_robomaster_resources_to_fastgpt(resources=None, force_upload=False):
    api_key = get_robocon_fastgpt_api_key()

    if not api_key:
        print("未配置 FASTGPT_API_KEY，跳过 Robomaster FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_api_key"}

    resources = resources or load_robomaster_resources_state() or get_robomaster_resources_snapshot()
    candidates = build_robomaster_fastgpt_upload_candidates(resources)
    if not candidates:
        print("Robomaster FastGPT 同步：没有可上传的本地规则文件")
        return {"success": True, "uploaded": 0, "skipped": 0, "total": 0}

    sync_state = load_robomaster_fastgpt_sync_state()
    sync_state["dataset_id"] = ROBOMASTER_FASTGPT_DATASET_ID or "per-track"
    sync_state["items"] = [item for item in sync_state.get("items", []) if isinstance(item, dict)]
    sync_state_pairs = {
        (
            item.get("dataset_id", ""),
            item.get("parent_id", ""),
            normalize_robomaster_filename(item.get("filename", "")),
            item.get("training_type", "chunk")
        )
        for item in sync_state["items"]
        if normalize_robomaster_filename(item.get("filename", ""))
    }

    parent_existing_cache = {}
    uploaded = []
    skipped = []
    errors = []

    for candidate in candidates:
        dataset_id = candidate.get("dataset_id", "")
        parent_id = candidate.get("parent_id") or ""
        if not dataset_id:
            errors.append(f"{candidate.get('filename', '')}: missing_dataset_id")
            print(f"Robomaster FastGPT 上传跳过，缺少 dataset_id: {candidate.get('filename', '')}")
            continue

        cache_key = f"{dataset_id}|{parent_id}"
        if cache_key not in parent_existing_cache:
            try:
                existing_records = list_fastgpt_collection_records(dataset_id, parent_id=parent_id)
            except Exception as exc:
                print(f"获取 Robomaster FastGPT 目录列表失败: dataset_id={dataset_id}, parent_id={parent_id} -> {exc}")
                existing_records = []
            parent_existing_cache[cache_key] = {
                "names": {item["normalized_name"] for item in existing_records},
                "name_type_pairs": {
                    (item["normalized_name"], item["training_type"])
                    for item in existing_records
                }
            }

        existing_names = parent_existing_cache[cache_key]["names"]
        existing_name_type_pairs = parent_existing_cache[cache_key]["name_type_pairs"]

        filename = candidate["filename"]
        normalized_name = normalize_robomaster_filename(filename)
        qa_collection_name = build_robocon_qa_collection_name(filename)
        qa_normalized_name = normalize_robomaster_filename(qa_collection_name)

        has_chunk = force_upload or not (
            (dataset_id, parent_id, normalized_name, "chunk") in sync_state_pairs
            or (normalized_name, "chunk") in existing_name_type_pairs
            or existing_robocon_name_matches(filename, existing_names)
        )
        has_qa = force_upload or not (
            (dataset_id, parent_id, qa_normalized_name, "qa") in sync_state_pairs
            or (qa_normalized_name, "qa") in existing_name_type_pairs
            or existing_robocon_name_matches(qa_collection_name, existing_names)
        )

        if not has_chunk:
            print(f"FastGPT 已存在 Robomaster chunk 版本，跳过上传: {filename}")
            skipped.append(filename)

        try:
            if has_chunk:
                collection_id = upload_robomaster_file_to_fastgpt(dataset_id, candidate)
                existing_names.add(normalized_name)
                existing_name_type_pairs.add((normalized_name, "chunk"))
                sync_state_pairs.add((dataset_id, parent_id, normalized_name, "chunk"))
                uploaded.append(filename)
                sync_state["items"] = [
                    item for item in sync_state["items"]
                    if not (
                        item.get("dataset_id", "") == dataset_id
                        and
                        item.get("parent_id", "") == parent_id
                        and normalize_robomaster_filename(item.get("filename")) == normalized_name
                        and item.get("training_type", "chunk") == "chunk"
                    )
                ]
                sync_state["items"].append({
                    "dataset_id": dataset_id,
                    "filename": filename,
                    "collection_id": collection_id,
                    "parent_id": parent_id,
                    "track_key": candidate.get("track_key", ""),
                    "date": candidate.get("date", ""),
                    "title": candidate.get("title", ""),
                    "version_text": candidate.get("version_text", ""),
                    "semantic_tags": candidate.get("semantic_tags", []),
                    "effective_tags": candidate.get("effective_tags", []),
                    "is_latest_version": candidate.get("is_latest_version", False),
                    "source_url": candidate.get("source_url", ""),
                    "training_type": "chunk",
                    "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_robomaster_fastgpt_sync_state(sync_state)
                print(f"Robomaster FastGPT 上传成功: {filename} -> {collection_id}")

            if should_upload_robomaster_rule_pdf_as_qa(candidate):
                if has_qa:
                    qa_collection_id = upload_robomaster_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate)
                    existing_names.add(qa_normalized_name)
                    existing_name_type_pairs.add((qa_normalized_name, "qa"))
                    sync_state_pairs.add((dataset_id, parent_id, qa_normalized_name, "qa"))
                    uploaded.append(qa_collection_name)
                    sync_state["items"] = [
                        item for item in sync_state["items"]
                        if not (
                            item.get("dataset_id", "") == dataset_id
                            and
                            item.get("parent_id", "") == parent_id
                            and normalize_robomaster_filename(item.get("filename")) == qa_normalized_name
                            and item.get("training_type", "chunk") == "qa"
                        )
                    ]
                    sync_state["items"].append({
                        "dataset_id": dataset_id,
                        "filename": qa_collection_name,
                        "source_filename": filename,
                        "collection_id": qa_collection_id,
                        "parent_id": parent_id,
                        "track_key": candidate.get("track_key", ""),
                        "date": candidate.get("date", ""),
                        "title": candidate.get("title", ""),
                        "version_text": candidate.get("version_text", ""),
                        "semantic_tags": candidate.get("semantic_tags", []),
                        "effective_tags": (candidate.get("effective_tags", []) or []) + ["问答对提取"],
                        "is_latest_version": candidate.get("is_latest_version", False),
                        "source_url": candidate.get("source_url", ""),
                        "training_type": "qa",
                        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_robomaster_fastgpt_sync_state(sync_state)
                    print(f"Robomaster FastGPT QA 上传成功: {qa_collection_name} -> {qa_collection_id}")
                else:
                    print(f"FastGPT 已存在 Robomaster QA 版本，跳过上传: {qa_collection_name}")
                    skipped.append(qa_collection_name)
        except Exception as exc:
            error_text = f"{filename}: {exc}"
            print(f"Robomaster FastGPT 上传失败: {error_text}")
            errors.append(error_text)

    return {
        "success": len(errors) == 0,
        "uploaded": len(uploaded),
        "skipped": len(skipped),
        "total": len(candidates),
        "uploaded_files": uploaded,
        "errors": errors
    }


def sync_robomaster_resources(force_upload=False):
    print(f"开始同步 Robomaster 官网规则: {ROBOMASTER_NEWS_URL}")
    track_docs_map = {}

    for track_key, track_config in ROBOMASTER_TRACK_DEFINITIONS.items():
        try:
            docs = extract_robomaster_page_docs(track_key, track_config)
            track_docs_map[track_key] = docs
            print(f"同步 Robomaster {track_config['label']} 成功，条目 {len(docs)} 条")
        except Exception as exc:
            print(f"同步 Robomaster {track_config['label']} 失败: {track_config['page_url']} -> {exc}")
            track_docs_map[track_key] = copy.deepcopy(
                ((get_robomaster_resources_snapshot().get(track_key) or {}).get("docs")) or []
            )

    synced_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    resources = build_robomaster_dynamic_resources(track_docs_map, synced_at)
    save_robomaster_resources_state(resources)
    try:
        sync_result = sync_robomaster_resources_to_fastgpt(resources, force_upload=force_upload)
        print(
            "Robomaster FastGPT 同步完成: "
            f"uploaded={sync_result.get('uploaded', 0)}, "
            f"skipped={sync_result.get('skipped', 0)}, "
            f"errors={len(sync_result.get('errors', []))}"
        )
    except Exception as exc:
        print(f"Robomaster FastGPT 自动同步失败: {exc}")
    return resources


def start_robomaster_fastgpt_backfill():
    def run():
        try:
            resources = load_robomaster_resources_state() or get_robomaster_resources_snapshot()
            sync_robomaster_resources_to_fastgpt(resources)
        except Exception as exc:
            print(f"Robomaster FastGPT 启动回填失败: {exc}")

    thread = threading.Thread(
        target=run,
        name="robomaster-fastgpt-backfill",
        daemon=True
    )
    thread.start()


def robomaster_scheduler_loop():
    print(
        "Robomaster 定时同步已启动，"
        f"计划每 {ROBOCON_SYNC_INTERVAL_DAYS} 天 {ROBOCON_SYNC_HOUR:02d}:{ROBOCON_SYNC_MINUTE:02d} 执行一次"
    )

    if not os.path.exists(ROBOMASTER_STATE_PATH):
        try:
            print("未发现 Robomaster 本地缓存，启动后先执行一次初始化同步")
            sync_robomaster_resources()
        except Exception as exc:
            print(f"初始化同步 Robomaster 官网失败: {exc}")

    while True:
        next_run = compute_next_robocon_sync()
        wait_seconds = max(30, int((next_run - datetime.now()).total_seconds()))
        print(f"下一次 Robomaster 定时同步时间: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
        time.sleep(wait_seconds)
        try:
            sync_robomaster_resources()
        except Exception as exc:
            print(f"Robomaster 定时同步失败: {exc}")
        time.sleep(1)


def start_robomaster_scheduler():
    if not should_start_background_scheduler():
        return

    with ROBOMASTER_SCHEDULER_STATE["lock"]:
        if ROBOMASTER_SCHEDULER_STATE["started"]:
            return

        scheduler_thread = threading.Thread(
            target=robomaster_scheduler_loop,
            name="robomaster-sync-scheduler",
            daemon=True
        )
        scheduler_thread.start()
        ROBOMASTER_SCHEDULER_STATE["thread"] = scheduler_thread
        ROBOMASTER_SCHEDULER_STATE["started"] = True


COMPETITION_RESOURCE_LOADERS = {
    "robocon_main": get_robocon_main_resources,
    "robocon_bionic_legged": get_robocon_bionic_resources,
    "robotac": get_robotac_resources,
    "robomaster": get_robomaster_resources,
}

COMPETITION_SYNC_HANDLERS = {
    "robocon_main": lambda force_upload=False: sync_robocon_main_resources(force_upload=force_upload),
    "robocon_bionic_legged": lambda force_upload=False: sync_robocon_bionic_resources(force_upload=force_upload),
    "robotac": lambda force_upload=False: sync_robotac_main_resources(force_refresh=True, force_upload=force_upload),
    "robomaster": lambda force_upload=False: sync_robomaster_resources(force_upload=force_upload),
}

COMPETITION_SYNC_STATE_LOADERS = {
    "robocon_main": load_robocon_fastgpt_sync_state,
    "robocon_bionic_legged": load_robocon_bionic_fastgpt_sync_state,
    "robotac": load_robotac_fastgpt_sync_state,
    "robomaster": load_robomaster_fastgpt_sync_state,
}


def build_competition_agent_context(agent):
    resource_loader_key = agent.get("resource_loader_key")
    resource_loader = COMPETITION_RESOURCE_LOADERS.get(resource_loader_key)
    competition_resources = (
        resource_loader()
        if resource_loader
        else get_competition_agent_snapshot(agent.get("key"))
    )
    agent_key = agent.get("key", "")
    resource_panel_title = agent.get("resource_panel_title")
    if not resource_panel_title:
        if agent_key == "robocon_main":
            resource_panel_title = "Robocon主赛资料区"
        elif agent_key == "robocon_bionic_legged":
            resource_panel_title = "Robocon足式资料区"
        else:
            resource_panel_title = f"{agent.get('competition_name', agent.get('name', ''))}比赛资料区"
    return {
        "competition_resources": competition_resources,
        "official_link_label": agent.get("official_link_label", "官网入口"),
        "assistant_title": agent.get("assistant_title", agent.get("name", "")),
        "competition_name": agent.get("competition_name", agent.get("name", "")),
        "default_category": agent.get("default_category", ""),
        "resource_panel_title": resource_panel_title,
    }


def build_robotac_fastgpt_upload_candidates(resources):
    candidates = []
    for section_key, section in (resources or {}).items():
        docs = (section or {}).get("docs", [])
        for doc in docs:
            if doc.get("download_policy") != "download":
                continue
            preview_url = doc.get("preview_url", "")
            downloaded_attachment = doc.get("downloaded_attachment", "")
            if not preview_url.startswith("/static/") or not downloaded_attachment:
                continue

            relative_path = preview_url.lstrip("/")
            absolute_path = os.path.join(ROBOTAC_BASE_DIR, relative_path)
            if not os.path.exists(absolute_path):
                print(f"Robotac 本地文件不存在，跳过 FastGPT 上传: {absolute_path}")
                continue

            filename = normalize_robotac_filename(downloaded_attachment)
            if not filename:
                continue

            candidates.append({
                "filename": filename,
                "absolute_path": absolute_path,
                "title": doc.get("title", ""),
                "date": doc.get("date", ""),
                "source_url": doc.get("url", ""),
                "doc_type": doc.get("type", ""),
                "category": section_key,
                "source": doc.get("source", ""),
                "metadata_source": "robotac_official_monitor"
            })

    latest_by_track = {}
    for candidate in candidates:
        if not candidate.get("semantic_tags"):
            semantic_info = extract_robotac_semantic_tags(
                candidate["filename"],
                candidate.get("title", ""),
                candidate.get("doc_type", "")
            )
            candidate["semantic_tags"] = semantic_info["tags"]
            candidate["version_text"] = semantic_info["version_text"]
            candidate["version_parts"] = semantic_info["version_parts"]
            candidate["track_key"] = f"ROBOTAC|{semantic_info['family_key'] or candidate['filename']}"
        candidate["version_text"] = candidate.get("version_text")
        candidate["version_parts"] = candidate.get("version_parts", ())
        candidate["track_key"] = candidate.get("track_key") or f"ROBOTAC|{candidate['filename']}"
        candidate["date_key"] = parse_robocon_date_key(candidate.get("date", ""))

        track_key = candidate["track_key"]
        current_best = latest_by_track.get(track_key)
        candidate_score = (candidate["version_parts"], candidate["date_key"], candidate["filename"])
        if current_best is None:
            latest_by_track[track_key] = candidate
            continue

        best_score = (
            current_best.get("version_parts", ()),
            current_best.get("date_key", datetime.min),
            current_best["filename"]
        )
        if candidate_score > best_score:
            latest_by_track[track_key] = candidate

    for candidate in candidates:
        if "is_latest_version" not in candidate:
            candidate["is_latest_version"] = latest_by_track.get(candidate["track_key"]) is candidate
        if "recall_priority" not in candidate:
            candidate["recall_priority"] = "latest" if candidate["is_latest_version"] else "history"
        if not candidate.get("effective_tags"):
            candidate["effective_tags"] = list(candidate.get("semantic_tags", []))
            candidate["effective_tags"].append(candidate.get("doc_type", ""))
            candidate["effective_tags"].append("最新版本" if candidate["is_latest_version"] else "历史版本")
            candidate["effective_tags"] = [tag for tag in candidate["effective_tags"] if tag]

    candidates.sort(key=lambda item: (item.get("date") or "", item["filename"]), reverse=True)
    return candidates


def upload_robotac_file_to_fastgpt(dataset_id, candidate):
    # Robotac 先只保持与 Robocon 一致的 chunk 上传（PDF 增强解析会自动开启）
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=candidate["filename"],
        training_type="chunk"
    )


def should_upload_robotac_rule_pdf_as_qa(candidate):
    filename = (candidate or {}).get("filename", "") or ""
    if detect_robocon_content_type(filename) != "application/pdf":
        return False

    title = normalize_text((candidate or {}).get("title", "") or "")
    doc_type = normalize_text((candidate or {}).get("doc_type", "") or "")
    return ("规则" in title) or ("规则" in doc_type)


def upload_robotac_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate):
    filename = candidate["filename"]
    collection_name = build_robocon_qa_collection_name(filename)
    config_overrides = {
        "trainingType": "qa",
        "customPdfParse": True,
        "indexPrefixTitle": True,
        "chunkSettingMode": "custom",
        "chunkSplitMode": "size",
        "chunkSize": 8000,
        "chunkSplitter": "\n\n",
        "qaPrompt": ""
    }
    return upload_robocon_file_to_fastgpt_with_config(
        dataset_id,
        candidate,
        collection_name=collection_name,
        training_type="qa",
        config_overrides=config_overrides
    )


def sync_robotac_resources_to_fastgpt(resources=None, force_upload=False):
    api_key = get_robocon_fastgpt_api_key()
    dataset_id = ROBOTAC_FASTGPT_DATASET_ID

    if not api_key:
        print("未配置 FASTGPT_API_KEY，跳过 Robotac FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_api_key"}
    if not dataset_id:
        print("未配置 FASTGPT_ROBOTAC_DATASET_ID，跳过 Robotac FastGPT 自动同步")
        return {"success": False, "skipped": True, "reason": "missing_dataset_id"}

    resources = resources or load_robotac_resources_state() or get_robotac_resources(force_refresh=True)
    candidates = build_robotac_fastgpt_upload_candidates(resources)
    if not candidates:
        print("Robotac FastGPT 同步：没有可上传的本地规则文件")
        return {"success": True, "uploaded": 0, "skipped": 0, "total": 0}

    print(f"开始同步 Robotac 规则到 FastGPT，候选文件 {len(candidates)} 个")
    existing_records = list_fastgpt_collection_records(dataset_id)
    existing_names = {item["normalized_name"] for item in existing_records}
    existing_name_type_pairs = {
        (item["normalized_name"], item["training_type"])
        for item in existing_records
    }
    print(f"FastGPT 知识库中已存在 {len(existing_names)} 个 collection 名称")

    sync_state = load_robotac_fastgpt_sync_state()
    sync_state["dataset_id"] = dataset_id
    sync_state["items"] = [
        item for item in sync_state.get("items", [])
        if isinstance(item, dict)
    ]
    sync_state_pairs = {
        (
            normalize_robotac_filename(item.get("filename", "")),
            item.get("training_type", "chunk")
        )
        for item in sync_state["items"]
        if normalize_robotac_filename(item.get("filename", ""))
    }

    uploaded = []
    skipped = []
    errors = []

    for candidate in candidates:
        filename = candidate["filename"]
        normalized_name = normalize_robotac_filename(filename)
        qa_collection_name = build_robocon_qa_collection_name(filename)
        qa_normalized_name = normalize_robotac_filename(qa_collection_name)

        has_chunk = force_upload or not (
            (normalized_name, "chunk") in sync_state_pairs
            or (normalized_name, "chunk") in existing_name_type_pairs
            or existing_robocon_name_matches(filename, existing_names)
        )
        has_qa = force_upload or not (
            (qa_normalized_name, "qa") in sync_state_pairs
            or (qa_normalized_name, "qa") in existing_name_type_pairs
            or existing_robocon_name_matches(qa_collection_name, existing_names)
        )

        if not has_chunk:
            print(f"FastGPT 已存在 chunk 版本，跳过上传: {filename}")
            skipped.append(filename)

        try:
            if has_chunk:
                collection_id = upload_robotac_file_to_fastgpt(dataset_id, candidate)
                existing_names.add(normalized_name)
                existing_name_type_pairs.add((normalized_name, "chunk"))
                sync_state_pairs.add((normalized_name, "chunk"))
                uploaded.append(filename)
                sync_state["items"] = [
                    item for item in sync_state["items"]
                    if normalize_robotac_filename(item.get("filename")) != normalized_name
                ]
                sync_state["items"].append({
                    "filename": filename,
                    "collection_id": collection_id,
                    "date": candidate.get("date", ""),
                    "title": candidate.get("title", ""),
                    "track_key": candidate.get("track_key", ""),
                    "version_text": candidate.get("version_text", ""),
                    "semantic_tags": candidate.get("semantic_tags", []),
                    "effective_tags": candidate.get("effective_tags", []),
                    "is_latest_version": candidate.get("is_latest_version", False),
                    "source_url": candidate.get("source_url", ""),
                    "training_type": "chunk",
                    "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                })
                save_robotac_fastgpt_sync_state(sync_state)
                print(f"Robotac FastGPT 上传成功: {filename} -> {collection_id}")

            if should_upload_robotac_rule_pdf_as_qa(candidate):
                if has_qa:
                    qa_collection_id = upload_robotac_rule_pdf_to_fastgpt_as_qa(dataset_id, candidate)
                    existing_names.add(qa_normalized_name)
                    existing_name_type_pairs.add((qa_normalized_name, "qa"))
                    sync_state_pairs.add((qa_normalized_name, "qa"))
                    uploaded.append(qa_collection_name)
                    sync_state["items"] = [
                        item for item in sync_state["items"]
                        if normalize_robotac_filename(item.get("filename")) != qa_normalized_name
                    ]
                    sync_state["items"].append({
                        "filename": qa_collection_name,
                        "source_filename": filename,
                        "collection_id": qa_collection_id,
                        "date": candidate.get("date", ""),
                        "title": candidate.get("title", ""),
                        "track_key": candidate.get("track_key", ""),
                        "version_text": candidate.get("version_text", ""),
                        "semantic_tags": candidate.get("semantic_tags", []),
                        "effective_tags": (candidate.get("effective_tags", []) or []) + ["问答对提取"],
                        "is_latest_version": candidate.get("is_latest_version", False),
                        "source_url": candidate.get("source_url", ""),
                        "training_type": "qa",
                        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    save_robotac_fastgpt_sync_state(sync_state)
                    print(f"Robotac FastGPT QA 上传成功: {qa_collection_name} -> {qa_collection_id}")
                else:
                    print(f"FastGPT 已存在 QA 版本，跳过上传: {qa_collection_name}")
                    skipped.append(qa_collection_name)
        except Exception as exc:
            error_text = f"{filename}: {exc}"
            print(f"Robotac FastGPT 上传失败: {error_text}")
            errors.append(error_text)

    return {
        "success": len(errors) == 0,
        "uploaded": len(uploaded),
        "skipped": len(skipped),
        "total": len(candidates),
        "uploaded_files": uploaded,
        "errors": errors
    }

@app_comp.route('/dashboard/kd/sync/<agent_identifier>', methods=['POST'])
def sync_competition_agent(agent_identifier):
    permission_response = require_teacher_json()
    if permission_response:
        return permission_response

    agent = (
        get_competition_agent_by_key(agent_identifier)
        or get_competition_agent_by_route_name(agent_identifier)
    )
    if not agent and agent_identifier.isdigit():
        agent = get_competition_agent_by_id(int(agent_identifier))
    if not agent:
        return jsonify({"success": False, "error": "找不到该比赛智能体"}), 404

    sync_handler = COMPETITION_SYNC_HANDLERS.get(agent.get("key"))
    if not sync_handler:
        return jsonify({"success": False, "error": "该智能体暂不支持手动同步"}), 400

    payload = request.get_json(silent=True) or {}
    force_upload = bool(payload.get("force_upload"))

    try:
        resources = sync_handler(force_upload=force_upload)
        sync_state_loader = COMPETITION_SYNC_STATE_LOADERS.get(agent.get("key"))
        sync_state = sync_state_loader() if sync_state_loader else {"items": []}
        national_docs = ((resources or {}).get("national") or {}).get("docs", [])
        first_section = next(iter((resources or {}).values()), {})
        doc_count = sum(len((section or {}).get("docs", [])) for section in (resources or {}).values())
        return jsonify({
            "success": True,
            "agent_key": agent.get("key"),
            "agent_name": agent.get("name"),
            "force_upload": force_upload,
            "resource_sections": list((resources or {}).keys()),
            "resource_doc_count": doc_count,
            "national_doc_count": len(national_docs),
            "synced_at": (
                ((resources or {}).get("national") or {}).get("synced_at")
                or first_section.get("synced_at", "")
            ),
            "fastgpt_dataset_id": (sync_state or {}).get("dataset_id", ""),
            "fastgpt_item_count": len((sync_state or {}).get("items", []))
        })
    except Exception as exc:
        print(f"手动同步比赛智能体失败: {agent.get('key')} -> {exc}")
        return jsonify({
            "success": False,
            "error": str(exc),
            "agent_key": agent.get("key"),
            "agent_name": agent.get("name")
        }), 500


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


@app_comp.route('/dashboard/kds/<agent_route_name>')
def view_kd(agent_route_name):
    login_response = require_login()
    if login_response:
        return login_response

    agent = get_competition_agent_by_route_name(agent_route_name)
    if not agent and agent_route_name.isdigit():
        agent = get_competition_agent_by_id(int(agent_route_name))
        if agent:
            return redirect(url_for('app_comp.view_kd', agent_route_name=agent['route_name']))
    if not agent:
        flash('找不到该知识库智能体', 'error')
        return redirect(url_for('app_comp.course_kd'))

    template_name = agent.get('template_name', 'dashboard/new_chat.html')
    extra_context = build_competition_agent_context(agent)

    return render_template(
        template_name,
        embed_url=agent['url'],
        agent=agent,
        username=session.get('username', '用户'),
        role=session.get('role', 'student'),
        **extra_context
    )


@app_comp.route('/dashboard/kds/id/<int:agent_id>')
def view_kd_by_id(agent_id):
    login_response = require_login()
    if login_response:
        return login_response

    agent = get_competition_agent_by_id(agent_id)
    if not agent:
        flash('找不到该知识库智能体', 'error')
        return redirect(url_for('app_comp.course_kd'))

    return redirect(url_for('app_comp.view_kd', agent_route_name=agent['route_name']))
