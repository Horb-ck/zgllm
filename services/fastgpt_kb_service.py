# -*- coding: utf-8 -*-
"""
FastGPT 知识库服务
适配 FastGPT 的 Dataset -> Collection -> Data 数据层级
支持文件夹（子目录）管理功能

🔧 架构说明：
   文件夹仅为 MongoDB 逻辑分组标签，不在 FastGPT 中创建子 Dataset。
   所有文档始终存放在用户根 Dataset 中，确保：
     - search() 能覆盖所有文档
     - sync 能同步所有文档
     - 前端文件夹展示正常

🔧 修复：支持从 FastGPT 同步历史文档到 MongoDB
🔧 修复：使用 list API 批量获取真实 trainingAmount，而非 detail API
🔧 简化：不再尝试移动旧知识库，直接在「个人知识库」文件夹内创建新的
🔧 新增：共享知识库管理（share / unshare）
🔧 新增：删除文档时同步清理共享副本
🔧 修复：共享时从 FastGPT 内部复制 Collection 数据
🔧 修复：数据块拉取增加响应日志 + GET 回退 + searchTest/rawText 多级回退
🔧 修复：批量插入使用 pushData 优先 + insertData 回退
🔒 隐私：共享知识库使用匿名文件名，不暴露学号/姓名
🔒 隐私：搜索结果中共享文档仅对所有者显示原始文件名
🔧 新增：每个 chunk 注入文件名，支持按文件名检索
🔧 新增：搜索增加文件名匹配回退（覆盖新旧文档）
🔧 新增：上传/写入耗时统计，控制台输出详细报告
"""

import os
import re
import requests
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import hashlib
import traceback
from urllib.parse import quote
import time


