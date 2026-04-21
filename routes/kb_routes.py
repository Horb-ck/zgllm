# /home/zgllm/test_server/routes/kb_routes.py
# -*- coding: utf-8 -*-
"""
个人知识库路由模块 —— v4.0 移除外部m3e预检，信任FastGPT内部索引
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
from flask import (
    Blueprint, session, render_template, request, jsonify, send_file
)

# ================== 创建蓝图 ==================
kb_bp = Blueprint('kb', __name__)

# ================== 全局引用 ==================
_fastgpt_kb_service = None
_db = None
_login_required = None
_process_user_courses = None
_media_parser = None
_media_upload_dir = None
_server_base_url = None
_fastgpt_api_url = None
_fastgpt_api_key = None


def init_kb_blueprint(app, db, fastgpt_kb_service, login_required_func,
                      process_user_courses_func, media_parser=None):
    global _fastgpt_kb_service, _db, _login_required, _process_user_courses
    global _media_parser, _media_upload_dir, _server_base_url
    global _fastgpt_api_url, _fastgpt_api_key

    _fastgpt_kb_service = fastgpt_kb_service
    _db = db
    _login_required = login_required_func
    _process_user_courses = process_user_courses_func
    _media_parser = media_parser

    # 服务器外部基址
    _server_base_url = os.environ.get('SERVER_BASE_URL', 'http://180.85.206.21:5003').rstrip('/')

    if _server_base_url:
        print(f"   🌐 服务器基址(环境变量): {_server_base_url}")
    else:
        print("   ⚠️  未设置 SERVER_BASE_URL 环境变量，将在请求时自动检测")

    # ★ 读取 FastGPT API（优先从已有服务读取，无需重复配置）
    _fastgpt_api_url = os.environ.get('FASTGPT_API_URL', '').rstrip('/')
    _fastgpt_api_key = os.environ.get('FASTGPT_API_KEY', '')

    # 从已有的 fastgpt_kb_service 自动读取（不用重复配环境变量）
    if _fastgpt_kb_service:
        if not _fastgpt_api_url:
            _fastgpt_api_url = getattr(_fastgpt_kb_service, 'api_url', '') or \
                               getattr(_fastgpt_kb_service, 'base_url', '')
            if _fastgpt_api_url and not _fastgpt_api_url.endswith('/api'):
                _fastgpt_api_url = _fastgpt_api_url.rstrip('/') + '/api'
        if not _fastgpt_api_key:
            _fastgpt_api_key = getattr(_fastgpt_kb_service, 'api_key', '')

    if not _fastgpt_api_url:
        _fastgpt_api_url = 'http://180.85.206.30:3000/api'

    _fastgpt_base = _fastgpt_api_url.rsplit('/api', 1)[0] if '/api' in _fastgpt_api_url else _fastgpt_api_url
    if _fastgpt_api_key:
        print(f"   🖼️  FastGPT 图片上传: {_fastgpt_api_url}")
        print(f"      Base URL: {_fastgpt_base}")
        print(f"      API Key: 已从服务读取 ✅")
    else:
        print("   ⚠️  FastGPT API Key 未找到，图片上传到 FastGPT 不可用")

    # 创建媒体文件存储目录
    _media_upload_dir = os.path.join(app.root_path, 'media_uploads')
    try:
        os.makedirs(_media_upload_dir, exist_ok=True)
        test_file = os.path.join(_media_upload_dir, '.write_test')
        with open(test_file, 'w') as f:
            f.write('ok')
        os.unlink(test_file)
        print(f"   📁 媒体文件存储目录: {_media_upload_dir}")
        print(f"   ✅ 媒体目录可写")
    except Exception as e:
        fallback = os.path.join('/tmp', 'kb_media_uploads')
        os.makedirs(fallback, exist_ok=True)
        _media_upload_dir = fallback
        print(f"   ⚠️  原目录权限不足({e}), 回退到: {fallback}")
        try:
            test_file = os.path.join(fallback, '.write_test')
            with open(test_file, 'w') as f:
                f.write('ok')
            os.unlink(test_file)
            print(f"   ✅ 媒体目录可写")
        except Exception as e2:
            print(f"   ❌ 媒体目录不可写: {e2}")


# ================== FastGPT 图片上传 ==================

def _get_fastgpt_base():
    if '/api' in _fastgpt_api_url:
        return _fastgpt_api_url.rsplit('/api', 1)[0]
    return _fastgpt_api_url


def _upload_image_to_fastgpt(file_content, filename, dataset_id=None):
    """
    尝试多种方式将图片上传到 FastGPT，获取可访问 URL
    """
    if not _fastgpt_api_key:
        return {'success': False, 'url': '', 'error': 'FastGPT API Key 未配置'}

    fastgpt_base = _get_fastgpt_base()
    headers = {'Authorization': f'Bearer {_fastgpt_api_key}'}
    mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'
    errors = []

    # === 方式1: /common/file/upload (bucketName=chat) ===
    try:
        url = f"{_fastgpt_api_url}/common/file/upload"
        files = {'file': (filename, io.BytesIO(file_content), mime)}
        data = {'bucketName': 'chat'}
        resp = http_requests.post(url, headers=headers, files=files,
                                  data=data, timeout=30)
        print(f"      [方式1: chat bucket] HTTP {resp.status_code}")
        if resp.status_code == 200:
            body = resp.json()
            fid = _extract_file_id(body)
            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                print(f"      ✅ 方式1成功: {img_url}")
                return {'success': True, 'url': img_url, 'file_id': fid}
            u = _extract_url(body)
            if u:
                if u.startswith('/'):
                    u = fastgpt_base + u
                return {'success': True, 'url': u}
            errors.append(f"chat bucket: 无file_id ({_safe_json(body)})")
        else:
            errors.append(f"chat bucket: HTTP {resp.status_code} ({resp.text[:150]})")
    except Exception as e:
        errors.append(f"chat bucket 异常: {e}")

    # === 方式2: /common/file/upload (bucketName=dataset, 带 datasetId) ===
    if dataset_id:
        try:
            url = f"{_fastgpt_api_url}/common/file/upload"
            files = {'file': (filename, io.BytesIO(file_content), mime)}
            metadata_json = json.dumps({'datasetId': dataset_id})
            data = {'bucketName': 'dataset', 'metadata': metadata_json}
            resp = http_requests.post(url, headers=headers, files=files,
                                      data=data, timeout=30)
            print(f"      [方式2: dataset bucket+id] HTTP {resp.status_code}")
            if resp.status_code == 200:
                body = resp.json()
                fid = _extract_file_id(body)
                if fid:
                    img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                    print(f"      ✅ 方式2成功: {img_url}")
                    return {'success': True, 'url': img_url, 'file_id': fid}
                u = _extract_url(body)
                if u:
                    if u.startswith('/'):
                        u = fastgpt_base + u
                    return {'success': True, 'url': u}
                errors.append(f"dataset bucket: 无file_id ({_safe_json(body)})")
            else:
                errors.append(f"dataset bucket: HTTP {resp.status_code} ({resp.text[:150]})")
        except Exception as e:
            errors.append(f"dataset bucket 异常: {e}")

    # === 方式3: /common/file/uploadImage ===
    try:
        url = f"{_fastgpt_api_url}/common/file/uploadImage"
        files = {'file': (filename, io.BytesIO(file_content), mime)}
        data = {'bucketName': 'chat'}
        resp = http_requests.post(url, headers=headers, files=files,
                                  data=data, timeout=30)
        print(f"      [方式3: uploadImage] HTTP {resp.status_code}")
        if resp.status_code == 200:
            body = resp.json()
            u = _extract_url(body)
            if u:
                if u.startswith('/'):
                    u = fastgpt_base + u
                print(f"      ✅ 方式3成功: {u}")
                return {'success': True, 'url': u}
            fid = _extract_file_id(body)
            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                return {'success': True, 'url': img_url, 'file_id': fid}
            errors.append(f"uploadImage: 无URL ({_safe_json(body)})")
        else:
            errors.append(f"uploadImage: HTTP {resp.status_code} ({resp.text[:150]})")
    except Exception as e:
        errors.append(f"uploadImage 异常: {e}")

    # === 方式4: 无 bucketName ===
    try:
        url = f"{_fastgpt_api_url}/common/file/upload"
        files = {'file': (filename, io.BytesIO(file_content), mime)}
        resp = http_requests.post(url, headers=headers, files=files, timeout=30)
        print(f"      [方式4: 无bucket] HTTP {resp.status_code}")
        if resp.status_code == 200:
            body = resp.json()
            fid = _extract_file_id(body)
            if fid:
                img_url = f"{fastgpt_base}/api/common/file/read/{fid}"
                print(f"      ✅ 方式4成功: {img_url}")
                return {'success': True, 'url': img_url, 'file_id': fid}
            errors.append(f"无bucket: 无file_id ({_safe_json(body)})")
        else:
            errors.append(f"无bucket: HTTP {resp.status_code} ({resp.text[:150]})")
    except Exception as e:
        errors.append(f"无bucket 异常: {e}")

    print(f"      ❌ 所有 FastGPT 图片上传均失败:")
    for err in errors:
        print(f"         - {err}")
    return {'success': False, 'url': '', 'error': ' | '.join(errors)}


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


# ================== 辅助函数 ==================

def _get_user_info():
    username = session.get('username', '')
    name = session.get('name', username)
    role = session.get('role', 'student')
    return username, name, role


def _get_kb_stats(username):
    if not _fastgpt_kb_service:
        return {'documents': 0, 'ready_documents': 0, 'chunks': 0, 'queries': 0, 'rag_enabled': False}
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
    return {'documents': 0, 'ready_documents': 0, 'chunks': 0, 'queries': 0, 'rag_enabled': False}


def _format_document(doc):
    shared_at = doc.get('shared_at')
    if shared_at and hasattr(shared_at, 'isoformat'):
        shared_at = shared_at.isoformat()
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
        'has_original_file': doc.get('has_original_file', False),
        'media_url': doc.get('media_url', ''),
        'public_media_url': doc.get('public_media_url', ''),
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


def _generate_public_token(doc_id, username):
    secret = f"media_pub_{doc_id}_{username}_salt2026"
    return hashlib.sha256(secret.encode()).hexdigest()[:20]


# ================== 卡住文档检测（仅提示，不自动标记失败） ==================

# 文档卡住阈值（分钟）
_STUCK_THRESHOLD_MINUTES = int(os.environ.get('STUCK_THRESHOLD_MINUTES', '10'))


def _detect_stuck_documents(documents):
    """检测卡住的文档：processing 超过阈值时间（仅用于前端提示）"""
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
                    upload_time.replace('Z', '').replace('+00:00', ''))
            except Exception:
                continue
        elapsed = (now - upload_time).total_seconds() / 60.0
        if elapsed >= _STUCK_THRESHOLD_MINUTES:
            stuck.append({
                'doc_id': doc.get('doc_id', ''),
                'filename': doc.get('filename', ''),
                'elapsed_minutes': round(elapsed, 1),
            })
    return stuck


# ================== 模型健康检查（仅保留文本模型和VLM，移除m3e外部检测） ==================

_health_cache = {}
_HEALTH_CACHE_TTL = 60  # 缓存 60 秒


def _cached_health(cache_key, check_fn):
    """带缓存的健康检查包装"""
    now = time.time()
    if cache_key in _health_cache:
        cached_result, cached_ts = _health_cache[cache_key]
        if now - cached_ts < _HEALTH_CACHE_TTL:
            return cached_result
    result = check_fn()
    _health_cache[cache_key] = (result, now)
    return result


def _do_check_text_model():
    """测试 FastGPT 的文本理解/问答模型 (Qwen3-8B)"""
    result = {
        'name': 'Qwen3-8B',
        'type': '文本理解/问答模型',
        'description': '用于知识库问答生成回答；不可用时无法智能问答',
    }
    api_url = _fastgpt_api_url
    api_key = _fastgpt_api_key
    if not api_url or not api_key:
        result.update({'available': False, 'error': '未配置 FastGPT API'})
        return result
    base = api_url.rsplit('/api', 1)[0] if '/api' in api_url else api_url
    llm_url = f"{base}/api/v1/chat/completions"
    try:
        start = time.time()
        resp = http_requests.post(
            llm_url,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json={
                'model': 'Qwen3-8B',
                'messages': [{'role': 'user', 'content': '你好'}],
                'max_tokens': 3,
                'stream': False,
            },
            timeout=15,
        )
        latency_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            body = resp.json()
            if body.get('choices'):
                result.update({'available': True, 'latency_ms': latency_ms})
            else:
                result.update({'available': False, 'error': 'API 返回无 choices'})
        else:
            result.update({'available': False,
                           'error': f'HTTP {resp.status_code}: {resp.text[:200]}'})
    except http_requests.exceptions.ConnectionError:
        result.update({'available': False, 'error': '无法连接到问答模型服务'})
    except http_requests.exceptions.Timeout:
        result.update({'available': False, 'error': '问答模型连接超时'})
    except Exception as e:
        result.update({'available': False, 'error': str(e)})
    return result


def _do_check_vlm():
    """测试 VLM 视觉模型"""
    result = {
        'type': 'VLM 视觉模型',
        'description': '用于图片/视频/PPT 内容理解；不可用时无法解析多媒体',
        'models': [],
    }
    if not _media_parser or not _media_parser.vlm_models:
        result.update({'available': False, 'name': '无', 'error': '未配置 VLM 模型'})
        return result
    any_ok = False
    for cfg in _media_parser.vlm_models:
        m = {'name': cfg.get('name', ''), 'model': cfg.get('model', '')}
        try:
            start = time.time()
            resp = http_requests.post(
                cfg['api_url'],
                headers={
                    'Authorization': f"Bearer {cfg['api_key']}",
                    'Content-Type': 'application/json',
                },
                json={
                    'model': cfg['model'],
                    'messages': [{'role': 'user', 'content': '你好'}],
                    'max_tokens': 3,
                },
                timeout=10,
            )
            latency_ms = int((time.time() - start) * 1000)
            if resp.status_code == 200 and resp.json().get('choices'):
                m.update({'available': True, 'latency_ms': latency_ms})
                any_ok = True
            else:
                m.update({'available': False,
                          'error': f'HTTP {resp.status_code}'})
        except Exception as e:
            m.update({'available': False, 'error': str(e)[:100]})
        result['models'].append(m)
    result['available'] = any_ok
    result['name'] = next(
        (m['name'] for m in result['models'] if m.get('available')),
        result['models'][0]['name'] if result['models'] else '无')
    if not any_ok:
        result['error'] = '所有 VLM 模型均不可用'
    return result


def _check_text_health():
    return _cached_health('text_model', _do_check_text_model)


def _check_vlm_health():
    return _cached_health('vlm', _do_check_vlm)


# ================== 辅助函数（续） ==================

def _get_user_dataset_id(username):
    """获取用户的 FastGPT dataset_id"""
    try:
        user_kb = _db.user_fastgpt_kb.find_one({'username': username})
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
        return jsonify({'success': False, 'error': '知识库服务未初始化',
                        'documents': 0, 'chunks': 0, 'queries': 0, 'rag_enabled': False})
    try:
        stats = _get_kb_stats(username)
        return jsonify({'success': True, **stats})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e),
                        'documents': 0, 'chunks': 0, 'queries': 0, 'rag_enabled': False})


@kb_bp.route('/api/kb/upload', methods=['POST'])
@_require_login
def api_kb_upload():
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '未选择文件'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '未选择文件'})

    folder_id = request.form.get('folder_id', None)
    if folder_id in ('', 'null', 'undefined'):
        folder_id = None

    filename = file.filename
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

    text_extensions = {'pdf', 'txt', 'md', 'doc', 'docx'}
    media_extensions = set()
    if _media_parser:
        media_extensions = _media_parser.ALL_EXTENSIONS
    all_allowed = text_extensions | media_extensions

    if ext not in all_allowed:
        return jsonify({
            'success': False,
            'error': f'不支持的文件类型: .{ext}，支持: {", ".join(sorted(all_allowed))}'
        })

    # ★ 不再预检 m3e，直接上传，由 FastGPT 内部完成索引 ★

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)

    max_size = 200 * 1024 * 1024 if ext in media_extensions else 50 * 1024 * 1024
    if file_size > max_size:
        return jsonify({
            'success': False,
            'error': f'文件过大，最大支持 {max_size // (1024 * 1024)}MB'
        })

    # ── 多媒体解析分支 ──
    if ext in media_extensions and _media_parser:
        try:
            file_content = file.read()
            file.seek(0)

            _ts = datetime.now().strftime('%Y%m%d%H%M%S')
            _h = hashlib.md5(f"{username}_{filename}_{_ts}".encode()).hexdigest()[:8]
            doc_id = f"doc_{username}_{_h}"
            media_type_val = _media_parser.get_media_type(filename)

            # 保存原始媒体文件到本地
            media_file_path = ''
            has_original_file = False
            media_url = ''
            public_media_url = ''
            public_token = ''
            if _media_upload_dir:
                try:
                    user_dir = os.path.join(_media_upload_dir, username)
                    os.makedirs(user_dir, exist_ok=True)
                    try:
                        os.chmod(user_dir, 0o755)
                    except Exception:
                        pass

                    stored_name = f"{doc_id}.{ext if ext else 'bin'}"
                    media_file_path = os.path.join(user_dir, stored_name)
                    with open(media_file_path, 'wb') as mf:
                        mf.write(file_content)
                    has_original_file = True
                    media_url = f"/api/kb/media/{doc_id}"

                    public_token = _generate_public_token(doc_id, username)
                    if _server_base_url:
                        server_base = _server_base_url
                    else:
                        try:
                            server_base = f"{request.scheme}://{request.host}"
                        except Exception:
                            server_base = 'http://localhost:5003'
                    public_media_url = f"{server_base}/api/kb/media/public/{doc_id}/{public_token}"

                    print(f"   💾 原始文件已保存: {media_file_path}")
                    print(f"   🔗 本地公开链接: {public_media_url}")
                except Exception as save_err:
                    print(f"   ⚠️ 保存原始文件失败: {save_err}")
                    traceback.print_exc()
                    media_file_path = ''

            # 捕获 server_base
            if _server_base_url:
                captured_server_base = _server_base_url
            else:
                try:
                    captured_server_base = f"{request.scheme}://{request.host}"
                except Exception:
                    captured_server_base = 'http://localhost:5003'

            # ★ 提前获取 dataset_id（给异步线程用）
            captured_dataset_id = _get_user_dataset_id(username)

            # MongoDB 创建记录
            _db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {
                    'doc_id': doc_id,
                    'username': username,
                    'filename': filename,
                    'file_type': ext,
                    'folder_id': folder_id,
                    'status': 'parsing',
                    'upload_time': datetime.now(),
                    'file_size': file_size,
                    'parsed_from_media': True,
                    'media_type': media_type_val,
                    'shared': False,
                    'has_original_file': has_original_file,
                    'media_file_path': media_file_path,
                    'media_url': media_url,
                    'public_media_url': public_media_url,
                    'public_media_token': public_token,
                }},
                upsert=True
            )

            # ★★★ 异步解析 ★★★
            def _async_parse():
                try:
                    def _on_progress(stage, pct):
                        try:
                            _db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {'parse_stage': stage, 'parse_progress': pct}}
                            )
                        except Exception:
                            pass

                    result = _media_parser.parse(
                        file_content, filename, username,
                        on_progress=_on_progress
                    )

                    if not result.get('success'):
                        _db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {
                                'status': 'failed',
                                'error_message': result.get('error', '多媒体解析失败'),
                            }}
                        )
                        return

                    parsed_text = result.get('text', '')
                    metadata = result.get('metadata', {})

                    if not parsed_text.strip():
                        _db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {'status': 'failed', 'error_message': '解析结果为空'}}
                        )
                        return

                    # ★★★ 图片：确定嵌入URL ★★★
                    embedded_img_url = ''
                    url_source = ''

                    if media_type_val == 'image' and has_original_file:
                        # 方案A：上传到 FastGPT
                        print(f"   🔄 正在上传图片到 FastGPT...")
                        fastgpt_result = _upload_image_to_fastgpt(
                            file_content, filename, dataset_id=captured_dataset_id)
                        if fastgpt_result.get('success'):
                            embedded_img_url = fastgpt_result['url']
                            url_source = 'fastgpt'
                            print(f"   ✅ 方案A成功: {embedded_img_url}")
                            _db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {'fastgpt_image_url': embedded_img_url, 'image_url_source': 'fastgpt'}}
                            )
                        else:
                            print(f"   ⚠️ 方案A失败: {fastgpt_result.get('error', '?')[:120]}")

                        # 方案B：本地公开URL
                        if not embedded_img_url and public_media_url:
                            embedded_img_url = public_media_url
                            url_source = 'local'
                            print(f"   📎 方案B: {embedded_img_url}")
                            _db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {'image_url_source': 'local'}}
                            )

                        # 方案C：构建URL
                        if not embedded_img_url:
                            token = _generate_public_token(doc_id, username)
                            embedded_img_url = f"{captured_server_base}/api/kb/media/public/{doc_id}/{token}"
                            url_source = 'constructed'
                            print(f"   📎 方案C: {embedded_img_url}")

                    # 嵌入图片链接到知识库文本
                    if embedded_img_url and media_type_val == 'image':
                        image_header = (
                            f"## 📎 图片文件：{filename}\n\n"
                            f"![{filename}]({embedded_img_url})\n\n"
                            f"图片直链：{embedded_img_url}\n\n"
                            f"---\n\n"
                            f"以下是对该图片的 AI 描述：\n\n"
                        )
                        parsed_text = image_header + parsed_text
                        print(f"   🖼️ 已嵌入图片链接 (来源: {url_source})")

                    # 存到 MongoDB
                    _db.kb_documents.update_one(
                        {'doc_id': doc_id},
                        {'$set': {
                            'parsed_text': parsed_text,
                            'parse_metadata': metadata,
                            'embedded_image_url': embedded_img_url,
                        }}
                    )

                    # 上传到 FastGPT 知识库
                    upload_result = _fastgpt_kb_service.upload_parsed_text(
                        username=username,
                        text_content=parsed_text,
                        original_filename=filename,
                        folder_id=folder_id,
                        metadata=metadata,
                    )

                    if not upload_result.get('success'):
                        _db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {
                                'status': 'failed',
                                'error_message': upload_result.get('error', '上传失败'),
                            }}
                        )
                        return

                    collection_id = upload_result.get('collection_id', '')
                    chunk_count = upload_result.get('chunk_count', 0)

                    if not collection_id:
                        dup = _db.kb_documents.find_one({
                            'username': username, 'filename': filename,
                            'doc_id': {'$ne': doc_id},
                            'collection_id': {'$exists': True, '$ne': ''},
                        }, sort=[('upload_time', -1)])
                        if dup:
                            collection_id = dup.get('collection_id', '')
                            chunk_count = chunk_count or dup.get('chunk_count', 0)

                    update_fields = {
                        'status': 'processing',
                        'chunk_count': chunk_count,
                        'data_count': chunk_count,
                    }
                    if collection_id:
                        update_fields['collection_id'] = collection_id

                    _db.kb_documents.update_one(
                        {'doc_id': doc_id},
                        {'$set': update_fields}
                    )

                    if collection_id:
                        _db.kb_documents.delete_many({
                            'username': username,
                            'collection_id': collection_id,
                            'doc_id': {'$ne': doc_id},
                        })

                    print(f"✅ 异步解析完成: {filename} → {chunk_count} 块 (图片: {url_source or 'N/A'})")

                except Exception as e:
                    traceback.print_exc()
                    try:
                        _db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {
                                'status': 'failed',
                                'error_message': f'异步解析异常: {str(e)}',
                            }},
                            upsert=True
                        )
                    except Exception:
                        pass

            thread = threading.Thread(target=_async_parse, daemon=True)
            thread.start()

            return jsonify({
                'success': True,
                'doc_id': doc_id,
                'status': 'parsing',
                'message': f'多媒体文件已开始解析（{media_type_val}），请稍候...',
                'media_type': media_type_val,
            })

        except Exception as e:
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)})

    # ── 传统文本上传 ──
    try:
        result = _fastgpt_kb_service.upload_file(username, file, file.filename, folder_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ★★★ v4.0：文档列表接口，不再检测 m3e，信任 FastGPT 同步状态 ★★★
@kb_bp.route('/api/kb/documents')
@_require_login
def api_kb_documents():
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化',
                        'documents': [], 'total': 0, 'has_processing': False})
    try:
        # 正常获取文档列表（状态由 FastGPT 同步决定，不做外部 m3e 预检）
        if hasattr(_fastgpt_kb_service, 'get_documents_with_realtime_status'):
            result = _fastgpt_kb_service.get_documents_with_realtime_status(username)
        else:
            documents = list(_db.kb_documents.find(
                {'username': username}, {'_id': 0}).sort('upload_time', -1))
            result = {
                'success': True, 'documents': documents,
                'total': len(documents),
                'has_processing': any(d.get('status') == 'processing' for d in documents)
            }

        if result.get('success'):
            documents = result.get('documents', [])
            formatted_docs = [_format_document(doc) for doc in documents]
            has_processing = result.get('has_processing', False)
            has_parsing = any(d.get('status') == 'parsing' for d in documents)

            # ★ 仅做简单的卡住提示，不自动标记失败
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
                    'stuck_docs': stuck_docs,
                }

            return jsonify({
                'success': True, 'documents': formatted_docs,
                'total': len(formatted_docs),
                'has_processing': has_processing or has_parsing,
                'model_warning': model_warning,
            })
        else:
            return jsonify({
                'success': False, 'error': result.get('error', '获取失败'),
                'documents': [], 'total': 0, 'has_processing': False
            })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e),
                        'documents': [], 'total': 0, 'has_processing': False})


@kb_bp.route('/api/kb/chat', methods=['POST'])
@_require_login
def api_kb_chat():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)
    if not query:
        return jsonify({'success': False, 'error': '问题不能为空'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.chat(username, query, top_k)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e),
                        'answer': '抱歉，处理您的问题时出现了错误。'})


@kb_bp.route('/api/kb/search', methods=['POST'])
@_require_login
def api_kb_search():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)
    if not query:
        return jsonify({'success': False, 'error': '搜索内容不能为空'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.search(username, query, top_k)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'results': []})


@kb_bp.route('/api/kb/dataset-id', methods=['GET'])
def api_kb_get_dataset_id():
    student_id = request.args.get('student_id', '').strip()
    if not student_id:
        return jsonify({'success': False, 'error': '缺少 student_id 参数', 'dataset_id': None})
    try:
        user_kb = _db.user_fastgpt_kb.find_one({'username': student_id})
        if user_kb and user_kb.get('dataset_id'):
            return jsonify({
                'success': True, 'student_id': student_id,
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
                    {'username': student_id},
                    {'$set': {'dataset_id': dataset_id, 'updated_at': datetime.now()}},
                    upsert=True
                )
                return jsonify({
                    'success': True, 'student_id': student_id,
                    'dataset_id': dataset_id,
                    'dataset_name': f'个人知识库_{student_id}'
                })
        return jsonify({
            'success': False, 'error': f'未找到用户 {student_id} 的知识库',
            'dataset_id': None
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'dataset_id': None})


@kb_bp.route('/api/kb/list-all-datasets', methods=['GET'])
def api_kb_list_all_datasets():
    try:
        mappings = list(_db.user_fastgpt_kb.find({}, {'_id': 0}))
        return jsonify({'success': True, 'total': len(mappings), 'mappings': mappings})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/smart-chat', methods=['POST'])
@_require_login
def api_kb_smart_chat():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'success': False, 'error': '问题不能为空'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.chat(username, query, top_k=5)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/workflow-search', methods=['POST'])
def api_kb_workflow_search():
    data = request.get_json() or {}
    student_id = data.get('student_id', '').strip()
    query = data.get('query', '').strip()
    top_k = data.get('top_k', 5)
    if not student_id or not query or not _fastgpt_kb_service:
        return jsonify([])
    try:
        dataset_id = _fastgpt_kb_service.get_or_create_user_dataset(student_id)
        result = _fastgpt_kb_service.search(student_id, query, top_k)
        if result.get('success') and result.get('results'):
            quote_list = []
            for i, item in enumerate(result['results']):
                content = item.get('content', '').strip()
                source = item.get('source', '未知来源')
                score = item.get('score', 0)
                collection_id = item.get('collection_id', '')
                if source.startswith('['):
                    source = re.sub(r'^\[.*?\]\s*', '', source) or source
                data_id = item.get('data_id', '')
                item_dataset_id = item.get('dataset_id', '') or dataset_id or ''
                if isinstance(score, (list, tuple)):
                    score = score[0] if len(score) > 0 else 0
                try:
                    score = float(score) if score else 0.0
                except (TypeError, ValueError):
                    score = 0.0
                if content:
                    quote_list.append({
                        'id': data_id or f'search_{i}',
                        'datasetId': item_dataset_id,
                        'collectionId': collection_id or '',
                        'sourceName': source,
                        'sourceId': collection_id or '',
                        'q': item.get('q', '') or content[:500],
                        'a': item.get('a', ''),
                        'score': round(score, 4)
                    })
            return jsonify(quote_list)
        return jsonify([])
    except Exception as e:
        traceback.print_exc()
        return jsonify([])


@kb_bp.route('/api/kb/workflow-search', methods=['GET'])
def api_kb_workflow_search_get():
    student_id = request.args.get('student_id', '').strip()
    query = request.args.get('query', '').strip()
    if not student_id or not query:
        return jsonify({
            'success': False, 'error': '请提供 student_id 和 query 参数',
            'usage': '/api/kb/workflow-search?student_id=20243334&query=你的问题'
        })
    try:
        top_k = int(request.args.get('top_k', 5))
        result = _fastgpt_kb_service.search(student_id, query, top_k)
        if result.get('success') and result.get('results'):
            context_parts = []
            for i, item in enumerate(result['results']):
                content = item.get('content', '').strip()
                source = item.get('source', '')
                if content:
                    context_parts.append(f"[{i+1}] （来源：{source}）\n{content}")
            return jsonify({
                'success': True, 'searchResult': '\n\n'.join(context_parts),
                'total': len(context_parts), 'student_id': student_id
            })
        return jsonify({
            'success': True, 'searchResult': '', 'total': 0,
            'student_id': student_id, 'message': '未找到相关内容'
        })
    except Exception as e:
        return jsonify({'success': True, 'searchResult': f'搜索出错: {str(e)}', 'isEmpty': True})


@kb_bp.route('/api/kb/sync-from-fastgpt', methods=['POST'])
@_require_login
def api_kb_sync_from_fastgpt():
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.sync_documents_from_fastgpt(username, force=True)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>', methods=['DELETE'])
@_require_login
def api_kb_delete_document(doc_id):
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        doc = _db.kb_documents.find_one({'doc_id': doc_id, 'username': username})
        media_path = doc.get('media_file_path', '') if doc else ''

        success = _fastgpt_kb_service.delete_document(username, doc_id)
        if success:
            if media_path and os.path.isfile(media_path):
                try:
                    os.unlink(media_path)
                    print(f"   🗑️ 已删除原始媒体文件: {media_path}")
                except OSError as e:
                    print(f"   ⚠️ 删除原始文件失败: {e}")
            return jsonify({'success': True, 'message': '文档删除成功'})
        else:
            return jsonify({'success': False, 'error': '文档不存在或删除失败'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>/share', methods=['POST'])
@_require_login
def api_kb_share_document(doc_id):
    username, _, _ = _get_user_info()
    if not doc_id or not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '缺少文档ID或服务未初始化'})
    try:
        result = _fastgpt_kb_service.share_document(username, doc_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>/unshare', methods=['POST'])
@_require_login
def api_kb_unshare_document(doc_id):
    username, _, _ = _get_user_info()
    if not doc_id or not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '缺少文档ID或服务未初始化'})
    try:
        result = _fastgpt_kb_service.unshare_document(username, doc_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/sync-names', methods=['POST'])
@_require_login
def api_kb_sync_names():
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.sync_all_collection_names(username)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/rename/<doc_id>', methods=['POST'])
@_require_login
def api_kb_rename_doc(doc_id):
    username, _, _ = _get_user_info()
    if not doc_id or not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '缺少文档ID或服务未初始化'})
    try:
        data = request.get_json() or {}
        new_name = data.get('new_name', '').strip()
        doc = _db.kb_documents.find_one({'username': username, 'doc_id': doc_id})
        if not doc:
            return jsonify({'success': False, 'error': '文档不存在'})
        collection_id = doc.get('collection_id')
        filename = new_name if new_name else doc.get('filename')
        if not collection_id:
            return jsonify({'success': False, 'error': '文档尚未同步到 FastGPT'})
        if not filename:
            return jsonify({'success': False, 'error': '缺少文件名'})
        result = _fastgpt_kb_service.update_collection_name(collection_id, filename)
        if result.get('success'):
            _db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {'filename': filename, 'name_synced': True, 'name_synced_at': datetime.now()}}
            )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ================== 文件夹管理 API ==================

@kb_bp.route('/api/kb/folders', methods=['GET'])
@_require_login
def api_kb_folders():
    username, _, _ = _get_user_info()
    parent_id = request.args.get('parent_id', None)
    if parent_id == '':
        parent_id = None
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化', 'folders': []})
    try:
        folders = _fastgpt_kb_service.get_folders(username, parent_id)
        return jsonify({'success': True, 'folders': folders, 'total': len(folders)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'folders': []})


@kb_bp.route('/api/kb/folders/tree', methods=['GET'])
@_require_login
def api_kb_folder_tree():
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化', 'tree': []})
    try:
        tree = _fastgpt_kb_service.get_folder_tree(username)
        return jsonify({'success': True, 'tree': tree})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'tree': []})


@kb_bp.route('/api/kb/folder', methods=['POST'])
@_require_login
def api_kb_create_folder():
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    folder_name = data.get('name', '').strip()
    parent_id = data.get('parent_id', None)
    if not folder_name:
        return jsonify({'success': False, 'error': '文件夹名称不能为空'})
    if len(folder_name) > 50:
        return jsonify({'success': False, 'error': '文件夹名称不能超过50个字符'})
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        if char in folder_name:
            return jsonify({'success': False, 'error': f'文件夹名称不能包含特殊字符: {char}'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.create_folder(username, folder_name, parent_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/folder/<folder_id>', methods=['DELETE'])
@_require_login
def api_kb_delete_folder(folder_id):
    username, _, _ = _get_user_info()
    recursive = request.args.get('recursive', 'false').lower() == 'true'
    if not folder_id or not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '缺少文件夹ID或服务未初始化'})
    try:
        result = _fastgpt_kb_service.delete_folder(username, folder_id, recursive)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/folder/<folder_id>/rename', methods=['POST'])
@_require_login
def api_kb_rename_folder(folder_id):
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    new_name = data.get('name', '').strip()
    if not folder_id:
        return jsonify({'success': False, 'error': '缺少文件夹ID'})
    if not new_name:
        return jsonify({'success': False, 'error': '新名称不能为空'})
    if len(new_name) > 50:
        return jsonify({'success': False, 'error': '文件夹名称不能超过50个字符'})
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        if char in new_name:
            return jsonify({'success': False, 'error': f'文件夹名称不能包含特殊字符: {char}'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.rename_folder(username, folder_id, new_name)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>/move', methods=['POST'])
@_require_login
def api_kb_move_document(doc_id):
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    target_folder_id = data.get('folder_id', None)
    if target_folder_id in ('', 'null'):
        target_folder_id = None
    if not doc_id or not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '缺少文档ID或服务未初始化'})
    try:
        result = _fastgpt_kb_service.move_document_to_folder(username, doc_id, target_folder_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ★★★ v4.0：文件夹文档列表，不再检测 m3e ★★★
@kb_bp.route('/api/kb/folder/<folder_id>/documents', methods=['GET'])
@_require_login
def api_kb_folder_documents(folder_id):
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化', 'documents': []})
    try:
        actual_folder_id = None if folder_id == 'root' else folder_id
        documents = _fastgpt_kb_service.get_documents_in_folder(username, actual_folder_id)
        formatted_docs = [_format_document(doc) for doc in documents]
        return jsonify({'success': True, 'documents': formatted_docs, 'total': len(formatted_docs)})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'documents': []})


@kb_bp.route('/api/kb/chat-url', methods=['GET'])
@_require_login
def api_kb_chat_url():
    username, _, _ = _get_user_info()
    share_id = os.environ.get('FASTGPT_SHARE_ID', 'zDrmPPnh9rdi3WmnyWCFwDcb')
    base_url = os.environ.get('FASTGPT_SHARE_BASE_URL', 'http://180.85.206.30:3000')
    user_auth_token = hashlib.md5(f"pkb_auth_{username}".encode()).hexdigest()
    chat_url = f"{base_url}/chat/share?shareId={share_id}&authToken={user_auth_token}"
    return jsonify({
        'success': True, 'chat_url': chat_url,
        'share_id': share_id, 'auth_token': user_auth_token,
        'username': username
    })


# ================== 媒体文件访问 API ==================

@kb_bp.route('/api/kb/media/<doc_id>', methods=['GET'])
@_require_login
def api_kb_serve_media(doc_id):
    username, _, _ = _get_user_info()
    doc = _db.kb_documents.find_one({'doc_id': doc_id, 'username': username})
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    media_path = doc.get('media_file_path', '')
    if not media_path or not os.path.isfile(media_path):
        return jsonify({'error': '原始文件不存在或已被清理'}), 404
    filename = doc.get('filename', 'file')
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_file(media_path, mimetype=mime_type, as_attachment=False, download_name=filename)


@kb_bp.route('/api/kb/media/<doc_id>/download', methods=['GET'])
@_require_login
def api_kb_download_media(doc_id):
    username, _, _ = _get_user_info()
    doc = _db.kb_documents.find_one({'doc_id': doc_id, 'username': username})
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    media_path = doc.get('media_file_path', '')
    if not media_path or not os.path.isfile(media_path):
        return jsonify({'error': '原始文件不存在'}), 404
    filename = doc.get('filename', 'file')
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_file(media_path, mimetype=mime_type, as_attachment=True, download_name=filename)


@kb_bp.route('/api/kb/media/public/<doc_id>/<token>', methods=['GET'])
def api_kb_serve_media_public(doc_id, token):
    """公开媒体访问（不需要登录），通过 token 验证"""
    doc = _db.kb_documents.find_one({'doc_id': doc_id})
    if not doc:
        return jsonify({'error': 'Not found'}), 404
    expected_token = doc.get('public_media_token', '')
    if not expected_token or token != expected_token:
        return jsonify({'error': 'Invalid token'}), 403
    media_path = doc.get('media_file_path', '')
    if not media_path or not os.path.isfile(media_path):
        return jsonify({'error': 'File not found'}), 404
    filename = doc.get('filename', 'file')
    mime_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    response = send_file(media_path, mimetype=mime_type, as_attachment=False, download_name=filename)
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Cache-Control'] = 'public, max-age=86400'
    return response


@kb_bp.route('/api/kb/document/<doc_id>/content', methods=['GET'])
@_require_login
def api_kb_document_content(doc_id):
    username, _, _ = _get_user_info()
    doc = _db.kb_documents.find_one({'doc_id': doc_id, 'username': username})
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    return jsonify({
        'success': True, 'doc_id': doc_id,
        'filename': doc.get('filename', ''),
        'media_type': doc.get('media_type', ''),
        'has_original_file': doc.get('has_original_file', False),
        'media_url': doc.get('media_url', ''),
        'public_media_url': doc.get('public_media_url', ''),
        'fastgpt_image_url': doc.get('fastgpt_image_url', ''),
        'embedded_image_url': doc.get('embedded_image_url', ''),
        'image_url_source': doc.get('image_url_source', ''),
        'parsed_text': doc.get('parsed_text', ''),
        'status': doc.get('status', ''),
        'metadata': doc.get('parse_metadata', {}),
    })


# ================== 解析进度查询 ==================

@kb_bp.route('/api/kb/parse-status/<doc_id>')
@_require_login
def api_kb_parse_status(doc_id):
    username, _, _ = _get_user_info()
    doc = _db.kb_documents.find_one(
        {'username': username, 'doc_id': doc_id},
        {'_id': 0, 'status': 1, 'parse_stage': 1, 'parse_progress': 1,
         'error_message': 1, 'chunk_count': 1, 'media_type': 1}
    )
    if not doc:
        return jsonify({'success': False, 'error': '文档不存在'})
    stage_labels = {
        'extracting_frames': '正在提取视频帧...',
        'analyzing_frames': '正在分析画面内容...',
        'transcribing_audio': '正在转录语音...',
        'summarizing': '正在整理内容...',
        'parsing_slides': '正在解析幻灯片...',
    }
    stage = doc.get('parse_stage', '')
    return jsonify({
        'success': True,
        'status': doc.get('status', 'unknown'),
        'stage': stage,
        'stage_label': stage_labels.get(stage, '处理中...'),
        'progress': doc.get('parse_progress', 0),
        'error': doc.get('error_message'),
        'chunk_count': doc.get('chunk_count', 0),
        'media_type': doc.get('media_type'),
    })


# ================== 模型健康检查路由（仅文本模型+VLM） ==================

@kb_bp.route('/api/kb/model-health')
@_require_login
def api_kb_model_health():
    """
    检测知识库相关模型的可用性（不包含 m3e，索引由 FastGPT 内部管理）
    """
    results = {
        'text_model': _check_text_health(),
        'vlm': _check_vlm_health(),
    }

    # 索引模型信息（仅展示，不做外部检测）
    results['embedding'] = {
        'name': 'm3e',
        'type': '索引模型（向量化）',
        'description': '由 FastGPT 内部管理，无需外部检测',
        'available': True,
        'note': '索引状态以 FastGPT 返回为准',
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
        'timestamp': datetime.now().isoformat(),
    })


@kb_bp.route('/api/kb/model-health/clear-cache', methods=['POST'])
@_require_login
def api_kb_clear_health_cache():
    """清除健康检查缓存，强制下次重新检测"""
    _health_cache.clear()
    return jsonify({'success': True, 'message': '健康检查缓存已清除'})


# ================== 调试端点 ==================

@kb_bp.route('/api/kb/debug/test-image-upload', methods=['POST'])
@_require_login
def api_kb_debug_test_image_upload():
    """调试：测试 FastGPT 图片上传各端点"""
    username, _, _ = _get_user_info()
    if 'file' not in request.files:
        return jsonify({'error': '请上传一个图片文件 (form field: file)'})
    file = request.files['file']
    content = file.read()
    filename = file.filename
    dataset_id = _get_user_dataset_id(username)

    results = {}
    headers = {'Authorization': f'Bearer {_fastgpt_api_key}'}
    mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

    test_configs = [
        ('common/file/upload + chat', 'common/file/upload', {'bucketName': 'chat'}),
        ('common/file/upload + dataset+id', 'common/file/upload',
         {'bucketName': 'dataset', 'metadata': json.dumps({'datasetId': dataset_id or ''})}),
        ('common/file/upload + 无bucket', 'common/file/upload', {}),
        ('common/file/uploadImage + chat', 'common/file/uploadImage', {'bucketName': 'chat'}),
    ]

    for label, path, extra_data in test_configs:
        try:
            url = f"{_fastgpt_api_url}/{path}"
            files_dict = {'file': (filename, io.BytesIO(content), mime)}
            resp = http_requests.post(url, headers=headers, files=files_dict,
                                      data=extra_data, timeout=15)
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:500]
            results[label] = {'status': resp.status_code, 'body': body}
        except Exception as e:
            results[label] = {'error': str(e)}

    full_result = _upload_image_to_fastgpt(content, filename, dataset_id=dataset_id)
    results['_upload_image_to_fastgpt'] = full_result

    results['config'] = {
        'fastgpt_api_url': _fastgpt_api_url,
        'fastgpt_api_key_set': bool(_fastgpt_api_key),
        'fastgpt_api_key_preview': _fastgpt_api_key[:8] + '...' if _fastgpt_api_key else 'N/A',
        'dataset_id': dataset_id,
        'server_base_url': _server_base_url or '(auto-detect)',
        'media_upload_dir': _media_upload_dir,
    }

    return jsonify({'success': True, 'results': results})


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
        'version': 'v4.0.0-trust-fastgpt-indexing',
        'features': {
            'fastgpt_kb': kb_ready,
            'mongodb': _db is not None,
            'dynamic_dataset': True,
            'shared_kb': True,
            'media_parser': media_ready,
            'media_preview': True,
            'public_media_url': True,
            'fastgpt_image_upload': bool(_fastgpt_api_key),
            'supported_media': sorted(list(_media_parser.ALL_EXTENSIONS)) if media_ready else [],
            'embedding_note': '索引由 FastGPT 内部管理，不做外部 m3e 连通性检测',
        },
        'media_upload_dir': _media_upload_dir,
        'server_base_url': _server_base_url or '(auto-detect)',
        'fastgpt_api_url': _fastgpt_api_url,
        'timestamp': datetime.now().isoformat()
    })
