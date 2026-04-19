import pymysql
from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify, send_from_directory
import os
from werkzeug.security import generate_password_hash, check_password_hash
import time
from functools import wraps
import uuid
from pymongo import MongoClient
import re
import random
from datetime import datetime, timedelta, timezone
from dateutil import parser
from urllib.parse import quote
import requests
import asyncio
from threading import Thread
from mcp_client import MCPClient
from flask_cors import CORS
from concurrent.futures import TimeoutError
from concurrent.futures import ThreadPoolExecutor
import traceback
import threading 
import subprocess
from contextlib import closing
from utils.canvas_utils import get_courses_by_teacher_id,get_courses_by_student_id,get_course_assignments,get_assignment_submissions,get_assignment_submission_summary,get_gradeable_students,get_course_enrollments,get_course_quizzes,get_course_modules,get_module_items,get_quiz_submissions,get_student_assignment_submission,get_student_quiz_submissions
from utils.email_verify import (
    send_email_via_CQU,
    _can_send,
    _bump_counters,
    _store_code,
    _verify_code,
    VERIFICATION_TTL_MINUTES,
)
from database_mongo import db, user_sessions_collection
from config import EMAIL_URL,MAIL_AUTH_KEY,APP_PORT,MYSQL_URL,MONGO_URL
from app_kg import app_kg
from app_comp import app_comp
from study_situation_LLM import study_situation_LLM
from study_situation_canvas import study_situation_canvas
import sys

EXTERNAL_URL="https://mingyueai.cqu.edu.cn"
INTERNAL_URL="http://180.85.206.21:5000"

app = Flask(__name__)
app.secret_key = 'your-secret-key-replace-in-production'
CORS_WHITELIST = [
    EXTERNAL_URL,
    INTERNAL_URL
]
CORS(app,
     resources={r"/*": {"origins": CORS_WHITELIST}},
     vary_header=True)
app.register_blueprint(app_kg)
app.register_blueprint(app_comp)
app.register_blueprint(study_situation_LLM)
app.register_blueprint(study_situation_canvas)

# ================== Flask 路由 ==================
@app.route('/dashboard/chat', methods=['POST'])
def chat():
    user_input = request.json.get("message")
    username = session.get('username')  # 获取当前用户
    print("Mcp username:",username)
    # 创建新事件循环（与主线程隔离）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # 同步阻塞执行异步代码
        response = loop.run_until_complete(
            mcp_client.process_query(user_input,username)
        )
        return jsonify({"response": response})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"response": f"Error: {str(e)}"}), 500
    finally:
        loop.close()  

# 内存中存储用户数据
users = {
    "admin@example.com": {
        "username": "admin",
        "password": generate_password_hash("password"),
        "favorites": []
    }
}

# 超级教师聊天页面
new_chat_url="https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=tDnGXv2xcnOmpGX2mvsuTPcp" # 默认
agent1="https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=ztwmryjyyn7a6zt6rtyl5pcg" # 不用

DEFAULT_EMBED_URL = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=cc1greng47slrl6ivb6ik03p"

qea_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=zci1ditlgimgguu13dz5ra5n&studentUid="
poac_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=my14ciwq8qa7moats2q4p28v&studentUid="
pp_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=k53UaEbEHTWKQRLHzIjV5jFT&studentUid="
syat_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=eajvaYCSBHZSXVN1q24sbYNR&studentUid="
vsdf_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=kbcdnjU7cfTVFjGjTAkKz223&studentUid="
aosaa_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=iZBNYVKb0zVZnnTZbq6gNnt6&studentUid="
mraad_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=i8Oeda9zIrXfVUfqZXQ1qKuv&studentUid="
la_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=fhw37s0q4ksu2mdt46yye54r&studentUid="
rm_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=cFXQK1BlZq1zNkWSuGsxbu8J&studentUid="
ptams_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=vqjCwyKQLzmNbxiJbNT8o3mi&studentUid="
hohc_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=ed78T6IEQ5hanDkXVovkQtjZ&studentUid="
hotd_agent_class_url = "https://mingyueai.cqu.edu.cn:8080/chat/share?shareId=zAwoWpdEmuQgdDG1kFJOnlq7&studentUid="

test_chat_url="http://180.85.206.21:3000/chat/share?shareId=akmo1p609wd6bbdaux0rj1rs&studentUid="

