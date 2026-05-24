# -*- coding: utf-8 -*-
"""
个人知识库路由模块 —— v4.6 原始文件名保存 + 源文件自动迁移清理 + 重命名同步本地源文件

★ v4.6 变更：
    1. 用户上传文件保存到 kb_raw_sources/<username>/ 时，优先使用原始文件名；
    2. 同名活跃文件冲突时自动追加序号，避免覆盖；
    3. 自动清理当前用户 kb_raw_sources 目录中 MongoDB 不再引用的多余文件；
    4. 自动把旧版 doc_xxx.ext 命名的源文件迁移为原始文件名；
    5. 前端重命名文件时，同步修改 FastGPT collection、MongoDB filename 和本地源文件名；
    6. 保留统一源文件查看和下载接口：
       /api/kb/document/<doc_id>/original
       /api/kb/document/<doc_id>/original/download
"""

import os
import io
import re
import json
import hashlib
import mimetypes
import threading
import traceback
import time
import requests as http_requests
from datetime import datetime
from flask import Blueprint, session, request, jsonify, send_file, render_template
from config_fastgpt import (
    FASTGPT_API_URL as _DEFAULT_FASTGPT_API_URL,
    FASTGPT_SHARE_BASE_URL as _DEFAULT_FASTGPT_SHARE_BASE_URL,
    FASTGPT_SHARE_ID as _DEFAULT_FASTGPT_SHARE_ID
)

kb_bp = Blueprint('kb', __name__)

_fastgpt_kb_service = None
_db = None
_login_required = None
_process_user_courses = None
_media_parser = None
_fastgpt_api_url = None
_fastgpt_api_key = None


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except Exception:
        return default


def _mb(n):
    return int(n) * 1024 * 1024


_MAX_DOCUMENTS_PER_USER = _env_int('KB_MAX_DOCUMENTS_PER_USER', 200)
_MAX_TOTAL_STORAGE_MB_PER_USER = _env_int('KB_MAX_TOTAL_STORAGE_MB', 5120)
_MAX_TOTAL_STORAGE_BYTES_PER_USER = _mb(_MAX_TOTAL_STORAGE_MB_PER_USER)

_MAX_VIDEO_MB = _env_int('KB_MAX_VIDEO_MB', 500)
_MAX_DOCUMENT_MB = _env_int('KB_MAX_DOCUMENT_MB', 100)
_MAX_IMAGE_MB = _env_int('KB_MAX_IMAGE_MB', 50)
_MAX_PPT_MB = _env_int('KB_MAX_PPT_MB', 100)

_MAX_VIDEO_BYTES = _mb(_MAX_VIDEO_MB)
_MAX_DOCUMENT_BYTES = _mb(_MAX_DOCUMENT_MB)
_MAX_IMAGE_BYTES = _mb(_MAX_IMAGE_MB)
_MAX_PPT_BYTES = _mb(_MAX_PPT_MB)

_TEXT_EXTS = {'pdf', 'txt', 'md', 'doc', 'docx'}
_IMAGE_EXTS = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}
_VIDEO_EXTS = {'mp4', 'avi', 'mov', 'mkv', 'flv', 'wmv', 'webm'}
_PPT_EXTS = {'pptx', 'ppt'}

_RAW_SOURCE_DIR = os.environ.get(
    'KB_RAW_SOURCE_DIR',
    '/home/zgllm/test_server/kb_raw_sources'
)

_RAW_SOURCE_BASE_URL = os.environ.get(
    'KB_RAW_SOURCE_BASE_URL',
    'http://180.85.206.21:7777'  # ✅ 与工作流端口一致
)

_AUTO_CLEAN_RAW_SOURCES_ON_LIST = os.environ.get(
    'KB_AUTO_CLEAN_RAW_SOURCES_ON_LIST',
    '1'
).lower() in ('1', 'true', 'yes')

_AUTO_MIGRATE_RAW_SOURCE_NAMES = os.environ.get(
    'KB_AUTO_MIGRATE_RAW_SOURCE_NAMES',
    '1'
).lower() in ('1', 'true', 'yes')

try:
    os.makedirs(_RAW_SOURCE_DIR, exist_ok=True)
except Exception as e:
    print(f"⚠️ 创建原始文件保存目录失败: {_RAW_SOURCE_DIR}, error={e}")


def init_kb_blueprint(app, db, fastgpt_kb_service, login_required_func,
                      process_user_courses_func, media_parser=None):
    global _fastgpt_kb_service, _db, _login_required, _process_user_courses
    global _media_parser, _fastgpt_api_url, _fastgpt_api_key

    _fastgpt_kb_service = fastgpt_kb_service
    _db = db
    _login_required = login_required_func
    _process_user_courses = process_user_courses_func
    _media_parser = media_parser

    _fastgpt_api_url = os.environ.get('FASTGPT_API_URL', '').rstrip('/')
    _fastgpt_api_key = os.environ.get('FASTGPT_API_KEY', '')

    if _fastgpt_kb_service:
        if not _fastgpt_api_url:
            _fastgpt_api_url = (
                getattr(_fastgpt_kb_service, 'api_url', '')
                or getattr(_fastgpt_kb_service, 'base_url', '')
            )
            if _fastgpt_api_url and not _fastgpt_api_url.endswith('/api'):
                _fastgpt_api_url = _fastgpt_api_url.rstrip('/') + '/api'

        if not _fastgpt_api_key:
            _fastgpt_api_key = getattr(_fastgpt_kb_service, 'api_key', '')

    if not _fastgpt_api_url:
        _fastgpt_api_url = _DEFAULT_FASTGPT_API_URL

    _fastgpt_base = (
        _fastgpt_api_url.rsplit('/api', 1)[0]
        if '/api' in _fastgpt_api_url
        else _fastgpt_api_url
    )

    if _fastgpt_api_key:
        print(f"   🖼️  FastGPT 图片上传: {_fastgpt_api_url}")
        print(f"      Base URL: {_fastgpt_base}")
        print("      API Key: 已从服务读取 ✅")
    else:
        print("   ⚠️  FastGPT API Key 未找到，图片上传到 FastGPT 不可用")

    print(f"   ★ 本地原始文件保存目录: {_RAW_SOURCE_DIR}")
    print("   ★ v4.6 已启用：源文件按原始文件名保存、重命名同步、孤儿源文件自动清理")


# ================== FastGPT 图片上传 ==================

def _get_fastgpt_base():
    if '/api' in _fastgpt_api_url:
        return _fastgpt_api_url.rsplit('/api', 1)[0]
    return _fastgpt_api_url


def _upload_image_to_fastgpt(file_content, filename, dataset_id=None):
    if not _fastgpt_api_key:
        return {'success': False, 'url': '', 'error': 'FastGPT API Key 未配置'}

    fastgpt_base = _get_fastgpt_base()
    headers = {'Authorization': f'Bearer {_fastgpt_api_key}'}
    mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'
    errors = []

    try:
        url = f"{_fastgpt_api_url}/common/file/upload"
        files = {'file': (filename, io.BytesIO(file_content), mime)}
        data = {'bucketName': 'chat'}
        resp = http_requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=30
        )

        if resp.status_code == 200:
            body = resp.json()
            fid = _extract_file_id(body)

            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                return {
                    'success': True,
                    'url': img_url,
                    'file_id': fid,
                    'bucket_name': 'chat'
                }

            u = _extract_url(body)
            if u:
                if u.startswith('/'):
                    u = fastgpt_base + u
                return {
                    'success': True,
                    'url': u,
                    'file_id': '',
                    'bucket_name': 'chat'
                }

            errors.append(f"chat bucket: 无file_id ({_safe_json(body)})")

        else:
            errors.append(f"chat bucket: HTTP {resp.status_code} ({resp.text[:150]})")

    except Exception as e:
        errors.append(f"chat bucket 异常: {e}")

    if dataset_id:
        try:
            url = f"{_fastgpt_api_url}/common/file/upload"
            files = {'file': (filename, io.BytesIO(file_content), mime)}
            metadata_json = json.dumps({'datasetId': dataset_id})
            data = {'bucketName': 'dataset', 'metadata': metadata_json}

            resp = http_requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=30
            )

            if resp.status_code == 200:
                body = resp.json()
                fid = _extract_file_id(body)

                if fid:
                    img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                    return {
                        'success': True,
                        'url': img_url,
                        'file_id': fid,
                        'bucket_name': 'dataset'
                    }

                u = _extract_url(body)
                if u:
                    if u.startswith('/'):
                        u = fastgpt_base + u
                    return {
                        'success': True,
                        'url': u,
                        'file_id': '',
                        'bucket_name': 'dataset'
                    }

                errors.append(f"dataset bucket: 无file_id ({_safe_json(body)})")

            else:
                errors.append(f"dataset bucket: HTTP {resp.status_code} ({resp.text[:150]})")

        except Exception as e:
            errors.append(f"dataset bucket 异常: {e}")

    try:
        url = f"{_fastgpt_api_url}/common/file/uploadImage"
        files = {'file': (filename, io.BytesIO(file_content), mime)}
        data = {'bucketName': 'chat'}

        resp = http_requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=30
        )

        if resp.status_code == 200:
            body = resp.json()
            u = _extract_url(body)

            if u:
                if u.startswith('/'):
                    u = fastgpt_base + u
                return {
                    'success': True,
                    'url': u,
                    'file_id': '',
                    'bucket_name': 'chat'
                }

            fid = _extract_file_id(body)
            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                return {
                    'success': True,
                    'url': img_url,
                    'file_id': fid,
                    'bucket_name': 'chat'
                }

            errors.append(f"uploadImage: 无URL ({_safe_json(body)})")

        else:
            errors.append(f"uploadImage: HTTP {resp.status_code} ({resp.text[:150]})")

    except Exception as e:
        errors.append(f"uploadImage 异常: {e}")

    try:
        url = f"{_fastgpt_api_url}/common/file/upload"
        files = {'file': (filename, io.BytesIO(file_content), mime)}

        resp = http_requests.post(
            url,
            headers=headers,
            files=files,
            timeout=30
        )

        if resp.status_code == 200:
            body = resp.json()
            fid = _extract_file_id(body)

            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                return {
                    'success': True,
                    'url': img_url,
                    'file_id': fid,
                    'bucket_name': ''
                }

            errors.append(f"无bucket: 无file_id ({_safe_json(body)})")

        else:
            errors.append(f"无bucket: HTTP {resp.status_code} ({resp.text[:150]})")

    except Exception as e:
        errors.append(f"无bucket 异常: {e}")

    print("      ❌ 所有 FastGPT 图片上传均失败:")
    for err in errors:
        print(f"         - {err}")

    return {
        'success': False,
        'url': '',
        'error': ' | '.join(errors)
    }


def _extract_file_id(body):
    if not isinstance(body, dict):
        return None

    data = body.get('data')

    if isinstance(data, str) and len(data) > 8:
        return data

    if isinstance(data, dict):
        for key in ('fileId', 'id', '_id', 'file_id'):
            if data.get(key):
                return data[key]

    return None


def _extract_url(body):
    if not isinstance(body, dict):
        return None

    data = body.get('data')

    if isinstance(data, str) and (data.startswith('http') or data.startswith('/')):
        return data

    if isinstance(data, dict):
        for key in ('url', 'imageUrl', 'img_url', 'link', 'src', 'previewUrl'):
            if data.get(key):
                return data[key]

    return None


def _safe_json(body):
    try:
        return json.dumps(body, ensure_ascii=False)[:150]
    except Exception:
        return str(body)[:150]


# ================== 通用辅助函数 ==================

def _safe_int(v, default=0):
    try:
        if v is None:
            return default
        return int(v)
    except Exception:
        return default


def _format_size(num_bytes):
    num_bytes = _safe_int(num_bytes)

    if num_bytes >= 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f}GB"
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.2f}MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.2f}KB"

    return f"{num_bytes}B"


def _get_upload_file_limit(ext):
    ext = (ext or '').lower().strip().lstrip('.')

    if ext in _VIDEO_EXTS:
        return _MAX_VIDEO_BYTES, f"视频文件最大支持 {_MAX_VIDEO_MB}MB"
    if ext in _IMAGE_EXTS:
        return _MAX_IMAGE_BYTES, f"图片文件最大支持 {_MAX_IMAGE_MB}MB"
    if ext in _PPT_EXTS:
        return _MAX_PPT_BYTES, f"PPT 文件最大支持 {_MAX_PPT_MB}MB"
    if ext in _TEXT_EXTS:
        return _MAX_DOCUMENT_BYTES, f"文档文件最大支持 {_MAX_DOCUMENT_MB}MB"

    return _MAX_DOCUMENT_BYTES, f"该类型文件最大支持 {_MAX_DOCUMENT_MB}MB"


def _is_path_inside(child_path, parent_path):
    try:
        child_path = os.path.abspath(child_path)
        parent_path = os.path.abspath(parent_path)
        return child_path == parent_path or child_path.startswith(parent_path + os.sep)
    except Exception:
        return False


def _get_file_ext(filename):
    if not filename or '.' not in filename:
        return ''

    ext = filename.rsplit('.', 1)[-1].lower().strip()

    if not re.fullmatch(r'[a-zA-Z0-9]{1,10}', ext):
        return ''

    return f'.{ext}'


def _build_raw_source_url(doc_id):
    return f"/api/kb/raw-source/file/{doc_id}"


def _build_original_file_url(doc_id):
    return f"/api/kb/document/{doc_id}/original"


def _build_original_download_url(doc_id):
    return f"/api/kb/document/{doc_id}/original/download"


def _truncate_filename_bytes(filename, max_bytes=180):
    """
    Linux 单个文件名通常限制 255 bytes。
    这里保守截断到 180 bytes，避免中文文件名过长导致保存失败。
    """
    filename = filename or 'file'

    try:
        if len(filename.encode('utf-8')) <= max_bytes:
            return filename
    except Exception:
        return filename[:80]

    stem, ext = os.path.splitext(filename)
    ext_bytes = len(ext.encode('utf-8', errors='ignore'))
    max_stem_bytes = max(max_bytes - ext_bytes, 20)

    while stem and len(stem.encode('utf-8', errors='ignore')) > max_stem_bytes:
        stem = stem[:-1]

    return (stem or 'file') + ext


def _sanitize_raw_filename(filename, fallback_doc_id='file'):
    """
    尽量保留用户上传的原始文件名，仅去除路径和危险控制字符。
    不使用 werkzeug.secure_filename，因为它会把中文文件名处理得不可读。
    """
    raw = str(filename or '').strip()

    # 浏览器正常只给 basename；这里额外兼容包含路径的异常情况。
    raw = raw.replace('\\', '/')
    name = os.path.basename(raw).strip()

    name = name.replace('\x00', '')
    name = re.sub(r'[\x00-\x1f\x7f]', '_', name)

    # 文件系统路径分隔符必须替换。
    name = name.replace('/', '_').replace('\\', '_')

    # 避免特殊目录名。
    name = name.strip()
    if not name or name in ('.', '..'):
        name = str(fallback_doc_id or 'file')

    return _truncate_filename_bytes(name)


