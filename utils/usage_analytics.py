from datetime import datetime, timedelta, timezone


CHINA_TZ = timezone(timedelta(hours=8))
ONLINE_WINDOW_MINUTES = 5
REQUEST_EVENT = "request"
HEARTBEAT_EVENT = "heartbeat"
LOGIN_SUCCESS_EVENT = "login_success"
REGISTER_SUCCESS_EVENT = "register_success"
AGENT_OPEN_EVENT = "agent_open"
KG_VIEW_EVENT = "kg_page_view"
CHAT_EVENT = "mcp_chat"
TRACKED_ACTIVITY_EVENTS = [
    REQUEST_EVENT,
    HEARTBEAT_EVENT,
    LOGIN_SUCCESS_EVENT,
    REGISTER_SUCCESS_EVENT,
    AGENT_OPEN_EVENT,
    KG_VIEW_EVENT,
    CHAT_EVENT,
]
SKIP_PREFIXES = ("/static/", "/js/", "/KG/static/output/")
SKIP_PATHS = {
    "/favicon.ico",
    "/get_session",
    "/usage/heartbeat",
}


def _now():
    return datetime.now(CHINA_TZ)


def _day_str(dt):
    return dt.strftime("%Y-%m-%d")


def _get_collection(db, name):
    return db[name] if db is not None else None


def init_usage_analytics(db):
    if db is None:
        return

    events = _get_collection(db, "usage_events")
    online = _get_collection(db, "usage_online_users")
    peaks = _get_collection(db, "usage_daily_peaks")

    try:
        events.create_index([("occurred_at", -1)])
        events.create_index([("event_type", 1), ("day", 1)])
        events.create_index([("username", 1), ("occurred_at", -1)])
        events.create_index([("path", 1), ("occurred_at", -1)])
    except Exception as e:
        print(f"⚠️ usage_events 索引创建失败: {e}")

    try:
        online.create_index("username", unique=True)
        online.create_index([("last_seen_at", -1)])
    except Exception as e:
        print(f"⚠️ usage_online_users 索引创建失败: {e}")

    try:
        peaks.create_index("day", unique=True)
    except Exception as e:
        print(f"⚠️ usage_daily_peaks 索引创建失败: {e}")


def should_track_request(request):
    path = request.path or ""
    if request.endpoint == "static":
        return False
    if path in SKIP_PATHS:
        return False
    return not any(path.startswith(prefix) for prefix in SKIP_PREFIXES)


def _safe_ip(request):
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def track_event(
    db,
    event_type,
    request=None,
    username=None,
    role=None,
    meta=None,
):
    if db is None:
        return

    now = _now()
    events = _get_collection(db, "usage_events")
    document = {
        "event_type": event_type,
        "username": username,
        "role": role,
        "occurred_at": now,
        "day": _day_str(now),
        "meta": meta or {},
    }

    if request is not None:
        document.update(
            {
                "path": request.path,
                "endpoint": request.endpoint,
                "method": request.method,
                "ip": _safe_ip(request),
                "user_agent": (request.headers.get("User-Agent") or "")[:255],
            }
        )

    try:
        events.insert_one(document)
    except Exception as e:
        print(f"⚠️ usage event 记录失败: {e}")