# 智能体数据
agents = [
    { 
        "id": 1,
        "name": "定量工程设计方法",
        "description": "学习定量工程设计方法，掌握机器人控制、优化决策与自主导航等核心技能。",
        "url": qea_agent_class_url,
        # "url": test_chat_url,
        "image_url": "/static/img/qea.jpg"
    },
    { 
        "id": 2,
        "name": "自动控制原理",
        "description": "深入学习控制理论的核心知识，掌握控制系统分析与设计的关键技能。",
        "url": poac_agent_class_url,
        "image_url": "/static/img/poac.jpg"
    },
    {
        "id": 3,
        "name": "程序设计实践",
        "description": "掌握C++工程化开发，培养高效编程与系统设计能力。",
        "url": pp_agent_class_url,
        "image_url": "/static/img/pp.jpg"
    },
    { 
        "id": 4,
        "name": "软件系统构架技术",
        "description": "掌握全栈软件设计，构建高可用、可扩展的工业级应用。",
        "url": syat_agent_class_url,
        "image_url": "/static/img/syat.jpg"
    },
    # { 
    #     "id": 5,
    #     "name": "车辆软件开发基础",
    #     "description": "掌握车载软件开发全流程，打造符合车规级标准的可靠系统。",
    #     "url": vsdf_agent_class_url,
    #     "image_url": "/static/img/vsdf.jpg"
    # },
    # {
    #     "id": 6,
    #     "name": "汽车操作系统及应用",
    #     "description": "深入学习控制理论的核心知识，掌握控制系统分析与设计的关键技能。",
    #     "url": aosaa_agent_class_url,
    #     "image_url": "/static/img/aosaa.jpg"
    # },
    { 
        "id": 5,
        "name": "移动机器人应用与开发",
        "description": "学习运用工程原理解决工程设计中的实际问题，掌握科学决策的核心技能。",
        "url": mraad_agent_class_url,
        "image_url": "/static/img/mraad.jpg"
    },
    { 
        "id": 6,
        "name": "线性代数",
        "description": "掌握线性代数的核心理论与方法，学会用矩阵和线性变换解决实际问题。",
        "url": la_agent_class_url,
        "image_url": "/static/img/la.jpg"
    },
    { 
        "id": 7,
        "name": "机器人基础",
        "description": "掌握机器人数学核心理论，实现算法设计与工程落地的全链路应用。",
        "url": rm_agent_class_url,
        "image_url": "/static/img/rm.jpg"
    },
    { 
        "id": 8,
        "name": "概率论与数理统计",
        "description": "掌握概率统计核心方法，培养数据驱动的工程决策能力。",
        "url": ptams_agent_class_url,
        "image_url": "/static/img/ptams.jpg"
    },
    { 
        "id": 9,
        "name": "人类文明史",
        "description": "掌握人类文明演进规律，培养历史洞察与系统设计的跨学科思维。",
        "url": hohc_agent_class_url,
        "image_url": "/static/img/hohc.jpg"
    },
    {
        "id": 10,
        "name": "科技发展史",
        "description": "理解科技发展脉络，培养历史洞察与未来设计的系统性思维。",
        "url": hotd_agent_class_url,
        "image_url": "/static/img/hotd.jpg"
    }
]


# 定义课程白名单
COURSES_LIST = [
    "定量工程设计方法", "自动控制原理", "程序设计实践", 
    "软件系统构架技术", "移动机器人应用与开发", "线性代数",
    "机器人基础", "概率论与数理统计", "人类文明史", "科技发展史"
]

# 允许的学期ID列表
ALLOWED_TERM_IDS = [3, 5, 11, 12]

# 定义KG服务相关的常量
KG_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'KG')

# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            flash('请先登录')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