def _normalize_renamed_filename(old_filename, new_name):
    """
    前端重命名时，如果用户没有输入扩展名，则默认沿用旧扩展名。
    """
    old_filename = old_filename or ''
    new_name = (new_name or '').strip()

    if not new_name:
        return ''

    old_ext = os.path.splitext(old_filename)[1]
    new_ext = os.path.splitext(new_name)[1]

    if old_ext and not new_ext:
        new_name = new_name + old_ext

    return new_name


def _get_raw_path_owner_map(username=None):
    """
    返回当前 MongoDB 中仍然有效的 raw_source_path -> doc_id 映射。
    只统计 status != deleted 的文档。
    """
    owners = {}

    if _db is None:
        return owners

    base_dir = os.path.abspath(_RAW_SOURCE_DIR)

    query = {
        'status': {'$ne': 'deleted'},
        'raw_source_path': {'$exists': True, '$ne': ''}
    }

    if username:
        query['username'] = username

    try:
        docs = _db.kb_documents.find(
            query,
            {
                '_id': 0,
                'doc_id': 1,
                'username': 1,
                'raw_source_path': 1
            }
        )

        for doc in docs:
            raw_path = doc.get('raw_source_path') or ''
            raw_abs = os.path.abspath(raw_path) if raw_path else ''

            if raw_abs and _is_path_inside(raw_abs, base_dir):
                owners[raw_abs] = doc.get('doc_id', '')

    except Exception as e:
        print(f"⚠️ 获取源文件 owner map 失败: {e}")

    return owners


def _choose_raw_source_path(username, filename, doc_id, current_path=None):
    """
    根据原始文件名选择保存路径。

    优先：
        kb_raw_sources/<username>/<原始文件名>

    若该路径已被另一个有效文档占用，则自动追加序号：
        文件名 (2).ext
        文件名 (3).ext
    """
    base_dir = os.path.abspath(_RAW_SOURCE_DIR)
    user_dir = os.path.abspath(os.path.join(base_dir, str(username)))

    if not _is_path_inside(user_dir, base_dir):
        raise ValueError('invalid raw source user path')

    os.makedirs(user_dir, exist_ok=True)

    safe_name = _sanitize_raw_filename(filename, fallback_doc_id=doc_id)
    stem, ext = os.path.splitext(safe_name)

    owner_map = _get_raw_path_owner_map(username)
    current_abs = os.path.abspath(current_path) if current_path else ''

    def _candidate_available(candidate_path):
        candidate_abs = os.path.abspath(candidate_path)

        if not _is_path_inside(candidate_abs, base_dir):
            return False

        owner = owner_map.get(candidate_abs)

        if owner and owner != doc_id:
            return False

        if current_abs and candidate_abs == current_abs:
            return True

        # 文件存在但 MongoDB 没有引用，视为孤儿文件，可以覆盖。
        if os.path.exists(candidate_abs) and not owner:
            return True

        if os.path.exists(candidate_abs) and owner == doc_id:
            return True

        return not os.path.exists(candidate_abs)

    first_path = os.path.abspath(os.path.join(user_dir, safe_name))

    if _candidate_available(first_path):
        return first_path, safe_name

    for i in range(2, 1000):
        candidate_name = f"{stem} ({i}){ext}"
        candidate_name = _truncate_filename_bytes(candidate_name)
        candidate_path = os.path.abspath(os.path.join(user_dir, candidate_name))

        if _candidate_available(candidate_path):
            return candidate_path, candidate_name

    # 极端情况兜底。
    fallback_name = f"{stem}_{hashlib.md5(str(time.time()).encode()).hexdigest()[:8]}{ext}"
    fallback_name = _truncate_filename_bytes(fallback_name)
    fallback_path = os.path.abspath(os.path.join(user_dir, fallback_name))

    return fallback_path, fallback_name


def _resolve_legacy_doc_id_raw_source_path(doc):
    """
    查找旧版 doc_id.ext 命名的源文件。
    """
    if not doc:
        return ''

    username = doc.get('username') or ''
    doc_id = doc.get('doc_id') or ''

    if not username or not doc_id:
        return ''

    base_dir = os.path.abspath(_RAW_SOURCE_DIR)
    user_dir = os.path.abspath(os.path.join(base_dir, str(username)))

    if not _is_path_inside(user_dir, base_dir) or not os.path.isdir(user_dir):
        return ''

    try:
        for name in os.listdir(user_dir):
            if name == doc_id or name.startswith(f"{doc_id}."):
                candidate = os.path.abspath(os.path.join(user_dir, name))

                if (
                    os.path.isfile(candidate)
                    and _is_path_inside(candidate, base_dir)
                ):
                    return candidate

    except Exception:
        pass

    return ''


def _resolve_raw_source_path(doc):
    """
    解析文档对应的本地源文件路径。

    查找顺序：
    1. MongoDB raw_source_path；
    2. raw_source_filename / filename 对应的原始文件名；
    3. 旧版 doc_id.ext 命名。
    """
    if not doc:
        return ''

    base_dir = os.path.abspath(_RAW_SOURCE_DIR)
    raw_path = doc.get('raw_source_path') or ''

    if raw_path:
        raw_abs = os.path.abspath(raw_path)

        if (
            _is_path_inside(raw_abs, base_dir)
            and os.path.exists(raw_abs)
            and os.path.isfile(raw_abs)
        ):
            return raw_abs

    username = doc.get('username') or ''
    doc_id = doc.get('doc_id') or ''

    if not username or not doc_id:
        return ''

    user_dir = os.path.abspath(os.path.join(base_dir, str(username)))

    if not _is_path_inside(user_dir, base_dir) or not os.path.isdir(user_dir):
        return ''

    # 新版：按原始文件名查找。
    candidate_names = []

    if doc.get('raw_source_filename'):
        candidate_names.append(doc.get('raw_source_filename'))

    if doc.get('filename'):
        candidate_names.append(doc.get('filename'))

    seen = set()
    for name in candidate_names:
        safe_name = _sanitize_raw_filename(name, fallback_doc_id=doc_id)

        if safe_name in seen:
            continue

        seen.add(safe_name)

        candidate = os.path.abspath(os.path.join(user_dir, safe_name))

        if (
            _is_path_inside(candidate, base_dir)
            and os.path.exists(candidate)
            and os.path.isfile(candidate)
        ):
            return candidate

    # 旧版：按 doc_id.ext 查找。
    legacy = _resolve_legacy_doc_id_raw_source_path(doc)
    if legacy:
        return legacy

    return ''


def _save_raw_source_file(file_content, filename, username, doc_id):
    """
    保存用户上传的源文件。

    v4.6：优先使用用户原始文件名，而不是 doc_id.ext。
    """
    if not file_content:
        return {
            'raw_source_saved': False,
            'raw_source_error': 'empty file content'
        }

    save_path, storage_name = _choose_raw_source_path(
        username=username,
        filename=filename,
        doc_id=doc_id
    )

    base_dir = os.path.abspath(_RAW_SOURCE_DIR)
    save_path_abs = os.path.abspath(save_path)

    if not _is_path_inside(save_path_abs, base_dir):
        raise ValueError('invalid raw source file path')

    # 如果目标是孤儿文件，直接覆盖。
    with open(save_path_abs, 'wb') as f:
        f.write(file_content)

    raw_url = _build_raw_source_url(doc_id)
    original_url = _build_original_file_url(doc_id)
    original_download_url = _build_original_download_url(doc_id)

    print(f"   ✅ 原始文件已保存: {save_path_abs}")
    print(f"   📝 保存文件名: {storage_name}")
    print(f"   🔗 统一查看接口: {original_url}")
    print(f"   🔗 统一下载接口: {original_download_url}")

    return {
        'raw_source_saved': True,
        'raw_source_path': save_path_abs,
        'raw_source_url': raw_url,
        'raw_source_download_url': raw_url,
        'original_url': original_url,
        'original_download_url': original_download_url,

        # storage_name 是实际落盘文件名；filename 是用户上传或重命名后的展示名。
        'raw_source_filename': storage_name,
        'raw_source_original_filename': filename,
        'raw_source_storage_name': storage_name,

        'raw_source_size': len(file_content),
        'raw_source_saved_at': datetime.now(),
        'raw_source_managed': True,
        'raw_source_naming': 'original_filename',
    }


def _delete_raw_source_for_doc(doc):
    result = {
        'deleted': False,
        'path': '',
        'error': ''
    }

    try:
        if not doc:
            result['error'] = 'doc is empty'
            return result

        raw_path_abs = _resolve_raw_source_path(doc)
        result['path'] = raw_path_abs

        if not raw_path_abs:
            result['error'] = 'raw source path not found'
            return result

        base_dir = os.path.abspath(_RAW_SOURCE_DIR)

        if not _is_path_inside(raw_path_abs, base_dir):
            result['error'] = 'path outside raw source dir'
            return result

        if os.path.exists(raw_path_abs) and os.path.isfile(raw_path_abs):
            os.remove(raw_path_abs)
            result['deleted'] = True
            print(f"   🧹 已删除本地源文件: {raw_path_abs}")
        else:
            result['error'] = 'file not exists'

    except Exception as e:
        result['error'] = str(e)
        print(f"   ⚠️ 删除本地源文件失败: {e}")

    return result


def _rename_raw_source_for_doc(doc, new_filename):
    """
    重命名本地源文件，并返回需要写入 MongoDB 的字段。
    """
    result = {
        'success': True,
        'renamed': False,
        'old_path': '',
        'new_path': '',
        'old_filename': '',
        'new_filename': '',
        'message': '',
        'update_fields': {},
    }

    try:
        if not doc:
            result.update({
                'success': False,
                'message': 'doc is empty'
            })
            return result

        username = doc.get('username') or ''
        doc_id = doc.get('doc_id') or ''

        if not username or not doc_id:
            result.update({
                'success': False,
                'message': 'missing username or doc_id'
            })
            return result

        old_path = _resolve_raw_source_path(doc)

        if not old_path:
            result.update({
                'success': True,
                'renamed': False,
                'message': 'no local raw source file'
            })
            return result

        base_dir = os.path.abspath(_RAW_SOURCE_DIR)
        old_abs = os.path.abspath(old_path)

        if not _is_path_inside(old_abs, base_dir):
            result.update({
                'success': False,
                'message': 'old path outside raw source dir',
                'old_path': old_abs
            })
            return result

        new_path, storage_name = _choose_raw_source_path(
            username=username,
            filename=new_filename,
            doc_id=doc_id,
            current_path=old_abs
        )

        new_abs = os.path.abspath(new_path)

        result['old_path'] = old_abs
        result['new_path'] = new_abs
        result['old_filename'] = os.path.basename(old_abs)
        result['new_filename'] = storage_name

        if old_abs == new_abs:
            size = os.path.getsize(old_abs) if os.path.exists(old_abs) else 0
            update_fields = {
                'raw_source_path': old_abs,
                'raw_source_filename': storage_name,
                'raw_source_original_filename': new_filename,
                'raw_source_storage_name': storage_name,
                'raw_source_size': size,
                'raw_source_renamed_at': datetime.now(),
                'raw_source_naming': 'original_filename',
            }

            result['update_fields'] = update_fields
            result['message'] = 'source filename already correct'
            return result

        # 若目标位置存在但没有被 MongoDB 活跃文档引用，视作孤儿文件，删除后再重命名。
        if os.path.exists(new_abs):
            owner_map = _get_raw_path_owner_map(username)
            owner = owner_map.get(new_abs)

            if owner and owner != doc_id:
                result.update({
                    'success': False,
                    'message': f'target path occupied by another active doc: {owner}'
                })
                return result

            if not owner and os.path.isfile(new_abs):
                os.remove(new_abs)

        os.rename(old_abs, new_abs)

        size = os.path.getsize(new_abs) if os.path.exists(new_abs) else 0

        update_fields = {
            'raw_source_path': new_abs,
            'raw_source_filename': storage_name,
            'raw_source_original_filename': new_filename,
            'raw_source_storage_name': storage_name,
            'raw_source_size': size,
            'raw_source_renamed_at': datetime.now(),
            'raw_source_naming': 'original_filename',
        }

        result['renamed'] = True
        result['update_fields'] = update_fields
        result['message'] = 'raw source renamed'

        print(f"   ✏️ 本地源文件已重命名: {old_abs} -> {new_abs}")

        return result

    except Exception as e:
        traceback.print_exc()
        result.update({
            'success': False,
            'message': str(e)
        })
        return result


def _cleanup_empty_dirs(root_dir):
    root_dir = os.path.abspath(root_dir)

    if not os.path.isdir(root_dir):
        return 0

    removed = 0

    for current, dirs, files in os.walk(root_dir, topdown=False):
        current_abs = os.path.abspath(current)

        if current_abs == root_dir:
            continue

        try:
            if not os.listdir(current_abs):
                os.rmdir(current_abs)
                removed += 1
        except Exception:
            pass

    return removed


