import pymysql


def get_conn():
    return pymysql.connect(
        host="180.85.206.21",
        user="root",
        password="123456",
        database="zgllm",
        charset="utf8mb4"
    )

Name=["G0006",33087,27015929,33286]