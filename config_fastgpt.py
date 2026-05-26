# -*- coding: utf-8 -*-
"""
FastGPT 环境配置中心
====================
★ 切换环境只需修改下面这一行 ★
"""

# ╔══════════════════════════════════════════╗
# ║  "prod" = 正式版    "test" = 测试版      ║
# ╚══════════════════════════════════════════╝
import os

FASTGPT_ENV = os.environ.get("FASTGPT_ENV", "prod").strip().lower()


# ================== 环境配置 ==================

_PROFILES = {

    # ──────── 正式版 ────────
    "prod": {
        "FASTGPT_BASE_URL":       "http://180.85.206.30:3000",
        "FASTGPT_API_URL":        "http://180.85.206.30:3000/api",
        "FASTGPT_API_KEY":        "fastgpt-suPpeQxXcXBuqdoxW4Y3HiPVS9ecccfeL958V64aJYK0Y4tQmApxuCQtCDxXV",
        "FASTGPT_APP_KEY":        "fastgpt-suPpeQxXcXBuqdoxW4Y3HiPVS9ecccfeL958V64aJYK0Y4tQmApxuCQtCDxXV",
        "FASTGPT_SHARE_ID":       "zDrmPPnh9rdi3WmnyWCFwDcb",       # 个人知识库 share
        "FASTGPT_SHARE_BASE_URL": "http://180.85.206.30:3000",

        "FASTGPT_SHARED_DATASET_ID": "",
        "FASTGPT_SHARED_DATASET_NAME": "共享知识库",

        "FASTGPT_SHARED_FILENAME_MODE": "tagged_original",
        "FASTGPT_SHARED_FILENAME_TAG": "【用户共享】",
        "FASTGPT_SHARED_FILENAME_TAG_POSITION": "prefix",

        # LLM / Whisper（经 FastGPT 转发）
        "LLM_API_URL":            "http://180.85.206.30:3000/api/v1",
        "WHISPER_API_URL":        "http://180.85.206.30:3000/api/v1",

        # LLM 回退端点
        "LLM_FALLBACK_ENDPOINTS": [
            "http://180.85.206.30:8000/v1",
            "http://180.85.206.30:11434/v1",
        ],

        # 学情分析 share 链接
        "STUDY_TEACHER_SHARE_URL": "http://180.85.206.30:3000/chat/share?shareId=eXdNT9oSlB5U6MDNrYCCFK0T",
        "STUDY_STUDENT_SHARE_URL": "http://180.85.206.30:3000/chat/share?shareId=eJTdUHhzeIBYWb7Kdp6URitd",
    },

    # ──────── 测试版 ────────
    "test": {
        "FASTGPT_BASE_URL":       "http://180.85.206.21:3002",
        "FASTGPT_API_URL":        "http://180.85.206.21:3002/api",
        "FASTGPT_API_KEY":        "fastgpt-tMjkB9yYNKapQofGcRNCDWcaQIUATRlrs9jMRilk6OzaVq311PAhY9IY1m2",   # ← 第二步会生成，填到这里
        "FASTGPT_APP_KEY":        "fastgpt-tMjkB9yYNKapQofGcRNCDWcaQIUATRlrs9jMRilk6OzaVq311PAhY9IY1m2",   # ← 同上
        "FASTGPT_SHARE_ID":       "bie35ySquF21ALJrOrZ0CxBi",       # 测试版个人知识库 share
        "FASTGPT_SHARE_BASE_URL": "http://180.85.206.21:3000",

        "FASTGPT_SHARED_DATASET_ID": "69ee18ed087319f305dfc711",
        "FASTGPT_SHARED_DATASET_NAME": "共享知识库",

        "FASTGPT_SHARED_FILENAME_MODE": "tagged_original",
        "FASTGPT_SHARED_FILENAME_TAG": "【用户共享】",
        "FASTGPT_SHARED_FILENAME_TAG_POSITION": "prefix",

        # LLM / Whisper（经测试版 FastGPT 转发）
        "LLM_API_URL":            "http://180.85.206.21:3002/api/v1",
        "WHISPER_API_URL":        "http://180.85.206.21:3002/api/v1",

        # LLM 回退端点（与正式版共用，因为是独立服务）
        "LLM_FALLBACK_ENDPOINTS": [
            "http://180.85.206.30:8000/v1",
            "http://180.85.206.30:11434/v1",
        ],

        # 学情分析（测试版暂无，留空）
        "STUDY_TEACHER_SHARE_URL": "",
        "STUDY_STUDENT_SHARE_URL": "",
    },
}