def _migrate_user_raw_sources_to_original_names(username=None, dry_run=False):
    """
    把旧版 doc_id.ext 命名的源文件迁移为原始文件名。

    只迁移 MongoDB 中明确有 raw_source_path 的活跃文档，避免误把同名文件分配给错误文档。
    """
    result = {
        'success': True,
        'dry_run': dry_run,
        'scope': username or 'all',
        'checked_docs': 0,
        'migrated': 0,
        'skipped': 0,
        'errors': [],
        'items': []
    }

    if _db is None:
        result['success'] = False
        result['errors'].append('MongoDB 未初始化')
        return result

    try:
        query = {
            'status': {'$ne': 'deleted'},
            'raw_source_path': {'$exists': True, '$ne': ''}
        }

        if username:
            query['username'] = username

        docs = list(_db.kb_documents.find(
            query,
            {
                '_id': 0,
                'doc_id': 1,
                'username': 1,
                'filename': 1,
                'raw_source_path': 1,
                'raw_source_filename': 1,
                'raw_source_original_filename': 1,
                'status': 1,
            }
        ))

        for doc in docs:
            result['checked_docs'] += 1

            doc_id = doc.get('doc_id')
            filename = doc.get('filename') or doc.get('raw_source_original_filename') or doc.get('raw_source_filename') or ''

            if not doc_id or not filename:
                result['skipped'] += 1
                continue

            raw_path = _resolve_raw_source_path(doc)

            if not raw_path:
                result['skipped'] += 1
                continue

            desired_safe = _sanitize_raw_filename(filename, fallback_doc_id=doc_id)

            # 已经是原始文件名或冲突序号形式时不强制迁移。
            current_base = os.path.basename(raw_path)

            if current_base == desired_safe or current_base.startswith(os.path.splitext(desired_safe)[0] + " ("):
                update_fields = {
                    'raw_source_path': os.path.abspath(raw_path),
                    'raw_source_filename': current_base,
                    'raw_source_storage_name': current_base,
                    'raw_source_original_filename': filename,
                    'raw_source_naming': 'original_filename',
                }

                if not dry_run:
                    _db.kb_documents.update_one(
                        {
                            'username': doc.get('username'),
                            'doc_id': doc_id
                        },
                        {
                            '$set': update_fields
                        }
                    )

                result['skipped'] += 1
                continue

            if dry_run:
                result['items'].append({
                    'doc_id': doc_id,
                    'filename': filename,
                    'old_path': raw_path,
                    'action': 'would_migrate'
                })
                continue

            rename_result = _rename_raw_source_for_doc(doc, filename)

            if rename_result.get('success'):
                update_fields = rename_result.get('update_fields') or {}

                if update_fields:
                    _db.kb_documents.update_one(
                        {
                            'username': doc.get('username'),
                            'doc_id': doc_id
                        },
                        {
                            '$set': update_fields
                        }
                    )

                if rename_result.get('renamed'):
                    result['migrated'] += 1
                else:
                    result['skipped'] += 1

                result['items'].append({
                    'doc_id': doc_id,
                    'filename': filename,
                    'old_path': rename_result.get('old_path', raw_path),
                    'new_path': rename_result.get('new_path', raw_path),
                    'renamed': rename_result.get('renamed', False),
                    'message': rename_result.get('message', '')
                })

            else:
                result['errors'].append({
                    'doc_id': doc_id,
                    'filename': filename,
                    'error': rename_result.get('message', 'unknown')
                })

    except Exception as e:
        traceback.print_exc()
        result['success'] = False
        result['errors'].append(str(e))

    return result


def _cleanup_orphan_raw_sources(username=None, dry_run=True):
    """
    清理 kb_raw_sources 中 MongoDB 已不再引用的多余文件。

    对当前用户而言：
    - 前端个人知识库不显示；
    - MongoDB 中也不存在活跃文档引用；
    - 但服务器 kb_raw_sources/<username>/ 下仍存在；
    则会被视作孤儿源文件。
    """
    base_dir = os.path.abspath(_RAW_SOURCE_DIR)

    result = {
        'success': True,
        'dry_run': dry_run,
        'scope': username or 'all',
        'base_dir': base_dir,
        'scanned_files': 0,
        'active_files': 0,
        'orphan_files': 0,
        'deleted_files': 0,
        'deleted_bytes': 0,
        'deleted_display': '0B',
        'empty_dirs_removed': 0,
        'orphans': [],
        'errors': []
    }

    if not os.path.isdir(base_dir):
        return result

    if _db is None:
        result['success'] = False
        result['errors'].append('MongoDB 未初始化')
        return result

    try:
        query = {
            'status': {'$ne': 'deleted'}
        }

        if username:
            query['username'] = username

        active_paths = set()

        docs = _db.kb_documents.find(
            query,
            {
                '_id': 0,
                'doc_id': 1,
                'username': 1,
                'filename': 1,
                'raw_source_path': 1,
                'raw_source_filename': 1,
                'raw_source_original_filename': 1,
                'status': 1
            }
        )

        for doc in docs:
            p = _resolve_raw_source_path(doc)

            if p:
                p_abs = os.path.abspath(p)

                if _is_path_inside(p_abs, base_dir):
                    active_paths.add(p_abs)

        result['active_files'] = len(active_paths)

        scan_root = base_dir

        if username:
            scan_root = os.path.abspath(os.path.join(base_dir, str(username)))

            if not _is_path_inside(scan_root, base_dir):
                result['success'] = False
                result['errors'].append('用户名路径非法')
                return result

            if not os.path.isdir(scan_root):
                return result

        for current, dirs, files in os.walk(scan_root):
            for name in files:
                path_abs = os.path.abspath(os.path.join(current, name))

                if not _is_path_inside(path_abs, base_dir):
                    continue

                result['scanned_files'] += 1

                if path_abs in active_paths:
                    continue

                size = 0

                try:
                    size = os.path.getsize(path_abs)
                except Exception:
                    pass

                result['orphan_files'] += 1
                result['deleted_bytes'] += size

                item = {
                    'path': path_abs,
                    'filename': name,
                    'size': size,
                    'size_display': _format_size(size)
                }

                result['orphans'].append(item)

                if not dry_run:
                    try:
                        os.remove(path_abs)
                        result['deleted_files'] += 1
                        print(f"   🧹 清理孤儿源文件: {path_abs}")
                    except Exception as e:
                        result['errors'].append({
                            'path': path_abs,
                            'error': str(e)
                        })

        if not dry_run:
            result['empty_dirs_removed'] = _cleanup_empty_dirs(scan_root)

        result['deleted_display'] = _format_size(result['deleted_bytes'])

        return result

    except Exception as e:
        traceback.print_exc()
        result['success'] = False
        result['errors'].append(str(e))
        return result


def _manage_user_raw_sources(username):
    """
    当前用户源文件目录维护：
    1. 迁移旧 doc_id.ext 命名为原始文件名；
    2. 删除 MongoDB 不再引用的多余文件。
    """
    result = {
        'success': True,
        'migration': None,
        'cleanup': None,
        'errors': []
    }

    try:
        if _AUTO_MIGRATE_RAW_SOURCE_NAMES:
            result['migration'] = _migrate_user_raw_sources_to_original_names(
                username=username,
                dry_run=False
            )

        if _AUTO_CLEAN_RAW_SOURCES_ON_LIST:
            result['cleanup'] = _cleanup_orphan_raw_sources(
                username=username,
                dry_run=False
            )

    except Exception as e:
        traceback.print_exc()
        result['success'] = False
        result['errors'].append(str(e))

    return result


def _extract_doc_id_from_upload_result(result):
    if not isinstance(result, dict):
        return ''

    for key in ('doc_id', 'document_id', 'documentId', 'id'):
        val = result.get(key)
        if val:
            return str(val)

    doc = result.get('document')
    if isinstance(doc, dict):
        for key in ('doc_id', 'document_id', 'documentId', 'id'):
            val = doc.get(key)
            if val:
                return str(val)

    data = result.get('data')
    if isinstance(data, dict):
        for key in ('doc_id', 'document_id', 'documentId', 'id'):
            val = data.get(key)
            if val:
                return str(val)

    return ''


def _find_uploaded_doc_for_raw_source(username, filename, folder_id, upload_started_at, upload_result=None):
    upload_result = upload_result or {}

    try:
        doc_id = _extract_doc_id_from_upload_result(upload_result)

        if doc_id:
            doc = _db.kb_documents.find_one(
                {
                    'username': username,
                    'doc_id': doc_id
                },
                {
                    '_id': 0
                }
            )

            if doc:
                return doc

        collection_id = (
            upload_result.get('collection_id')
            or upload_result.get('collectionId')
            or ''
        )

        if collection_id:
            doc = _db.kb_documents.find_one(
                {
                    'username': username,
                    'collection_id': collection_id
                },
                {
                    '_id': 0
                }
            )

            if doc:
                return doc

        query = {
            'username': username,
            'filename': filename,
            'status': {'$ne': 'deleted'}
        }

        if folder_id is None:
            query['$or'] = [
                {'folder_id': None},
                {'folder_id': {'$exists': False}},
                {'folder_id': ''}
            ]
        else:
            query['folder_id'] = folder_id

        if upload_started_at:
            query['upload_time'] = {'$gte': upload_started_at}

        doc = _db.kb_documents.find_one(
            query,
            {'_id': 0},
            sort=[('upload_time', -1)]
        )

        if doc:
            return doc

        query.pop('upload_time', None)

        doc = _db.kb_documents.find_one(
            query,
            {'_id': 0},
            sort=[('upload_time', -1)]
        )

        if doc:
            return doc

    except Exception as e:
        print(f"   ⚠️ 反查上传文档失败: {e}")

    return None


def _wait_for_uploaded_doc(username, filename, folder_id, upload_started_at,
                           upload_result=None, retries=8, delay=0.25):
    for _ in range(retries):
        doc = _find_uploaded_doc_for_raw_source(
            username,
            filename,
            folder_id,
            upload_started_at,
            upload_result
        )

        if doc:
            return doc

        time.sleep(delay)

    return None


def _get_user_info():
    username = session.get('username', '')
    name = session.get('name', username)
    role = session.get('role', 'student')
    return username, name, role


def _get_kb_stats(username):
    if not _fastgpt_kb_service:
        return {
            'documents': 0,
            'ready_documents': 0,
            'chunks': 0,
            'queries': 0,
            'rag_enabled': False
        }

    try:
        return _fastgpt_kb_service.get_user_stats(username)

    except AttributeError:
        try:
            stats = _fastgpt_kb_service.get_kb_stats(username)
            return {
                'documents': stats.get('total_documents', 0),
                'ready_documents': stats.get('ready_documents', 0),
                'chunks': stats.get('total_chunks', 0),
                'queries': stats.get('queries', 0),
                'rag_enabled': stats.get('ready_documents', 0) > 0
            }
        except Exception:
            pass

    except Exception:
        pass

    return {
        'documents': 0,
        'ready_documents': 0,
        'chunks': 0,
        'queries': 0,
        'rag_enabled': False
    }


def _get_document_storage_size(doc):
    if not isinstance(doc, dict):
        return 0

    sizes = []

    raw_source_size = _safe_int(doc.get('raw_source_size'), 0)
    if raw_source_size > 0:
        sizes.append(raw_source_size)

    file_size = _safe_int(doc.get('file_size'), 0)
    if file_size > 0:
        sizes.append(file_size)

    try:
        raw_path = _resolve_raw_source_path(doc)
        if raw_path and os.path.exists(raw_path):
            sizes.append(os.path.getsize(raw_path))
    except Exception:
        pass

    return max(sizes) if sizes else 0


def _get_user_quota_usage(username):
    usage = {
        'document_count': 0,
        'used_bytes': 0,
        'max_documents': _MAX_DOCUMENTS_PER_USER,
        'max_bytes': _MAX_TOTAL_STORAGE_BYTES_PER_USER,
    }

    if _db is None:
        print("⚠️ MongoDB _db 未初始化，无法统计上传配额")
        return usage

    try:
        usage['document_count'] = _db.kb_documents.count_documents({
            'username': username,
            'status': {'$nin': ['failed', 'deleted']}
        })
    except Exception as e:
        print(f"⚠️ 文档数量统计失败: {e}")

    try:
        docs = _db.kb_documents.find(
            {
                'username': username,
                'status': {'$ne': 'deleted'}
            },
            {
                'file_size': 1,
                'raw_source_size': 1,
                'raw_source_path': 1,
                'doc_id': 1,
                'username': 1,
                'filename': 1,
                'raw_source_filename': 1,
            }
        )

        total = 0

        for doc in docs:
            total += _get_document_storage_size(doc)

        usage['used_bytes'] = total

    except Exception as e:
        print(f"⚠️ 文档容量统计失败: {e}")

    return usage


def _check_user_upload_quota(username, incoming_size):
    incoming_size = _safe_int(incoming_size)
    usage = _get_user_quota_usage(username)

    current_count = usage.get('document_count', 0)
    used_bytes = usage.get('used_bytes', 0)

    if current_count >= _MAX_DOCUMENTS_PER_USER:
        return {
            'ok': False,
            'error': (
                f"已达到文档数量上限（{_MAX_DOCUMENTS_PER_USER} 个）。"
                f"当前已有 {current_count} 个文件，请删除部分文件后再上传。"
            ),
            'usage': usage
        }

    if used_bytes + incoming_size > _MAX_TOTAL_STORAGE_BYTES_PER_USER:
        remaining = max(_MAX_TOTAL_STORAGE_BYTES_PER_USER - used_bytes, 0)

        return {
            'ok': False,
            'error': (
                f"已超过个人知识库总容量上限。"
                f"当前已用 {_format_size(used_bytes)}，"
                f"总上限 {_format_size(_MAX_TOTAL_STORAGE_BYTES_PER_USER)}，"
                f"本次文件大小 {_format_size(incoming_size)}，"
                f"剩余可用 {_format_size(remaining)}。"
                f"请删除部分文件后再上传。"
            ),
            'usage': usage
        }

    usage['incoming_size'] = incoming_size
    usage['after_upload_bytes'] = used_bytes + incoming_size

    print(
        f"✅ 上传配额检查通过: "
        f"user={username}, "
        f"count={current_count}/{_MAX_DOCUMENTS_PER_USER}, "
        f"used={_format_size(used_bytes)}/{_format_size(_MAX_TOTAL_STORAGE_BYTES_PER_USER)}, "
        f"incoming={_format_size(incoming_size)}"
    )

    return {
        'ok': True,
        'usage': usage
    }


def _format_document(doc, username=None):
    shared_at = doc.get('shared_at')

    if shared_at and hasattr(shared_at, 'isoformat'):
        shared_at = shared_at.isoformat()

    doc_id = doc.get('doc_id', '')
    doc_username = doc.get('username') or username or ''

    raw_path = ''
    if doc_id:
        raw_path = _resolve_raw_source_path({
            **doc,
            'doc_id': doc_id,
            'username': doc_username,
        })

    has_original_file = bool(
        doc.get('fastgpt_image_url')
        or doc.get('embedded_image_url')
        or doc.get('raw_source_url')
        or doc.get('raw_source_path')
        or raw_path
    )

    media_url = (
        doc.get('fastgpt_image_url')
        or doc.get('embedded_image_url')
        or doc.get('raw_source_url')
        or ''
    )

    return {
        'doc_id': doc.get('doc_id', ''),
        'filename': doc.get('filename', '未知文件'),
        'file_type': doc.get('file_type', ''),
        'file_size': doc.get('file_size', 0),
        'status': doc.get('status', 'pending'),
        'chunk_count': doc.get('chunk_count', 0),
        'training_count': doc.get('training_count', 0),
        'data_count': doc.get('data_count', 0),
        'upload_time': doc.get('upload_time').isoformat() if doc.get('upload_time') else None,
        'collection_id': doc.get('collection_id', ''),
        'folder_id': doc.get('folder_id'),
        'shared': doc.get('shared', False),
        'shared_at': shared_at,

        'media_type': doc.get('media_type', ''),
        'parsed_from_media': doc.get('parsed_from_media', False),
        'parse_stage': doc.get('parse_stage', ''),
        'parse_progress': doc.get('parse_progress', 0),

        'has_original_file': has_original_file,
        'media_url': media_url,

        'raw_source_saved': bool(doc.get('raw_source_saved')),
        'raw_source_url': doc.get('raw_source_url', ''),
        'raw_source_download_url': doc.get('raw_source_download_url', ''),
        'raw_source_filename': doc.get('raw_source_filename', ''),
        'raw_source_original_filename': doc.get('raw_source_original_filename', ''),
        'raw_source_storage_name': doc.get('raw_source_storage_name', ''),
        'raw_source_size': doc.get('raw_source_size', 0),

        'original_url': _build_original_file_url(doc_id) if has_original_file and doc_id else '',
        'original_file_url': _build_original_file_url(doc_id) if has_original_file and doc_id else '',
        'original_download_url': _build_original_download_url(doc_id) if has_original_file and doc_id else '',
        'download_url': _build_original_download_url(doc_id) if has_original_file and doc_id else '',
    }


