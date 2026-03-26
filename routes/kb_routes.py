# /home/zgllm/test_server/routes/kb_routes.py
# -*- coding: utf-8 -*-
"""
个人知识库路由模块（从 app_v3.py 提取）
所有 /api/kb/* 和 /dashboard/his 路由
"""

import os
import re
import json
import hashlib
import traceback
from datetime import datetime
from flask import Blueprint, session, render_template, request, jsonify

# ================== 创建蓝图 ==================
kb_bp = Blueprint('kb', __name__)

# ================== 全局引用（由 init_kb_blueprint 注入） ==================
_fastgpt_kb_service = None
_db = None
_login_required = None
_process_user_courses = None


def init_kb_blueprint(app, db, fastgpt_kb_service, login_required_func, process_user_courses_func):
    """
    初始化 KB 蓝图所需的依赖

    在 app.py 中调用：
        from routes.kb_routes import kb_bp, init_kb_blueprint
        init_kb_blueprint(app, db, fastgpt_kb_service, login_required, process_user_courses)
        app.register_blueprint(kb_bp)
    """
    global _fastgpt_kb_service, _db, _login_required, _process_user_courses
    _fastgpt_kb_service = fastgpt_kb_service
    _db = db
    _login_required = login_required_func
    _process_user_courses = process_user_courses_func


# ================== 辅助函数 ==================

def _get_user_info():
    """获取当前登录用户信息"""
    username = session.get('username', '')
    name = session.get('name', username)
    role = session.get('role', 'student')
    return username, name, role


def _safe_process_user_courses(username, role):
    """安全地获取用户课程列表"""
    try:
        if _process_user_courses:
            return _process_user_courses(username, role)
    except Exception as e:
        print(f"⚠️ process_user_courses 调用失败: {e}")
    return []


def _get_kb_stats(username):
    """获取用户知识库统计信息"""
    if not _fastgpt_kb_service:
        return {
            'documents': 0, 'ready_documents': 0,
            'chunks': 0, 'queries': 0, 'rag_enabled': False
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
        'documents': 0, 'ready_documents': 0,
        'chunks': 0, 'queries': 0, 'rag_enabled': False
    }


def _format_document(doc):
    """将后端文档数据格式化为前端需要的结构"""
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
    }


# ================== 装饰器包装 ==================
# Flask Blueprint 无法直接用外部的 login_required 装饰器
# 使用 before_request 统一鉴权，或在每个路由中手动调用

def _require_login(f):
    """包装外部的 login_required 装饰器"""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if _login_required:
            # 检查是否已登录（直接检查 session）
            if not session.get('username'):
                from flask import redirect, url_for
                return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


# ================== 页面路由 ==================

@kb_bp.route('/dashboard/his')
@_require_login
def his():
    """个人知识库页面"""
    username, name, role = _get_user_info()
    user_courses_info = _safe_process_user_courses(username, role)
    kb_stats = _get_kb_stats(username)

    return render_template('dashboard/his.html',
                           username=username,
                           name=name,
                           role=role,
                           courses_info=user_courses_info,
                           kb_stats=kb_stats,
                           page_title='个人知识库')


# ================== API 路由 ==================

@kb_bp.route('/api/kb/stats')
@_require_login
def api_kb_stats():
    """获取知识库统计信息"""
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
    """上传文件到知识库"""
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

    allowed_extensions = {'pdf', 'txt', 'md', 'doc', 'docx'}
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed_extensions:
        return jsonify({'success': False,
                        'error': f'不支持的文件类型: {ext}，支持: {", ".join(allowed_extensions)}'})

    file.seek(0, 2)
    file_size = file.tell()
    file.seek(0)
    if file_size > 50 * 1024 * 1024:
        return jsonify({'success': False, 'error': '文件过大，最大支持 50MB'})

    try:
        result = _fastgpt_kb_service.upload_file(username, file, file.filename, folder_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/documents')
@_require_login
def api_kb_documents():
    """获取文档列表"""
    username, _, _ = _get_user_info()

    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化',
                        'documents': [], 'total': 0, 'has_processing': False})
    try:
        if hasattr(_fastgpt_kb_service, 'get_documents_with_realtime_status'):
            result = _fastgpt_kb_service.get_documents_with_realtime_status(username)
        else:
            documents = list(_db.kb_documents.find(
                {'username': username}, {'_id': 0}
            ).sort('upload_time', -1))
            result = {
                'success': True, 'documents': documents,
                'total': len(documents),
                'has_processing': any(d.get('status') == 'processing' for d in documents)
            }

        if result.get('success'):
            documents = result.get('documents', [])
            formatted_docs = [_format_document(doc) for doc in documents]
            return jsonify({
                'success': True, 'documents': formatted_docs,
                'total': len(formatted_docs),
                'has_processing': result.get('has_processing', False)
            })
        else:
            return jsonify({'success': False, 'error': result.get('error', '获取失败'),
                            'documents': [], 'total': 0, 'has_processing': False})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e),
                        'documents': [], 'total': 0, 'has_processing': False})