# 创建必要的目录
os.makedirs('static/img', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('templates/auth', exist_ok=True)
os.makedirs('templates/dashboard', exist_ok=True)


# 创建示例图片文件
def create_sample_images():
    # 创建一些简单的空图片文件作为占位符
    placeholder_images = [
        'static/img/deepseek.png',
        'static/img/coding.png',
        'static/img/math.png',
        'static/img/academic.png'
    ]

    for img_path in placeholder_images:
        if not os.path.exists(img_path):
            with open(img_path, 'w') as f:
                f.write('placeholder')

def process_user_courses(username, role):
    """
    处理用户课程：获取课程、应用白名单和学期筛选、设置当前课程
    将用户信息存储到 MongoDB 的 user_sessions 表中
    返回处理后的用户课程数据和当前课程信息
    """
    # 1. 根据身份获取原始课程列表
    user_courses = []
    if role == 'teacher':
        try:
            user_courses = get_courses_by_teacher_id(username)
        except Exception as e:
            print(f"获取教师课程失败: {e}")
            return None, None, True 
    else:
        try:
            user_courses = get_courses_by_student_id(username)
        except Exception as e:
            print(f"获取学生课程失败: {e}")
            return None, None, True
    
    if not user_courses:
        print(f"用户 {username} 没有找到课程")
        return [], {}, True
    
    # 2. 应用课程白名单筛选
    filtered_courses = []
    for course in user_courses:
        course_name = course.get('name', '')
        if course_name in COURSES_LIST:
            filtered_courses.append(course)
        else:
            print(f"课程 '{course_name}' 不在白名单中，已过滤")
    
    # 3. 应用允许学期筛选
    semester_filtered_courses = []
    for course in filtered_courses:
        term_id = course.get('enrollment_term_id')
        if term_id in ALLOWED_TERM_IDS:
            semester_filtered_courses.append(course)
        else:
            print(f"课程 '{course.get('name', '')}' 的学期ID {term_id} 不在允许列表中，已过滤")
    
    # 统计过滤情况
    original_count = len(user_courses)
    whitelist_count = len(filtered_courses)
    final_count = len(semester_filtered_courses)
    
    print(f"用户 {username} 课程筛选结果: 原始 {original_count} 门 -> 白名单筛选后 {whitelist_count} 门 -> 学期筛选后 {final_count} 门")
    
    # 4. 设置当前课程（使用筛选后的第一个课程）
    current_course = {}
    if semester_filtered_courses:
        first_course = semester_filtered_courses[0]
        current_course = {
            'course_id': first_course.get('course_id'),
            'name': first_course.get('name', '未命名课程'),
            'sis_course_id': first_course.get('sis_course_id', ''),
            'enrollment_term_id': first_course.get('enrollment_term_id', ''),
            'workflow_state': first_course.get('workflow_state', '')
        }
        print(f"设置当前课程: {current_course.get('name')} (ID: {current_course.get('course_id')})")
    else:
        print(f"警告: 用户 {username} 经过筛选后没有可用课程")
    
    # 5. 将用户信息存储到 MongoDB
    now = datetime.now()
    user_session_data = {
        'username': username,
        'role': role,
        'user_courses': semester_filtered_courses,
        'current_course': current_course,
    }
    print("user_session_data!!!",user_session_data)
    # 存储到 MongoDB（如果集合可用）
    if user_sessions_collection is not None:
        try:
            # 使用 upsert 操作：如果用户已存在则更新，否则插入
            result = user_sessions_collection.update_one(
                {'username': username},
                {
                    '$set': {
                        'role': role,
                        'user_courses': semester_filtered_courses,
                        'current_course': current_course,
                    },
                },
                upsert=True  # 不存在则插入
            )
            
            if result.upserted_id:
                print(f"✅ 用户 {username} 信息已插入到 MongoDB")
            else:
                print(f"✅ 用户 {username} 信息已更新到 MongoDB")
                
        except errors.DuplicateKeyError:
            print(f"⚠️ 用户 {username} 已存在，更新信息")
            # 更新已存在用户的信息
            user_sessions_collection.update_one(
                {'username': username},
                {'$set': user_session_data}
            )
        except Exception as e:
            print(f"❌ 存储用户信息到 MongoDB 失败: {e}")
    else:
        print(f"⚠️ MongoDB 不可用，用户 {username} 信息未持久化存储")

    print(f"用户 {username} 信息处理完成")
    return semester_filtered_courses, current_course, True


# 路由
@app.route('/')
def index():
    if 'user_email' in session:
        return redirect(url_for('new_chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        sql = "SELECT `password`, `role` FROM `student` WHERE `sid` = %s"
        
        # 每次请求都新建连接/游标；避免复用全局对象
        with closing(get_conn()) as conn, conn.cursor() as cursor:
            # 参数化查询，防注入；sid 若是字符串，照样安全
            cursor.execute(sql, (username,))
            result = cursor.fetchone()
            if result and result[0] == password:
                session['username'] = username
                session['role'] = result[1] or 'student'
                session['user_courses'] = []
                # 调用统一函数处理用户课程
                user_courses, current_course, success = process_user_courses(session['username'], session['role'])
                if not success:
                    flash('获取课程信息失败，请联系管理员', 'danger')
                    return render_template('auth/login.html')
                session['user_courses'] = user_courses
                session['current_course'] = current_course
                flash('登录成功', 'success')
                return redirect(url_for('new_chat'))
            else:
                print("error")
                flash('用户名或密码错误，请重试！', 'danger')
    return render_template('auth/login.html')

@app.route('/auth/send_code', methods=['POST'])
def send_verification_code():
    data = request.form if request.form else request.json or {}
    email = data.get('email')
    account = data.get('username') or data.get('sid') or ''
    scene = data.get('scene') or 'register'
    ip_addr = request.remote_addr or 'unknown'

    if not email or not account:
        return jsonify({'error': '缺少邮箱或账号'}), 400
    if scene not in ('register', 'reset'):
        return jsonify({'error': 'scene 参数无效'}), 400
    if not _can_send(ip_addr, account):
        return jsonify({'error': '今日发送次数已达上限'}), 429

    email_lower = str(email).lower()
    role = 'teacher' if email_lower.endswith('@cqu.edu.cn') else 'student' if email_lower.endswith('@stu.cqu.edu.cn') else 'student'

    code = f"{random.randint(0, 999999):06d}"
    subject = "明月科创教育大模型｜验证码"
    html_body = render_template(
        "email/verification_code.html",
        account=account,
        role=role,
        code=code,
        ttl=VERIFICATION_TTL_MINUTES,
        scene=scene
    )

    ok = send_email_via_CQU(
        to_addrs=email,
        subject=subject,
        body=html_body,
        from_addr=EMAIL_URL,
        auth_code=MAIL_AUTH_KEY,
        is_html=True
    )
    if not ok:
        return jsonify({'error': '邮件发送失败'}), 500

    _store_code(scene, account, email, code)
    _bump_counters(ip_addr, account)
    return jsonify({'success': True, 'message': '验证码已发送'})

# 新的注册逻辑，学号不在数据库中依然能够注册
@app.route('/register', methods=['GET', 'POST'])
def register():
    global user_global_store
    form_data = request.form if request.method == 'POST' else None
    if request.method == 'POST':
        username = request.form.get('username')  # 学号 sid
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        verification_code = request.form.get('verification_code')

        if role not in ('student', 'teacher'):
            flash('身份信息错误')
            return render_template('auth/register.html', form_data=form_data)
        if not verification_code:
            flash('请填写邮箱验证码')
            return render_template('auth/register.html', form_data=form_data)
        
        with closing(get_conn()) as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT sid, email FROM student WHERE sid = %s OR email = %s",
                (username, email)
            )
            rows = cursor.fetchall()
            dup_username = any(str(row[0]) == str(username) for row in rows if row[0] is not None)
            dup_email = any(str(row[1]) == str(email) for row in rows if row[1] is not None)

            if dup_username or dup_email:
                if dup_username and dup_email:
                    flash('账号和邮箱已被注册')
                elif dup_username:
                    flash('账号已被注册')
                else:
                    flash('邮箱已被注册')
                return render_template('auth/register.html', form_data=form_data)

            if not _verify_code("register", username, email, verification_code):
                flash('验证码错误或已过期')
                return render_template('auth/register.html', form_data=form_data)

            cursor.execute(
                "INSERT INTO student (sid, email, password, role) VALUES (%s, %s, %s, %s)",
                (username, email, password, role)
            )
            conn.commit()
            flash('注册成功，正在登录', 'success')
            session['username'] = username
            session['role'] = role
            
            session['user_courses'] = []
            # 调用统一函数处理用户课程和全局变量
            user_courses, current_course, success = process_user_courses(session['username'], session['role'])
            if not success:
                flash('获取课程信息失败，请联系管理员', 'danger')
                return render_template('auth/login.html')
            session['user_courses'] = user_courses
            session['current_course'] = current_course
            return redirect(url_for('new_chat'))

    return render_template('auth/register.html', form_data=form_data)

@app.route('/change_password')
def change_password():
    if request.method == 'POST':
        p1 = request.form.get('p1')
        p2 = request.form.get('p2')
        if p1 == p2:
            with closing(get_conn()) as conn, conn.cursor() as cursor:
                cursor.execute("UPDATE student SET password = %s WHERE sid = %s", (p1, session["username"]))            
        else:
            flash('两次输入的密码不相同，请重新修改')
    return redirect(url_for('new_chat'))

@app.route('/forget_password', methods=['GET', 'POST'])
def forget_password():
    if request.method == 'POST':
        sid = request.form.get('username')
        email = request.form.get('email')
        verification_code = request.form.get('verification_code')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        if not verification_code:
            flash('请填写邮箱验证码')
            return redirect(url_for('forget_password'))
        if not new_password or not confirm_password:
            flash('请填写新密码并确认')
            return redirect(url_for('forget_password'))
        if new_password != confirm_password:
            flash('两次输入的密码不一致')
            return redirect(url_for('forget_password'))

        # 查询数据库，检查学号和邮箱是否匹配
        # e = "\"" + email + "\""
        with closing(get_conn()) as conn, conn.cursor() as cursor:
            cursor.execute("SELECT password FROM student WHERE sid = %s AND email = %s", (sid, email))
            user = cursor.fetchone()

            if not user:  # 数据库中找不到匹配的记录
                flash('输入学号或邮箱错误')
                return redirect(url_for('forget_password'))
            if not _verify_code("reset", sid, email, verification_code):
                flash('验证码错误或已过期')
                return redirect(url_for('forget_password'))
            cursor.execute("UPDATE student SET password = %s WHERE sid = %s", (new_password, sid))
            conn.commit()
            return redirect(url_for('login'))

    return render_template('auth/forget_password.html')

# 添加辅助函数：用户登出时可选清理
def remove_user_session(username):
    """用户登出时清理会话（可选）"""
    if user_sessions_collection is not None:
        try:
            user_sessions_collection.delete_one({'username': username})
            print(f"用户 {username} 已登出")
        except Exception as e:
            print(f"❌ 处理用户登出失败: {e}")
@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        remove_user_session(username)
        print(f"用户 {username} 登出，已从数据库中删除会话信息")
    
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard/new-chat')
@login_required
def new_chat():
    return render_template('dashboard/new_chat.html', 
                          embed_url=new_chat_url,
                          username=session.get('username', '用户'),
                            role=session.get('role', 'student'))


def _build_new_home_context():
    username = session.get('username', '用户')
    role = session.get('role', 'student')
    current_course = session.get('current_course') or {}
    user_courses = session.get('user_courses') or []

    current_course_name = current_course.get('name')
    showcase_agent = None
    if current_course_name:
        showcase_agent = next((a for a in agents if a.get('name') == current_course_name), None)
    if showcase_agent is None and agents:
        showcase_agent = agents[0]

    owned_course_names = {
        course.get('name')
        for course in user_courses
        if isinstance(course, dict) and course.get('name')
    }

    kg_embed_url = ''
    if showcase_agent is not None:
        kg_mode = 'visitor'
        if role == 'teacher' and showcase_agent.get('name') in owned_course_names:
            kg_mode = 'teacher'
        elif showcase_agent.get('name') in owned_course_names:
            kg_mode = 'student'
        kg_embed_url = url_for('kg_page', course_id=showcase_agent['id'], mode=kg_mode)

    return {
        'username': username,
        'role': role,
        'embed_url': new_chat_url,
        'kg_embed_url': kg_embed_url,
    }


@app.route('/dashboard/new-home')
@login_required
def home():
    return render_template('dashboard/new_home_fullscreen.html', **_build_new_home_context())

@app.route('/dashboard/his')
@login_required
def his():
    username = session.get('username', '用户')
    role = session.get('role', 'student')
    # 获取知识库统计（kb 模块初始化后 _get_kb_stats_for_page 才可用）
    kb_stats = _get_kb_stats_for_page(username)
    user_courses_info = process_user_courses(username, role)[0] or []
    return render_template('dashboard/his.html',
                          username=username,
                          name=username,
                          role=role,
                          courses_info=user_courses_info,
                          kb_stats=kb_stats,
                          page_title='个人知识库')


@app.route('/dashboard/agents') 
@login_required
def course_agents():
    role = session.get('role', 'student')
    username = session.get('username', '用户')
    is_teacher = role == 'teacher'
    try:
        user_courses = session.get('user_courses')  # 可能为 None
        name_set = {i['name'] for i in user_courses} # type: ignore
    except TypeError:
        name_set = set()
    own_agents = [a for a in agents if a.get('name') in name_set]
    other_agents = [a for a in agents if a.get('name') not in name_set]
    return render_template(
        'dashboard/agents.html',
        own_agents=own_agents,
        other_agents=other_agents,
        agents=agents,
        is_teacher=is_teacher,
        username=username,
        role=role
    )


@app.route('/dashboard/agent/<int:agent_id>')
@login_required
def view_agent(agent_id):
    agent = next((a for a in agents if a['id'] == agent_id), None)
    if not agent:
        flash('找不到该智能体')
        return redirect(url_for('course_agents'))
    role = session.get('role', 'student')
    username = session.get('username', '用户')

    try:
        user_courses = session.get('user_courses')
        course_names = list({i['name'] for i in user_courses}) # type: ignore
    except TypeError:
        course_names=[]
    
    is_teacher = role == 'teacher'
    is_own = agent.get('name') in set(course_names)
    
    kg_mode = "visitor"
    if is_teacher and is_own:
        kg_mode="teacher"
    elif is_own:
        kg_mode="student"
    
    base_student_url = agent.get('url') or DEFAULT_EMBED_URL
    embed_url = f"{base_student_url}{username}"
    kg_url = url_for('kg_page', course_id=agent['id'], mode=kg_mode)

    return render_template('dashboard/class_chat.html',
                        embed_url=embed_url,
                        kg_url=kg_url,
                        agent=agent,
                        username=session.get('username', '用户'),
                        role=role)

@app.route('/update_kg', methods=['POST'])
def update_kg():
    """接收请求并触发特定课程知识图谱的更新"""
    try:
        data = request.json
        
        # 解析必要参数
        course_id = data.get('course_id')
        keyword = data.get('query', '')
        display_mode = data.get("display_mode",'current_page')  # 强制使用current_page模式
        print(f"shared_id = {course_id}, keyword = {keyword}, display_mode = {display_mode}")
        if 'qy5v984hcneb036tgf7fwysy' == course_id:
            course_id = 1
        print('course id = {course_id}')
        # 验证参数
        if not course_id:
            return jsonify({'error': '缺少course_id参数'}), 400
        if not keyword:
            return jsonify({'error': '关键词不能为空'}), 400
        # 生成知识图谱数据
        try:
            from KG.kg_json import KnowledgeGraphGenerator
            from KG.kg_json2graph import create_graph, load_json_data
            
            # 创建目录
            KG_STATIC_DIR = os.path.join(KG_FOLDER, 'static')
            KG_OUTPUT_DIR = os.path.join(KG_STATIC_DIR, 'output')
            os.makedirs(KG_STATIC_DIR, exist_ok=True)
            os.makedirs(KG_OUTPUT_DIR, exist_ok=True)
            
            # 创建唯一文件名
            unique_id = str(uuid.uuid4())[:8]
            json_file = os.path.join(KG_OUTPUT_DIR, f'kg_{keyword}_{unique_id}.json')
            
            # 生成知识图谱
            kg_generator = KnowledgeGraphGenerator()
            json_result = kg_generator.generate_knowledge_graph(keyword=keyword, output_file=json_file)
            
            if not json_result:
                return jsonify({'error': '知识图谱生成失败'}), 500
            
            # 加载生成的JSON数据
            temp, nodes, links = load_json_data(json_file)
            
            if not nodes or not links:
                return jsonify({'error': '知识图谱数据为空'}), 500
            
            # 将更新数据存储在服务器上，供客户端轮询获取
            # 我们使用一个简单的内存存储，实际生产环境可以使用Redis等
            update_data = {
                'course_id': course_id,
                'keyword': keyword,
                'nodes': nodes,
                'links': links,
                'timestamp': time.time()
            }
            
            # 如果没有全局字典则创建
            if not hasattr(app, 'kg_updates'):
                app.kg_updates = {}
            
            # 存储更新数据
            app.kg_updates[str(course_id)] = update_data
            
            return jsonify({
                'success': True,
                'message': f'课程{course_id}的知识图谱更新数据已准备好',
                'update_id': unique_id
            })
            
        except Exception as e:
            import traceback
            print(f"知识图谱生成失败: {str(e)}")
            print(traceback.format_exc())
            return jsonify({'error': f'知识图谱生成失败: {str(e)}'}), 500
            
    except Exception as e:
        print(f"处理请求时出错: {str(e)}")
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500
    
@app.route('/check_kg_update/<int:course_id>', methods=['GET'])
def check_kg_update(course_id):
    """检查特定课程的知识图谱是否有更新"""
    # 获取客户端最后检查时间
    last_check = float(request.args.get('last_check', 0))
    
    # 如果没有全局字典则创建
    if not hasattr(app, 'kg_updates'):
        app.kg_updates = {}
    
    # 检查是否有更新
    course_key = str(course_id)
    if course_key in app.kg_updates:
        update = app.kg_updates[course_key]
        if update['timestamp'] > last_check:
            # 返回更新数据
            return jsonify({
                'has_update': True,
                'data': {
                    'keyword': update['keyword'],
                    'nodes': update['nodes'],
                    'links': update['links']
                },
                'timestamp': update['timestamp']
            })
    
    # 没有更新
    return jsonify({
        'has_update': False,
        'timestamp': time.time()
    })

@app.route('/api/toggle-favorite/<int:agent_id>', methods=['POST'])
@login_required
def toggle_favorite(agent_id):
    user_email = session.get('user_email')
    if not user_email or user_email not in users:
        return {'error': 'User not found'}, 404

    user_favorites = users[user_email]['favorites']

    if agent_id in user_favorites:
        user_favorites.remove(agent_id)
        return {'status': 'removed'}
    else:
        user_favorites.append(agent_id)
        return {'status': 'added'}


@app.route("/get_session")
def get_session():
    # temp={"username":session.get("username", "1111")}
    return jsonify(dict(session))


# 知识图谱相关路由
@app.route('/kg_page')
def kg_index():
    """显示知识图谱主页"""
    return send_from_directory(KG_FOLDER, 'nn_output_enhanced.html')

## 课程广场知识图谱路由
@app.route('/classkg/<int:course_id>')
@login_required  # 确保用户已登录，以便获取学号
def kg_page(course_id):
    """
    根据课程编号跳转到教师/学生/游客端知识图谱页面。
    优先按 override_mode (teacher/student/visitor)，否则按课程归属判定，无法匹配则访客。
    """
    role = session.get('role', 'student')
    user_id = session.get('username', 'guest')
    override_mode = request.args.get('mode')

    # TODO:似乎复杂度o(n)了，但是目前还能跑
    course_agent = next((agent for agent in agents if agent['id'] == course_id), None)
    course_name = course_agent['name'] if course_agent else f"未知课程 (ID: {course_id})"

    # 取课程名称集合，判定是否属教师/学生本人
    user_courses = session.get('user_courses') or []
    user_course_names = {c.get('name') for c in user_courses if isinstance(c, dict)}

    allowed_modes = {'teacher', 'student', 'visitor'}
    if override_mode in allowed_modes:
        selected = override_mode
    elif role == 'teacher' and course_name in user_course_names:
        selected = 'teacher'
    elif role == 'student' and course_name in user_course_names:
        selected = 'student'
    else:
        selected = 'visitor'

    if selected == 'teacher':
        target_url = url_for('app_kg.teacher_view', course_name=course_name, student_id=user_id)
    elif selected == 'student':
        target_url = url_for('app_kg.student_view', course_name=course_name, student_id=user_id)
    else:
        target_url = url_for('app_kg.visitor_view', course_name=course_name, visitor_id=user_id)

    # print(f"[KG 跳转] course_id={course_id}, course_name={course_name}, role={role}, selected_mode={selected}, target={target_url}")
    return redirect(target_url)

@app.route('/js/<path:filename>')
def kg_js(filename):
    """提供JavaScript文件服务"""
    return send_from_directory(KG_FOLDER, filename)
    
@app.route('/generate_kg', methods=['POST'])
def proxy_generate_kg():
    """处理生成知识图谱的请求"""
    try:
        # 从请求中获取数据
        data = request.json
        
        # 直接导入KG服务中的相关模块
        try:
            from KG.kg_json import KnowledgeGraphGenerator
            from KG.kg_json2graph import create_graph, load_json_data
            
            keyword = data.get('keyword')
            display_mode = data.get('display_mode', 'new_page')
            
            print(f"收到生成知识图谱请求：关键词 = {keyword}, 显示模式 = {display_mode}")
            
            if not keyword:
                print("错误：关键词为空")
                return jsonify({'error': '关键词不能为空'}), 400
            
            # 创建目录
            KG_STATIC_DIR = os.path.join(KG_FOLDER, 'static')
            KG_OUTPUT_DIR = os.path.join(KG_STATIC_DIR, 'output')
            os.makedirs(KG_STATIC_DIR, exist_ok=True)
            os.makedirs(KG_OUTPUT_DIR, exist_ok=True)
            
            # 创建唯一文件名
            unique_id = str(uuid.uuid4())[:8]
            json_file = os.path.join(KG_OUTPUT_DIR, f'kg_{keyword}_{unique_id}.json')
            html_file = os.path.join(KG_OUTPUT_DIR, f'kg_{keyword}_{unique_id}.html')
            
            print(f"将生成JSON文件：{json_file}")
            print(f"将生成HTML文件：{html_file}")
            
            # 生成知识图谱
            kg_generator = KnowledgeGraphGenerator()
            json_result = kg_generator.generate_knowledge_graph(keyword=keyword, output_file=json_file)
            
            if not json_result:
                print("知识图谱生成失败：无返回结果")
                return jsonify({'error': '知识图谱生成失败'}), 500
            
            # 加载生成的JSON数据
            
            temp, nodes, links = load_json_data(json_file)
            
            if not nodes or not links:
                print(f"知识图谱数据为空：nodes={nodes}, links={links}")
                return jsonify({'error': '知识图谱数据为空'}), 500
            
            # 创建图表
            c = create_graph(nodes, links)
            
            # 渲染HTML文件
            c.render(html_file)
            
            result = {
                'success': True,
                'keyword': keyword,
                'json_path': f'/KG/static/output/{os.path.basename(json_file)}',
                'html_path': f'/KG/static/output/{os.path.basename(html_file)}',
                'nodes': nodes,
                'links': links,
                'display_mode': display_mode
            }
            
            print(f"知识图谱生成成功：{result}")
            return jsonify(result)
            
        except Exception as e:
            import traceback
            print(f"处理请求时出错: {str(e)}")
            print(traceback.format_exc())
            return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500
            
    except Exception as e:
        print(f"处理请求时出错: {str(e)}")
        return jsonify({'error': f'处理请求时出错: {str(e)}'}), 500

@app.route('/KG/static/output/<path:filename>')
def kg_output_files(filename):
    """提供KG生成的输出文件"""
    output_dir = os.path.join(KG_FOLDER, 'static', 'output')
    return send_from_directory(output_dir, filename)


#####################################################################################################

@app.route('/dashboard/chat')
@login_required
def study_situation():
    role = session.get('role')
    if role == 'teacher':
        return render_template('dashboard/teacher_learning_analysis.html',embed_url=chat,
                              username=session.get('username', '用户'))
    else:
        return render_template('dashboard/student_learning_analysis.html',embed_url=chat,
                              username=session.get('username', '用户'))
    

#获取某课程下“既未完成也未学习”的学生名单->基础功能    + （站内提醒功能 + 学生提问/答疑功能）->这两个涉及后端数据库，现在需要做吗
# @app.route('/dashboard/study_situation/course/<int:course_id>/at_risk_students')
# def get_at_risk_students(course_id):
#     course = db.courses.find_one({"course_id": course_id}, {"_id": 0})
#     if not course:
#         return jsonify({"error": "课程不存在"}), 404

#     total_knowledges = db.knowledges.count_documents({"course_id": course_id})
#     student_list = course.get("student_list", [])
#     now = datetime.now(timezone.utc)
#     week_ago = now - timedelta(days=7)

#     result = []

#     for student in student_list:
#         student_id = student["student_id"]
#         student_name = student.get("student_name", "未知")

#         student_data = db.students.find_one({
#             "student_id": student_id,
#             "course_list.course_id": course_id
#         }, {"_id": 0})

#         if not student_data:
#             continue

#         course_data = next((c for c in student_data["course_list"] if c["course_id"] == course_id), None)
#         if not course_data:
#             continue

#         knowledge_list = course_data.get("knowledge_list", [])
#         completed_count = sum(1 for k in knowledge_list if k.get("state") == "Learned")
#         completion_rate = completed_count / total_knowledges if total_knowledges else 0

#         # 活跃度（7天内是否访问过知识点）
#         recent_accesses = db.knowledges.find_one({
#             "course_id": course_id,
#             "access_records": {
#                 "$elemMatch": {
#                     "student_id": student_id,
#                     "access_time.$date": {"$gt": week_ago.isoformat()}
#                 }
#             }
#         })

#         if completion_rate < 0.5 and not recent_accesses:
#             result.append({
#                 "student_id": student_id,
#                 "student_name": student_name,
#                 "completion_rate": round(completion_rate * 100, 2)
#             })

#     return jsonify({
#         "course_id": course_id,
#         "at_risk_students": result
#     })

# async def initialize_mcp_client():
#     global mcp_client
#     mcp_client = MCPClient()
#     server_script_path = "mcp_server.py"
#     print("✅ MCP Client 开始连接 MCP Server")
#     await mcp_client.connect_to_server(server_script_path)  #连接有问题
#     print("✅ MCP Client 已连接到 MCP Server")
def start_mcp_server():
    """Run mcp_server.py in a subprocess (blocking call)"""
    global mcp_server_process
    try:
        print("🚀 Starting MCP server...")
        mcp_server_process = subprocess.Popen(
            [sys.executable, "mcp_server.py"],
            stdout=None,  
            stderr=None
        )
        time.sleep(3)
        print("✅ MCP server is running.")
    except Exception as e:
        print("❌ Failed to start MCP server:", e)
        traceback.print_exc()
def shutdown_mcp(signum, frame):
    global mcp_server_process
    if mcp_server_process:
        print("\n🛑 Shutting down MCP server...")
        mcp_server_process.terminate()
        mcp_server_process.wait(timeout=5)
    exit(0)
####################################################################################################


## 管理mysql连接
def get_conn():
    return pymysql.connect(
        host=MYSQL_URL,
        user="root",
        password="123456",
        database="zgllm",
        charset="utf8mb4"
    )

# 应用启动前初始化
create_sample_images()
# client = MongoClient(
#         host=MONGO_URL,
#         port=27027,
#         username='root',
#         password='123456',
#         authSource='admin'
#     )
# db = client["education2"]
# user_sessions_collection = db["user_sessions"]
# user_sessions_collection.create_index("username", unique=True)
mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
mcp_thread.start()
# 预加载KG模块，确保可以正常导入
try:
    from KG.kg_json import KnowledgeGraphGenerator
    from KG.kg_json2graph import create_graph, load_json_data
    print("KG模块加载成功")
except Exception as e:
    print(f"KG模块加载失败: {str(e)}")


# ╔════════════════════════════════════════════════════════════════════════╗
# ║  📚 个人知识库 (KB) 模块                                              ║
# ║  所有 KB 相关代码集中在此，方便统一维护                                  ║
# ║  包含：环境变量、服务初始化、辅助函数、蓝图注册                           ║
# ║  依赖：services/fastgpt_kb_service.py, routes/kb_routes.py            ║
# ║  注意：上方 /dashboard/his 路由调用了本区块中的 _get_kb_stats_for_page  ║
# ╚════════════════════════════════════════════════════════════════════════╝

# ---- 1. KB 环境变量 ----
os.environ.setdefault('FASTGPT_API_URL',        'http://180.85.206.30:3000/api')
os.environ.setdefault('FASTGPT_API_KEY',         'fastgpt-suPpeQxXcXBuqdoxW4Y3HiPVS9ecccfeL958V64aJYK0Y4tQmApxuCQtCDxXV')
os.environ.setdefault('FASTGPT_APP_KEY',         'fastgpt-suPpeQxXcXBuqdoxW4Y3HiPVS9ecccfeL958V64aJYK0Y4tQmApxuCQtCDxXV')
os.environ.setdefault('FASTGPT_SHARE_ID',        'zDrmPPnh9rdi3WmnyWCFwDcb')
os.environ.setdefault('FASTGPT_SHARE_BASE_URL',  'http://180.85.206.30:3000')

# ---- 2. KB 服务初始化 ----
fastgpt_kb_service = None
try:
    from services.fastgpt_kb_service import FastGPTKBService
    fastgpt_kb_service = FastGPTKBService(
        db=db,
        base_url=os.environ.get('FASTGPT_API_URL'),
        api_key=os.environ.get('FASTGPT_API_KEY')
    )
    print("✅ FastGPT 知识库服务初始化成功")
except Exception as e:
    print(f"⚠️ FastGPT 知识库服务初始化失败（KB 功能不可用）: {e}")
    traceback.print_exc()

# ---- 3. KB 辅助函数（供上方 his() 路由调用） ----
def _get_kb_stats_for_page(username):
    """获取用户知识库统计信息，供 /dashboard/his 页面渲染使用"""
    _default = {
        'documents': 0, 'ready_documents': 0,
        'chunks': 0, 'queries': 0, 'rag_enabled': False
    }
    if not fastgpt_kb_service:
        return _default
    try:
        if hasattr(fastgpt_kb_service, 'get_user_stats'):
            return fastgpt_kb_service.get_user_stats(username)
        if hasattr(fastgpt_kb_service, 'get_kb_stats'):
            stats = fastgpt_kb_service.get_kb_stats(username)
            return {
                'documents': stats.get('total_documents', 0),
                'ready_documents': stats.get('ready_documents', 0),
                'chunks': stats.get('total_chunks', 0),
                'queries': stats.get('queries', 0),
                'rag_enabled': stats.get('ready_documents', 0) > 0
            }
    except Exception as e:
        print(f"⚠️ 获取 KB 统计失败: {e}")
    return _default

# ---- 4. KB 蓝图注册（只注册 /api/kb/* 的 API 路由） ----
try:
    from routes.kb_routes import kb_bp, init_kb_blueprint
    init_kb_blueprint(
        app=app,
        db=db,
        fastgpt_kb_service=fastgpt_kb_service,
        login_required_func=login_required,
        process_user_courses_func=process_user_courses
    )
    app.register_blueprint(kb_bp)
    print("✅ 知识库路由蓝图注册成功（/api/kb/*）")
except Exception as e:
    print(f"⚠️ 知识库路由注册失败: {e}")
    traceback.print_exc()

# ╔════════════════════════════════════════════════════════════════════════╗
# ║  📚 个人知识库 (KB) 模块结束                                          ║
# ╚════════════════════════════════════════════════════════════════════════╝



if __name__ == '__main__': 
    app.run(debug=False, use_reloader=True, host='0.0.0.0', port=APP_PORT) 