def _require_login(f):
    from functools import wraps

    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('username'):
            from flask import redirect, url_for
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated


# ================== 卡住文档检测 ==================

_STUCK_THRESHOLD_MINUTES = int(os.environ.get('STUCK_THRESHOLD_MINUTES', '10'))


def _detect_stuck_documents(documents):
    stuck = []
    now = datetime.now()

    for doc in documents:
        if doc.get('status') != 'processing':
            continue

        upload_time = doc.get('upload_time')

        if not upload_time:
            continue

        if isinstance(upload_time, str):
            try:
                upload_time = datetime.fromisoformat(
                    upload_time.replace('Z', '').replace('+00:00', '')
                )
            except Exception:
                continue

        elapsed = (now - upload_time).total_seconds() / 60.0

        if elapsed >= _STUCK_THRESHOLD_MINUTES:
            stuck.append({
                'doc_id': doc.get('doc_id', ''),
                'filename': doc.get('filename', ''),
                'elapsed_minutes': round(elapsed, 1)
            })

    return stuck


# ================== 模型健康检查 ==================

_health_cache = {}
_HEALTH_CACHE_TTL = 60


def _cached_health(cache_key, check_fn):
    now = time.time()

    if cache_key in _health_cache:
        cached_result, cached_ts = _health_cache[cache_key]

        if now - cached_ts < _HEALTH_CACHE_TTL:
            return cached_result

    result = check_fn()
    _health_cache[cache_key] = (result, now)

    return result


def _do_check_text_model():
    result = {
        'name': 'Qwen3-8B',
        'type': '文本理解/问答模型',
        'description': '用于知识库问答生成回答；不可用时无法智能问答'
    }

    api_url = _fastgpt_api_url
    api_key = _fastgpt_api_key

    if not api_url or not api_key:
        result.update({
            'available': False,
            'error': '未配置 FastGPT API'
        })
        return result

    base = api_url.rsplit('/api', 1)[0] if '/api' in api_url else api_url
    llm_url = f"{base}/api/v1/chat/completions"

    try:
        start = time.time()

        resp = http_requests.post(
            llm_url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'Qwen3-8B',
                'messages': [
                    {
                        'role': 'user',
                        'content': '你好'
                    }
                ],
                'max_tokens': 3,
                'stream': False
            },
            timeout=15
        )

        latency_ms = int((time.time() - start) * 1000)

        if resp.status_code == 200:
            body = resp.json()

            if body.get('choices'):
                result.update({
                    'available': True,
                    'latency_ms': latency_ms
                })
            else:
                result.update({
                    'available': False,
                    'error': 'API 返回无 choices'
                })

        else:
            result.update({
                'available': False,
                'error': f'HTTP {resp.status_code}: {resp.text[:200]}'
            })

    except http_requests.exceptions.ConnectionError:
        result.update({
            'available': False,
            'error': '无法连接到问答模型服务'
        })

    except http_requests.exceptions.Timeout:
        result.update({
            'available': False,
            'error': '问答模型连接超时'
        })

    except Exception as e:
        result.update({
            'available': False,
            'error': str(e)
        })

    return result


def _do_check_vlm():
    result = {
        'type': 'VLM 视觉模型',
        'description': '用于图片/视频/PPT 内容理解；不可用时无法解析多媒体',
        'models': []
    }

    if not _media_parser or not _media_parser.vlm_models:
        result.update({
            'available': False,
            'name': '无',
            'error': '未配置 VLM 模型'
        })
        return result

    any_ok = False

    for cfg in _media_parser.vlm_models:
        m = {
            'name': cfg.get('name', ''),
            'model': cfg.get('model', '')
        }

        try:
            start = time.time()

            resp = http_requests.post(
                cfg['api_url'],
                headers={
                    'Authorization': f"Bearer {cfg['api_key']}",
                    'Content-Type': 'application/json'
                },
                json={
                    'model': cfg['model'],
                    'messages': [
                        {
                            'role': 'user',
                            'content': '你好'
                        }
                    ],
                    'max_tokens': 3
                },
                timeout=10
            )

            latency_ms = int((time.time() - start) * 1000)

            if resp.status_code == 200 and resp.json().get('choices'):
                m.update({
                    'available': True,
                    'latency_ms': latency_ms
                })
                any_ok = True
            else:
                m.update({
                    'available': False,
                    'error': f'HTTP {resp.status_code}'
                })

        except Exception as e:
            m.update({
                'available': False,
                'error': str(e)[:100]
            })

        result['models'].append(m)

    result['available'] = any_ok
    result['name'] = next(
        (m['name'] for m in result['models'] if m.get('available')),
        result['models'][0]['name'] if result['models'] else '无'
    )

    if not any_ok:
        result['error'] = '所有 VLM 模型均不可用'

    return result


def _check_text_health():
    return _cached_health('text_model', _do_check_text_model)


def _check_vlm_health():
    return _cached_health('vlm', _do_check_vlm)


def _get_user_dataset_id(username):
    try:
        user_kb = _db.user_fastgpt_kb.find_one({
            'username': username
        })

        if user_kb and user_kb.get('dataset_id'):
            return user_kb['dataset_id']

        if _fastgpt_kb_service:
            if hasattr(_fastgpt_kb_service, 'get_or_create_user_dataset'):
                return _fastgpt_kb_service.get_or_create_user_dataset(username)

            if hasattr(_fastgpt_kb_service, '_user_dataset_cache'):
                return _fastgpt_kb_service._user_dataset_cache.get(username)

    except Exception:
        pass

    return None


# ================== API 路由 ==================

@kb_bp.route('/api/kb/stats')
@_require_login
def api_kb_stats():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化',
            'documents': 0,
            'chunks': 0,
            'queries': 0,
            'rag_enabled': False
        })

    try:
        stats = _get_kb_stats(username)
        quota_usage = _get_user_quota_usage(username)

        stats['quota'] = {
            'document_count': quota_usage.get('document_count', 0),
            'max_documents': quota_usage.get('max_documents', _MAX_DOCUMENTS_PER_USER),
            'used_bytes': quota_usage.get('used_bytes', 0),
            'used_display': _format_size(quota_usage.get('used_bytes', 0)),
            'max_bytes': quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER),
            'max_display': _format_size(
                quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER)
            ),
            'remaining_bytes': max(
                quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER)
                - quota_usage.get('used_bytes', 0),
                0
            ),
            'remaining_display': _format_size(max(
                quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER)
                - quota_usage.get('used_bytes', 0),
                0
            )),
            'limits': {
                'document_mb': _MAX_DOCUMENT_MB,
                'ppt_mb': _MAX_PPT_MB,
                'image_mb': _MAX_IMAGE_MB,
                'video_mb': _MAX_VIDEO_MB
            }
        }

        return jsonify({
            'success': True,
            **stats
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'documents': 0,
            'chunks': 0,
            'queries': 0,
            'rag_enabled': False
        })


