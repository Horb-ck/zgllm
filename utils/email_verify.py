import os
import sys
import smtplib
import random
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from typing import Iterable

# Ensure project root is on sys.path so `config` can be imported when running this file directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import MAIL_AUTH_KEY, EMAIL_URL  # noqa: E402

# https://net.cqu.edu.cn/info/1028/1571.htm

# 简单的验证码与发送计数存储（内存级） 
verification_store = {}
send_counter_ip = {}
send_counter_account = {}
VERIFICATION_TTL_MINUTES = 10
SEND_LIMIT_PER_DAY = 5

def _today_key():
    return datetime.utcnow().date()

def _cleanup_counters():
    today = _today_key()
    for counter in (send_counter_ip, send_counter_account):
        expired = [k for k, v in counter.items() if v["day"] != today]
        for k in expired:
            counter.pop(k, None)

def _can_send(ip_addr: str, account: str):
    _cleanup_counters()
    today = _today_key()
    ip_info = send_counter_ip.get(ip_addr, {"day": today, "count": 0})
    acct_info = send_counter_account.get(account, {"day": today, "count": 0})
    return ip_info["count"] < SEND_LIMIT_PER_DAY and acct_info["count"] < SEND_LIMIT_PER_DAY

def _bump_counters(ip_addr: str, account: str):
    today = _today_key()
    send_counter_ip[ip_addr] = {
        "day": today,
        "count": send_counter_ip.get(ip_addr, {"day": today, "count": 0})["count"] + 1
    }
    send_counter_account[account] = {
        "day": today,
        "count": send_counter_account.get(account, {"day": today, "count": 0})["count"] + 1
    }

def _store_code(scene: str, account: str, email: str, code: str):
    key = f"{scene}:{account}:{email.lower()}"
    verification_store[key] = {
        "code": code,
        "expires_at": datetime.utcnow() + timedelta(minutes=VERIFICATION_TTL_MINUTES)
    }

def _verify_code(scene: str, account: str, email: str, code: str) -> bool:
    key = f"{scene}:{account}:{email.lower()}"
    entry = verification_store.get(key)
    if not entry:
        return False
    if datetime.utcnow() > entry["expires_at"]:
        verification_store.pop(key, None)
        return False
    if entry["code"] != code:
        return False
    verification_store.pop(key, None)
    return True

def send_email_via_CQU(
    to_addrs: Iterable[str],
    subject: str,
    body: str,
    from_addr: str,
    auth_code: str = MAIL_AUTH_KEY,
    *,
    is_html: bool = False,
    timeout: int = 10,
) -> bool:
    """
    Send an email through CQU SMTP.
    """
    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]

    msg = MIMEText(body, "html" if is_html else "plain", "utf-8")
    msg["From"] = from_addr
    msg["To"] = ",".join(to_addrs)
    msg["Subject"] = Header(subject, "utf-8")

    try:
        with smtplib.SMTP_SSL("smtp.cqu.edu.cn", 465 , timeout=timeout) as server:
            server.login(from_addr, auth_code)
            server.sendmail(from_addr, list(to_addrs), msg.as_string())
        return True
    except Exception as exc:
        # 检查异常是否为 (-1, b'\x00\x00\x00')
        if str(exc) == "(-1, b'\\x00\\x00\\x00')":
            print("Warning: CQU SMTP returned error (-1, b'\\x00\\x00\\x00'), but email sent successfully.")
            return True  # 返回True，表示邮件成功发送
        print(f"Failed to send email via CQU SMTP: {exc}")
        return False

if __name__ == "__main__":
    target_email = "202414131117@stu.cqu.edu.cn"
    account = "202414131117"
    code = f"{random.randint(0, 999999):06d}"

    _store_code("test", account, target_email, code)
    body = f"测试验证码：{code}，{VERIFICATION_TTL_MINUTES} 分钟内有效。"
    sent = send_email_via_CQU(
        to_addrs=target_email,
        subject="测试验证码",
        body=body,
        from_addr=EMAIL_URL,
        auth_code=MAIL_AUTH_KEY,
    )
    print(f"Send result: {sent}")
    if not sent:
        sys.exit(1)

    user_input = input("请输入邮件中的验证码后回车：").strip()
    if _verify_code("test", account, target_email, user_input):
        print("验证码正确")
    else:
        print("验证码错误或已过期")
