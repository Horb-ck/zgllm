# fastgpt_image_uploader.py
"""
将图片上传到 FastGPT 文件存储，获取可访问的图片 URL
"""
import os
import io
import requests
import mimetypes
import traceback


class FastGPTImageUploader:
    """通过 FastGPT API 上传图片并获取内部可访问 URL"""

    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        # FastGPT 的外部访问基址（用于构建图片URL）
        # 通常是 http://180.85.206.30:3000
        self.base_url = self.api_url.rsplit('/api', 1)[0]

        print(f"   🖼️ FastGPT 图片上传器初始化")
        print(f"      API: {self.api_url}")
        print(f"      Base: {self.base_url}")

    def upload_image(self, file_content: bytes, filename: str,
                     team_id: str = None) -> dict:
        """
        上传图片到 FastGPT，返回可访问 URL

        Returns:
            {
                'success': True/False,
                'url': 'http://...',      # 可直接访问的图片 URL
                'file_id': '...',         # FastGPT 文件 ID
                'error': '...',
            }
        """
        # 方案1: 尝试 FastGPT 的通用文件上传 API
        result = self._try_upload_common(file_content, filename)
        if result.get('success'):
            return result

        # 方案2: 尝试 dataset 图片上传 API
        result2 = self._try_upload_dataset_image(file_content, filename)
        if result2.get('success'):
            return result2

        # 方案3: 尝试 img 上传 API
        result3 = self._try_upload_img(file_content, filename)
        if result3.get('success'):
            return result3

        return {
            'success': False,
            'url': '',
            'error': f"所有上传方式均失败: "
                     f"方式1={result.get('error','?')}, "
                     f"方式2={result2.get('error','?')}, "
                     f"方式3={result3.get('error','?')}",
        }

    def _try_upload_common(self, file_content, filename) -> dict:
        """方式1: POST /api/common/file/upload"""
        try:
            url = f"{self.api_url}/common/file/upload"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

            files = {
                'file': (filename, io.BytesIO(file_content), mime),
            }
            data = {
                'bucketName': 'dataset',
            }

            resp = requests.post(url, headers=headers,
                                 files=files, data=data, timeout=30)
            print(f"      [upload_common] HTTP {resp.status_code}")

            if resp.status_code == 200:
                body = resp.json()
                # FastGPT 可能返回 { code: 200, data: "fileId" }
                # 或 { code: 200, data: { fileId: "..." } }
                file_id = self._extract_file_id(body)
                if file_id:
                    img_url = f"{self.base_url}/api/common/file/read/{file_id}"
                    print(f"      ✅ 上传成功, URL: {img_url}")
                    return {
                        'success': True,
                        'url': img_url,
                        'file_id': file_id,
                    }
                else:
                    return {
                        'success': False,
                        'error': f'无法提取 file_id: {body}',
                    }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {resp.status_code}: '
                             f'{resp.text[:200]}',
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _try_upload_dataset_image(self, file_content, filename) -> dict:
        """方式2: POST /api/core/dataset/image/upload"""
        try:
            url = f"{self.api_url}/core/dataset/image/upload"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

            files = {
                'file': (filename, io.BytesIO(file_content), mime),
            }

            resp = requests.post(url, headers=headers,
                                 files=files, timeout=30)
            print(f"      [upload_dataset_image] HTTP {resp.status_code}")

            if resp.status_code == 200:
                body = resp.json()
                img_url = self._extract_url(body)
                if img_url:
                    if img_url.startswith('/'):
                        img_url = self.base_url + img_url
                    print(f"      ✅ 上传成功, URL: {img_url}")
                    return {'success': True, 'url': img_url}
                file_id = self._extract_file_id(body)
                if file_id:
                    img_url = (f"{self.base_url}"
                               f"/api/common/file/read/{file_id}")
                    return {
                        'success': True, 'url': img_url,
                        'file_id': file_id
                    }
                return {
                    'success': False,
                    'error': f'无法提取 URL: {body}',
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {resp.status_code}: '
                             f'{resp.text[:200]}',
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _try_upload_img(self, file_content, filename) -> dict:
        """方式3: POST /api/common/file/uploadImage"""
        try:
            url = f"{self.api_url}/common/file/uploadImage"
            headers = {'Authorization': f'Bearer {self.api_key}'}
            mime = mimetypes.guess_type(filename)[0] or 'image/jpeg'

            files = {
                'file': (filename, io.BytesIO(file_content), mime),
            }
            data = {
                'bucketName': 'dataset',
            }

            resp = requests.post(url, headers=headers,
                                 files=files, data=data, timeout=30)
            print(f"      [uploadImage] HTTP {resp.status_code}")

            if resp.status_code == 200:
                body = resp.json()
                img_url = self._extract_url(body)
                if img_url:
                    if img_url.startswith('/'):
                        img_url = self.base_url + img_url
                    return {'success': True, 'url': img_url}
                file_id = self._extract_file_id(body)
                if file_id:
                    img_url = (f"{self.base_url}"
                               f"/api/common/file/read/{file_id}")
                    return {
                        'success': True, 'url': img_url,
                        'file_id': file_id
                    }
                return {
                    'success': False,
                    'error': f'无法提取: {body}',
                }
            else:
                return {
                    'success': False,
                    'error': f'HTTP {resp.status_code}: '
                             f'{resp.text[:200]}',
                }
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @staticmethod
    def _extract_file_id(body):
        """从 FastGPT 响应中提取 file_id"""
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

    @staticmethod
    def _extract_url(body):
        """从 FastGPT 响应中提取 URL"""
        if not isinstance(body, dict):
            return None
        data = body.get('data')
        if isinstance(data, str) and (
            data.startswith('http') or data.startswith('/')
        ):
            return data
        if isinstance(data, dict):
            for key in ('url', 'imageUrl', 'img_url', 'link', 'src'):
                if data.get(key):
                    return data[key]
        return None