@kb_bp.route('/api/kb/upload', methods=['POST'])
@_require_login
def api_kb_upload():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    if 'file' not in request.files:
        return jsonify({
            'success': False,
            'error': '未选择文件'
        })

    file = request.files['file']

    if file.filename == '':
        return jsonify({
            'success': False,
            'error': '未选择文件'
        })

    folder_id = request.form.get('folder_id', None)

    if folder_id in ('', 'null', 'undefined'):
        folder_id = None

    filename = file.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    text_extensions = _TEXT_EXTS
    media_extensions = set(_media_parser.ALL_EXTENSIONS) if _media_parser else set()
    all_allowed = text_extensions | media_extensions

    if ext not in all_allowed:
        return jsonify({
            'success': False,
            'error': f'不支持的文件类型: .{ext}，支持: {", ".join(sorted(all_allowed))}'
        })

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    max_size, limit_message = _get_upload_file_limit(ext)

    if file_size > max_size:
        return jsonify({
            'success': False,
            'error': f'文件过大：当前文件 {_format_size(file_size)}，{limit_message}',
            'limit': {
                'file_size': file_size,
                'file_size_display': _format_size(file_size),
                'max_size': max_size,
                'max_size_display': _format_size(max_size),
                'ext': ext
            }
        })

    try:
        quota_check = _check_user_upload_quota(username, file_size)

        if not quota_check.get('ok'):
            usage = quota_check.get('usage', {})

            return jsonify({
                'success': False,
                'error': quota_check.get('error', '已超过个人知识库限制'),
                'quota': {
                    'document_count': usage.get('document_count', 0),
                    'max_documents': usage.get('max_documents', _MAX_DOCUMENTS_PER_USER),
                    'used_bytes': usage.get('used_bytes', 0),
                    'used_display': _format_size(usage.get('used_bytes', 0)),
                    'max_bytes': usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER),
                    'max_display': _format_size(
                        usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER)
                    ),
                    'incoming_size': file_size,
                    'incoming_display': _format_size(file_size)
                }
            })

    except Exception as e:
        print(f"⚠️ 上传配额检查失败，为安全起见拒绝上传: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': '上传配额检查失败，请稍后重试',
            'detail': str(e)
        })

    try:
        file_content = file.read()
        file.seek(0)
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'读取上传文件失败: {str(e)}'
        })

    # ================== 多媒体上传：图片 / 视频 / PPT ==================
    if ext in media_extensions and _media_parser:
        try:
            _ts = datetime.now().strftime('%Y%m%d%H%M%S')
            _h = hashlib.md5(f"{username}_{filename}_{_ts}".encode()).hexdigest()[:8]
            doc_id = f"doc_{username}_{_h}"
            media_type_val = _media_parser.get_media_type(filename)
            captured_dataset_id = _get_user_dataset_id(username)

            try:
                raw_source_info = _save_raw_source_file(
                    file_content=file_content,
                    filename=filename,
                    username=username,
                    doc_id=doc_id
                )
            except Exception as e:
                traceback.print_exc()
                raw_source_info = {
                    'raw_source_saved': False,
                    'raw_source_error': str(e)
                }
                print(f"   ⚠️ 原始文件本地保存失败: {e}")

            init_doc_fields = {
                'doc_id': doc_id,
                'username': username,
                'filename': filename,
                'file_type': ext,
                'dataset_id': captured_dataset_id,
                'folder_id': folder_id,
                'status': 'parsing',
                'upload_time': datetime.now(),
                'file_size': file_size,
                'parsed_from_media': True,
                'media_type': media_type_val,
                'shared': False
            }

            init_doc_fields.update(raw_source_info)

            _db.kb_documents.update_one(
                {
                    'doc_id': doc_id
                },
                {
                    '$set': init_doc_fields
                },
                upsert=True
            )

            def _async_parse():
                try:
                    def _on_progress(stage, pct):
                        try:
                            _db.kb_documents.update_one(
                                {
                                    'doc_id': doc_id
                                },
                                {
                                    '$set': {
                                        'parse_stage': stage,
                                        'parse_progress': pct
                                    }
                                }
                            )
                        except Exception:
                            pass

                    result = _media_parser.parse(
                        file_content,
                        filename,
                        username,
                        on_progress=_on_progress
                    )

                    if not result.get('success'):
                        _db.kb_documents.update_one(
                            {
                                'doc_id': doc_id
                            },
                            {
                                '$set': {
                                    'status': 'failed',
                                    'error_message': result.get('error', '多媒体解析失败')
                                }
                            }
                        )
                        return

                    parsed_text = result.get('text', '')
                    metadata = result.get('metadata', {})

                    if not parsed_text.strip():
                        _db.kb_documents.update_one(
                            {
                                'doc_id': doc_id
                            },
                            {
                                '$set': {
                                    'status': 'failed',
                                    'error_message': '解析结果为空'
                                }
                            }
                        )
                        return

                    embedded_img_url = ''

                    if media_type_val == 'image':
                        print("   🔄 正在上传图片到 FastGPT...")

                        fastgpt_result = _upload_image_to_fastgpt(
                            file_content,
                            filename,
                            dataset_id=captured_dataset_id
                        )

                        if fastgpt_result.get('success'):
                            embedded_img_url = fastgpt_result['url']

                            _db.kb_documents.update_one(
                                {
                                    'doc_id': doc_id
                                },
                                {
                                    '$set': {
                                        'fastgpt_image_url': embedded_img_url,
                                        'image_url_source': 'fastgpt',
                                        'fastgpt_image_file_id': fastgpt_result.get('file_id', ''),
                                        'fastgpt_image_bucket': fastgpt_result.get('bucket_name', '')
                                    }
                                }
                            )

                        else:
                            print(
                                f"   ⚠️ 图片上传到 FastGPT 失败: "
                                f"{fastgpt_result.get('error', '?')[:120]}"
                            )

                    if embedded_img_url and media_type_val == 'image':
                        image_header = (
                            f"## 📎 图片文件：{filename}\n\n"
                            f"![{filename}]({embedded_img_url})\n\n"
                            f"图片直链：{embedded_img_url}\n\n"
                            f"---\n\n"
                            f"以下是对该图片的 AI 描述：\n\n"
                        )
                        parsed_text = image_header + parsed_text

                    _db.kb_documents.update_one(
                        {
                            'doc_id': doc_id
                        },
                        {
                            '$set': {
                                'parsed_text': parsed_text,
                                'parse_metadata': metadata,
                                'embedded_image_url': embedded_img_url
                            }
                        }
                    )

                    metadata_for_upload = (
                        dict(metadata)
                        if isinstance(metadata, dict)
                        else {
                            'raw_metadata': metadata
                        }
                    )

                    metadata_for_upload.update({
                        'doc_id': doc_id,
                        'source_doc_id': doc_id,
                        'original_doc_id': doc_id,

                        'username': username,
                        'filename': filename,
                        'file_type': ext,
                        'folder_id': folder_id,
                        'dataset_id': captured_dataset_id,

                        'media_type': media_type_val,
                        'parsed_from_media': True,

                        'file_size': file_size,
                        'raw_source_size': raw_source_info.get('raw_source_size', file_size),
                        'raw_source_path': raw_source_info.get('raw_source_path', ''),
                        'raw_source_url': raw_source_info.get('raw_source_url', ''),
                        'raw_source_download_url': raw_source_info.get('raw_source_download_url', ''),
                        'original_url': raw_source_info.get('original_url', ''),
                        'original_download_url': raw_source_info.get('original_download_url', ''),
                        'raw_source_saved': raw_source_info.get('raw_source_saved', False),
                        'raw_source_filename': raw_source_info.get('raw_source_filename', filename),
                        'raw_source_original_filename': raw_source_info.get('raw_source_original_filename', filename),
                        'raw_source_storage_name': raw_source_info.get('raw_source_storage_name', ''),

                        'embedded_image_url': embedded_img_url,
                        'fastgpt_image_url': embedded_img_url
                    })

                    upload_result = _fastgpt_kb_service.upload_parsed_text(
                        username=username,
                        text_content=parsed_text,
                        original_filename=filename,
                        folder_id=folder_id,
                        metadata=metadata_for_upload
                    )

                    if not upload_result.get('success'):
                        _db.kb_documents.update_one(
                            {
                                'doc_id': doc_id
                            },
                            {
                                '$set': {
                                    'status': 'failed',
                                    'error_message': upload_result.get('error', '上传失败')
                                }
                            }
                        )
                        return

                    collection_id = upload_result.get('collection_id', '')
                    chunk_count = upload_result.get('chunk_count', 0)

                    if not collection_id:
                        _db.kb_documents.update_one(
                            {
                                'username': username,
                                'doc_id': doc_id
                            },
                            {
                                '$set': {
                                    'status': 'failed',
                                    'error_message': '解析文本已上传，但未返回 collection_id'
                                }
                            }
                        )
                        return

                    update_fields = {
                        'status': 'processing',
                        'collection_id': collection_id,
                        'chunk_count': chunk_count,
                        'data_count': chunk_count,
                        'updated_at': datetime.now()
                    }

                    _db.kb_documents.update_one(
                        {
                            'username': username,
                            'doc_id': doc_id
                        },
                        {
                            '$set': update_fields
                        }
                    )

                    delete_result = _db.kb_documents.delete_many({
                        'username': username,
                        'collection_id': collection_id,
                        'doc_id': {
                            '$ne': doc_id
                        }
                    })

                    if delete_result.deleted_count > 0:
                        print(
                            f"   🧹 清理重复临时文档: "
                            f"collection_id={collection_id}, "
                            f"deleted={delete_result.deleted_count}"
                        )

                    print(f"✅ 异步解析完成: {filename} → {chunk_count} 块")

                except Exception as e:
                    traceback.print_exc()

                    try:
                        _db.kb_documents.update_one(
                            {
                                'doc_id': doc_id
                            },
                            {
                                '$set': {
                                    'status': 'failed',
                                    'error_message': f'异步解析异常: {str(e)}'
                                }
                            },
                            upsert=True
                        )
                    except Exception:
                        pass

            thread = threading.Thread(target=_async_parse, daemon=True)
            thread.start()

            try:
                _cleanup_orphan_raw_sources(username=username, dry_run=False)
            except Exception:
                pass

            return jsonify({
                'success': True,
                'doc_id': doc_id,
                'status': 'parsing',
                'message': f'多媒体文件已开始解析（{media_type_val}），请稍候...',
                'media_type': media_type_val,
                'raw_source_saved': raw_source_info.get('raw_source_saved', False),
                'raw_source_filename': raw_source_info.get('raw_source_filename', filename),
                'original_url': raw_source_info.get('original_url', ''),
                'original_download_url': raw_source_info.get('original_download_url', '')
            })

        except Exception as e:
            traceback.print_exc()
            return jsonify({
                'success': False,
                'error': str(e)
            })

    # ================== 普通文档上传：PDF / TXT / MD / DOC / DOCX ==================
    try:
        upload_started_at = datetime.now()

        file.seek(0)

        result = _fastgpt_kb_service.upload_file(
            username,
            file,
            file.filename,
            folder_id
        )

        if result.get('success'):
            doc_id = _extract_doc_id_from_upload_result(result)
            doc = None

            if doc_id:
                for _ in range(8):
                    doc = _db.kb_documents.find_one(
                        {
                            'username': username,
                            'doc_id': doc_id
                        },
                        {
                            '_id': 0
                        }
                    )

                    if doc:
                        break

                    time.sleep(0.25)

            if not doc:
                doc = _wait_for_uploaded_doc(
                    username,
                    filename,
                    folder_id,
                    upload_started_at,
                    result,
                    retries=8,
                    delay=0.25
                )

            if doc:
                doc_id = doc.get('doc_id')

                try:
                    raw_source_info = _save_raw_source_file(
                        file_content=file_content,
                        filename=filename,
                        username=username,
                        doc_id=doc_id
                    )

                    update_fields = dict(raw_source_info)
                    update_fields.update({
                        'file_size': file_size,
                        'raw_source_managed': True,
                        'updated_at': datetime.now()
                    })

                    _db.kb_documents.update_one(
                        {
                            'username': username,
                            'doc_id': doc_id
                        },
                        {
                            '$set': update_fields
                        }
                    )

                    result.update({
                        'doc_id': doc_id,
                        'raw_source_saved': raw_source_info.get('raw_source_saved', False),
                        'raw_source_url': raw_source_info.get('raw_source_url', ''),
                        'raw_source_download_url': raw_source_info.get('raw_source_download_url', ''),
                        'raw_source_filename': raw_source_info.get('raw_source_filename', filename),
                        'original_url': raw_source_info.get('original_url', ''),
                        'original_download_url': raw_source_info.get('original_download_url', '')
                    })

                    print(
                        f"   ✅ 普通文档源文件已保存: "
                        f"doc_id={doc_id}, filename={filename}, "
                        f"raw={raw_source_info.get('raw_source_filename')}"
                    )

                except Exception as e:
                    traceback.print_exc()
                    result.update({
                        'raw_source_saved': False,
                        'raw_source_error': str(e)
                    })
                    print(f"   ⚠️ 普通文档源文件保存失败: {e}")

            else:
                print(
                    f"   ⚠️ 普通文档上传成功，但未能定位 MongoDB 文档，"
                    f"暂无法保存 raw_source。filename={filename}, result={result}"
                )
                result.update({
                    'raw_source_saved': False,
                    'raw_source_error': 'upload success but document record not found'
                })

            try:
                _cleanup_orphan_raw_sources(username=username, dry_run=False)
            except Exception:
                pass

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/documents')
@_require_login
def api_kb_documents():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化',
            'documents': [],
            'total': 0,
            'has_processing': False
        })

    raw_source_manage_result = None

    try:
        raw_source_manage_result = _manage_user_raw_sources(username)
    except Exception as e:
        print(f"⚠️ 当前用户源文件自动整理失败: {e}")

    try:
        if hasattr(_fastgpt_kb_service, 'get_documents_with_realtime_status'):
            result = _fastgpt_kb_service.get_documents_with_realtime_status(username)
        else:
            documents = list(
                _db.kb_documents.find(
                    {
                        'username': username
                    },
                    {
                        '_id': 0
                    }
                ).sort('upload_time', -1)
            )
            result = {
                'success': True,
                'documents': documents,
                'total': len(documents),
                'has_processing': any(d.get('status') == 'processing' for d in documents)
            }

        if result.get('success'):
            documents = result.get('documents', [])
            formatted_docs = [_format_document(doc, username=username) for doc in documents]
            has_processing = result.get('has_processing', False)
            has_parsing = any(d.get('status') == 'parsing' for d in documents)

            model_warning = None
            stuck_docs = _detect_stuck_documents(documents)

            if stuck_docs:
                model_warning = {
                    'type': 'processing_slow',
                    'message': (
                        f"⏳ {len(stuck_docs)} 个文档已处理超过 "
                        f"{_STUCK_THRESHOLD_MINUTES} 分钟，"
                        f"可能是 FastGPT 队列积压，请耐心等待。"
                    ),
                    'stuck_count': len(stuck_docs),
                    'stuck_docs': stuck_docs
                }

            return jsonify({
                'success': True,
                'documents': formatted_docs,
                'total': len(formatted_docs),
                'has_processing': has_processing or has_parsing,
                'model_warning': model_warning,
                'raw_source_manage': raw_source_manage_result
            })

        return jsonify({
            'success': False,
            'error': result.get('error', '获取失败'),
            'documents': [],
            'total': 0,
            'has_processing': False
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'documents': [],
            'total': 0,
            'has_processing': False
        })


@kb_bp.route('/api/kb/chat', methods=['POST'])
@_require_login
def api_kb_chat():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)

    if not query:
        return jsonify({
            'success': False,
            'error': '问题不能为空'
        })

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.chat(username, query, top_k)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'answer': '抱歉，处理您的问题时出现了错误。'
        })


@kb_bp.route('/api/kb/search', methods=['POST'])
@_require_login
def api_kb_search():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)

    if not query:
        return jsonify({
            'success': False,
            'error': '搜索内容不能为空'
        })

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.search(username, query, top_k)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'results': []
        })


@kb_bp.route('/api/kb/dataset-id', methods=['GET'])
def api_kb_get_dataset_id():
    student_id = request.args.get('student_id', '').strip()

    if not student_id:
        return jsonify({
            'success': False,
            'error': '缺少 student_id 参数',
            'dataset_id': None
        })

    try:
        user_kb = _db.user_fastgpt_kb.find_one({
            'username': student_id
        })

        if user_kb and user_kb.get('dataset_id'):
            return jsonify({
                'success': True,
                'student_id': student_id,
                'dataset_id': user_kb['dataset_id'],
                'dataset_name': f'个人知识库_{student_id}'
            })

        if _fastgpt_kb_service:
            dataset_id = None

            if hasattr(_fastgpt_kb_service, '_find_existing_user_dataset'):
                dataset_id = _fastgpt_kb_service._find_existing_user_dataset(student_id)
            elif hasattr(_fastgpt_kb_service, '_user_dataset_cache'):
                dataset_id = _fastgpt_kb_service._user_dataset_cache.get(student_id)

            if dataset_id:
                _db.user_fastgpt_kb.update_one(
                    {
                        'username': student_id
                    },
                    {
                        '$set': {
                            'dataset_id': dataset_id,
                            'updated_at': datetime.now()
                        }
                    },
                    upsert=True
                )

                return jsonify({
                    'success': True,
                    'student_id': student_id,
                    'dataset_id': dataset_id,
                    'dataset_name': f'个人知识库_{student_id}'
                })

        return jsonify({
            'success': False,
            'error': f'未找到用户 {student_id} 的知识库',
            'dataset_id': None
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'dataset_id': None
        })


