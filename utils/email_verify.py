import os
import sys
import smtplib
import random
import traceback
import pymysql
from contextlib import closing
from threading import Lock
from datetime import datetime, timedelta
from email.header import Header
from email.mime.text import MIMEText
from typing import Iterable, Optional, Dict

# Ensure project root is on sys.path so `config` can be imported when running this file directly
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import MAIL_AUTH_KEY, EMAIL_URL, MYSQL_URL  # noqa: E402

# https://net.cqu.edu.cn/info/1028/1571.htm

VERIFICATION_TTL_MINUTES = 10
SEND_LIMIT_PER_DAY = 5
MAX_VERIFY_FAILS = 5

# 验证码状态
STATUS_UNUSED = 0
STATUS_USED = 1
STATUS_EXPIRED = 2
STATUS_INVALID = 3

_last_code_ctx_by_account: Dict[str, dict] = {}
_last_code_ctx_lock = Lock()


def _get_conn():
    """
    Keep connection settings aligned with current project defaults.
    Env vars are supported to avoid hard-coding credentials in all environments.
    """
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", MYSQL_URL),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", "123456"),
        database=os.getenv("MYSQL_DATABASE", "zgllm"),
        charset="utf8mb4",
    )


def _purpose_key(scene: str, account: str, email: str) -> str:
    return f"{scene}:{account}:{email.lower()}"


def _remember_last_code(account: str, scene: str, email: str, code_id: int):
    with _last_code_ctx_lock:
        _last_code_ctx_by_account[account] = {
            "scene": scene,
            "email": email.lower(),
            "code_id": code_id,
            "created_at": datetime.utcnow(),
        }


def _get_last_code_ctx(account: str) -> Optional[dict]:
    with _last_code_ctx_lock:
        ctx = _last_code_ctx_by_account.get(account)
        if not ctx:
            return None
        if datetime.utcnow() - ctx["created_at"] > timedelta(minutes=30):
            _last_code_ctx_by_account.pop(account, None)
            return None
        return dict(ctx)

def _can_send(ip_addr: str, account: str):
    ip_addr = (ip_addr or "unknown").strip() or "unknown"
    account = str(account or "").strip()
    if not account:
        return False

    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    try:
        with closing(_get_conn()) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM email_send_log
                WHERE ip_addr = %s
                  AND send_status = 1
                  AND created_at >= %s
                  AND created_at < %s
                """,
                (ip_addr, day_start, day_end),
            )
            ip_count = int(cursor.fetchone()[0] or 0)

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM email_send_log
                WHERE account = %s
                  AND send_status = 1
                  AND created_at >= %s
                  AND created_at < %s
                """,
                (account, day_start, day_end),
            )
            account_count = int(cursor.fetchone()[0] or 0)

        return ip_count < SEND_LIMIT_PER_DAY and account_count < SEND_LIMIT_PER_DAY
    except Exception as exc:
        print(f"_can_send failed: {exc}")
        traceback.print_exc()
        # 安全起见，频控不可用时默认不允许发送
        return False