@kb_bp.route('/api/kb/chat', methods=['POST'])
@_require_login
def api_kb_chat():
    """知识库问答"""
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
    """知识库搜索"""
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
    """根据学号获取 FastGPT 知识库 ID（供 FastGPT 工作流调用，无需登录）"""
    student_id = request.args.get('student_id', '').strip()
    if not student_id:
        return jsonify({'success': False, 'error': '缺少 student_id 参数', 'dataset_id': None})

    try:
        user_kb = _db.user_fastgpt_kb.find_one({'username': student_id})
        if user_kb and user_kb.get('dataset_id'):
            dataset_id = user_kb['dataset_id']
            return jsonify({
                'success': True, 'student_id': student_id,
                'dataset_id': dataset_id,
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

        return jsonify({'success': False, 'error': f'未找到用户 {student_id} 的知识库',
                        'dataset_id': None})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e), 'dataset_id': None})


@kb_bp.route('/api/kb/list-all-datasets', methods=['GET'])
def api_kb_list_all_datasets():
    """列出所有用户的知识库映射（调试用）"""
    try:
        mappings = list(_db.user_fastgpt_kb.find({}, {'_id': 0}))
        return jsonify({'success': True, 'total': len(mappings), 'mappings': mappings})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/smart-chat', methods=['POST'])
@_require_login
def api_kb_smart_chat():
    """智能问答"""
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
    """供 FastGPT 工作流调用的搜索接口"""
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
            search_results = result['results']
            quote_list = []

            for i, item in enumerate(search_results):
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
        else:
            return jsonify([])
    except Exception as e:
        traceback.print_exc()
        return jsonify([])


@kb_bp.route('/api/kb/workflow-search', methods=['GET'])
def api_kb_workflow_search_get():
    """GET 方法测试接口"""
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
                'success': True,
                'searchResult': '\n\n'.join(context_parts),
                'total': len(context_parts),
                'student_id': student_id
            })
        else:
            return jsonify({
                'success': True, 'searchResult': '', 'total': 0,
                'student_id': student_id, 'message': '未找到相关内容'
            })
    except Exception as e:
        return jsonify({'success': True, 'searchResult': f'搜索出错: {str(e)}', 'isEmpty': True})


@kb_bp.route('/api/kb/sync-from-fastgpt', methods=['POST'])
@_require_login
def api_kb_sync_from_fastgpt():
    """手动同步 FastGPT 文档到 MongoDB"""
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
    """删除文档"""
    username, _, _ = _get_user_info()
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        success = _fastgpt_kb_service.delete_document(username, doc_id)
        if success:
            return jsonify({'success': True, 'message': '文档删除成功'})
        else:
            return jsonify({'success': False, 'error': '文档不存在或删除失败'})
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>/share', methods=['POST'])
@_require_login
def api_kb_share_document(doc_id):
    """共享文档到共享知识库"""
    username, _, _ = _get_user_info()
    if not doc_id:
        return jsonify({'success': False, 'error': '缺少文档ID'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.share_document(username, doc_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/document/<doc_id>/unshare', methods=['POST'])
@_require_login
def api_kb_unshare_document(doc_id):
    """取消文档共享"""
    username, _, _ = _get_user_info()
    if not doc_id:
        return jsonify({'success': False, 'error': '缺少文档ID'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.unshare_document(username, doc_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/sync-names', methods=['POST'])
@_require_login
def api_kb_sync_names():
    """同步所有文档名称到 FastGPT"""
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
    """重命名文档"""
    username, _, _ = _get_user_info()
    if not doc_id:
        return jsonify({'success': False, 'error': '缺少文档ID'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})

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
                {'$set': {'filename': filename, 'name_synced': True,
                          'name_synced_at': datetime.now()}}
            )
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


# ================== 文件夹管理 API ==================

@kb_bp.route('/api/kb/folders', methods=['GET'])
@_require_login
def api_kb_folders():
    """获取文件夹列表"""
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
    """获取完整文件夹树"""
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
    """创建文件夹"""
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
    """删除文件夹"""
    username, _, _ = _get_user_info()
    recursive = request.args.get('recursive', 'false').lower() == 'true'

    if not folder_id:
        return jsonify({'success': False, 'error': '缺少文件夹ID'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.delete_folder(username, folder_id, recursive)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/folder/<folder_id>/rename', methods=['POST'])
@_require_login
def api_kb_rename_folder(folder_id):
    """重命名文件夹"""
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
    """移动文档到指定文件夹"""
    username, _, _ = _get_user_info()
    data = request.get_json() or {}
    target_folder_id = data.get('folder_id', None)
    if target_folder_id in ('', 'null'):
        target_folder_id = None

    if not doc_id:
        return jsonify({'success': False, 'error': '缺少文档ID'})
    if not _fastgpt_kb_service:
        return jsonify({'success': False, 'error': '知识库服务未初始化'})
    try:
        result = _fastgpt_kb_service.move_document_to_folder(username, doc_id, target_folder_id)
        return jsonify(result)
    except Exception as e:
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)})


@kb_bp.route('/api/kb/folder/<folder_id>/documents', methods=['GET'])
@_require_login
def api_kb_folder_documents(folder_id):
    """获取指定文件夹中的文档"""
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
    """获取用户知识库的聊天URL"""
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


# ================== 健康检查 ==================

@kb_bp.route('/api/kb/health')
def api_kb_health():
    """知识库服务健康检查"""
    kb_ready = False
    if _fastgpt_kb_service:
        try:
            kb_ready = _fastgpt_kb_service.is_ready()
        except Exception:
            pass

    return jsonify({
        'status': 'ok',
        'version': 'v3.0.0-fastgpt',
        'features': {
            'fastgpt_kb': kb_ready,
            'mongodb': _db is not None,
            'dynamic_dataset': True,
            'shared_kb': True
        },
        'timestamp': datetime.now().isoformat()
    })