@kb_bp.route('/api/kb/list-all-datasets', methods=['GET'])
def api_kb_list_all_datasets():
    try:
        mappings = list(
            _db.user_fastgpt_kb.find(
                {},
                {
                    '_id': 0
                }
            )
        )

        return jsonify({
            'success': True,
            'total': len(mappings),
            'mappings': mappings
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/smart-chat', methods=['POST'])
@_require_login
def api_kb_smart_chat():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()

    if not query:
        return jsonify({
            'success': False,
            'error': '问题不能为空'
        })

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.chat(username, query, top_k=5)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


# ================== workflow-search 引用增强 ==================

def _normalize_workflow_score(score):
    if isinstance(score, (list, tuple)):
        if len(score) > 0:
            if isinstance(score[0], dict):
                try:
                    return float(score[0].get('value', 0))
                except Exception:
                    return 0.0
            try:
                return float(score[0])
            except Exception:
                return 0.0
        return 0.0

    try:
        return float(score) if score else 0.0
    except (TypeError, ValueError):
        return 0.0


def _clean_quote_text(text):
    if text is None:
        return ''

    return (
        str(text)
        .replace('\u00a0', ' ')
        .replace('\u202f', ' ')
        .replace('\ufeff', '')
    )


def _normalize_quote_content_for_dedupe(text):
    s = _clean_quote_text(text)

    s = re.sub(r'^【文件】.*?【正文片段】\s*', '', s, flags=re.S)
    s = re.sub(r'^【文件名命中】.*?【正文片段\s*\d*】\s*', '', s, flags=re.S)
    s = re.sub(r'引用ID：[a-fA-F0-9]{24}', '', s)
    s = re.sub(r'\s+', '', s)

    return s[:500]


def _dedupe_quote_list(quote_list):
    seen_ids = set()
    seen_content = set()
    deduped = []

    for item in quote_list or []:
        if not isinstance(item, dict):
            continue

        item = item.copy()

        qid = str(item.get('id') or item.get('_id') or '').strip()

        source = (
            item.get('sourceName')
            or item.get('source')
            or item.get('filename')
            or ''
        )
        source = _clean_quote_text(source)

        if 'sourceName' in item:
            item['sourceName'] = source

        if 'source' in item:
            item['source'] = source

        item['q'] = _clean_quote_text(item.get('q', ''))
        item['a'] = _clean_quote_text(item.get('a', ''))

        if qid:
            if qid in seen_ids:
                continue
            seen_ids.add(qid)

        content_sig = (
            source,
            _normalize_quote_content_for_dedupe(
                (item.get('q') or '') + '\n' + (item.get('a') or '')
            )
        )

        if content_sig[1] and content_sig in seen_content:
            continue

        seen_content.add(content_sig)
        deduped.append(item)

    return deduped


def _is_fastgpt_object_id(val):
    if not val:
        return False
    return bool(re.fullmatch(r'[a-fA-F0-9]{24}', str(val).strip()))


def _extract_fastgpt_chunk_id(item):
    if not isinstance(item, dict):
        return ''

    candidates = []

    for key in (
        '_id',
        'id',
        'dataId',
        'data_id',
        'datasetDataId',
        'datasetData_id',
        'datasetDataID'
    ):
        val = item.get(key)
        if val:
            candidates.append(str(val))

    for parent_key in (
        'data',
        'datasetData',
        'datasetDataItem',
        'rawData',
        'item'
    ):
        sub = item.get(parent_key)

        if isinstance(sub, dict):
            for key in (
                '_id',
                'id',
                'dataId',
                'data_id',
                'datasetDataId',
                'datasetData_id'
            ):
                val = sub.get(key)
                if val:
                    candidates.append(str(val))

    for val in candidates:
        if _is_fastgpt_object_id(val):
            return val

    return candidates[0] if candidates else ''


def _looks_like_filename_only_hit(text, source=''):
    s = (text or '').strip()

    if not s:
        return False

    head = s[:200]

    filename_hit_signals = [
        '文件：',
        '[文件：',
        '共',
        '知识块',
        '文件名命中'
    ]

    if len(s) < 800 and ('文件' in head and '知识块' in head):
        return True

    if len(s) < 500 and any(x in head for x in filename_hit_signals):
        return True

    return False


def _extract_list_from_fastgpt_response(body):
    if isinstance(body, list):
        return body

    if not isinstance(body, dict):
        return []

    data = body.get('data', body)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ('list', 'data', 'records', 'items', 'rows'):
            val = data.get(key)

            if isinstance(val, list):
                return val

    for key in ('list', 'data', 'records', 'items', 'rows'):
        val = body.get(key)

        if isinstance(val, list):
            return val

    return []


def _fetch_collection_chunks_from_fastgpt(collection_id, dataset_id='', limit=5):
    if not collection_id or not _fastgpt_api_url or not _fastgpt_api_key:
        return []

    url = f"{_fastgpt_api_url}/core/dataset/data/list"

    headers = {
        'Authorization': f'Bearer {_fastgpt_api_key}',
        'Content-Type': 'application/json'
    }

    base_payload = {
        'collectionId': collection_id
    }

    if dataset_id:
        base_payload['datasetId'] = dataset_id

    payload_candidates = [
        {
            **base_payload,
            'pageNum': 1,
            'pageSize': limit
        },
        {
            **base_payload,
            'offset': 0,
            'pageSize': limit
        },
        {
            **base_payload,
            'limit': limit
        },
        {
            **base_payload,
            'pageSize': limit
        }
    ]

    for payload in payload_candidates:
        try:
            resp = http_requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=8
            )

            if resp.status_code != 200:
                continue

            body = resp.json()
            items = _extract_list_from_fastgpt_response(body)

            chunks = []

            for idx, it in enumerate(items[:limit]):
                if not isinstance(it, dict):
                    continue

                q = (
                    it.get('q')
                    or it.get('content')
                    or it.get('text')
                    or it.get('question')
                    or ''
                )
                a = it.get('a') or it.get('answer') or ''

                q = _clean_quote_text(q).strip()
                a = _clean_quote_text(a).strip()

                if not q and not a:
                    continue

                data_id = _extract_fastgpt_chunk_id(it)

                chunks.append({
                    'id': str(data_id) if data_id else '',
                    'q': q,
                    'a': a,
                    'chunkIndex': it.get('chunkIndex', idx)
                })

            if chunks:
                return chunks

        except Exception as e:
            print(f"   ⚠️ 回查 FastGPT chunk 失败 payload={payload}: {str(e)[:120]}")

    return []


def _get_local_parsed_text_by_collection(student_id, collection_id, source_name='', limit_chars=2500):
    try:
        query = {
            'username': student_id,
            'collection_id': collection_id
        }

        doc = _db.kb_documents.find_one(query)

        if not doc and source_name:
            doc = _db.kb_documents.find_one({
                'username': student_id,
                'filename': source_name
            })

        if not doc:
            return ''

        text = (
            doc.get('parsed_text')
            or doc.get('content')
            or doc.get('text')
            or ''
        )

        text = _clean_quote_text(text).strip()

        if not text:
            return ''

        return text[:limit_chars]

    except Exception as e:
        print(f"   ⚠️ 本地 parsed_text 回退失败: {str(e)[:120]}")
        return ''


def _enrich_filename_hit_content(student_id, source, collection_id, dataset_id, original_q):
    source = _clean_quote_text(source or '未知文件')
    original_q = _clean_quote_text(original_q or '')

    chunks = _fetch_collection_chunks_from_fastgpt(
        collection_id=collection_id,
        dataset_id=dataset_id,
        limit=5
    )

    if chunks:
        parts = [
            f"【文件名命中】{source}",
            f"【说明】用户问题命中了该文件名，已自动补充该文件下的正文知识块。"
        ]

        for idx, ch in enumerate(chunks, 1):
            chunk_text = ch.get('q', '')

            if ch.get('a'):
                chunk_text += "\n" + ch.get('a', '')

            chunk_text = _clean_quote_text(chunk_text).strip()
            cite_id = ch.get('id', '')

            if chunk_text:
                parts.append(
                    f"\n【正文片段 {idx}】\n"
                    f"引用ID：{cite_id}\n"
                    f"{chunk_text[:1200]}"
                )

        return {
            'text': '\n'.join(parts),
            'first_data_id': chunks[0].get('id', ''),
            'chunks': chunks
        }

    local_text = _get_local_parsed_text_by_collection(
        student_id=student_id,
        collection_id=collection_id,
        source_name=source,
        limit_chars=2500
    )

    if local_text:
        return {
            'text': (
                f"【文件名命中】{source}\n"
                f"【说明】用户问题命中了该文件名，以下为本地解析内容片段。\n\n"
                f"{local_text}"
            ),
            'first_data_id': '',
            'chunks': []
        }

    return {
        'text': (
            f"【文件名命中】{source}\n"
            f"【说明】用户问题命中了该文件，但暂未回查到更多正文 chunk。"
            f"请基于文件名和已有摘要回答，严禁回答未找到。\n\n"
            f"【已有摘要】\n{original_q}"
        ),
        'first_data_id': '',
        'chunks': []
    }


def _build_workflow_answer_context(query, quote_list):
    query = _clean_quote_text(query)

    if not quote_list:
        return (
            "【检索状态】found=false\n"
            "【result_count】0\n"
            "【must_answer】false\n"
            "【说明】个人知识库未返回相关结果。\n"
        )

    file_names = []

    for q in quote_list:
        name = _clean_quote_text(q.get('sourceName') or q.get('source') or '')

        if name and name not in file_names:
            file_names.append(name)

    lines = [
        "【检索状态】found=true",
        f"【result_count】{len(quote_list)}",
        "【must_answer】true",
        "【强制规则】已经在个人知识库中找到相关文件或片段，必须基于以下内容回答，严禁回答“未找到相关信息”。",
        f"【用户问题】{query}"
    ]

    if file_names:
        lines.append("【参考文件】" + "、".join([f"《{x}》" for x in file_names]))

    for idx, item in enumerate(quote_list, 1):
        cite_id = _clean_quote_text(item.get('id', ''))
        source_name = _clean_quote_text(item.get('sourceName', ''))
        q_text = _clean_quote_text(item.get('q', ''))
        a_text = _clean_quote_text(item.get('a', ''))

        content = q_text

        if a_text:
            content += "\n" + a_text

        lines.append(
            f"\n【检索结果 {idx}】\n"
            f"引用ID：{cite_id}\n"
            f"文件名：{source_name}\n"
            f"内容：\n{content}\n"
            f"引用格式要求：回答使用 [{cite_id}](CITE)"
        )

    return "\n".join(lines)


@kb_bp.route('/api/kb/workflow-search', methods=['POST'])
def api_kb_workflow_search():
    data = request.get_json() or {}
    student_id = (data.get('student_id') or '').strip()
    query = (data.get('query') or '').strip()
    top_k = data.get('top_k', 5)

    if student_id in ('null', 'undefined', 'None', ''):
        student_id = ''
        print(f"   ⚠️ workflow-search: student_id 无效，原始数据: {data}")

    if not student_id or not query or not _fastgpt_kb_service:
        response_data = {
            'success': False,
            'found': False,
            'must_answer': False,
            'result_count': 0,
            'message': '参数不足或知识库服务未初始化',
            'answer_context': '',
            'results': [],
            'quoteList': []
        }
        return jsonify(response_data)

    query = _clean_quote_text(query).strip()

    try:
        dataset_id = _fastgpt_kb_service.get_or_create_user_dataset(student_id)
        result = _fastgpt_kb_service.search(student_id, query, top_k)

        raw_results = []

        if result.get('success') and result.get('results'):
            raw_results = result.get('results', [])

        quote_list = []

        for i, item in enumerate(raw_results):
            content = (
                item.get('content')
                or item.get('q')
                or item.get('text')
                or ''
            )
            content = _clean_quote_text(content).strip()

            source = (
                item.get('source')
                or item.get('sourceName')
                or item.get('filename')
                or '未知来源'
            )
            source = _clean_quote_text(source).strip()

            score = item.get('score', 0)
            collection_id = (
                item.get('collection_id')
                or item.get('collectionId')
                or ''
            )

            if source.startswith('['):
                source = re.sub(r'^\[.*?\]\s*', '', source) or source

            data_id = (
                item.get('data_id')
                or item.get('dataId')
                or item.get('id')
                or item.get('_id')
                or item.get('doc_id')
                or ''
            )

            item_dataset_id = (
                item.get('dataset_id')
                or item.get('datasetId')
                or dataset_id
                or ''
            )

            score_val = _normalize_workflow_score(score)

            q_text = item.get('q') or content or ''
            q_text = _clean_quote_text(q_text).strip()

            a_text = _clean_quote_text(item.get('a') or '').strip()

            is_filename_hit = _looks_like_filename_only_hit(q_text, source)

            if is_filename_hit:
                enriched = _enrich_filename_hit_content(
                    student_id=student_id,
                    source=source,
                    collection_id=collection_id,
                    dataset_id=item_dataset_id,
                    original_q=q_text
                )

                chunks = enriched.get('chunks') or []

                if chunks:
                    for cidx, ch in enumerate(chunks):
                        chunk_q = _clean_quote_text(ch.get('q') or '').strip()
                        chunk_a = _clean_quote_text(ch.get('a') or '').strip()
                        chunk_id = str(ch.get('id') or '').strip()

                        if not chunk_q and not chunk_a:
                            continue

                        final_chunk_id = (
                            chunk_id
                            or data_id
                            or item.get('doc_id')
                            or collection_id
                            or f'search_{i}_{cidx}'
                        )

                        quote_list.append({
                            'id': str(final_chunk_id),
                            'datasetId': str(item_dataset_id),
                            'collectionId': str(collection_id or ''),
                            'sourceName': source,
                            'sourceId': str(collection_id or ''),
                            'q': (
                                f"【文件】{source}\n"
                                f"【正文片段】\n{chunk_q}"
                            )[:4000],
                            'a': chunk_a[:2000],
                            'chunkIndex': ch.get('chunkIndex', cidx),
                            'score': [
                                {
                                    'type': 'embedding',
                                    'value': round(max(score_val - cidx * 0.001, 0), 4),
                                    'index': cidx
                                }
                            ]
                        })

                    continue

                q_text = _clean_quote_text(enriched.get('text') or q_text)
                first_data_id = enriched.get('first_data_id') or ''

                if first_data_id and (
                    not data_id
                    or str(data_id).startswith('search_')
                    or str(data_id).startswith('doc_')
                ):
                    data_id = first_data_id

            if not q_text and not a_text:
                continue

            final_id = (
                data_id
                or item.get('doc_id')
                or collection_id
                or f'search_{i}'
            )

            quote_list.append({
                'id': str(final_id),
                'datasetId': str(item_dataset_id),
                'collectionId': str(collection_id or ''),
                'sourceName': source,
                'sourceId': str(collection_id or ''),
                'q': q_text[:4000],
                'a': a_text[:2000],
                'chunkIndex': i,
                'score': [
                    {
                        'type': 'embedding',
                        'value': round(score_val, 4),
                        'index': i
                    }
                ]
            })

        before_dedupe_count = len(quote_list)
        quote_list = _dedupe_quote_list(quote_list)
        after_dedupe_count = len(quote_list)

        if after_dedupe_count != before_dedupe_count:
            print(f"   🧹 workflow-search 引用去重: {before_dedupe_count} -> {after_dedupe_count}")

        found = len(quote_list) > 0
        answer_context = _clean_quote_text(
            _build_workflow_answer_context(query, quote_list)
        )

        response_data = {
            'success': True,
            'found': found,
            'must_answer': found,
            'result_count': len(quote_list),
            'message': (
                '已在个人知识库中找到相关文件或片段，必须基于结果回答。'
                if found
                else '个人知识库未找到相关结果。'
            ),
            'answer_context': answer_context,
            'results': quote_list,
            'quoteList': quote_list,
            'student_id': student_id,
            'query': query
        }

        return jsonify(response_data)

    except Exception as e:
        traceback.print_exc()

        response_data = {
            'success': False,
            'found': False,
            'must_answer': False,
            'result_count': 0,
            'message': f'workflow-search 异常: {str(e)}',
            'answer_context': '',
            'results': [],
            'quoteList': [],
            'student_id': student_id,
            'query': query
        }

        return jsonify(response_data)


@kb_bp.route('/api/kb/workflow-search', methods=['GET'])
def api_kb_workflow_search_get():
    student_id = request.args.get('student_id', '').strip()
    query = request.args.get('query', '').strip()

    if not student_id or not query:
        return jsonify({
            'success': False,
            'error': '请提供 student_id 和 query 参数',
            'usage': '/api/kb/workflow-search?student_id=20243334&query=你的问题'
        })

    try:
        top_k = int(request.args.get('top_k', 5))
        result = _fastgpt_kb_service.search(student_id, query, top_k)

        if result.get('success') and result.get('results'):
            context_parts = []

            for i, item in enumerate(result['results']):
                content = _clean_quote_text(item.get('content', '')).strip()
                source = _clean_quote_text(item.get('source', ''))

                if content:
                    context_parts.append(f"[{i + 1}] （来源：{source}）\n{content}")

            return jsonify({
                'success': True,
                'searchResult': '\n\n'.join(context_parts),
                'total': len(context_parts),
                'student_id': student_id
            })

        return jsonify({
            'success': True,
            'searchResult': '',
            'total': 0,
            'student_id': student_id,
            'message': '未找到相关内容'
        })

    except Exception as e:
        return jsonify({
            'success': True,
            'searchResult': f'搜索出错: {str(e)}',
            'isEmpty': True
        })


@kb_bp.route('/api/kb/sync-from-fastgpt', methods=['POST'])
@_require_login
def api_kb_sync_from_fastgpt():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.sync_documents_from_fastgpt(username, force=True)

        try:
            _manage_user_raw_sources(username)
        except Exception:
            pass

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/document/<doc_id>', methods=['DELETE'])
@_require_login
def api_kb_delete_document(doc_id):
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        doc_before_delete = _db.kb_documents.find_one(
            {
                'username': username,
                'doc_id': doc_id
            },
            {
                '_id': 0
            }
        )

        success = _fastgpt_kb_service.delete_document(username, doc_id)

        if success:
            raw_delete_result = _delete_raw_source_for_doc(doc_before_delete)
            cleanup_result = _cleanup_orphan_raw_sources(username=username, dry_run=False)
            empty_dirs_removed = _cleanup_empty_dirs(os.path.join(_RAW_SOURCE_DIR, username))

            return jsonify({
                'success': True,
                'message': '文档删除成功',
                'raw_source_delete': raw_delete_result,
                'raw_source_cleanup': cleanup_result,
                'raw_source_empty_dirs_removed': empty_dirs_removed
            })

        return jsonify({
            'success': False,
            'error': '文档不存在或删除失败'
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/document/<doc_id>/share', methods=['POST'])
@_require_login
def api_kb_share_document(doc_id):
    username, _, _ = _get_user_info()

    if not doc_id or not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '缺少文档ID或服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.share_document(username, doc_id)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/document/<doc_id>/unshare', methods=['POST'])
@_require_login
def api_kb_unshare_document(doc_id):
    username, _, _ = _get_user_info()

    if not doc_id or not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '缺少文档ID或服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.unshare_document(username, doc_id)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/sync-names', methods=['POST'])
@_require_login
def api_kb_sync_names():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.sync_all_collection_names(username)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/rename/<doc_id>', methods=['POST'])
@_require_login
def api_kb_rename_doc(doc_id):
    """
    重命名文档。

    v4.6：
    - 同步 FastGPT collection 名称；
    - 同步 MongoDB filename；
    - 同步 kb_raw_sources/<username>/ 下的本地源文件名。
    """
    username, _, _ = _get_user_info()

    if not doc_id or not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '缺少文档ID或服务未初始化'
        })

    try:
        data = request.get_json() or {}
        new_name_raw = data.get('new_name', '').strip()

        if not new_name_raw:
            return jsonify({
                'success': False,
                'error': '新文件名不能为空'
            })

        if '\x00' in new_name_raw or '/' in new_name_raw or '\\' in new_name_raw:
            return jsonify({
                'success': False,
                'error': '文件名不能包含路径分隔符'
            })

        doc = _db.kb_documents.find_one({
            'username': username,
            'doc_id': doc_id
        })

        if not doc:
            return jsonify({
                'success': False,
                'error': '文档不存在'
            })

        old_filename = doc.get('filename') or ''
        filename = _normalize_renamed_filename(old_filename, new_name_raw)

        if not filename:
            return jsonify({
                'success': False,
                'error': '缺少文件名'
            })

        collection_id = doc.get('collection_id')

        fastgpt_result = {
            'success': True,
            'message': '文档尚未同步到 FastGPT，仅更新本地记录'
        }

        if collection_id:
            fastgpt_result = _fastgpt_kb_service.update_collection_name(
                collection_id,
                filename
            )

            if not fastgpt_result.get('success'):
                return jsonify(fastgpt_result)

        doc_for_rename = {
            **doc,
            'username': username,
            'doc_id': doc_id
        }

        raw_rename_result = _rename_raw_source_for_doc(
            doc_for_rename,
            filename
        )

        update_fields = {
            'filename': filename,
            'name_synced': True,
            'name_synced_at': datetime.now(),
            'updated_at': datetime.now()
        }

        if raw_rename_result.get('update_fields'):
            update_fields.update(raw_rename_result.get('update_fields'))

        _db.kb_documents.update_one(
            {
                'username': username,
                'doc_id': doc_id
            },
            {
                '$set': update_fields
            }
        )

        try:
            cleanup_result = _cleanup_orphan_raw_sources(
                username=username,
                dry_run=False
            )
        except Exception:
            cleanup_result = None

        response = dict(fastgpt_result or {})
        response.update({
            'success': True,
            'message': '文档重命名成功',
            'doc_id': doc_id,
            'old_name': old_filename,
            'new_name': filename,
            'raw_source_rename': raw_rename_result,
            'raw_source_cleanup': cleanup_result
        })

        return jsonify(response)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


