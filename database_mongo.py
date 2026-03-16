# database.py
from pymongo import MongoClient
from config import MONGO_URL
# 初始化MongoDB连接
print("🔄 初始化MongoDB连接...")
client = MongoClient(
        host=MONGO_URL,
        port=27027,
        username='root',
        password='123456',
        authSource='admin'
)
db = client["education2"]
user_sessions_collection = db["user_sessions"]

# 创建索引
try:
    user_sessions_collection.create_index("username", unique=True)
    print("✅ MongoDB索引创建成功")
except Exception as e:
    print(f"⚠️ MongoDB索引创建警告: {e}")

print("✅ MongoDB连接成功")