class FastGPTKBService:
    """FastGPT 知识库服务封装"""

    def __init__(self, db, base_url: str = None, api_key: str = None):
        self.db = db
        self.base_url = base_url or os.environ.get('FASTGPT_API_URL', 'http://180.85.206.30:3000/api')
        self.api_key = api_key or os.environ.get('FASTGPT_API_KEY', '')

        self.llm_base_url = os.environ.get('LLM_API_URL', 'http://180.85.206.30:3000/api/v1')
        self.llm_api_key = os.environ.get('LLM_API_KEY', self.api_key)
        self.llm_model = os.environ.get('LLM_MODEL', 'Qwen3-8B')
        self.app_api_key = os.environ.get('FASTGPT_APP_KEY', '')

        self.default_vector_model = os.environ.get('FASTGPT_VECTOR_MODEL', 'm3e')
        self.default_agent_model = os.environ.get('FASTGPT_AGENT_MODEL', 'Qwen3-8B')

        self._user_dataset_cache = {}
        self._filename_cache = {}
        self._folder_cache = {}
        self._last_sync_time = {}
        self._parent_folder_id = None
        self._shared_dataset_id = None

        self._reset_old_bindings()

        print(f"✅ FastGPT KB Service 初始化")
        print(f"   API URL: {self.base_url}")
        print(f"   API Key: {'已配置' if self.api_key else '未配置'}")
        print(f"   支持功能: 文件夹管理（纯逻辑分组）+ FastGPT 文档同步 + 共享知识库")
        print(f"   🔧 架构: 文件夹仅为 MongoDB 逻辑标签，所有文档始终在根 Dataset")
        print(f"   🔧 修复: 使用 list API 获取真实 trainingAmount")
        print(f"   🔧 新增: 共享知识库 + 无文件共享（多级回退）")
        print(f"   🔒 隐私: 共享知识库匿名化，不暴露学号/姓名")
        print(f"   🔧 新增: chunk注入文件名 + 文件名匹配回退搜索")

    def _reset_old_bindings(self):
        try:
            result = self.db.user_fastgpt_kb.update_many(
                {},
                {'$unset': {'in_parent_folder': ''}}
            )
            if result.modified_count > 0:
                print(f"   🔄 重置了 {result.modified_count} 条知识库绑定标记")
        except Exception as e:
            print(f"   ⚠️ 重置绑定标记失败: {e}")

    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

    def _get_upload_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.api_key}'
        }

    def is_ready(self) -> bool:
        return bool(self.api_key)

    # ================== 🔒 隐私工具方法 ==================

    def _generate_shared_anonymous_name(self, doc_id: str, filename: str) -> str:
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        anonymous_hash = hashlib.sha256(
            f"shared_{doc_id}_pkb_anonymous_salt_v1".encode()
        ).hexdigest()[:12]
        return f"shared_{anonymous_hash}.{ext}"

    def _generate_shared_doc_id(self, doc_id: str) -> str:
        return f"shared_{hashlib.sha256(doc_id.encode()).hexdigest()[:16]}"

    def _resolve_shared_source(self, username: str, source_name: str,
                                collection_id: str) -> str:
        if not collection_id:
            return "共享文档"

        try:
            doc = self.db.kb_documents.find_one(
                {'shared_collection_id': collection_id},
                {'username': 1, 'filename': 1}
            )

            if doc:
                if doc.get('username') == username:
                    return doc.get('filename', source_name or '共享文档')
                else:
                    return "共享文档"
        except Exception as e:
            print(f"   ⚠️ 解析共享来源失败: {e}")

        return source_name or "共享文档"

    # ================== 从 FastGPT 同步文档到 MongoDB ==================

    def _should_sync(self, username: str, interval: int = 60) -> bool:
        last_time = self._last_sync_time.get(username)
        if last_time is None:
            return True
        return (datetime.now() - last_time).total_seconds() >= interval

    def sync_documents_from_fastgpt(self, username: str, force: bool = False) -> Dict[str, Any]:
        if not force and not self._should_sync(username):
            return {'success': True, 'synced': 0, 'message': '跳过同步（冷却中）'}

        print(f"\n{'='*50}")
        print(f"🔄 开始从 FastGPT 同步文档到 MongoDB")
        print(f"👤 用户: {username}")

        dataset_id = self.get_or_create_user_dataset(username)
        if not dataset_id:
            return {'success': False, 'error': '无法获取用户知识库', 'synced': 0}

        fastgpt_collections = self._fetch_all_collections_from_fastgpt(dataset_id)

        if fastgpt_collections is None:
            print(f"⚠️ 从 FastGPT 获取 Collection 列表失败，跳过同步")
            self._last_sync_time[username] = datetime.now()
            return {'success': False, 'error': '从 FastGPT 获取列表失败', 'synced': 0}

        print(f"📦 FastGPT 中共有 {len(fastgpt_collections)} 个 Collection")

        existing_collection_ids = set()
        existing_docs = self.db.kb_documents.find(
            {'username': username, 'collection_id': {'$exists': True, '$ne': None}},
            {'collection_id': 1}
        )
        for doc in existing_docs:
            cid = doc.get('collection_id')
            if cid:
                existing_collection_ids.add(cid)

        print(f"📋 MongoDB 中已有 {len(existing_collection_ids)} 条记录")

        fastgpt_collection_ids = set()
        for c in fastgpt_collections:
            cid = c.get('_id', '')
            if cid:
                fastgpt_collection_ids.add(cid)

        missing_ids = fastgpt_collection_ids - existing_collection_ids

        if not missing_ids:
            print(f"✅ 无需同步，所有文档都已在 MongoDB 中")
            self._last_sync_time[username] = datetime.now()
            return {'success': True, 'synced': 0, 'existing': len(existing_collection_ids),
                    'total': len(fastgpt_collections)}

        print(f"🔍 发现 {len(missing_ids)} 个需要同步的文档")

        synced = 0
        errors = []

        for collection in fastgpt_collections:
            collection_id = collection.get('_id', '')

            if not collection_id or collection_id not in missing_ids:
                continue

            collection_type = collection.get('type', '')
            if collection_type in ('virtual', 'link', 'folder'):
                print(f"   ⏭️ 跳过非文件类型: {collection.get('name', '')} (type={collection_type})")
                continue

            try:
                fastgpt_name = collection.get('name', '未知文件')

                file_type = ''
                if '.' in fastgpt_name:
                    file_type = fastgpt_name.rsplit('.', 1)[-1].lower()

                doc_id = self._generate_doc_id(username, fastgpt_name)

                data_count = (
                    collection.get('dataAmount', 0) or
                    collection.get('indexAmount', 0) or
                    0
                )
                training_count = collection.get('trainingAmount', 0) or 0

                if training_count > 0:
                    status = 'processing'
                elif data_count > 0:
                    status = 'ready'
                else:
                    status = 'pending'

                upload_time = self._parse_fastgpt_time(collection.get('createTime'))

                doc_record = {
                    'doc_id': doc_id,
                    'username': username,
                    'filename': fastgpt_name,
                    'file_type': file_type,
                    'dataset_id': dataset_id,
                    'collection_id': collection_id,
                    'folder_id': None,
                    'status': status,
                    'chunk_count': data_count,
                    'upload_time': upload_time,
                    'file_size': collection.get('rawTextLength', 0) or 0,
                    'name_synced': True,
                    'synced_from_fastgpt': True,
                    'synced_at': datetime.now(),
                    'shared': False
                }

                self.db.kb_documents.insert_one(doc_record)
                synced += 1

                print(f"   ✅ 同步: {fastgpt_name} (status={status}, chunks={data_count})")

            except Exception as e:
                error_msg = f"同步 {collection.get('name', collection_id)} 失败: {str(e)}"
                print(f"   ❌ {error_msg}")
                errors.append(error_msg)

        self._clear_filename_cache(username)
        self._last_sync_time[username] = datetime.now()

        print(f"🔄 同步完成: 新同步 {synced} 个, 已存在 {len(existing_collection_ids)} 个, 错误 {len(errors)} 个")
        print(f"{'='*50}")

        return {
            'success': True,
            'synced': synced,
            'existing': len(existing_collection_ids),
            'total': len(fastgpt_collections),
            'errors': errors
        }

    def _fetch_all_collections_from_fastgpt(self, dataset_id: str) -> Optional[List[Dict]]:
        all_collections = []
        page_num = 1
        page_size = 50

        while True:
            url = f"{self.base_url}/core/dataset/collection/list"

            payload = {
                "datasetId": dataset_id,
                "parentId": None,
                "pageNum": page_num,
                "pageSize": page_size,
                "searchText": ""
            }

            try:
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )

                if response.status_code != 200:
                    print(f"   ❌ HTTP 错误: {response.status_code}")
                    if page_num == 1:
                        return self._fetch_collections_get_fallback(dataset_id)
                    break

                result = response.json()

                if result.get('code') != 200:
                    print(f"   ❌ API 错误: {result.get('message', '未知错误')}")
                    if page_num == 1:
                        return self._fetch_collections_get_fallback(dataset_id)
                    break

                data = result.get('data', {})

                if isinstance(data, dict):
                    items = data.get('data', [])
                    total = data.get('total', 0)
                elif isinstance(data, list):
                    items = data
                    total = len(data)
                else:
                    items = []
                    total = 0

                if not items:
                    break

                all_collections.extend(items)

                print(f"   📄 第 {page_num} 页: {len(items)} 个 (累计 {len(all_collections)}/{total})")

                if len(all_collections) >= total or len(items) < page_size:
                    break

                page_num += 1

                if page_num > 100:
                    break

            except Exception as e:
                print(f"   ❌ 获取 Collection 列表异常: {e}")
                if page_num == 1:
                    return self._fetch_collections_get_fallback(dataset_id)
                break

        return all_collections

    def _fetch_collections_get_fallback(self, dataset_id: str) -> Optional[List[Dict]]:
        url = f"{self.base_url}/core/dataset/collection/list"

        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                params={'datasetId': dataset_id, 'pageNum': 1, 'pageSize': 100},
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    data = result.get('data', {})
                    if isinstance(data, dict):
                        return data.get('data', [])
                    elif isinstance(data, list):
                        return data

            return None

        except Exception as e:
            print(f"   ❌ GET 方法异常: {e}")
            return None

    def _parse_fastgpt_time(self, time_value) -> datetime:
        if not time_value:
            return datetime.now()

        try:
            if isinstance(time_value, str):
                cleaned = time_value.replace('Z', '').replace('+00:00', '')
                if 'T' in cleaned:
                    return datetime.fromisoformat(cleaned)
                return datetime.strptime(cleaned, '%Y-%m-%d %H:%M:%S')
            elif isinstance(time_value, (int, float)):
                if time_value > 1e12:
                    return datetime.fromtimestamp(time_value / 1000)
                return datetime.fromtimestamp(time_value)
            elif isinstance(time_value, datetime):
                return time_value
        except Exception:
            pass

        return datetime.now()

    # ================== 批量获取真实状态 ==================

    def _batch_get_collection_statuses(self, dataset_id: str) -> Dict[str, Dict]:
        statuses = {}

        try:
            collections = self._fetch_all_collections_from_fastgpt(dataset_id)
            if not collections:
                return statuses

            for c in collections:
                cid = c.get('_id', '')
                if not cid:
                    continue

                training_amount = c.get('trainingAmount', 0) or 0
                data_amount = c.get('dataAmount', 0) or c.get('indexAmount', 0) or 0
                error_count = c.get('errorCount', 0) or 0

                print(f"   📊 [list API] Collection {cid[:8]}...: "
                      f"trainingAmount={training_amount}, dataAmount={data_amount}, errorCount={error_count}")

                if error_count > 0:
                    status = 'error'
                elif training_amount > 0:
                    status = 'processing'
                elif data_amount > 0:
                    status = 'ready'
                else:
                    status = 'processing'

                statuses[cid] = {
                    'success': True,
                    'status': status,
                    'trainingCount': training_amount,
                    'dataCount': data_amount,
                    'errorCount': error_count
                }

        except Exception as e:
            print(f"⚠️ 批量获取 Collection 状态失败: {e}")

        return statuses

    # ================== 获取带实时状态的文档列表 ==================

    def get_documents_with_realtime_status(self, username: str) -> Dict[str, Any]:
        try:
            sync_result = self.sync_documents_from_fastgpt(username)
            if sync_result.get('synced', 0) > 0:
                print(f"📥 从 FastGPT 同步了 {sync_result['synced']} 个新文档到 MongoDB")
        except Exception as e:
            print(f"⚠️ FastGPT 文档同步失败（不影响正常显示）: {e}")

        local_docs = list(self.db.kb_documents.find(
            {'username': username},
            {'_id': 0}
        ).sort('upload_time', -1))

        if not local_docs:
            return {
                'success': True,
                'documents': [],
                'total': 0,
                'has_processing': False
            }

        processing_collection_ids = [
            doc.get('collection_id') for doc in local_docs
            if doc.get('status') == 'processing' and doc.get('collection_id')
        ]

        batch_statuses = {}
        if processing_collection_ids:
            dataset_id = self.get_or_create_user_dataset(username)
            if dataset_id:
                print(f"🔄 使用 list API 批量查询 {len(processing_collection_ids)} 个处理中文档的真实状态")
                batch_statuses = self._batch_get_collection_statuses(dataset_id)
                print(f"   获取到 {len(batch_statuses)} 个 Collection 的状态")

        has_processing = False
        updated_docs = []

        for doc in local_docs:
            doc_id = doc.get('doc_id', '')
            collection_id = doc.get('collection_id', '')
            current_status = doc.get('status', 'pending')
            filename = doc.get('filename', '')

            if current_status == 'processing' and collection_id:
                try:
                    fastgpt_status = batch_statuses.get(collection_id)

                    if not fastgpt_status or not fastgpt_status.get('success'):
                        print(f"   ⚠️ {filename}: list API 中未找到，回退到 _get_collection_status_detail")
                        fastgpt_status = self._get_collection_status_detail(collection_id)

                    if fastgpt_status and fastgpt_status.get('success'):
                        real_status = fastgpt_status.get('status', 'processing')
                        training_count = fastgpt_status.get('trainingCount', 0)
                        data_count = fastgpt_status.get('dataCount', 0)

                        print(f"🔍 检查文档状态: {filename}")
                        print(f"   真实状态: {real_status}, 训练队列: {training_count}, 已索引: {data_count}")

                        if real_status == 'ready':
                            self.db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {
                                    'status': 'ready',
                                    'chunk_count': data_count,
                                    'processed_at': datetime.now()
                                }}
                            )
                            doc['status'] = 'ready'
                            doc['chunk_count'] = data_count
                            print(f"   ✅ 状态已更新为 ready (索引数: {data_count})")

                            if filename and collection_id:
                                print(f"   🔄 同步文件名到 FastGPT: {filename}")
                                name_sync_result = self.update_collection_name(collection_id, filename)
                                if name_sync_result.get('success'):
                                    print(f"   ✅ 文件名同步成功")
                                    self.db.kb_documents.update_one(
                                        {'doc_id': doc_id},
                                        {'$set': {
                                            'name_synced': True,
                                            'name_synced_at': datetime.now()
                                        }}
                                    )
                                else:
                                    print(f"   ⚠️ 文件名同步失败: {name_sync_result.get('error')}")

                            self._clear_filename_cache(username)

                        elif real_status == 'error':
                            error_msg = fastgpt_status.get('error', '处理失败')
                            self.db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {'status': 'failed', 'error_message': error_msg}}
                            )
                            doc['status'] = 'failed'
                            print(f"   ❌ 处理失败: {error_msg}")

                        else:
                            has_processing = True
                            doc['training_count'] = training_count
                            doc['data_count'] = data_count
                            print(f"   ⏳ 仍在处理中 (训练队列: {training_count}, 已索引: {data_count})")
                    else:
                        has_processing = True

                except Exception as e:
                    print(f"⚠️ 检查文档状态失败 {doc_id}: {e}")
                    has_processing = True

            elif current_status == 'processing':
                has_processing = True

            updated_docs.append(doc)

        return {
            'success': True,
            'documents': updated_docs,
            'total': len(updated_docs),
            'has_processing': has_processing
        }

    # ================== detail API 回退方案 ==================

    def _get_collection_status_detail(self, collection_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/core/dataset/collection/detail"

        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                params={'id': collection_id},
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()

                if result.get('code') == 200:
                    data = result.get('data', {})

                    index_amount = data.get('indexAmount', 0) or 0
                    training_amount = data.get('trainingAmount', 0) or 0
                    raw_text_length = data.get('rawTextLength', 0) or 0
                    error_count = data.get('errorCount', 0) or 0

                    print(f"      📊 [detail API] Collection {collection_id[:8]}...:")
                    print(f"         indexAmount={index_amount}, trainingAmount={training_amount}")
                    print(f"         rawTextLength={raw_text_length}, errorCount={error_count}")

                    if error_count > 0:
                        return {
                            'success': True,
                            'status': 'error',
                            'trainingCount': training_amount,
                            'dataCount': index_amount,
                            'error': f'处理出错，错误数: {error_count}'
                        }

                    if training_amount > 0:
                        return {
                            'success': True,
                            'status': 'processing',
                            'trainingCount': training_amount,
                            'dataCount': index_amount
                        }

                    if raw_text_length > 0 and index_amount > 0 and training_amount == 0:
                        estimated_chunks = max(1, raw_text_length // 500)
                        if index_amount < estimated_chunks * 0.5:
                            print(f"         🔧 保守判断: indexAmount({index_amount}) < 预期({estimated_chunks})的50%，"
                                  f"标记为 processing")
                            return {
                                'success': True,
                                'status': 'processing',
                                'trainingCount': 1,
                                'dataCount': index_amount
                            }

                    if index_amount > 0 and training_amount == 0:
                        return {
                            'success': True,
                            'status': 'ready',
                            'trainingCount': 0,
                            'dataCount': index_amount
                        }

                    if raw_text_length > 0 and index_amount == 0:
                        return {
                            'success': True,
                            'status': 'processing',
                            'trainingCount': training_amount or 1,
                            'dataCount': 0
                        }

                    return {
                        'success': True,
                        'status': 'processing',
                        'trainingCount': 0,
                        'dataCount': 0
                    }
                else:
                    return {
                        'success': False,
                        'status': 'unknown',
                        'error': result.get('message', '查询失败')
                    }
            else:
                return {
                    'success': False,
                    'status': 'unknown',
                    'error': f'HTTP {response.status_code}'
                }

        except Exception as e:
            print(f"⚠️ 获取 Collection 状态失败: {e}")
            return {
                'success': False,
                'status': 'unknown',
                'error': str(e)
            }

    def _get_collection_data_count(self, collection_id: str) -> int:
        url = f"{self.base_url}/core/dataset/data/list"

        try:
            payload = {
                "collectionId": collection_id,
                "pageNum": 1,
                "pageSize": 1
            }

            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()

                if result.get('code') == 200:
                    data = result.get('data', {})
                    total = (
                        data.get('total') or
                        data.get('count') or
                        len(data.get('data', []) if isinstance(data.get('data'), list) else [])
                    )
                    if isinstance(data, list):
                        total = len(data)
                    return int(total) if total else 0

        except Exception as e:
            print(f"      ⚠️ 查询数据数量失败: {e}")

        return 0

    # ================== 文件名映射 ==================

    def _get_filename_mapping(self, username: str) -> Dict[str, str]:
        cache_key = f"filenames_{username}"

        if cache_key in self._filename_cache:
            cached_data, cached_time = self._filename_cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < 300:
                return cached_data

        mapping = {}
        try:
            docs = self.db.kb_documents.find(
                {
                    'username': username,
                    'collection_id': {'$exists': True, '$ne': None}
                },
                {'collection_id': 1, 'filename': 1, 'doc_id': 1}
            )

            for doc in docs:
                collection_id = doc.get('collection_id', '')
                filename = doc.get('filename', '')
                doc_id = doc.get('doc_id', '')

                if collection_id and filename:
                    mapping[collection_id] = filename
                if doc_id and filename:
                    mapping[doc_id] = filename

            self._filename_cache[cache_key] = (mapping, datetime.now())

        except Exception as e:
            print(f"⚠️ 加载文件名映射失败: {e}")

        return mapping

    def _clear_filename_cache(self, username: str):
        cache_key = f"filenames_{username}"
        if cache_key in self._filename_cache:
            del self._filename_cache[cache_key]

    def _resolve_filename(self, username: str, collection_id: str, fastgpt_source: str = '') -> str:
        if not collection_id:
            return fastgpt_source or '未知文档'

        mapping = self._get_filename_mapping(username)

        if collection_id in mapping:
            return mapping[collection_id]

        if fastgpt_source:
            if fastgpt_source.startswith('doc_'):
                doc_id = fastgpt_source.rsplit('.', 1)[0]
                if doc_id in mapping:
                    return mapping[doc_id]

        if fastgpt_source:
            if fastgpt_source.startswith('doc_') and '_' in fastgpt_source:
                doc = self.db.kb_documents.find_one(
                    {'username': username, 'collection_id': collection_id},
                    {'filename': 1}
                )
                if doc and doc.get('filename'):
                    mapping[collection_id] = doc['filename']
                    return doc['filename']
            return fastgpt_source

        return '未知文档'

    # ================== 更新 Collection 名称 ==================

    def update_collection_name(self, collection_id: str, new_name: str) -> Dict[str, Any]:
        if not collection_id or not new_name:
            return {'success': False, 'error': '参数不完整'}

        url = f"{self.base_url}/core/dataset/collection/update"

        payload = {
            "id": collection_id,
            "name": new_name
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    return {'success': True, 'message': '名称更新成功'}

            response = requests.put(url, headers=self._get_headers(), json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    return {'success': True, 'message': '名称更新成功'}
                else:
                    return {'success': False, 'error': result.get('message', '更新失败')}

            return {'success': False, 'error': '所有方法均失败'}

        except Exception as e:
            print(f"❌ 更新 Collection 名称异常: {e}")
            return {'success': False, 'error': str(e)}

    def sync_all_collection_names(self, username: str) -> Dict[str, Any]:
        docs = list(self.db.kb_documents.find(
            {
                'username': username,
                'collection_id': {'$exists': True, '$ne': None},
                'status': 'ready'
            },
            {'collection_id': 1, 'filename': 1, 'doc_id': 1}
        ))

        if not docs:
            return {'success': True, 'message': '没有需要同步的文档', 'total': 0, 'updated': 0, 'failed': 0}

        updated = 0
        failed = 0
        errors = []

        for doc in docs:
            collection_id = doc.get('collection_id')
            filename = doc.get('filename')
            doc_id = doc.get('doc_id')

            if not collection_id or not filename:
                continue

            result = self.update_collection_name(collection_id, filename)

            if result.get('success'):
                updated += 1
                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {'$set': {'name_synced': True, 'name_synced_at': datetime.now()}}
                )
            else:
                failed += 1
                errors.append({'doc_id': doc_id, 'filename': filename, 'error': result.get('error')})

            time.sleep(0.2)

        return {
            'success': True,
            'message': '同步完成',
            'total': len(docs),
            'updated': updated,
            'failed': failed,
            'errors': errors if errors else None
        }

    def auto_sync_ready_documents(self, username: str) -> Dict[str, Any]:
        docs_to_sync = list(self.db.kb_documents.find(
            {
                'username': username,
                'status': 'ready',
                'collection_id': {'$exists': True, '$ne': None, '$ne': ''},
                '$or': [
                    {'name_synced': {'$exists': False}},
                    {'name_synced': False}
                ]
            },
            {'collection_id': 1, 'filename': 1, 'doc_id': 1}
        ))

        if not docs_to_sync:
            return {'synced': 0, 'errors': []}

        synced = 0
        errors = []

        for doc in docs_to_sync:
            collection_id = doc.get('collection_id')
            filename = doc.get('filename')
            doc_id = doc.get('doc_id')

            if not collection_id or not filename:
                continue

            try:
                result = self.update_collection_name(collection_id, filename)

                if result.get('success'):
                    synced += 1
                    self.db.kb_documents.update_one(
                        {'doc_id': doc_id},
                        {'$set': {'name_synced': True, 'name_synced_at': datetime.now()}}
                    )
                else:
                    errors.append({'doc_id': doc_id, 'filename': filename, 'error': result.get('error')})
            except Exception as e:
                errors.append({'doc_id': doc_id, 'filename': filename, 'error': str(e)})

            time.sleep(0.1)

        if synced > 0:
            self._clear_filename_cache(username)

        return {'synced': synced, 'errors': errors}

    def check_and_update_document_status(self, username: str) -> Dict[str, Any]:
        processing_docs = list(self.db.kb_documents.find(
            {
                'username': username,
                'status': 'processing',
                'collection_id': {'$exists': True, '$ne': None}
            },
            {'collection_id': 1, 'doc_id': 1, 'filename': 1}
        ))

        if not processing_docs:
            return {'updated': 0}

        dataset_id = self.get_or_create_user_dataset(username)
        batch_statuses = {}
        if dataset_id:
            print(f"🔄 [check_and_update] 使用 list API 批量查询 {len(processing_docs)} 个处理中文档的真实状态")
            batch_statuses = self._batch_get_collection_statuses(dataset_id)

        updated = 0

        for doc in processing_docs:
            collection_id = doc.get('collection_id')
            doc_id = doc.get('doc_id')
            filename = doc.get('filename', '')

            if not collection_id:
                continue

            try:
                status_info = batch_statuses.get(collection_id)

                if not status_info or not status_info.get('success'):
                    print(f"   ⚠️ {filename}: 回退到 detail API")
                    status_info = self._get_collection_status_detail(collection_id)

                if status_info and status_info.get('success'):
                    fastgpt_status = status_info.get('status', 'processing')

                    if fastgpt_status in ['ready', 'finish', 'active']:
                        self.db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {
                                'status': 'ready',
                                'chunk_count': status_info.get('dataCount', 0),
                                'processed_at': datetime.now()
                            }}
                        )
                        updated += 1
                        print(f"   ✅ {filename}: 更新为 ready (索引数: {status_info.get('dataCount', 0)})")

                    elif fastgpt_status in ['failed', 'error']:
                        self.db.kb_documents.update_one(
                            {'doc_id': doc_id},
                            {'$set': {
                                'status': 'failed',
                                'error_message': status_info.get('error', '处理失败')
                            }}
                        )
                        updated += 1
                        print(f"   ❌ {filename}: 更新为 failed")
                    else:
                        print(f"   ⏳ {filename}: 仍在处理 "
                              f"(训练队列: {status_info.get('trainingCount', 0)}, "
                              f"已索引: {status_info.get('dataCount', 0)})")

            except Exception as e:
                print(f"⚠️ 检查文档状态失败 {doc_id}: {e}")

            time.sleep(0.1)

        return {'updated': updated}

    # ================== 知识库（Dataset）管理 ==================

    def get_or_create_user_dataset(self, username: str) -> Optional[str]:
        if username in self._user_dataset_cache:
            return self._user_dataset_cache[username]

        user_kb = self.db.user_fastgpt_kb.find_one({'username': username})
        if user_kb and user_kb.get('dataset_id'):
            dataset_id = user_kb['dataset_id']
            if self._verify_dataset_exists(dataset_id):
                if self._is_dataset_in_parent_folder(dataset_id):
                    self._user_dataset_cache[username] = dataset_id
                    print(f"✅ 用户 {username} 的知识库 {dataset_id} 已在「个人知识库」文件夹内")
                    return dataset_id
                else:
                    print(f"⚠️ 用户 {username} 的知识库 {dataset_id} 不在「个人知识库」文件夹内，将重新创建")
                    self.db.user_fastgpt_kb.delete_one({'username': username})

        existing_dataset_id = self._find_existing_user_dataset(username)
        if existing_dataset_id:
            self.db.user_fastgpt_kb.update_one(
                {'username': username},
                {'$set': {'dataset_id': existing_dataset_id, 'updated_at': datetime.now()}},
                upsert=True
            )
            self._user_dataset_cache[username] = existing_dataset_id
            return existing_dataset_id

        dataset_id = self._create_dataset(username)
        if dataset_id:
            self.db.user_fastgpt_kb.update_one(
                {'username': username},
                {'$set': {'dataset_id': dataset_id, 'created_at': datetime.now(),
                          'updated_at': datetime.now()}},
                upsert=True
            )
            self._user_dataset_cache[username] = dataset_id

        return dataset_id

    def _get_or_create_parent_folder(self) -> Optional[str]:
        if self._parent_folder_id:
            return self._parent_folder_id

        folder_name = "个人知识库"

        url = f"{self.base_url}/core/dataset/list"
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"parentId": None},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get('code') == 200:
                all_datasets = result.get('data', [])
                for ds in all_datasets:
                    if ds.get('name') == folder_name:
                        folder_id = ds.get('_id')
                        print(f"✅ 找到「{folder_name}」父文件夹: {folder_id}")
                        self._parent_folder_id = folder_id
                        return folder_id
        except Exception as e:
            print(f"⚠️ 查找父文件夹失败: {e}")

        print(f"📁 创建「{folder_name}」父文件夹...")
        create_url = f"{self.base_url}/core/dataset/create"

        payload = {
            "parentId": None,
            "name": folder_name,
            "intro": "所有用户的个人知识库都在此目录下",
            "type": "folder",
            "avatar": "/icon/logo.svg"
        }

        try:
            response = requests.post(
                create_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get('code') == 200:
                folder_id = result.get('data')
                print(f"✅ 创建「{folder_name}」父文件夹成功: {folder_id}")
                self._parent_folder_id = folder_id
                return folder_id
            else:
                print(f"❌ 创建父文件夹失败: {result}")
                return None
        except Exception as e:
            print(f"❌ 创建父文件夹异常: {e}")
            return None

    def _verify_dataset_exists(self, dataset_id: str) -> bool:
        url = f"{self.base_url}/core/dataset/detail"
        try:
            response = requests.get(url, headers=self._get_headers(), params={'id': dataset_id}, timeout=10)
            return response.status_code == 200 and response.json().get('code') == 200
        except Exception as e:
            print(f"⚠️ 验证知识库失败: {e}")
            return False

    def _is_dataset_in_parent_folder(self, dataset_id: str) -> bool:
        parent_folder_id = self._get_or_create_parent_folder()
        if not parent_folder_id:
            return True

        url = f"{self.base_url}/core/dataset/detail"
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                params={'id': dataset_id},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    data = result.get('data', {})
                    current_parent = data.get('parentId') or data.get('parent') or None

                    if current_parent == '' or current_parent == 'null':
                        current_parent = None

                    is_in = (current_parent == parent_folder_id)
                    print(f"   📍 知识库 {dataset_id} 的 parentId={current_parent}, "
                          f"目标={parent_folder_id}, 匹配={is_in}")
                    return is_in
        except Exception as e:
            print(f"⚠️ 检查知识库位置失败: {e}")

        return True

    def _find_existing_user_dataset(self, username: str) -> Optional[str]:
        parent_folder_id = self._get_or_create_parent_folder()
        if not parent_folder_id:
            return None

        url = f"{self.base_url}/core/dataset/list"
        target_name = f'个人知识库_{username}'

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"parentId": parent_folder_id},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get('code') == 200:
                all_datasets = result.get('data', [])
                for ds in all_datasets:
                    if ds.get('name') == target_name and ds.get('type') == 'dataset':
                        dataset_id = ds.get('_id')
                        print(f"✅ 在「个人知识库」文件夹内找到用户知识库: {target_name} -> {dataset_id}")
                        return dataset_id
        except Exception as e:
            print(f"⚠️ 在父文件夹内查找用户知识库失败: {e}")

        return None

    def _create_dataset(self, username: str) -> Optional[str]:
        parent_folder_id = self._get_or_create_parent_folder()

        url = f"{self.base_url}/core/dataset/create"

        payload = {
            "parentId": parent_folder_id,
            "name": f"个人知识库_{username}",
            "intro": f"用户 {username} 的个人知识库",
            "type": "dataset",
            "avatar": "/icon/logo.svg",
            "vectorModel": self.default_vector_model,
            "agentModel": self.default_agent_model
        }

        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if result.get('code') == 200:
                dataset_id = result.get('data')
                print(f"✅ 为用户 {username} 创建知识库成功: {dataset_id} (父文件夹: {parent_folder_id})")
                return dataset_id
            else:
                print(f"❌ 创建知识库失败: {result}")
                return None
        except Exception as e:
            print(f"❌ 创建知识库异常: {e}")
            traceback.print_exc()
            return None

    # ================== 共享知识库管理 ==================

    def _get_or_create_shared_dataset(self) -> Optional[str]:
        if self._shared_dataset_id:
            return self._shared_dataset_id

        shared_record = self.db.system_config.find_one({'key': 'shared_dataset_id'})
        if shared_record and shared_record.get('value'):
            dataset_id = shared_record['value']
            if self._verify_dataset_exists(dataset_id):
                self._shared_dataset_id = dataset_id
                print(f"✅ 共享知识库已存在: {dataset_id}")
                return dataset_id

        shared_name = "共享知识库"
        url = f"{self.base_url}/core/dataset/list"
        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json={"parentId": None},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            if result.get('code') == 200:
                for ds in result.get('data', []):
                    if ds.get('name') == shared_name and ds.get('type') == 'dataset':
                        dataset_id = ds.get('_id')
                        print(f"✅ 找到已有共享知识库: {dataset_id}")
                        self.db.system_config.update_one(
                            {'key': 'shared_dataset_id'},
                            {'$set': {'value': dataset_id, 'updated_at': datetime.now()}},
                            upsert=True
                        )
                        self._shared_dataset_id = dataset_id
                        return dataset_id
        except Exception as e:
            print(f"⚠️ 搜索共享知识库失败: {e}")

        print(f"📁 创建共享知识库...")
        create_url = f"{self.base_url}/core/dataset/create"
        payload = {
            "parentId": None,
            "name": shared_name,
            "intro": "所有用户公开共享的文档汇总",
            "type": "dataset",
            "avatar": "/icon/logo.svg",
            "vectorModel": self.default_vector_model,
            "agentModel": self.default_agent_model
        }

        try:
            response = requests.post(
                create_url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            if result.get('code') == 200:
                dataset_id = result.get('data')
                print(f"✅ 共享知识库创建成功: {dataset_id}")
                self.db.system_config.update_one(
                    {'key': 'shared_dataset_id'},
                    {'$set': {'value': dataset_id, 'created_at': datetime.now(),
                              'updated_at': datetime.now()}},
                    upsert=True
                )
                self._shared_dataset_id = dataset_id
                return dataset_id
            else:
                print(f"❌ 创建共享知识库失败: {result}")
                return None
        except Exception as e:
            print(f"❌ 创建共享知识库异常: {e}")
            return None

    def share_document(self, username: str, doc_id: str) -> Dict[str, Any]:
        print(f"\n🌐 共享文档: doc_id={doc_id}, user={username}")

        doc = self.db.kb_documents.find_one({'username': username, 'doc_id': doc_id})
        if not doc:
            return {'success': False, 'error': '文档不存在'}

        if doc.get('status') != 'ready':
            return {'success': False, 'error': '文档尚未处理完成，无法共享'}

        if doc.get('shared'):
            return {'success': True, 'message': '文档已处于共享状态'}

        filename = doc.get('filename', '')
        if not filename:
            return {'success': False, 'error': '文档文件名为空'}

        shared_dataset_id = self._get_or_create_shared_dataset()
        if not shared_dataset_id:
            return {'success': False, 'error': '无法获取共享知识库'}

        anonymous_filename = self._generate_shared_anonymous_name(doc_id, filename)
        anonymous_doc_id = self._generate_shared_doc_id(doc_id)

        print(f"   🔒 匿名文件名: {anonymous_filename}")
        print(f"   🔒 匿名 doc_id: {anonymous_doc_id}")

        shared_collection_id = None
        share_method = None

        collection_id = doc.get('collection_id')
        if collection_id:
            print(f"   📤 从 FastGPT 数据块复制到共享知识库（匿名）")
            result = self._copy_collection_data_to_shared(
                collection_id, shared_dataset_id,
                anonymous_filename,
                anonymous_doc_id,
                username
            )
            if result.get('success'):
                shared_collection_id = result.get('collection_id')
                share_method = 'data_copy'
                print(f"   ✅ 数据复制成功: {shared_collection_id}")
            else:
                print(f"   ⚠️ 数据复制失败: {result.get('error')}")

        if not shared_collection_id:
            print(f"   ⚠️ 复制失败，仅标记共享状态")
            self.db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {
                    'shared': True,
                    'shared_at': datetime.now(),
                    'shared_collection_id': None,
                    'shared_no_file': True,
                    'shared_anonymous_name': anonymous_filename
                }}
            )
            return {
                'success': True,
                'message': '文档已标记为共享，但内容无法同步到共享知识库',
                'warning': 'no_content_available'
            }

        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {'$set': {
                'shared': True,
                'shared_at': datetime.now(),
                'shared_collection_id': shared_collection_id,
                'shared_dataset_id': shared_dataset_id,
                'share_method': share_method,
                'shared_anonymous_name': anonymous_filename
            }}
        )

        if shared_collection_id:
            time.sleep(0.5)
            self.update_collection_name(shared_collection_id, anonymous_filename)

        print(f"   ✅ 文档共享成功（匿名）: method={share_method}, "
              f"shared_collection_id={shared_collection_id}")

        return {
            'success': True,
            'message': '文档已公开到共享知识库',
            'shared_collection_id': shared_collection_id,
            'share_method': share_method
        }

    # ================== 从 FastGPT 内部复制数据块到共享知识库（多级回退） ==================

    def _copy_collection_data_to_shared(self, source_collection_id: str,
                                         shared_dataset_id: str,
                                         filename: str,
                                         doc_id: str,
                                         username: str) -> Dict[str, Any]:
        print(f"      源 collection_id: {source_collection_id}")

        all_data = self._fetch_all_collection_data(source_collection_id)

        if not all_data:
            print(f"      方案A 无数据，尝试方案B: searchTest")
            all_data = self._extract_data_via_search(source_collection_id, username)

        if not all_data:
            print(f"      方案B 无数据，尝试方案C: rawText")
            all_data = self._extract_data_from_detail(source_collection_id)

        if not all_data:
            return {'success': False, 'error': '源 Collection 没有数据块可复制（A/B/C 均失败）'}

        print(f"      📊 获取到 {len(all_data)} 个数据块，开始复制...")

        shared_collection_id = self._create_text_collection(
            shared_dataset_id,
            filename,
            doc_id
        )

        if not shared_collection_id:
            print(f"      ⚠️ create 接口失败，尝试备选方式")
            shared_collection_id = self._create_virtual_collection_v2(
                shared_dataset_id,
                filename,
                doc_id
            )

        if not shared_collection_id:
            return {'success': False, 'error': '在共享知识库中创建 Collection 失败'}

        success_count = self._batch_insert_data(shared_collection_id, all_data)

        print(f"      ✅ 复制完成: {success_count}/{len(all_data)} 个数据块")

        if success_count == 0:
            try:
                self._delete_fastgpt_collection(shared_collection_id)
            except Exception:
                pass
            return {'success': False, 'error': '数据块写入失败'}

        return {
            'success': True,
            'collection_id': shared_collection_id,
            'copied_count': success_count,
            'total_count': len(all_data)
        }

    def _fetch_all_collection_data(self, collection_id: str) -> List[Dict]:
        all_data = []
        page_num = 1
        page_size = 30

        while True:
            url = f"{self.base_url}/core/dataset/data/list"
            payload = {
                "collectionId": collection_id,
                "pageNum": page_num,
                "pageSize": page_size,
                "searchText": ""
            }

            try:
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )

                print(f"      [data/list] HTTP {response.status_code}")

                if response.status_code != 200:
                    print(f"      ⚠️ HTTP {response.status_code}, 响应: {response.text[:300]}")
                    if page_num == 1:
                        fallback = self._fetch_collection_data_get(collection_id)
                        if fallback:
                            return fallback
                    break

                result = response.json()
                print(f"      [data/list] code={result.get('code')}, "
                      f"data type={type(result.get('data')).__name__}")

                if result.get('code') != 200:
                    print(f"      ⚠️ API 错误: {result.get('message')}")
                    if page_num == 1:
                        fallback = self._fetch_collection_data_get(collection_id)
                        if fallback:
                            return fallback
                    break

                data = result.get('data', {})

                items = []
                total = 0

                if isinstance(data, dict):
                    items = data.get('data', [])
                    total = data.get('total', 0)

                    if not items:
                        items = data.get('list', [])

                    if not items and data.get('q'):
                        items = [data]
                        total = 1

                elif isinstance(data, list):
                    items = data
                    total = len(data)

                print(f"      [data/list] items={len(items)}, total={total}")

                if items and page_num == 1:
                    first = items[0]
                    keys = list(first.keys()) if isinstance(first, dict) else []
                    print(f"      [data/list] 第一条 keys: {keys}")
                    if isinstance(first, dict):
                        q_val = first.get('q', '')
                        a_val = first.get('a', '')
                        print(f"      [data/list] q={q_val[:50] if q_val else '(空)'}, "
                              f"a={a_val[:50] if a_val else '(空)'}")

                if not items:
                    if page_num == 1:
                        print(f"      ⚠️ 第1页就为空，尝试 GET 回退")
                        fallback = self._fetch_collection_data_get(collection_id)
                        if fallback:
                            return fallback
                    break

                all_data.extend(items)
                print(f"      第{page_num}页: {len(items)} 块 (累计 {len(all_data)}/{total})")

                if len(all_data) >= total or len(items) < page_size:
                    break

                page_num += 1
                if page_num > 200:
                    break

                time.sleep(0.1)

            except Exception as e:
                print(f"      ⚠️ 获取数据块异常: {e}")
                traceback.print_exc()
                if page_num == 1:
                    fallback = self._fetch_collection_data_get(collection_id)
                    if fallback:
                        return fallback
                break

        return all_data

    def _fetch_collection_data_get(self, collection_id: str) -> List[Dict]:
        url = f"{self.base_url}/core/dataset/data/list"
        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                params={
                    'collectionId': collection_id,
                    'pageNum': 1,
                    'pageSize': 100
                },
                timeout=30
            )
            print(f"      [data/list GET] HTTP {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    data = result.get('data', {})
                    if isinstance(data, dict):
                        items = data.get('data', []) or data.get('list', [])
                        print(f"      [data/list GET] 获取到 {len(items)} 条")
                        return items
                    elif isinstance(data, list):
                        print(f"      [data/list GET] 获取到 {len(data)} 条")
                        return data
                else:
                    print(f"      [data/list GET] API 错误: {result.get('message')}")
            else:
                print(f"      [data/list GET] 响应: {response.text[:200]}")
        except Exception as e:
            print(f"      [data/list GET] 异常: {e}")

        return []

    def _extract_data_via_search(self, collection_id: str, username: str) -> List[Dict]:
        try:
            doc_record = self.db.kb_documents.find_one(
                {'collection_id': collection_id},
                {'dataset_id': 1, 'filename': 1}
            )
            if not doc_record or not doc_record.get('dataset_id'):
                print(f"      [searchTest] 找不到 dataset_id")
                return []

            dataset_id = doc_record['dataset_id']
            filename = doc_record.get('filename', '内容')

            search_terms = [filename, filename.rsplit('.', 1)[0] if '.' in filename else filename]

            all_results = []
            seen_ids = set()

            for term in search_terms:
                url = f"{self.base_url}/core/dataset/searchTest"
                payload = {
                    "datasetId": dataset_id,
                    "text": term,
                    "limit": 50,
                    "similarity": 0.0,
                    "searchMode": "embedding",
                    "usingReRank": False
                }

                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 200:
                        data = result.get('data', {})
                        items = []
                        if isinstance(data, dict):
                            items = data.get('list', [])
                        elif isinstance(data, list):
                            items = data

                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            item_cid = item.get('collectionId', '')
                            item_id = item.get('id', '') or item.get('_id', '')

                            if item_cid == collection_id and item_id not in seen_ids:
                                seen_ids.add(item_id)
                                all_results.append({
                                    'q': item.get('q', '') or item.get('content', ''),
                                    'a': item.get('a', '')
                                })

                        print(f"      [searchTest] 搜索 '{term}': 命中 {len(items)} 条, "
                              f"匹配 collection 的 {len(all_results)} 条")

            return all_results

        except Exception as e:
            print(f"      [searchTest] 异常: {e}")
            return []

    def _extract_data_from_detail(self, collection_id: str) -> List[Dict]:
        try:
            url = f"{self.base_url}/core/dataset/collection/detail"
            response = requests.get(
                url,
                headers=self._get_headers(),
                params={'id': collection_id},
                timeout=15
            )

            if response.status_code != 200:
                return []

            result = response.json()
            if result.get('code') != 200:
                return []

            data = result.get('data', {})
            raw_text = data.get('rawText', '') or data.get('text', '') or ''

            if not raw_text:
                print(f"      [detail] rawText 为空")
                return []

            print(f"      [detail] rawText 长度: {len(raw_text)}")

            chunks = []
            chunk_size = 500
            paragraphs = raw_text.split('\n\n')

            current_chunk = ''
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                if len(current_chunk) + len(para) + 2 > chunk_size and current_chunk:
                    chunks.append({'q': current_chunk.strip(), 'a': ''})
                    current_chunk = para
                else:
                    current_chunk = (current_chunk + '\n\n' + para).strip()

            if current_chunk.strip():
                chunks.append({'q': current_chunk.strip(), 'a': ''})

            if not chunks and raw_text.strip():
                text = raw_text.strip()
                for i in range(0, len(text), chunk_size):
                    chunk = text[i:i + chunk_size].strip()
                    if chunk:
                        chunks.append({'q': chunk, 'a': ''})

            print(f"      [detail] 切分为 {len(chunks)} 个数据块")
            return chunks

        except Exception as e:
            print(f"      [detail] 异常: {e}")
            return []

    def _create_text_collection(self, dataset_id: str,
                                 name: str,
                                 doc_id: str) -> Optional[str]:
        url = f"{self.base_url}/core/dataset/collection/create"

        payload = {
            "datasetId": dataset_id,
            "parentId": None,
            "name": name,
            "type": "virtual",
            "trainingType": "chunk",
            "chunkSize": 500,
            "metadata": {
                "docId": doc_id,
                "source": "shared_copy"
            }
        }

        try:
            response = requests.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=30
            )

            print(f"      [create collection] HTTP {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    data = result.get('data', {})
                    if isinstance(data, str):
                        return data
                    elif isinstance(data, dict):
                        return data.get('_id') or data.get('id') or data.get('collectionId')

            print(f"      ⚠️ 创建 Collection 失败: {response.status_code} {response.text[:200]}")
            return None

        except Exception as e:
            print(f"      ⚠️ 创建 Collection 异常: {e}")
            return None

    def _create_virtual_collection_v2(self, dataset_id: str,
                                       name: str,
                                       doc_id: str) -> Optional[str]:
        url = f"{self.base_url}/core/dataset/collection/create"

        for coll_type in ['virtual', 'file', 'link']:
            payload = {
                "datasetId": dataset_id,
                "parentId": None,
                "name": name,
                "type": coll_type,
                "metadata": {"docId": doc_id, "source": "shared_copy"}
            }

            if coll_type == 'link':
                payload['rawLink'] = f"shared://{doc_id}"

            try:
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=30
                )

                print(f"      [create v2] type={coll_type}, HTTP {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 200:
                        data = result.get('data', {})
                        if isinstance(data, str):
                            return data
                        elif isinstance(data, dict):
                            cid = data.get('_id') or data.get('id') or data.get('collectionId')
                            if cid:
                                return cid
                    else:
                        print(f"      [create v2] type={coll_type} 失败: {result.get('message')}")

            except Exception as e:
                print(f"      [create v2] type={coll_type} 异常: {e}")

        return None

    def _batch_insert_data(self, collection_id: str,
                            data_list: List[Dict]) -> int:
        push_url = f"{self.base_url}/core/dataset/data/pushData"
        insert_url = f"{self.base_url}/core/dataset/data/insertData"

        batch_size = 10
        success_count = 0
        use_push = True

        for i in range(0, len(data_list), batch_size):
            batch = data_list[i:i + batch_size]

            insert_items = []
            for item in batch:
                q = item.get('q', '') or item.get('content', '') or item.get('text', '') or ''
                a = item.get('a', '') or ''
                if q.strip():
                    insert_items.append({
                        'q': q.strip(),
                        'a': a.strip(),
                        'indexes': []
                    })

            if not insert_items:
                continue

            batch_num = i // batch_size + 1

            payload = {
                "collectionId": collection_id,
                "data": insert_items
            }

            url = push_url if use_push else insert_url

            try:
                response = requests.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=60
                )

                print(f"      批次 {batch_num}: HTTP {response.status_code} ({url.split('/')[-1]})")

                if response.status_code == 200:
                    result = response.json()
                    if result.get('code') == 200:
                        inserted = len(insert_items)
                        success_count += inserted
                        print(f"      批次 {batch_num}: ✅ 插入 {inserted} 块")
                    else:
                        msg = result.get('message', '')
                        print(f"      批次 {batch_num} API 错误: {msg}")

                        if use_push:
                            print(f"      尝试切换到 insertData...")
                            use_push = False
                            response2 = requests.post(
                                insert_url,
                                headers=self._get_headers(),
                                json=payload,
                                timeout=60
                            )
                            if response2.status_code == 200:
                                r2 = response2.json()
                                if r2.get('code') == 200:
                                    inserted = len(insert_items)
                                    success_count += inserted
                                    print(f"      批次 {batch_num}: ✅ insertData 成功 {inserted} 块")

                elif response.status_code == 404 and use_push:
                    print(f"      pushData 404，切换到 insertData")
                    use_push = False
                    response2 = requests.post(
                        insert_url,
                        headers=self._get_headers(),
                        json=payload,
                        timeout=60
                    )
                    if response2.status_code == 200:
                        r2 = response2.json()
                        if r2.get('code') == 200:
                            inserted = len(insert_items)
                            success_count += inserted
                            print(f"      批次 {batch_num}: ✅ insertData 成功 {inserted} 块")
                else:
                    print(f"      批次 {batch_num} HTTP {response.status_code}: {response.text[:200]}")

            except Exception as e:
                print(f"      批次 {batch_num} 异常: {e}")

            time.sleep(0.3)

        return success_count

    def _delete_fastgpt_collection(self, collection_id: str) -> bool:
        url = f"{self.base_url}/core/dataset/collection/delete"
        try:
            response = requests.delete(
                url,
                headers=self._get_headers(),
                params={'id': collection_id},
                timeout=30
            )
            return response.status_code == 200
        except Exception:
            return False

    def unshare_document(self, username: str, doc_id: str) -> Dict[str, Any]:
        print(f"\n🔒 取消共享: doc_id={doc_id}, user={username}")

        doc = self.db.kb_documents.find_one({'username': username, 'doc_id': doc_id})
        if not doc:
            return {'success': False, 'error': '文档不存在'}

        if not doc.get('shared'):
            return {'success': True, 'message': '文档已处于非共享状态'}

        shared_collection_id = doc.get('shared_collection_id')
        if shared_collection_id:
            try:
                url = f"{self.base_url}/core/dataset/collection/delete"
                response = requests.delete(
                    url,
                    headers=self._get_headers(),
                    params={'id': shared_collection_id},
                    timeout=30
                )
                if response.status_code == 200:
                    print(f"   ✅ 已从共享知识库删除 Collection: {shared_collection_id}")
                else:
                    print(f"   ⚠️ 删除共享 Collection 返回: {response.status_code}")
            except Exception as e:
                print(f"   ⚠️ 删除共享 Collection 失败: {e}")

        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {
                '$set': {
                    'shared': False,
                    'unshared_at': datetime.now()
                },
                '$unset': {
                    'shared_collection_id': '',
                    'shared_dataset_id': '',
                    'shared_at': '',
                    'shared_no_file': '',
                    'share_method': '',
                    'shared_anonymous_name': ''
                }
            }
        )

        print(f"   ✅ 文档取消共享成功")
        return {'success': True, 'message': '已取消公开'}

    # ================== 文件夹管理 — 纯 MongoDB 逻辑分组 ==================

    def create_folder(self, username: str, folder_name: str, parent_folder_id: str = None) -> Dict[str, Any]:
        print(f"\n📁 创建文件夹: {folder_name}")

        root_dataset_id = self.get_or_create_user_dataset(username)
        if not root_dataset_id:
            return {'success': False, 'error': '无法获取用户知识库'}

        if parent_folder_id:
            parent_folder = self.db.kb_folders.find_one({
                'username': username,
                'folder_id': parent_folder_id
            })
            if not parent_folder:
                return {'success': False, 'error': '父文件夹不存在'}

        existing = self.db.kb_folders.find_one({
            'username': username,
            'name': folder_name,
            'parent_id': parent_folder_id
        })
        if existing:
            return {'success': False, 'error': '同名文件夹已存在'}

        folder_id = self._generate_folder_id(username, folder_name)

        folder_doc = {
            'folder_id': folder_id,
            'username': username,
            'name': folder_name,
            'parent_id': parent_folder_id,
            'fastgpt_dataset_id': root_dataset_id,
            'created_at': datetime.now(),
            'updated_at': datetime.now(),
            'document_count': 0
        }

        self.db.kb_folders.insert_one(folder_doc)
        self._clear_folder_cache(username)

        print(f"✅ 文件夹「{folder_name}」创建成功 (仅 MongoDB 逻辑分组)")

        return {
            'success': True,
            'folder_id': folder_id,
            'name': folder_name,
            'fastgpt_dataset_id': root_dataset_id,
            'message': '文件夹创建成功'
        }

    def _generate_folder_id(self, username: str, folder_name: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        hash_str = hashlib.md5(f"{username}_{folder_name}_{timestamp}".encode()).hexdigest()[:8]
        return f"folder_{username}_{hash_str}"

    def get_folders(self, username: str, parent_id: str = None) -> List[Dict]:
        query = {'username': username, 'parent_id': parent_id}
        folders = list(self.db.kb_folders.find(query, {'_id': 0}).sort('name', 1))

        for folder in folders:
            folder_id = folder.get('folder_id')
            doc_count = self.db.kb_documents.count_documents({
                'username': username,
                'folder_id': folder_id
            })
            subfolder_count = self.db.kb_folders.count_documents({
                'username': username,
                'parent_id': folder_id
            })
            folder['document_count'] = doc_count
            folder['subfolder_count'] = subfolder_count

            if folder.get('created_at'):
                folder['created_at'] = folder['created_at'].isoformat()
            if folder.get('updated_at'):
                folder['updated_at'] = folder['updated_at'].isoformat()

        return folders

    def get_folder_tree(self, username: str) -> List[Dict]:
        all_folders = list(self.db.kb_folders.find(
            {'username': username},
            {'_id': 0}
        ).sort('name', 1))

        def build_tree(parent_id):
            children = []
            for folder in all_folders:
                if folder.get('parent_id') == parent_id:
                    folder_copy = folder.copy()
                    folder_copy['children'] = build_tree(folder['folder_id'])
                    folder_copy['document_count'] = self.db.kb_documents.count_documents({
                        'username': username,
                        'folder_id': folder['folder_id']
                    })
                    if folder_copy.get('created_at'):
                        folder_copy['created_at'] = folder_copy['created_at'].isoformat()
                    if folder_copy.get('updated_at'):
                        folder_copy['updated_at'] = folder_copy['updated_at'].isoformat()
                    children.append(folder_copy)
            return children

        return build_tree(None)

    def delete_folder(self, username: str, folder_id: str, recursive: bool = False) -> Dict[str, Any]:
        folder = self.db.kb_folders.find_one({
            'username': username,
            'folder_id': folder_id
        })

        if not folder:
            return {'success': False, 'error': '文件夹不存在'}

        doc_count = self.db.kb_documents.count_documents({
            'username': username,
            'folder_id': folder_id
        })
        subfolder_count = self.db.kb_folders.count_documents({
            'username': username,
            'parent_id': folder_id
        })

        if (doc_count > 0 or subfolder_count > 0) and not recursive:
            return {
                'success': False,
                'error': f'文件夹非空（包含 {doc_count} 个文档和 {subfolder_count} 个子文件夹）',
                'document_count': doc_count,
                'subfolder_count': subfolder_count
            }

        if recursive:
            subfolders = list(self.db.kb_folders.find({
                'username': username,
                'parent_id': folder_id
            }))
            for subfolder in subfolders:
                self.delete_folder(username, subfolder['folder_id'], recursive=True)

            docs = list(self.db.kb_documents.find({
                'username': username,
                'folder_id': folder_id
            }))
            for doc in docs:
                self.delete_document(username, doc['doc_id'])

        self.db.kb_folders.delete_one({
            'username': username,
            'folder_id': folder_id
        })

        self._clear_folder_cache(username)

        return {'success': True, 'message': '文件夹删除成功'}

    def rename_folder(self, username: str, folder_id: str, new_name: str) -> Dict[str, Any]:
        folder = self.db.kb_folders.find_one({
            'username': username,
            'folder_id': folder_id
        })

        if not folder:
            return {'success': False, 'error': '文件夹不存在'}

        existing = self.db.kb_folders.find_one({
            'username': username,
            'name': new_name,
            'parent_id': folder.get('parent_id'),
            'folder_id': {'$ne': folder_id}
        })
        if existing:
            return {'success': False, 'error': '同名文件夹已存在'}

        self.db.kb_folders.update_one(
            {'folder_id': folder_id},
            {'$set': {'name': new_name, 'updated_at': datetime.now()}}
        )

        self._clear_folder_cache(username)

        return {'success': True, 'message': '重命名成功'}

    def move_document_to_folder(self, username: str, doc_id: str,
                                 target_folder_id: str = None) -> Dict[str, Any]:
        doc = self.db.kb_documents.find_one({
            'username': username,
            'doc_id': doc_id
        })

        if not doc:
            return {'success': False, 'error': '文档不存在'}

        if target_folder_id:
            target_folder = self.db.kb_folders.find_one({
                'username': username,
                'folder_id': target_folder_id
            })
            if not target_folder:
                return {'success': False, 'error': '目标文件夹不存在'}

        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {'$set': {
                'folder_id': target_folder_id,
                'updated_at': datetime.now()
            }}
        )

        return {
            'success': True,
            'message': f'文档已移动到{"根目录" if not target_folder_id else "指定文件夹"}'
        }

    def get_documents_in_folder(self, username: str, folder_id: str = None) -> List[Dict]:
        if not folder_id:
            try:
                sync_result = self.sync_documents_from_fastgpt(username)
                if sync_result.get('synced', 0) > 0:
                    print(f"📥 同步了 {sync_result['synced']} 个文档到根目录")
            except Exception as e:
                print(f"⚠️ 同步失败（不影响显示）: {e}")

        query = {'username': username}

        if folder_id:
            query['folder_id'] = folder_id
        else:
            query['$or'] = [
                {'folder_id': {'$exists': False}},
                {'folder_id': None},
                {'folder_id': ''}
            ]

        docs = list(self.db.kb_documents.find(query, {'_id': 0}).sort('upload_time', -1))

        processing_docs = [d for d in docs if d.get('status') == 'processing' and d.get('collection_id')]
        batch_statuses = {}
        if processing_docs:
            dataset_id = self.get_or_create_user_dataset(username)
            if dataset_id:
                print(f"🔄 [get_documents_in_folder] 使用 list API 查询 {len(processing_docs)} 个处理中文档")
                batch_statuses = self._batch_get_collection_statuses(dataset_id)

        updated_docs = []
        for doc in docs:
            doc_id = doc.get('doc_id', '')
            collection_id = doc.get('collection_id', '')
            current_status = doc.get('status', 'pending')
            filename = doc.get('filename', '')

            if current_status == 'processing' and collection_id:
                try:
                    fastgpt_status = batch_statuses.get(collection_id)

                    if not fastgpt_status or not fastgpt_status.get('success'):
                        print(f"   ⚠️ {filename}: 回退到 _get_collection_status_detail")
                        fastgpt_status = self._get_collection_status_detail(collection_id)

                    if fastgpt_status and fastgpt_status.get('success'):
                        real_status = fastgpt_status.get('status', 'processing')
                        data_count = fastgpt_status.get('dataCount', 0)
                        training_count = fastgpt_status.get('trainingCount', 0)

                        if real_status == 'ready':
                            self.db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {
                                    'status': 'ready',
                                    'chunk_count': data_count,
                                    'processed_at': datetime.now()
                                }}
                            )
                            doc['status'] = 'ready'
                            doc['chunk_count'] = data_count
                            print(f"   ✅ {filename}: 更新为 ready (索引数: {data_count})")

                            if filename and collection_id:
                                time.sleep(1)
                                name_sync_result = self.update_collection_name(collection_id, filename)
                                if name_sync_result.get('success'):
                                    self.db.kb_documents.update_one(
                                        {'doc_id': doc_id},
                                        {'$set': {'name_synced': True, 'name_synced_at': datetime.now()}}
                                    )

                            self._clear_filename_cache(username)

                        elif real_status == 'error':
                            error_msg = fastgpt_status.get('error', '处理失败')
                            self.db.kb_documents.update_one(
                                {'doc_id': doc_id},
                                {'$set': {'status': 'failed', 'error_message': error_msg}}
                            )
                            doc['status'] = 'failed'
                            print(f"   ❌ {filename}: 处理失败")

                        else:
                            doc['training_count'] = training_count
                            doc['data_count'] = data_count
                            print(f"   ⏳ {filename}: 仍在处理 "
                                  f"(训练队列: {training_count}, 已索引: {data_count})")

                except Exception as e:
                    print(f"⚠️ 检查文档状态失败 {doc_id}: {e}")

            updated_docs.append(doc)

        return updated_docs

    def _clear_folder_cache(self, username: str):
        cache_key = f"folders_{username}"
        if cache_key in self._folder_cache:
            del self._folder_cache[cache_key]

    # ================== 文件上传（★ 已添加耗时统计） ==================

    def upload_file(self, username: str, file, filename: str, folder_id: str = None) -> Dict[str, Any]:
        # ★ 总计时
        total_start = time.time()

        print(f"\n{'='*50}")
        print(f"📤 开始上传文件: {filename}")
        print(f"👤 用户: {username}")
        print(f"📁 逻辑文件夹: {folder_id or '根目录'}")

        if folder_id:
            folder = self.db.kb_folders.find_one({
                'username': username,
                'folder_id': folder_id
            })
            if not folder:
                return {'success': False, 'error': '目标文件夹不存在'}

        dataset_id = self.get_or_create_user_dataset(username)

        if not dataset_id:
            return {'success': False, 'error': '无法获取或创建知识库'}

        doc_id = self._generate_doc_id(username, filename)

        try:
            file.seek(0, 2)
            file_size = file.tell()
            file.seek(0)
            file_content = file.read()
            file.seek(0)
        except Exception as e:
            return {'success': False, 'error': f'读取文件失败: {e}'}

        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {
                '$set': {
                    'doc_id': doc_id,
                    'username': username,
                    'filename': filename,
                    'file_type': filename.rsplit('.', 1)[-1].lower() if '.' in filename else '',
                    'dataset_id': dataset_id,
                    'folder_id': folder_id,
                    'status': 'uploading',
                    'upload_time': datetime.now(),
                    'file_size': file_size,
                    'name_synced': False,
                    'shared': False
                }
            },
            upsert=True
        )

        self._clear_filename_cache(username)

        try:
            # ★ FastGPT 上传计时
            t_upload_start = time.time()
            result = self._upload_file_to_fastgpt(dataset_id, file_content, filename, doc_id)
            t_upload_elapsed = time.time() - t_upload_start                # ★

            if result.get('success'):
                collection_id = result.get('collection_id')

                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {
                        '$set': {
                            'status': 'processing',
                            'collection_id': collection_id,
                            'chunk_count': 0,
                            'uploaded_at': datetime.now()
                        }
                    }
                )

                self._clear_filename_cache(username)

                if username in self._last_sync_time:
                    del self._last_sync_time[username]

                # ★ 打印耗时报告
                total_elapsed = time.time() - total_start
                file_size_mb = file_size / 1024 / 1024
                print(f"\n{'─'*60}")
                print(f"⏱️  文件上传耗时报告")
                print(f"   📄 文件名:      {filename}")
                print(f"   👤 用户:        {username}")
                print(f"   📦 大小:        {file_size_mb:.2f} MB")
                print(f"   🔧 类型:        文档直传 (FastGPT 处理)")
                print(f"   ⏱️  FastGPT上传: {t_upload_elapsed:.2f}s")
                print(f"   ⏱️  总处理耗时:  {total_elapsed:.2f}s")
                if file_size_mb > 0 and t_upload_elapsed > 0:
                    print(f"   📊 上传速度:    {file_size_mb / t_upload_elapsed:.2f} MB/s")
                print(f"   ✅ 上传成功，等待 FastGPT 索引")
                print(f"{'─'*60}")

                return {
                    'success': True,
                    'doc_id': doc_id,
                    'collection_id': collection_id,
                    'folder_id': folder_id,
                    'status': 'processing',
                    'message': '文件上传成功，正在处理中...',
                    'upload_time_seconds': round(total_elapsed, 2),         # ★
                }
            else:
                error_msg = result.get('error', '上传失败')
                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {'$set': {'status': 'failed', 'error_message': error_msg}}
                )

                # ★ 失败也打印耗时
                total_elapsed = time.time() - total_start
                print(f"\n{'─'*60}")
                print(f"⏱️  文件上传耗时报告 (失败)")
                print(f"   📄 文件名: {filename} | ⏱️ {total_elapsed:.2f}s | ❌ {error_msg}")
                print(f"{'─'*60}")

                return {'success': False, 'doc_id': doc_id, 'error': error_msg}

        except Exception as e:
            error_msg = str(e)
            self.db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {'status': 'failed', 'error_message': error_msg}}
            )
            # ★ 异常也打印耗时
            total_elapsed = time.time() - total_start
            print(f"   ⏱️  异常耗时: {total_elapsed:.2f}s | ❌ {error_msg}")
            traceback.print_exc()
            return {'success': False, 'doc_id': doc_id, 'error': error_msg}

    # ================== 解析文本上传（★ 已添加耗时统计） ==================

    def upload_parsed_text(
        self,
        username: str,
        text_content: str,
        original_filename: str,
        folder_id: str = None,
        metadata: Dict = None,
    ) -> Dict[str, Any]:
        """
        将解析后的纯文本上传到知识库
        用于多媒体文件（图片/视频/PPT）解析后的文本入库
        """
        # ★ 总计时
        total_start = time.time()

        print(f"\n{'='*50}")
        print(f"📤 上传解析文本到知识库")
        print(f"👤 用户: {username}")
        print(f"📄 原始文件: {original_filename}")
        print(f"📝 文本长度: {len(text_content)}")

        if not text_content or not text_content.strip():
            return {'success': False, 'error': '解析文本为空'}

        if folder_id:
            folder = self.db.kb_folders.find_one({
                'username': username,
                'folder_id': folder_id
            })
            if not folder:
                return {'success': False, 'error': '目标文件夹不存在'}

        dataset_id = self.get_or_create_user_dataset(username)
        if not dataset_id:
            return {'success': False, 'error': '无法获取或创建知识库'}

        # 生成文档 ID
        doc_id = self._generate_doc_id(username, original_filename)

        # 记录到 MongoDB
        media_type = (metadata or {}).get('media_type', 'unknown')
        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {
                '$set': {
                    'doc_id': doc_id,
                    'username': username,
                    'filename': original_filename,
                    'file_type': original_filename.rsplit('.', 1)[-1].lower()
                                 if '.' in original_filename else '',
                    'dataset_id': dataset_id,
                    'folder_id': folder_id,
                    'status': 'processing',
                    'upload_time': datetime.now(),
                    'file_size': len(text_content.encode('utf-8')),
                    'name_synced': False,
                    'shared': False,
                    'parsed_from_media': True,
                    'media_type': media_type,
                    'parse_metadata': metadata or {},
                    'parsed_text': text_content[:5000],
                }
            },
            upsert=True
        )

        self._clear_filename_cache(username)

        try:
            # ★ 创建 Collection 计时
            t_create_start = time.time()
            collection_id = self._create_text_collection(
                dataset_id, original_filename, doc_id)

            if not collection_id:
                collection_id = self._create_virtual_collection_v2(
                    dataset_id, original_filename, doc_id)

            t_create_elapsed = time.time() - t_create_start                # ★
            print(f"   ⏱️  创建 Collection: {t_create_elapsed:.2f}s")

            if not collection_id:
                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {'$set': {'status': 'failed',
                              'error_message': '在 FastGPT 中创建 Collection 失败'}}
                )
                return {'success': False, 'error': '在 FastGPT 中创建文档容器失败'}

            # ★ 文本切分计时
            t_split_start = time.time()
            chunks = self._split_text_to_chunks(text_content, filename=original_filename)
            t_split_elapsed = time.time() - t_split_start                  # ★
            print(f"   ⏱️  文本切分: {t_split_elapsed:.2f}s ({len(chunks)} 个数据块)")

            # ★ 批量写入计时
            t_insert_start = time.time()
            success_count = self._batch_insert_data(collection_id, chunks)
            t_insert_elapsed = time.time() - t_insert_start                # ★
            print(f"   ⏱️  批量写入: {t_insert_elapsed:.2f}s ({success_count}/{len(chunks)} 块)")

            if success_count == 0:
                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {'$set': {'status': 'failed',
                              'error_message': '数据块写入失败'}}
                )
                return {'success': False, 'error': '数据块写入 FastGPT 失败'}

            # 更新状态
            self.db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {
                    'status': 'ready',
                    'collection_id': collection_id,
                    'chunk_count': success_count,
                    'processed_at': datetime.now(),
                    'name_synced': False,
                }}
            )

            # 同步文件名
            time.sleep(0.5)
            name_result = self.update_collection_name(
                collection_id, original_filename)
            if name_result.get('success'):
                self.db.kb_documents.update_one(
                    {'doc_id': doc_id},
                    {'$set': {'name_synced': True,
                              'name_synced_at': datetime.now()}}
                )

            self._clear_filename_cache(username)

            if username in self._last_sync_time:
                del self._last_sync_time[username]

            # ★ 打印完整耗时报告
            total_elapsed = time.time() - total_start
            text_size_kb = len(text_content.encode('utf-8')) / 1024
            print(f"\n{'─'*60}")
            print(f"⏱️  知识库写入耗时报告")
            print(f"   📄 文件名:        {original_filename}")
            print(f"   👤 用户:          {username}")
            print(f"   🔧 媒体类型:      {media_type}")
            print(f"   📝 文本大小:      {text_size_kb:.1f} KB")
            print(f"   📊 数据块:        {success_count} 个")
            print(f"   ⏱️  创建Collection: {t_create_elapsed:.2f}s")
            print(f"   ⏱️  文本切分:      {t_split_elapsed:.2f}s")
            print(f"   ⏱️  批量写入:      {t_insert_elapsed:.2f}s")
            print(f"   ⏱️  总写入耗时:    {total_elapsed:.2f}s")
            print(f"   ✅ 写入完成")
            print(f"{'─'*60}")

            return {
                'success': True,
                'doc_id': doc_id,
                'collection_id': collection_id,
                'folder_id': folder_id,
                'status': 'ready',
                'chunk_count': success_count,
                'message': f'多媒体文件解析完成，已生成 {success_count} 个知识块',
                'upload_time_seconds': round(total_elapsed, 2),            # ★
            }

        except Exception as e:
            error_msg = str(e)
            self.db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {'status': 'failed', 'error_message': error_msg}}
            )
            # ★ 异常也打印耗时
            total_elapsed = time.time() - total_start
            print(f"   ⏱️  异常耗时: {total_elapsed:.2f}s | ❌ {error_msg}")
            traceback.print_exc()
            return {'success': False, 'doc_id': doc_id, 'error': error_msg}

    # ★★★ 修改点① _split_text_to_chunks — 每个 chunk 前注入文件名 ★★★
    def _split_text_to_chunks(
        self,
        text: str,
        chunk_size: int = 500,
        overlap: int = 50,
        filename: str = None,
    ) -> List[Dict]:
        """
        将长文本切分为 q/a 数据块
        优先按段落/章节切分，保持语义完整性
        ★ 每个 chunk 前注入文件名，确保按文件名搜索也能命中
        """
        chunks = []

        # 按 Markdown 标题切分
        sections = re.split(r'\n(?=##?\s)', text)

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(section) <= chunk_size:
                chunks.append({'q': section, 'a': '', 'indexes': []})
            else:
                # 按段落进一步切分
                paragraphs = section.split('\n\n')
                current = ''
                for para in paragraphs:
                    para = para.strip()
                    if not para:
                        continue

                    if len(current) + len(para) + 2 > chunk_size and current:
                        chunks.append(
                            {'q': current.strip(), 'a': '', 'indexes': []})
                        # 保留 overlap
                        if overlap > 0 and len(current) > overlap:
                            current = current[-overlap:] + '\n\n' + para
                        else:
                            current = para
                    else:
                        current = (current + '\n\n' + para).strip()

                if current.strip():
                    chunks.append(
                        {'q': current.strip(), 'a': '', 'indexes': []})

        # 如果没切出来，强制按字符数切分
        if not chunks and text.strip():
            for i in range(0, len(text), chunk_size - overlap):
                chunk = text[i:i + chunk_size].strip()
                if chunk:
                    chunks.append({'q': chunk, 'a': '', 'indexes': []})

        # ★★★ 每个 chunk 注入文件名标签，确保按文件名搜索能命中 ★★★
        if filename and chunks:
            # 去掉扩展名部分作为关键词（如 "凶巴巴的猪猪.jpg" → "凶巴巴的猪猪"）
            name_no_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            prefix = f"[文件：{filename}] [关键词：{name_no_ext}]\n"
            for chunk in chunks:
                # 只对不包含文件名的 chunk 添加（第1个chunk通常已含文件名）
                if filename not in chunk['q'][:100]:
                    chunk['q'] = prefix + chunk['q']

        return chunks

    def _upload_file_to_fastgpt(self, dataset_id: str, file_content: bytes,
                                 filename: str, doc_id: str) -> Dict:
        url = f"{self.base_url}/core/dataset/collection/create/localFile"

        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'txt'
        safe_filename = f"{doc_id}.{ext}"

        config_data = {
            "datasetId": dataset_id,
            "parentId": None,
            "trainingType": "chunk",
            "chunkSize": 500,
            "chunkSplitter": "",
            "qaPrompt": "",
            "metadata": {
                "originalName": filename,
                "docId": doc_id
            }
        }

        try:
            files = {
                'file': (safe_filename, file_content, self._get_mime_type(filename))
            }

            form_data = {
                'data': json.dumps(config_data, ensure_ascii=False)
            }

            response = requests.post(
                url,
                headers=self._get_upload_headers(),
                files=files,
                data=form_data,
                timeout=120
            )

            if response.status_code == 200:
                result = response.json()
                if result.get('code') == 200:
                    data = result.get('data', {})
                    collection_id = data.get('collectionId') or data.get('_id')

                    results = data.get('results', {})
                    if isinstance(results, dict):
                        insert_len = results.get('insertLen', 0)
                    elif isinstance(results, list):
                        insert_len = len(results)
                    else:
                        insert_len = data.get('insertLen', 0)

                    return {
                        'success': True,
                        'collection_id': collection_id,
                        'chunks': insert_len
                    }
                else:
                    return {'success': False, 'error': result.get('message', '上传失败')}
            else:
                try:
                    error_data = response.json()
                    error_msg = (error_data.get('message', '') or
                                 error_data.get('statusText', '') or response.text)
                except Exception:
                    error_msg = response.text or f'HTTP {response.status_code}'
                return {'success': False, 'error': f'FastGPT返回错误: {error_msg}'}

        except requests.exceptions.Timeout:
            return {'success': False, 'error': '上传超时，请稍后重试'}
        except Exception as e:
            traceback.print_exc()
            return {'success': False, 'error': f'上传异常: {str(e)}'}

    def _generate_doc_id(self, username: str, filename: str) -> str:
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        hash_str = hashlib.md5(f"{username}_{filename}_{timestamp}".encode()).hexdigest()[:8]
        return f"doc_{username}_{hash_str}"

    def _get_mime_type(self, filename: str) -> str:
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        mime_types = {
            'pdf': 'application/pdf',
            'txt': 'text/plain',
            'md': 'text/markdown',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'xls': 'application/vnd.ms-excel',
            'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'ppt': 'application/vnd.ms-powerpoint',
            'csv': 'text/csv',
            'json': 'application/json',
            'html': 'text/html',
            'htm': 'text/html'
        }
        return mime_types.get(ext, 'application/octet-stream')

    # ================== 搜索与问答 ==================

    def _get_shared_dataset_id_cached(self) -> Optional[str]:
        """获取共享知识库 ID（仅查询缓存和 MongoDB，不创建）"""
        if self._shared_dataset_id:
            return self._shared_dataset_id
        try:
            shared_record = self.db.system_config.find_one({'key': 'shared_dataset_id'})
            if shared_record and shared_record.get('value'):
                self._shared_dataset_id = shared_record['value']
                return self._shared_dataset_id
        except Exception:
            pass
        return None

    def _search_single_dataset(self, dataset_id: str, username: str,
                                query: str, top_k: int = 5,
                                is_shared: bool = False) -> List[Dict]:
        """
        搜索单个 Dataset，返回标准化结果列表
        """
        url = f"{self.base_url}/core/dataset/searchTest"
        payload = {
            "datasetId": dataset_id,
            "text": query,
            "limit": top_k,
            "similarity": 0.3,
            "searchMode": "embedding",
            "usingReRank": False
        }

        try:
            response = requests.post(url, headers=self._get_headers(),
                                     json=payload, timeout=30)
            response.raise_for_status()
            result = response.json()

            if result.get('code') != 200:
                return []

            data = result.get('data', {})
            if isinstance(data, dict):
                items = data.get('list', [])
            elif isinstance(data, list):
                items = data
            else:
                items = []

            results = []
            for item in items:
                if item is None or not isinstance(item, dict):
                    continue

                q_content = item.get('q', '')
                a_content = item.get('a', '')
                content = ''
                if q_content:
                    content = q_content
                if a_content:
                    content = (content + '\n' + a_content) if content else a_content
                if not content:
                    content = item.get('content', '') or item.get('text', '')
                if not content:
                    continue

                data_id = item.get('id', '') or item.get('_id', '')
                collection_id = item.get('collectionId', '')
                dataset_id_item = item.get('datasetId', '') or dataset_id
                fastgpt_source = (item.get('sourceName', '') or
                                  item.get('collectionName', '') or '')

                if is_shared:
                    original_filename = self._resolve_shared_source(
                        username, fastgpt_source, collection_id)
                else:
                    original_filename = self._resolve_filename(
                        username, collection_id, fastgpt_source)

                    if original_filename and original_filename.startswith('['):
                        cleaned = re.sub(r'^\[.*?\]\s*', '', original_filename)
                        if cleaned:
                            original_filename = cleaned

                raw_score = item.get('score', 0)
                if isinstance(raw_score, (list, tuple)):
                    raw_score = raw_score[0] if len(raw_score) > 0 else 0
                try:
                    raw_score = float(raw_score) if raw_score else 0.0
                except (TypeError, ValueError):
                    raw_score = 0.0

                results.append({
                    'content': content.strip(),
                    'q': q_content,
                    'a': a_content,
                    'score': raw_score,
                    'source': original_filename,
                    'data_id': data_id,
                    'collection_id': collection_id,
                    'dataset_id': dataset_id_item,
                    'fastgpt_source': fastgpt_source
                })

            return results

        except Exception as e:
            print(f"⚠️ 搜索 Dataset {dataset_id[:8]}... 失败: {e}")
            return []

    def search(self, username: str, query: str, top_k: int = 5,
               include_shared: bool = True) -> Dict[str, Any]:
        """
        搜索用户知识库
        ★ 增加文件名匹配回退：当用户按文件名搜索时也能命中
        """
        all_results = []

        # ★★★ 新增：文件名模糊匹配（覆盖历史文档） ★★★
        filename_results = self._search_by_filename(username, query)
        if filename_results:
            print(f"🔍 文件名匹配: {len(filename_results)} 条结果")
            all_results.extend(filename_results)

        # ① 搜索个人知识库
        dataset_id = self.get_or_create_user_dataset(username)
        if dataset_id:
            personal = self._search_single_dataset(
                dataset_id, username, query, top_k, is_shared=False)
            for r in personal:
                r['source_type'] = 'personal'
            all_results.extend(personal)
            if personal:
                print(f"🔍 个人知识库: {len(personal)} 条结果")

        # ② 搜索共享知识库（使用隐私保护）
        if include_shared:
            shared_dataset_id = self._get_shared_dataset_id_cached()
            if shared_dataset_id and shared_dataset_id != dataset_id:
                shared = self._search_single_dataset(
                    shared_dataset_id, username, query, top_k, is_shared=True)
                for r in shared:
                    r['source_type'] = 'shared'
                all_results.extend(shared)
                if shared:
                    print(f"🔍 共享知识库: {len(shared)} 条结果")

        if not all_results:
            return {'success': True, 'results': [], 'total': 0}

        # ③ 按分数排序
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)

        # ④ 去重
        seen = {}
        deduped = []
        for r in all_results:
            key = r.get('content', '')[:100].strip()
            if not key:
                deduped.append(r)
                continue

            if key in seen:
                existing = seen[key]
                if (existing.get('source_type') == 'personal'
                        and r.get('source_type') == 'shared'):
                    idx = deduped.index(existing)
                    deduped[idx] = r
                    seen[key] = r
            else:
                seen[key] = r
                deduped.append(r)

        final = deduped[:top_k]

        return {
            'success': True,
            'results': final,
            'total': len(final)
        }

    def _search_by_filename(self, username: str, query: str, max_results: int = 3) -> List[Dict]:
        """
        ★ 按文件名模糊匹配搜索（覆盖历史文档和新文档）
        当用户输入的 query 与某个文件名匹配时，返回该文件的摘要内容
        """
        if not query or len(query) < 2:
            return []

        try:
            # 在 MongoDB 中按文件名模糊匹配
            docs = list(self.db.kb_documents.find(
                {
                    'username': username,
                    'status': 'ready',
                    'filename': {'$regex': re.escape(query), '$options': 'i'}
                },
                {
                    'collection_id': 1, 'filename': 1, 'dataset_id': 1,
                    'parsed_text': 1, 'doc_id': 1, 'media_type': 1,
                    'file_type': 1, 'chunk_count': 1
                }
            ).limit(max_results))

            if not docs:
                return []

            results = []
            for doc in docs:
                filename = doc.get('filename', '')
                collection_id = doc.get('collection_id', '')

                # 优先使用已解析的文本摘要
                parsed_text = doc.get('parsed_text', '')
                if parsed_text:
                    # 取前1500字作为内容摘要
                    content = parsed_text[:1500]
                    if len(parsed_text) > 1500:
                        content += '\n\n...（内容较长，已截断）'
                else:
                    content = f"文件：{filename}（共 {doc.get('chunk_count', 0)} 个知识块）"

                results.append({
                    'content': content,
                    'q': content[:500],
                    'a': '',
                    'score': 1.0,  # 文件名精确匹配给高分
                    'source': filename,
                    'data_id': doc.get('doc_id', ''),
                    'collection_id': collection_id,
                    'dataset_id': doc.get('dataset_id', ''),
                    'fastgpt_source': filename,
                    'source_type': 'personal',
                    'match_type': 'filename',
                })

                print(f"   📎 文件名命中: {filename} (collection={collection_id[:8] if collection_id else 'N/A'}...)")

            return results

        except Exception as e:
            print(f"⚠️ 文件名搜索失败: {e}")
            return []

    def chat(self, username: str, question: str, top_k: int = 5,
             chat_id: str = None) -> Dict[str, Any]:
        start_time = time.time()

        search_result = self.search(username, question, top_k)

        if not search_result.get('success') or not search_result.get('results'):
            doc_count = self.db.kb_documents.count_documents({'username': username, 'status': 'ready'})

            if doc_count == 0:
                return {
                    'success': True,
                    'answer': '您的知识库中还没有上传任何文档。请先上传学习资料。',
                    'sources': [],
                    'processing_time': time.time() - start_time
                }

            return {
                'success': True,
                'answer': '抱歉，在您的知识库中没有找到与此问题相关的内容。',
                'sources': [],
                'processing_time': time.time() - start_time
            }

        contexts = []
        sources = []
        for idx, item in enumerate(search_result['results']):
            content = item.get('content', '')
            if content:
                contexts.append(f"[{idx+1}] {content}")
                sources.append({
                    'index': idx + 1,
                    'content': content[:200] + '...' if len(content) > 200 else content,
                    'filename': item.get('source', ''),
                    'score': item.get('score', 0)
                })

        if not contexts:
            return {
                'success': True,
                'answer': '抱歉，在您的知识库中没有找到与此问题相关的内容。',
                'sources': [],
                'processing_time': time.time() - start_time
            }

        context_text = "\n\n".join(contexts)
        answer = self._generate_answer(question, context_text)

        try:
            self.db.kb_queries.insert_one({
                'username': username,
                'question': question,
                'answer': answer,
                'sources_count': len(sources),
                'query_time': datetime.now(),
                'processing_time': time.time() - start_time
            })
        except Exception as e:
            print(f"⚠️ 记录查询历史失败: {e}")

        return {
            'success': True,
            'answer': answer,
            'sources': sources,
            'retrieved_count': len(sources),
            'processing_time': time.time() - start_time
        }

    def _generate_answer(self, question: str, context: str) -> str:
        if self.app_api_key:
            result = self._call_fastgpt_app(question, context)
            if result:
                return result

        result = self._call_direct_llm(question, context)
        if result:
            return result

        return self._fallback_answer(context)

    def _call_fastgpt_app(self, question: str, context: str) -> Optional[str]:
        if not self.app_api_key:
            return None

        url = f"{self.base_url}/v1/chat/completions"

        system_prompt = """你是一个专业的学习助手。请根据用户提供的知识库内容，准确回答用户的问题。

回答要求：
1. 只使用知识库中的信息来回答，不要编造内容
2. 如果知识库内容不足以完整回答问题，请明确说明
3. 回答要清晰、有条理，适当使用列表或分段
4. 在适当的地方引用来源"""

        user_prompt = f"""请根据以下知识库内容回答问题。

【知识库内容】
{context}

【用户问题】
{question}

请给出准确、详细的回答："""

        try:
            response = requests.post(
                url,
                headers={
                    'Authorization': f'Bearer {self.app_api_key}',
                    'Content-Type': 'application/json'
                },
                json={
                    'model': self.llm_model,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': user_prompt}
                    ],
                    'temperature': 0.7,
                    'max_tokens': 2000,
                    'stream': False
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                if answer:
                    return answer

        except Exception as e:
            print(f"⚠️ FastGPT 应用 API 异常: {e}")

        return None

    def _call_direct_llm(self, question: str, context: str) -> Optional[str]:
        llm_endpoints = [
            self.llm_base_url,
            'http://180.85.206.30:8000/v1',
            'http://180.85.206.30:11434/v1',
        ]

        llm_endpoints = list(dict.fromkeys([ep for ep in llm_endpoints if ep]))

        system_prompt = """你是一个专业的学习助手。请根据用户提供的知识库内容，准确回答用户的问题。"""

        user_prompt = f"""请根据以下知识库内容回答问题。

【知识库内容】
{context}

【用户问题】
{question}

请给出准确、详细的回答："""

        for endpoint in llm_endpoints:
            url = f"{endpoint}/chat/completions"

            try:
                response = requests.post(
                    url,
                    headers={
                        'Authorization': f'Bearer {self.llm_api_key}',
                        'Content-Type': 'application/json'
                    },
                    json={
                        'model': self.llm_model,
                        'messages': [
                            {'role': 'system', 'content': system_prompt},
                            {'role': 'user', 'content': user_prompt}
                        ],
                        'temperature': 0.7,
                        'max_tokens': 2000,
                        'stream': False
                    },
                    timeout=60
                )

                if response.status_code == 200:
                    result = response.json()
                    answer = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                    if answer:
                        return answer

            except Exception as e:
                print(f"⚠️ LLM 端点 {endpoint} 异常: {e}")

        return None

    def _fallback_answer(self, context: str) -> str:
        truncated = context[:1500]
        if len(context) > 1500:
            truncated += "..."

        return f"""根据您知识库中的相关内容：

{truncated}

（注：AI回答生成暂时不可用，以上为检索到的相关内容摘要。）"""

    # ================== 文档管理 ==================

    def list_documents(self, username: str) -> List[Dict]:
        docs = list(self.db.kb_documents.find(
            {'username': username},
            {'_id': 0}
        ).sort('upload_time', -1))
        return docs

    def get_document_list(self, username: str) -> List[Dict]:
        return self.list_documents(username)

    def get_document(self, username: str, doc_id: str) -> Optional[Dict]:
        doc = self.db.kb_documents.find_one(
            {'username': username, 'doc_id': doc_id},
            {'_id': 0}
        )
        return doc

    def delete_document(self, username: str, doc_id: str) -> bool:
        doc = self.db.kb_documents.find_one({'username': username, 'doc_id': doc_id})
        if not doc:
            return False

        collection_id = doc.get('collection_id')

        if doc.get('shared') and doc.get('shared_collection_id'):
            shared_cid = doc['shared_collection_id']
            print(f"   🔗 文档已共享，同步删除共享副本: {shared_cid}")
            try:
                url = f"{self.base_url}/core/dataset/collection/delete"
                requests.delete(
                    url,
                    headers=self._get_headers(),
                    params={'id': shared_cid},
                    timeout=30
                )
                print(f"   ✅ 共享副本已删除")
            except Exception as e:
                print(f"   ⚠️ 删除共享副本失败: {e}")

        if collection_id:
            try:
                url = f"{self.base_url}/core/dataset/collection/delete"
                requests.delete(
                    url,
                    headers=self._get_headers(),
                    params={'id': collection_id},
                    timeout=30
                )
            except Exception as e:
                print(f"⚠️ 删除FastGPT集合失败: {e}")

        self.db.kb_documents.delete_one({'username': username, 'doc_id': doc_id})
        self._clear_filename_cache(username)

        return True

    def rename_document(self, username: str, doc_id: str, new_name: str) -> Dict[str, Any]:
        doc = self.db.kb_documents.find_one({
            'username': username,
            'doc_id': doc_id
        })

        if not doc:
            return {'success': False, 'error': '文档不存在'}

        collection_id = doc.get('collection_id')
        if collection_id:
            result = self.update_collection_name(collection_id, new_name)
            if not result.get('success'):
                print(f"⚠️ 更新 FastGPT 名称失败: {result.get('error')}")

        if doc.get('shared') and doc.get('shared_collection_id'):
            shared_cid = doc['shared_collection_id']
            new_anonymous_name = self._generate_shared_anonymous_name(doc_id, new_name)
            self.update_collection_name(shared_cid, new_anonymous_name)
            self.db.kb_documents.update_one(
                {'doc_id': doc_id},
                {'$set': {'shared_anonymous_name': new_anonymous_name}}
            )

        self.db.kb_documents.update_one(
            {'doc_id': doc_id},
            {'$set': {
                'filename': new_name,
                'name_synced': True,
                'name_synced_at': datetime.now(),
                'updated_at': datetime.now()
            }}
        )

        self._clear_filename_cache(username)

        return {'success': True, 'message': '重命名成功'}

    def get_kb_stats(self, username: str) -> Dict[str, Any]:
        pipeline = [
            {'$match': {'username': username}},
            {'$group': {
                '_id': '$status',
                'count': {'$sum': 1},
                'total_size': {'$sum': '$file_size'},
                'total_chunks': {'$sum': {'$ifNull': ['$chunk_count', 0]}}
            }}
        ]

        stats = list(self.db.kb_documents.aggregate(pipeline))

        result = {
            'total_documents': 0,
            'ready_documents': 0,
            'processing_documents': 0,
            'failed_documents': 0,
            'total_size': 0,
            'total_chunks': 0,
            'folder_count': 0
        }

        for stat in stats:
            status = stat['_id']
            count = stat['count']
            size = stat.get('total_size', 0) or 0
            chunks = stat.get('total_chunks', 0) or 0

            result['total_documents'] += count
            result['total_size'] += size
            result['total_chunks'] += chunks

            if status == 'ready':
                result['ready_documents'] = count
            elif status == 'processing':
                result['processing_documents'] = count
            elif status == 'failed':
                result['failed_documents'] = count

        result['folder_count'] = self.db.kb_folders.count_documents({'username': username})

        query_count = self.db.kb_queries.count_documents({'username': username})
        result['queries'] = query_count
        result['rag_enabled'] = result['ready_documents'] > 0

        if result['total_size'] > 1024 * 1024:
            result['total_size_display'] = f"{result['total_size'] / (1024*1024):.2f} MB"
        elif result['total_size'] > 1024:
            result['total_size_display'] = f"{result['total_size'] / 1024:.2f} KB"
        else:
            result['total_size_display'] = f"{result['total_size']} B"

        return result

    def get_user_stats(self, username: str) -> Dict[str, Any]:
        stats = self.get_kb_stats(username)
        return {
            'documents': stats['total_documents'],
            'ready_documents': stats['ready_documents'],
            'chunks': stats['total_chunks'],
            'queries': stats['queries'],
            'rag_enabled': stats['rag_enabled'],
            'total_size': stats['total_size'],
            'total_size_display': stats.get('total_size_display', '0 B'),
            'folder_count': stats.get('folder_count', 0)
        }


def create_fastgpt_kb_service(db):
    """创建 FastGPT 知识库服务实例"""
    return FastGPTKBService(db)