# ================== 文件夹管理 API ==================

@kb_bp.route('/api/kb/folders', methods=['GET'])
@_require_login
def api_kb_folders():
    username, _, _ = _get_user_info()
    parent_id = request.args.get('parent_id', None)

    if parent_id == '':
        parent_id = None

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化',
            'folders': []
        })

    try:
        folders = _fastgpt_kb_service.get_folders(username, parent_id)

        return jsonify({
            'success': True,
            'folders': folders,
            'total': len(folders)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'folders': []
        })


@kb_bp.route('/api/kb/folders/tree', methods=['GET'])
@_require_login
def api_kb_folder_tree():
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化',
            'tree': []
        })

    try:
        tree = _fastgpt_kb_service.get_folder_tree(username)

        return jsonify({
            'success': True,
            'tree': tree
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'tree': []
        })


@kb_bp.route('/api/kb/folder', methods=['POST'])
@_require_login
def api_kb_create_folder():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    folder_name = data.get('name', '').strip()
    parent_id = data.get('parent_id', None)

    if not folder_name:
        return jsonify({
            'success': False,
            'error': '文件夹名称不能为空'
        })

    if len(folder_name) > 50:
        return jsonify({
            'success': False,
            'error': '文件夹名称不能超过50个字符'
        })

    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']

    for char in invalid_chars:
        if char in folder_name:
            return jsonify({
                'success': False,
                'error': f'文件夹名称不能包含特殊字符: {char}'
            })

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.create_folder(username, folder_name, parent_id)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/folder/<folder_id>', methods=['DELETE'])
@_require_login
def api_kb_delete_folder(folder_id):
    username, _, _ = _get_user_info()
    recursive = request.args.get('recursive', 'false').lower() == 'true'

    if not folder_id or not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '缺少文件夹ID或服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.delete_folder(username, folder_id, recursive)

        if result.get('success'):
            cleanup_result = _cleanup_orphan_raw_sources(
                username=username,
                dry_run=False
            )
            result['raw_source_cleanup'] = cleanup_result

        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/folder/<folder_id>/rename', methods=['POST'])
@_require_login
def api_kb_rename_folder(folder_id):
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    new_name = data.get('name', '').strip()

    if not folder_id:
        return jsonify({
            'success': False,
            'error': '缺少文件夹ID'
        })

    if not new_name:
        return jsonify({
            'success': False,
            'error': '新名称不能为空'
        })

    if len(new_name) > 50:
        return jsonify({
            'success': False,
            'error': '文件夹名称不能超过50个字符'
        })

    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']

    for char in invalid_chars:
        if char in new_name:
            return jsonify({
                'success': False,
                'error': f'文件夹名称不能包含特殊字符: {char}'
            })

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.rename_folder(username, folder_id, new_name)
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/document/<doc_id>/move', methods=['POST'])
@_require_login
def api_kb_move_document(doc_id):
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    target_folder_id = data.get('folder_id', None)

    if target_folder_id in ('', 'null'):
        target_folder_id = None

    if not doc_id or not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '缺少文档ID或服务未初始化'
        })

    try:
        result = _fastgpt_kb_service.move_document_to_folder(
            username,
            doc_id,
            target_folder_id
        )
        return jsonify(result)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        })


@kb_bp.route('/api/kb/folder/<folder_id>/documents', methods=['GET'])
@_require_login
def api_kb_folder_documents(folder_id):
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({
            'success': False,
            'error': '知识库服务未初始化',
            'documents': []
        })

    try:
        actual_folder_id = None if folder_id == 'root' else folder_id

        documents = _fastgpt_kb_service.get_documents_in_folder(
            username,
            actual_folder_id
        )

        formatted_docs = [_format_document(doc, username=username) for doc in documents]

        return jsonify({
            'success': True,
            'documents': formatted_docs,
            'total': len(formatted_docs)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'documents': []
        })


@kb_bp.route('/api/kb/chat-url', methods=['GET'])
@_require_login
def api_kb_chat_url():
    username, _, _ = _get_user_info()
    share_id = os.environ.get('FASTGPT_SHARE_ID', _DEFAULT_FASTGPT_SHARE_ID)
    base_url = os.environ.get('FASTGPT_SHARE_BASE_URL', _DEFAULT_FASTGPT_SHARE_BASE_URL)

    user_auth_token = hashlib.md5(f"pkb_auth_{username}".encode()).hexdigest()

    from urllib.parse import quote

    chat_url = (
        f"{base_url}/chat/share"
        f"?shareId={share_id}"
        f"&authToken={user_auth_token}"
        f"&{quote('用户学号')}={username}"
    )

    return jsonify({
        'success': True,
        'chat_url': chat_url,
        'share_id': share_id,
        'auth_token': user_auth_token,
        'username': username
    })


@kb_bp.route('/api/kb/document/<doc_id>/content', methods=['GET'])
@_require_login
def api_kb_document_content(doc_id):
    username, _, _ = _get_user_info()

    doc = _db.kb_documents.find_one({
        'doc_id': doc_id,
        'username': username
    })

    if not doc:
        return jsonify({
            'error': '文档不存在'
        }), 404

    raw_path = _resolve_raw_source_path(doc)

    has_original_file = bool(
        raw_path
        or doc.get('raw_source_path')
        or doc.get('raw_source_url')
        or doc.get('fastgpt_image_url')
        or doc.get('embedded_image_url')
    )

    original_url = _build_original_file_url(doc_id) if has_original_file else ''
    original_download_url = _build_original_download_url(doc_id) if has_original_file else ''

    return jsonify({
        'success': True,
        'doc_id': doc_id,
        'filename': doc.get('filename', ''),
        'media_type': doc.get('media_type', ''),
        'file_type': doc.get('file_type', ''),

        'fastgpt_image_url': doc.get('fastgpt_image_url', ''),
        'embedded_image_url': doc.get('embedded_image_url', ''),
        'image_url_source': doc.get('image_url_source', ''),

        'raw_source_saved': bool(doc.get('raw_source_saved')),
        'raw_source_url': doc.get('raw_source_url', ''),
        'raw_source_download_url': doc.get('raw_source_download_url', ''),
        'raw_source_filename': doc.get('raw_source_filename', ''),
        'raw_source_original_filename': doc.get('raw_source_original_filename', ''),
        'raw_source_storage_name': doc.get('raw_source_storage_name', ''),
        'raw_source_exists': bool(raw_path),

        'original_url': original_url,
        'original_file_url': original_url,
        'original_download_url': original_download_url,
        'download_url': original_download_url,
        'has_original_file': has_original_file,

        'parsed_text': doc.get('parsed_text', ''),
        'status': doc.get('status', ''),
        'metadata': doc.get('parse_metadata', {})
    })


def _send_original_file_response(doc, as_attachment=False):
    if not doc:
        return jsonify({
            'success': False,
            'error': '文档不存在'
        }), 404

    raw_path_abs = _resolve_raw_source_path(doc)

    if not raw_path_abs:
        return jsonify({
            'success': False,
            'error': '原始源文件不存在或未保存',
            'doc_id': doc.get('doc_id', '')
        }), 404

    base_dir = os.path.abspath(_RAW_SOURCE_DIR)

    if not _is_path_inside(raw_path_abs, base_dir):
        return jsonify({
            'success': False,
            'error': '源文件路径非法',
            'doc_id': doc.get('doc_id', '')
        }), 403

    if not os.path.exists(raw_path_abs):
        return jsonify({
            'success': False,
            'error': '源文件不存在',
            'doc_id': doc.get('doc_id', ''),
            'raw_source_path': raw_path_abs
        }), 404

    filename = (
        doc.get('filename')
        or doc.get('raw_source_original_filename')
        or doc.get('raw_source_filename')
        or os.path.basename(raw_path_abs)
    )

    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    return send_file(
        raw_path_abs,
        mimetype=mime,
        as_attachment=as_attachment,
        download_name=filename,
        conditional=True,
        max_age=0
    )


@kb_bp.route('/api/kb/document/<doc_id>/original', methods=['GET'])
@_require_login
def api_kb_document_original(doc_id):
    username, _, _ = _get_user_info()

    try:
        doc = _db.kb_documents.find_one(
            {
                'doc_id': doc_id,
                'username': username,
                'status': {'$ne': 'deleted'}
            },
            {
                '_id': 0
            }
        )

        if not doc:
            return jsonify({
                'success': False,
                'error': '文档不存在或无权限访问',
                'doc_id': doc_id
            }), 404

        return _send_original_file_response(doc, as_attachment=False)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'doc_id': doc_id
        }), 500


@kb_bp.route('/api/kb/document/<doc_id>/original/download', methods=['GET'])
@_require_login
def api_kb_document_original_download(doc_id):
    username, _, _ = _get_user_info()

    try:
        doc = _db.kb_documents.find_one(
            {
                'doc_id': doc_id,
                'username': username,
                'status': {'$ne': 'deleted'}
            },
            {
                '_id': 0
            }
        )

        if not doc:
            return jsonify({
                'success': False,
                'error': '文档不存在或无权限访问',
                'doc_id': doc_id
            }), 404

        return _send_original_file_response(doc, as_attachment=True)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'doc_id': doc_id
        }), 500


@kb_bp.route('/api/kb/raw-source/file/<doc_id>', methods=['GET'])
def api_kb_raw_source_file(doc_id):
    try:
        doc = _db.kb_documents.find_one(
            {
                'doc_id': doc_id,
                'status': {'$ne': 'deleted'}
            },
            {
                '_id': 0,
                'doc_id': 1,
                'username': 1,
                'filename': 1,
                'raw_source_path': 1,
                'raw_source_saved': 1,
                'raw_source_filename': 1,
                'raw_source_original_filename': 1,
                'raw_source_storage_name': 1,
                'file_type': 1,
                'media_type': 1
            }
        )

        if not doc:
            return jsonify({
                'success': False,
                'error': 'doc_id 不存在',
                'doc_id': doc_id
            }), 404

        inline = request.args.get('inline', '').lower() in ('1', 'true', 'yes')
        as_attachment = not inline

        return _send_original_file_response(doc, as_attachment=as_attachment)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'doc_id': doc_id
        }), 500


@kb_bp.route('/api/kb/raw-source/cleanup', methods=['POST'])
@_require_login
def api_kb_raw_source_cleanup():
    username, _, role = _get_user_info()
    data = request.get_json() or {}

    scope = data.get('scope', 'current')
    dry_run = data.get('dry_run', True)
    migrate = data.get('migrate', True)

    if isinstance(dry_run, str):
        dry_run = dry_run.lower() in ('1', 'true', 'yes')

    target_username = username

    if scope == 'all':
        allow_all = (
            role in ('teacher', 'admin')
            or os.environ.get('KB_ALLOW_RAW_SOURCE_CLEANUP_ALL', '0') == '1'
        )

        if not allow_all:
            return jsonify({
                'success': False,
                'error': '无权限清理整个 kb_raw_sources 目录'
            }), 403

        target_username = None

    if not dry_run and data.get('confirm') != 'DELETE_ORPHAN_RAW_SOURCES':
        return jsonify({
            'success': False,
            'error': (
                '为了避免误删，实际删除时必须传入 '
                '{"confirm": "DELETE_ORPHAN_RAW_SOURCES"}'
            )
        }), 400

    migration_result = None

    if migrate:
        migration_result = _migrate_user_raw_sources_to_original_names(
            username=target_username,
            dry_run=dry_run
        )

    cleanup_result = _cleanup_orphan_raw_sources(
        username=target_username,
        dry_run=dry_run
    )

    return jsonify({
        'success': bool(cleanup_result.get('success')),
        'migration': migration_result,
        'cleanup': cleanup_result
    })