def _bump_counters(ip_addr: str, account: str):
    ip_addr = (ip_addr or "unknown").strip() or "unknown"
    account = str(account or "").strip()
    if not account:
        return

    now = datetime.utcnow()
    ctx = _get_last_code_ctx(account)

    try:
        with closing(_get_conn()) as conn, conn.cursor() as cursor:
            scene = None
            email = None
            code_id = None

            if ctx:
                scene = ctx["scene"]
                email = ctx["email"]
                code_id = ctx["code_id"]
            else:
                cursor.execute(
                    """
                    SELECT id, scene, email
                    FROM email_verification_code
                    WHERE account = %s
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (account,),
                )
                row = cursor.fetchone()
                if row:
                    code_id, scene, email = row[0], row[1], row[2]

            if not scene:
                scene = "register"
            if email is None:
                email = ""

            cursor.execute(
                """
                INSERT INTO email_send_log (
                    scene, account, email, code_id, ip_addr, user_agent,
                    send_status, error_message, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (scene, account, email.lower(), code_id, ip_addr, None, 1, None, now),
            )
            conn.commit()
    except Exception as exc:
        print(f"_bump_counters failed: {exc}")
        traceback.print_exc()

def _store_code(scene: str, account: str, email: str, code: str):
    scene = str(scene or "").strip()
    account = str(account or "").strip()
    email_lower = str(email or "").strip().lower()
    code = str(code or "").strip()
    if not scene or not account or not email_lower or not code:
        return

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=VERIFICATION_TTL_MINUTES)
    purpose_key = _purpose_key(scene, account, email_lower)

    try:
        with closing(_get_conn()) as conn, conn.cursor() as cursor:
            # 同一业务键下老的未使用验证码置为作废，避免多码并存
            cursor.execute(
                """
                UPDATE email_verification_code
                SET status = %s, updated_at = %s
                WHERE purpose_key = %s AND status = %s
                """,
                (STATUS_INVALID, now, purpose_key, STATUS_UNUSED),
            )

            cursor.execute(
                """
                INSERT INTO email_verification_code (
                    scene, account, email, code, purpose_key,
                    status, fail_count, ip_addr, user_agent,
                    expires_at, used_at, created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s
                )
                """,
                (
                    scene,
                    account,
                    email_lower,
                    code,
                    purpose_key,
                    STATUS_UNUSED,
                    0,
                    None,
                    None,
                    expires_at,
                    None,
                    now,
                    now,
                ),
            )
            code_id = int(cursor.lastrowid)
            conn.commit()

        _remember_last_code(account, scene, email_lower, code_id)
    except Exception as exc:
        print(f"_store_code failed: {exc}")
        traceback.print_exc()

def _verify_code(scene: str, account: str, email: str, code: str) -> bool:
    scene = str(scene or "").strip()
    account = str(account or "").strip()
    email_lower = str(email or "").strip().lower()
    input_code = str(code or "").strip()
    if not scene or not account or not email_lower or not input_code:
        return False

    now = datetime.utcnow()
    purpose_key = _purpose_key(scene, account, email_lower)

    try:
        with closing(_get_conn()) as conn, conn.cursor() as cursor:
            # 清理已过期未使用验证码
            cursor.execute(
                """
                UPDATE email_verification_code
                SET status = %s, updated_at = %s
                WHERE purpose_key = %s
                  AND status = %s
                  AND expires_at <= %s
                """,
                (STATUS_EXPIRED, now, purpose_key, STATUS_UNUSED, now),
            )

            cursor.execute(
                """
                SELECT id, code, expires_at, fail_count
                FROM email_verification_code
                WHERE purpose_key = %s
                  AND status = %s
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (purpose_key, STATUS_UNUSED),
            )
            row = cursor.fetchone()
            if not row:
                conn.commit()
                return False

            code_id, saved_code, expires_at, fail_count = row
            fail_count = int(fail_count or 0)

            if now >= expires_at:
                cursor.execute(
                    """
                    UPDATE email_verification_code
                    SET status = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (STATUS_EXPIRED, now, code_id),
                )
                conn.commit()
                return False

            if saved_code != input_code:
                new_fail_count = fail_count + 1
                if new_fail_count >= MAX_VERIFY_FAILS:
                    cursor.execute(
                        """
                        UPDATE email_verification_code
                        SET fail_count = %s, status = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (new_fail_count, STATUS_INVALID, now, code_id),
                    )
                else:
                    cursor.execute(
                        """
                        UPDATE email_verification_code
                        SET fail_count = %s, updated_at = %s
                        WHERE id = %s
                        """,
                        (new_fail_count, now, code_id),
                    )
                conn.commit()
                return False

            cursor.execute(
                """
                UPDATE email_verification_code
                SET status = %s, used_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (STATUS_USED, now, now, code_id),
            )
            conn.commit()
            return True
    except Exception as exc:
        print(f"_verify_code failed: {exc}")
        traceback.print_exc()
        return False

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