# ================== VLM 模型配置（与 FastGPT 无关，不随环境切换） ==================

VLM_MODELS = [
    {
        'name':    'qwen3-vl-plus',
        'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'api_key': 'sk-f72cad3abb5a46d09dec2660948390ad',
        'model':   'qwen3-vl-plus',
    },
    {
        'name':    'sili-Qwen-72B-VL',
        'api_url': 'https://api.siliconflow.cn/v1/chat/completions',
        'api_key': 'sk-jsyegxvsmgntuxzstxtrcxlbwzoqtfffdldjwzzpoqgqtufc',
        'model':   'Qwen/Qwen2.5-VL-72B-Instruct',
    },
]

LLM_MODELS = [
    {
        'name':    'qwen-plus',
        'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'api_key': 'sk-f72cad3abb5a46d09dec2660948390ad',
        'model':   'qwen-plus',
    },
    {
        'name':    'qwen3-max-preview',
        'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'api_key': 'sk-f72cad3abb5a46d09dec2660948390ad',
        'model':   'qwen3-max-preview',
    },
    {
        'name':    'qwen3-vl-plus',
        'api_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions',
        'api_key': 'sk-f72cad3abb5a46d09dec2660948390ad',
        'model':   'qwen3-vl-plus',
    },
    {
        'name':    'sili-Qwen-72B-VL',
        'api_url': 'https://api.siliconflow.cn/v1/chat/completions',
        'api_key': 'sk-jsyegxvsmgntuxzstxtrcxlbwzoqtfffdldjwzzpoqgqtufc',
        'model':   'Qwen/Qwen2.5-VL-72B-Instruct',
    },
]


# ================== 导出当前环境配置 ==================

def get_config():
    """获取当前环境的配置字典"""
    env = FASTGPT_ENV
    if env not in _PROFILES:
        raise ValueError(f"未知环境: {env}，可选: {list(_PROFILES.keys())}")
    cfg = _PROFILES[env].copy()
    print(f"🌍 FastGPT 环境: {env.upper()} → {cfg['FASTGPT_BASE_URL']}")
    return cfg


# 便捷访问
_cfg = get_config()

FASTGPT_BASE_URL       = _cfg["FASTGPT_BASE_URL"]
FASTGPT_API_URL        = _cfg["FASTGPT_API_URL"]
FASTGPT_API_KEY        = _cfg["FASTGPT_API_KEY"]
FASTGPT_APP_KEY        = _cfg["FASTGPT_APP_KEY"]
FASTGPT_SHARE_ID       = _cfg["FASTGPT_SHARE_ID"]
FASTGPT_SHARE_BASE_URL = _cfg["FASTGPT_SHARE_BASE_URL"]

FASTGPT_SHARED_DATASET_ID = _cfg.get("FASTGPT_SHARED_DATASET_ID", "")
FASTGPT_SHARED_DATASET_NAME = _cfg.get("FASTGPT_SHARED_DATASET_NAME", "共享知识库")

FASTGPT_SHARED_FILENAME_MODE = _cfg.get("FASTGPT_SHARED_FILENAME_MODE", "tagged_original")
FASTGPT_SHARED_FILENAME_TAG = _cfg.get("FASTGPT_SHARED_FILENAME_TAG", "【用户共享】")
FASTGPT_SHARED_FILENAME_TAG_POSITION = _cfg.get("FASTGPT_SHARED_FILENAME_TAG_POSITION", "prefix")

LLM_API_URL            = _cfg["LLM_API_URL"]
WHISPER_API_URL         = _cfg["WHISPER_API_URL"]
LLM_FALLBACK_ENDPOINTS = _cfg["LLM_FALLBACK_ENDPOINTS"]
STUDY_TEACHER_SHARE_URL = _cfg["STUDY_TEACHER_SHARE_URL"]
STUDY_STUDENT_SHARE_URL = _cfg["STUDY_STUDENT_SHARE_URL"]