def refresh_online_user(db, username, role, request=None):
    if db is None or not username:
        return 0

    now = _now()
    online = _get_collection(db, "usage_online_users")
    peaks = _get_collection(db, "usage_daily_peaks")

    payload = {
        "role": role,
        "last_seen_at": now,
        "updated_at": now,
    }
    if request is not None:
        payload["last_path"] = request.path
        payload["ip"] = _safe_ip(request)

    try:
        online.update_one(
            {"username": username},
            {
                "$set": payload,
                "$setOnInsert": {"first_seen_at": now},
            },
            upsert=True,
        )
    except Exception as e:
        print(f"⚠️ 在线用户状态更新失败: {e}")
        return 0

    active_since = now - timedelta(minutes=ONLINE_WINDOW_MINUTES)
    try:
        current_online = len(
            online.distinct("username", {"last_seen_at": {"$gte": active_since}})
        )
        peaks.update_one(
            {"day": _day_str(now)},
            {
                "$max": {"peak_online": current_online},
                "$set": {"updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        return current_online
    except Exception as e:
        print(f"⚠️ 在线人数统计失败: {e}")
        return 0


def cleanup_stale_online_users(db):
    if db is None:
        return

    online = _get_collection(db, "usage_online_users")
    stale_before = _now() - timedelta(days=30)
    try:
        online.delete_many({"last_seen_at": {"$lt": stale_before}})
    except Exception as e:
        print(f"⚠️ 清理过期在线状态失败: {e}")


def collect_request_usage(db, request, username=None, role=None):
    if not should_track_request(request):
        return
    track_event(
        db,
        REQUEST_EVENT,
        request=request,
        username=username,
        role=role,
        meta={"query_string": request.query_string.decode("utf-8", errors="ignore")[:255]},
    )


def _distinct_count(collection, field, query):
    try:
        return len(collection.distinct(field, query))
    except Exception:
        return 0


def _daily_counts(events, peaks, day):
    dau = _distinct_count(
        events,
        "username",
        {
            "day": day,
            "event_type": {"$in": TRACKED_ACTIVITY_EVENTS},
            "username": {"$nin": [None, ""]},
        },
    )
    requests = events.count_documents({"day": day, "event_type": REQUEST_EVENT})
    logins = events.count_documents({"day": day, "event_type": LOGIN_SUCCESS_EVENT})
    registrations = events.count_documents({"day": day, "event_type": REGISTER_SUCCESS_EVENT})
    chats = events.count_documents({"day": day, "event_type": CHAT_EVENT})
    peak_doc = peaks.find_one({"day": day}, {"peak_online": 1}) or {}
    return {
        "day": day,
        "dau": dau,
        "requests": requests,
        "logins": logins,
        "registrations": registrations,
        "chats": chats,
        "peak_online": peak_doc.get("peak_online", 0),
    }


def _parse_date(value):
    if not value:
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
        return datetime(parsed.year, parsed.month, parsed.day, tzinfo=CHINA_TZ)
    except ValueError:
        return None


def resolve_date_range(start_date=None, end_date=None):
    today_dt = _now()
    today = datetime(today_dt.year, today_dt.month, today_dt.day, tzinfo=CHINA_TZ)
    first_day_of_month = datetime(today_dt.year, today_dt.month, 1, tzinfo=CHINA_TZ)

    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)

    if parsed_start is None and parsed_end is None:
        parsed_end = today
        parsed_start = first_day_of_month
    elif parsed_start is None:
        parsed_start = parsed_end
    elif parsed_end is None:
        parsed_end = parsed_start

    if parsed_start > parsed_end:
        parsed_start, parsed_end = parsed_end, parsed_start

    start_at = parsed_start
    end_at = parsed_end + timedelta(days=1)
    total_days = (parsed_end.date() - parsed_start.date()).days + 1

    return {
        "start_date": parsed_start.strftime("%Y-%m-%d"),
        "end_date": parsed_end.strftime("%Y-%m-%d"),
        "start_at": start_at,
        "end_at": end_at,
        "days": total_days,
        "label": f"{parsed_start.strftime('%Y-%m-%d')} 至 {parsed_end.strftime('%Y-%m-%d')}",
        "is_single_day": total_days == 1,
    }


def _top_pages(events, start_at, end_at, limit=8):
    pipeline = [
        {
            "$match": {
                "event_type": REQUEST_EVENT,
                "occurred_at": {"$gte": start_at, "$lt": end_at},
                "username": {"$nin": [None, ""]},
            }
        },
        {
            "$group": {
                "_id": "$path",
                "views": {"$sum": 1},
                "users": {"$addToSet": "$username"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "path": "$_id",
                "views": 1,
                "uv": {"$size": "$users"},
            }
        },
        {"$sort": {"views": -1, "uv": -1}},
        {"$limit": limit},
    ]
    return list(events.aggregate(pipeline))


def _top_agents(events, start_at, end_at, limit=8):
    pipeline = [
        {
            "$match": {
                "event_type": AGENT_OPEN_EVENT,
                "occurred_at": {"$gte": start_at, "$lt": end_at},
                "meta.agent_id": {"$exists": True},
            }
        },
        {
            "$group": {
                "_id": {
                    "agent_id": "$meta.agent_id",
                    "agent_name": "$meta.agent_name",
                },
                "opens": {"$sum": 1},
                "users": {"$addToSet": "$username"},
            }
        },
        {
            "$project": {
                "_id": 0,
                "agent_id": "$_id.agent_id",
                "agent_name": "$_id.agent_name",
                "opens": 1,
                "uv": {"$size": "$users"},
            }
        },
        {"$sort": {"opens": -1, "uv": -1}},
        {"$limit": limit},
    ]
    return list(events.aggregate(pipeline))


def _role_distribution(events, day):
    pipeline = [
        {
            "$match": {
                "day": day,
                "event_type": {"$in": TRACKED_ACTIVITY_EVENTS},
                "username": {"$nin": [None, ""]},
            }
        },
        {
            "$group": {
                "_id": {"role": "$role", "username": "$username"},
            }
        },
        {
            "$group": {
                "_id": "$_id.role",
                "users": {"$sum": 1},
            }
        },
        {"$project": {"_id": 0, "role": {"$ifNull": ["$_id", "unknown"]}, "users": 1}},
        {"$sort": {"users": -1}},
    ]
    return list(events.aggregate(pipeline))


def get_usage_summary(db, start_date=None, end_date=None):
    date_range = resolve_date_range(start_date, end_date)
    trend_days = date_range["days"]
    default_summary = {
        "today": {
            "dau": 0,
            "requests": 0,
            "logins": 0,
            "registrations": 0,
            "chats": 0,
            "current_online": 0,
            "peak_online": 0,
        },
        "selected_period": {
            "active_users": 0,
            "requests": 0,
            "logins": 0,
            "registrations": 0,
            "chats": 0,
            "peak_online": 0,
        },
        "rolling": {"wau": 0, "mau": 0},
        "top_pages": [],
        "top_agents": [],
        "role_distribution": [],
        "daily_trend": [],
        "date_range": date_range,
        "generated_at": _now(),
    }
    if db is None:
        return default_summary

    events = _get_collection(db, "usage_events")
    online = _get_collection(db, "usage_online_users")
    peaks = _get_collection(db, "usage_daily_peaks")

    now = _now()
    today = _day_str(now)
    current_online = _distinct_count(
        online,
        "username",
        {"last_seen_at": {"$gte": now - timedelta(minutes=ONLINE_WINDOW_MINUTES)}},
    )

    today_counts = _daily_counts(events, peaks, today)
    today_counts["current_online"] = current_online

    period_start = date_range["start_at"]
    period_end = date_range["end_at"]
    rolling_7_start = now - timedelta(days=6)
    rolling_30_start = now - timedelta(days=29)
    default_summary["today"] = today_counts
    default_summary["selected_period"] = {
        "active_users": _distinct_count(
            events,
            "username",
            {
                "occurred_at": {"$gte": period_start, "$lt": period_end},
                "event_type": {"$in": TRACKED_ACTIVITY_EVENTS},
                "username": {"$nin": [None, ""]},
            },
        ),
        "requests": events.count_documents(
            {"event_type": REQUEST_EVENT, "occurred_at": {"$gte": period_start, "$lt": period_end}}
        ),
        "logins": events.count_documents(
            {"event_type": LOGIN_SUCCESS_EVENT, "occurred_at": {"$gte": period_start, "$lt": period_end}}
        ),
        "registrations": events.count_documents(
            {"event_type": REGISTER_SUCCESS_EVENT, "occurred_at": {"$gte": period_start, "$lt": period_end}}
        ),
        "chats": events.count_documents(
            {"event_type": CHAT_EVENT, "occurred_at": {"$gte": period_start, "$lt": period_end}}
        ),
        "peak_online": 0,
    }
    default_summary["rolling"] = {
        "wau": _distinct_count(
            events,
            "username",
            {
                "occurred_at": {"$gte": rolling_7_start},
                "event_type": {"$in": TRACKED_ACTIVITY_EVENTS},
                "username": {"$nin": [None, ""]},
            },
        ),
        "mau": _distinct_count(
            events,
            "username",
            {
                "occurred_at": {"$gte": rolling_30_start},
                "event_type": {"$in": TRACKED_ACTIVITY_EVENTS},
                "username": {"$nin": [None, ""]},
            },
        ),
    }

    trend = []
    range_end_day = datetime.strptime(date_range["end_date"], "%Y-%m-%d").replace(tzinfo=CHINA_TZ)
    for offset in range(trend_days - 1, -1, -1):
        day = _day_str(range_end_day - timedelta(days=offset))
        trend.append(_daily_counts(events, peaks, day))
    if trend:
        default_summary["selected_period"]["peak_online"] = max(
            item.get("peak_online", 0) for item in trend
        )

    default_summary["top_pages"] = _top_pages(events, period_start, period_end)
    default_summary["top_agents"] = _top_agents(events, period_start, period_end)
    default_summary["role_distribution"] = _role_distribution(events, today)
    default_summary["daily_trend"] = trend
    default_summary["generated_at"] = now
    return default_summary