@kb_bp.route('/api/kb/raw-source/status', methods=['GET'])
@_require_login
def api_kb_raw_source_status():
    username, _, _ = _get_user_info()

    try:
        base_dir = os.path.abspath(_RAW_SOURCE_DIR)
        user_dir = os.path.abspath(os.path.join(base_dir, str(username)))

        if not _is_path_inside(user_dir, base_dir):
            return jsonify({
                'success': False,
                'error': '用户源文件目录路径非法'
            }), 400

        total_files = 0
        total_bytes = 0
        files = []

        if os.path.isdir(user_dir):
            for current, dirs, fs in os.walk(user_dir):
                for name in fs:
                    path_abs = os.path.abspath(os.path.join(current, name))

                    if not _is_path_inside(path_abs, base_dir):
                        continue

                    total_files += 1

                    size = 0
                    try:
                        size = os.path.getsize(path_abs)
                        total_bytes += size
                    except Exception:
                        pass

                    files.append({
                        'filename': name,
                        'path': path_abs,
                        'size': size,
                        'size_display': _format_size(size)
                    })

        quota_usage = _get_user_quota_usage(username)

        dry_cleanup = _cleanup_orphan_raw_sources(
            username=username,
            dry_run=True
        )

        return jsonify({
            'success': True,
            'username': username,
            'raw_source_dir': user_dir,
            'exists': os.path.isdir(user_dir),
            'file_count': total_files,
            'total_bytes': total_bytes,
            'total_display': _format_size(total_bytes),
            'files': files,
            'orphan_preview': dry_cleanup,
            'quota': {
                'document_count': quota_usage.get('document_count', 0),
                'used_bytes': quota_usage.get('used_bytes', 0),
                'used_display': _format_size(quota_usage.get('used_bytes', 0)),
                'max_bytes': quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER),
                'max_display': _format_size(
                    quota_usage.get('max_bytes', _MAX_TOTAL_STORAGE_BYTES_PER_USER)
                )
            }
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@kb_bp.route('/api/kb/raw-source/by-collection/<collection_id>', methods=['GET'])
def api_kb_raw_source_by_collection(collection_id):
    try:
        projection = {
            '_id': 0,
            'doc_id': 1,
            'username': 1,
            'filename': 1,
            'file_type': 1,
            'media_type': 1,

            'collection_id': 1,

            'shared': 1,
            'shared_collection_id': 1,
            'shared_dataset_id': 1,
            'shared_display_name': 1,
            'shared_original_filename': 1,

            'fastgpt_image_url': 1,
            'embedded_image_url': 1,
            'fastgpt_image_file_id': 1,
            'fastgpt_image_bucket': 1,

            'raw_source_saved': 1,
            'raw_source_path': 1,
            'raw_source_url': 1,
            'raw_source_download_url': 1,
            'raw_source_filename': 1,
            'raw_source_original_filename': 1,
            'raw_source_storage_name': 1,
            'raw_source_size': 1,

            'original_url': 1,
            'original_download_url': 1,

            'shared_raw_source_url': 1,
            'shared_raw_source_path': 1,
            'shared_fastgpt_image_url': 1,
            'shared_fastgpt_image_file_id': 1,
            'shared_fastgpt_image_bucket': 1,

            'parsed_from_media': 1,
            'status': 1
        }

        matched_by = ''

        doc = _db.kb_documents.find_one(
            {
                'collection_id': collection_id
            },
            projection
        )

        if doc:
            matched_by = 'collection_id'

        if not doc:
            doc = _db.kb_documents.find_one(
                {
                    'shared_collection_id': collection_id
                },
                projection
            )

            if doc:
                matched_by = 'shared_collection_id'

        if not doc:
            print(
                f"   ⚠️ raw-source/by-collection 未找到映射: "
                f"collection_id={collection_id}"
            )
            return jsonify({
                'success': False,
                'error': 'collection_id 未找到对应文档',
                'collection_id': collection_id
            })

        file_id = (
            doc.get('fastgpt_image_file_id')
            or doc.get('shared_fastgpt_image_file_id')
            or ''
        )

        bucket = (
            doc.get('fastgpt_image_bucket')
            or doc.get('shared_fastgpt_image_bucket')
            or ''
        )

        raw_path = _resolve_raw_source_path(doc)
        raw_path_exists = bool(raw_path and os.path.exists(raw_path))

        local_original_url = ''
        local_original_download_url = ''

        if doc.get('doc_id') and raw_path_exists:
            local_original_url = _build_original_file_url(doc.get('doc_id'))
            local_original_download_url = _build_original_download_url(doc.get('doc_id'))

        url = (
            doc.get('fastgpt_image_url')
            or doc.get('shared_fastgpt_image_url')
            or doc.get('embedded_image_url')
            or local_original_url
            or doc.get('original_url')
            or doc.get('shared_raw_source_url')
            or doc.get('raw_source_url')
            or ''
        )

        raw_url = (
            local_original_url
            or doc.get('original_url')
            or doc.get('raw_source_url')
            or ''
        )

        download_url = (
            local_original_download_url
            or doc.get('original_download_url')
            or doc.get('raw_source_download_url')
            or raw_url
            or ''
        )

        if not url and not file_id:
            print(
                f"   ⚠️ raw-source 找到文档但没有可用源文件: "
                f"collection_id={collection_id}, "
                f"matched_by={matched_by}, "
                f"doc_id={doc.get('doc_id')}, "
                f"filename={doc.get('filename')}"
            )

            return jsonify({
                'success': False,
                'error': '该文档没有可用的原始文件 URL 或 file_id',
                'collection_id': collection_id,
                'matched_by': matched_by,
                'doc': doc
            })

        display_filename = (
            doc.get('shared_display_name')
            if matched_by == 'shared_collection_id'
            else ''
        ) or doc.get('filename', '') or doc.get('raw_source_original_filename', '') or doc.get('raw_source_filename', '')

        print(
            f"   ✅ raw-source 命中: "
            f"collection_id={collection_id}, "
            f"matched_by={matched_by}, "
            f"doc_id={doc.get('doc_id')}, "
            f"filename={display_filename}, "
            f"url={'yes' if url else 'no'}, "
            f"file_id={'yes' if file_id else 'no'}, "
            f"local_file={'yes' if raw_path_exists else 'no'}"
        )

        return jsonify({
            'success': True,
            'type': 'url' if url else 'fileId',
            'value': url or file_id,

            'url': url,
            'rawUrl': raw_url or url,
            'download_url': download_url,
            'original_url': local_original_url,
            'original_download_url': local_original_download_url,

            'file_id': file_id,
            'bucket': bucket or 'chat',

            'filename': display_filename,
            'original_filename': doc.get('filename', ''),
            'media_type': doc.get('media_type', ''),
            'file_type': doc.get('file_type', ''),

            'collection_id': collection_id,
            'source_collection_id': doc.get('collection_id', ''),
            'shared_collection_id': doc.get('shared_collection_id', ''),
            'matched_by': matched_by,

            'doc_id': doc.get('doc_id', ''),
            'username': doc.get('username', ''),
            'raw_source_saved': bool(doc.get('raw_source_saved')),
            'raw_source_url': doc.get('raw_source_url', ''),
            'raw_source_filename': doc.get('raw_source_filename', ''),
            'raw_source_original_filename': doc.get('raw_source_original_filename', ''),
            'raw_source_storage_name': doc.get('raw_source_storage_name', ''),
            'raw_source_path_exists': raw_path_exists,
            'shared': bool(doc.get('shared'))
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'collection_id': collection_id
        })


# ================== 解析进度查询 ==================

@kb_bp.route('/api/kb/parse-status/<doc_id>')
@_require_login
def api_kb_parse_status(doc_id):
    username, _, _ = _get_user_info()

    doc = _db.kb_documents.find_one(
        {
            'username': username,
            'doc_id': doc_id
        },
        {
            '_id': 0,
            'doc_id': 1,
            'username': 1,
            'filename': 1,
            'status': 1,
            'parse_stage': 1,
            'parse_progress': 1,
            'error_message': 1,
            'chunk_count': 1,
            'media_type': 1,
            'raw_source_saved': 1,
            'raw_source_path': 1,
            'raw_source_url': 1,
            'raw_source_filename': 1,
            'raw_source_original_filename': 1,
            'raw_source_storage_name': 1,
            'original_url': 1,
            'original_download_url': 1
        }
    )

    if not doc:
        return jsonify({
            'success': False,
            'error': '文档不存在'
        })

    stage_labels = {
        'extracting_frames': '正在提取视频帧...',
        'analyzing_frames': '正在分析画面内容...',
        'transcribing_audio': '正在转录语音...',
        'summarizing': '正在整理内容...',
        'parsing_slides': '正在解析幻灯片...'
    }

    stage = doc.get('parse_stage', '')

    raw_path = _resolve_raw_source_path(doc)
    has_original_file = bool(raw_path or doc.get('raw_source_url'))

    return jsonify({
        'success': True,
        'status': doc.get('status', 'unknown'),
        'stage': stage,
        'stage_label': stage_labels.get(stage, '处理中...'),
        'progress': doc.get('parse_progress', 0),
        'error': doc.get('error_message'),
        'chunk_count': doc.get('chunk_count', 0),
        'media_type': doc.get('media_type'),
        'raw_source_saved': bool(doc.get('raw_source_saved')),
        'raw_source_filename': doc.get('raw_source_filename', ''),
        'raw_source_original_filename': doc.get('raw_source_original_filename', ''),
        'has_original_file': has_original_file,
        'original_url': _build_original_file_url(doc_id) if has_original_file else '',
        'original_download_url': _build_original_download_url(doc_id) if has_original_file else ''
    })


# ================== 模型健康检查路由 ==================

@kb_bp.route('/api/kb/model-health')
@_require_login
def api_kb_model_health():
    results = {
        'text_model': _check_text_health(),
        'vlm': _check_vlm_health()
    }

    results['embedding'] = {
        'name': 'm3e',
        'type': '索引模型（向量化）',
        'description': '由 FastGPT 内部管理，无需外部检测',
        'available': True,
        'note': '索引状态以 FastGPT 返回为准'
    }

    all_ok = all(r.get('available', False) for r in results.values())

    warnings = []

    if not results['text_model'].get('available'):
        warnings.append(
            f"⚠️ 问答模型 ({results['text_model'].get('name', 'Qwen3-8B')}) 不可用: "
            f"{results['text_model'].get('error', '未知')}。"
            f"智能问答功能不可用，仅返回检索原文。"
        )

    if not results.get('vlm', {}).get('available'):
        warnings.append(
            f"⚠️ 视觉模型不可用: "
            f"{results.get('vlm', {}).get('error', '未知')}。"
            f"图片/视频/PPT 内容解析功能受影响。"
        )

    return jsonify({
        'success': True,
        'all_healthy': all_ok,
        'models': results,
        'warnings': warnings,
        'timestamp': datetime.now().isoformat()
    })


@kb_bp.route('/api/kb/model-health/clear-cache', methods=['POST'])
@_require_login
def api_kb_clear_health_cache():
    _health_cache.clear()

    return jsonify({
        'success': True,
        'message': '健康检查缓存已清除'
    })


# ================== 调试端点 ==================

@kb_bp.route('/api/kb/debug/test-image-upload', methods=['POST'])
@_require_login
def api_kb_debug_test_image_upload():
    username, _, _ = _get_user_info()

    if 'file' not in request.files:
        return jsonify({
            'error': '请上传一个图片文件 (form field: file)'
        })

    file = request.files['file']
    content = file.read()
    filename = file.filename
    dataset_id = _get_user_dataset_id(username)

    results = {}

    headers = {
        'Authorization': f'Bearer {_fastgpt_api_key}'
    }

    mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

    test_configs = [
        (
            'common/file/upload + chat',
            'common/file/upload',
            {
                'bucketName': 'chat'
            }
        ),
        (
            'common/file/upload + dataset+id',
            'common/file/upload',
            {
                'bucketName': 'dataset',
                'metadata': json.dumps({
                    'datasetId': dataset_id or ''
                })
            }
        ),
        (
            'common/file/upload + 无bucket',
            'common/file/upload',
            {}
        ),
        (
            'common/file/uploadImage + chat',
            'common/file/uploadImage',
            {
                'bucketName': 'chat'
            }
        )
    ]

    for label, path, extra_data in test_configs:
        try:
            url = f"{_fastgpt_api_url}/{path}"

            files_dict = {
                'file': (
                    filename,
                    io.BytesIO(content),
                    mime
                )
            }

            resp = http_requests.post(
                url,
                headers=headers,
                files=files_dict,
                data=extra_data,
                timeout=15
            )

            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]

            results[label] = {
                'status': resp.status_code,
                'body': body
            }

        except Exception as e:
            results[label] = {
                'error': str(e)
            }

    full_result = _upload_image_to_fastgpt(
        content,
        filename,
        dataset_id=dataset_id
    )

    results['_upload_image_to_fastgpt'] = full_result

    results['config'] = {
        'fastgpt_api_url': _fastgpt_api_url,
        'fastgpt_api_key_set': bool(_fastgpt_api_key),
        'fastgpt_api_key_preview': (
            _fastgpt_api_key[:8] + '...'
            if _fastgpt_api_key
            else 'N/A'
        ),
        'dataset_id': dataset_id
    }

    return jsonify({
        'success': True,
        'results': results
    })


# ================== 健康检查 ==================

@kb_bp.route('/api/kb/health')
def api_kb_health():
    kb_ready = False

    if _fastgpt_kb_service:
        try:
            kb_ready = _fastgpt_kb_service.is_ready()
        except Exception:
            pass

    media_ready = _media_parser is not None

    return jsonify({
        'status': 'ok',
        'version': 'v4.6.0-original-filename-raw-source-save-and-cleanup',
        'features': {
            'fastgpt_kb': kb_ready,
            'mongodb': _db is not None,
            'dynamic_dataset': True,
            'shared_kb': True,

            'media_parser': media_ready,
            'fastgpt_image_upload': bool(_fastgpt_api_key),
            'supported_media': (
                sorted(list(_media_parser.ALL_EXTENSIONS))
                if media_ready
                else []
            ),

            'embedding_note': '索引由 FastGPT 内部管理',

            'local_raw_source_storage': True,
            'raw_source_dir': _RAW_SOURCE_DIR,
            'raw_source_base_url': _RAW_SOURCE_BASE_URL,

            'raw_source_save_name': 'original_filename',
            'raw_source_duplicate_strategy': 'append_number_suffix',
            'raw_source_auto_migrate_old_doc_id_names': _AUTO_MIGRATE_RAW_SOURCE_NAMES,
            'raw_source_auto_cleanup_on_list': _AUTO_CLEAN_RAW_SOURCES_ON_LIST,

            'unified_original_file_api': True,
            'original_file_view_api': '/api/kb/document/<doc_id>/original',
            'original_file_download_api': '/api/kb/document/<doc_id>/original/download',

            'raw_source_cleanup_api': '/api/kb/raw-source/cleanup',
            'raw_source_status_api': '/api/kb/raw-source/status',
            'rename_syncs_mongodb_and_raw_source_file': True,
            'all_uploads_save_raw_source': True,

            'workflow_quote_dedupe': True,
            'quote_text_clean': True
        },
        'fastgpt_api_url': _fastgpt_api_url,
        'timestamp': datetime.now().isoformat()
    })
