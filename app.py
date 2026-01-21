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
from utils.canvas_utils import get_courses_by_teacher_id,get_courses_by_student_id
from utils.email_verify import (
    send_email_via_CQU,
    _can_send,
    _bump_counters,
    _store_code,
    _verify_code,
    VERIFICATION_TTL_MINUTES,
)
from config import EMAIL_URL,MAIL_AUTH_KEY,APP_PORT,MYSQL_URL,MONGO_URL
from app_kg import app_kg

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
new_chat_url="http://180.85.206.30:3000/chat/share?shareId=tDnGXv2xcnOmpGX2mvsuTPcp" # 默认
agent1="http://180.85.206.30:3000/chat/share?shareId=ztwmryjyyn7a6zt6rtyl5pcg" # 不用

DEFAULT_EMBED_URL = "http://180.85.206.30:3000/chat/share?shareId=cc1greng47slrl6ivb6ik03p"

qea_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=zci1ditlgimgguu13dz5ra5n&studentUid="
poac_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=my14ciwq8qa7moats2q4p28v&studentUid="
pp_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=k53UaEbEHTWKQRLHzIjV5jFT&studentUid="
syat_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=eajvaYCSBHZSXVN1q24sbYNR&studentUid="
vsdf_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=kbcdnjU7cfTVFjGjTAkKz223&studentUid="
aosaa_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=iZBNYVKb0zVZnnTZbq6gNnt6&studentUid="
mraad_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=i8Oeda9zIrXfVUfqZXQ1qKuv&studentUid="
la_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=fhw37s0q4ksu2mdt46yye54r&studentUid="
rm_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=cFXQK1BlZq1zNkWSuGsxbu8J&studentUid="
ptams_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=vqjCwyKQLzmNbxiJbNT8o3mi&studentUid="
hohc_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=ed78T6IEQ5hanDkXVovkQtjZ&studentUid="
hotd_agent_class_url = "http://180.85.206.30:3000/chat/share?shareId=zAwoWpdEmuQgdDG1kFJOnlq7&studentUid="

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


agents_kd = [
    {
        "id": 2,
        "name": "编程助手",
        "description": "专注于帮助解决编程问题的智能体，支持多种编程语言。",
        "url": new_chat_url,
        "image_url": "/static/img/c1.png"
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
    处理用户课程：获取课程、应用白名单和学期筛选、设置当前课程和全局变量
    返回处理后的用户课程数据和当前课程信息
    """
    global user_global_store
    
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
    
    # 5. 更新全局存储
    if username not in user_global_store:
        user_global_store[username] = {}
    
    user_global_store[username].update({
        'user_courses': semester_filtered_courses,
        'current_course': current_course,
        'last_login': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'role': role
    })
    
    print(f"已更新全局存储中的用户 {username} 信息")
    print("存储的用户的信息",user_global_store[username])
    return semester_filtered_courses, current_course, True

# 路由
@app.route('/')
def index():
    if 'user_email' in session:
        return redirect(url_for('new_chat'))
    return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    global user_global_store
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
                # 调用统一函数处理用户课程和全局变量
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


@app.route('/logout')
def logout():
    username = session.get('username')
    if username:
        # 从全局存储中删除该用户的数据
        if username in user_global_store:
            del user_global_store[username]
            print(f"用户 {username} 登出，已从全局存储中删除")
        else:
            print(f"用户 {username} 登出，但全局存储中未找到该用户")
    session.pop('user_email', None)
    session.pop('username', None)
    session.pop('role', None)
    session.pop('user_course', None)
    session.pop('current_course', None)
    return redirect(url_for('login'))


@app.route('/dashboard/new-chat')
@login_required
def new_chat():
    return render_template('dashboard/new_chat.html', 
                          embed_url=new_chat_url,
                          username=session.get('username', '用户'),
                            role=session.get('role', 'student'))

@app.route('/dashboard/kd')
@login_required
def course_kd():
    # 参照course_agents传递完整智能体列表
    return render_template('dashboard/kd.html', 
                         agents=agents_kd,  # 关键修改点：传递列表而非单个URL
                         username=session.get('username', '用户'),
                            role=session.get('role', 'student'))

@app.route('/dashboard/kds/<int:agent_id>')
@login_required
def view_kd(agent_id):
    agent = next((a for a in agents_kd if a['id'] == agent_id), None)
    if not agent:
        flash('找不到该知识库智能体', 'error')
        return redirect(url_for('course_kd'))
    return render_template('dashboard/new_chat.html', 
                         embed_url=agent['url'],
                         agent=agent,
                         username=session.get('username', '用户'))


@app.route('/dashboard/his')
@login_required
def his():
    return render_template('dashboard/his.html', 
                          embed_url=new_chat_url,
                          username=session.get('username', '用户'),
                            role=session.get('role', 'student'))

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
    

#根据课程ID或课程名称查询课程信息，当前课程人数、课程下知识点学习总进度、知识点完成率

import logging
from flask import request, jsonify
import re

# 可选：配置日志格式（如果还没配）
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_global_store = {}
@app.route('/dashboard/study_situation/update_current_course', methods=['POST'])
def update_current_course():
    """更新session和全局存储中当前选中的课程"""
    global user_global_store
    try:
        data = request.json
        course_id = data.get('course_id')
        course_name = data.get('course_name')
        sis_course_id = data.get('sis_course_id', '')
        enrollment_term_id = data.get('enrollment_term_id', '')
        workflow_state = data.get('workflow_state', '')
        
        if not course_id or not course_name:
            return jsonify({"error": "课程ID和课程名称不能为空"}), 400
        
        username = session.get('username')
        if not username:
            return jsonify({"error": "用户未登录"}), 401
        
        # 构建完整的课程信息
        current_course = {
            'course_id': course_id,
            'name': course_name,
            'sis_course_id': sis_course_id,
            'enrollment_term_id': enrollment_term_id,
            'workflow_state': workflow_state
        }
        
        # 1. 更新session中的当前课程
        session['current_course'] = current_course
        print(f"session['current_course']: {session['current_course']}")
        
        # 2. 更新全局存储中的当前课程
        if username in user_global_store:
            user_global_store[username]['current_course'] = current_course
            print(f"全局存储更新用户 {username} 的当前课程: {current_course}")
        else:
            print(f"警告: 用户 {username} 不在全局存储中")
        
        # 3. 验证课程是否属于该用户
        user_courses = session.get('user_courses', [])
        is_valid_course = any(
            str(course.get('course_id')) == str(course_id) 
            for course in user_courses
        )
        
        if not is_valid_course:
            print(f"警告：课程 {course_id} 不在用户课程列表中，但仍然允许选择")
        
        return jsonify({
            "success": True,
            "message": "当前课程已更新",
            "current_course": current_course,
            "updated_in_global_store": username in user_global_store
        })
    except Exception as e:
        print(f"更新当前课程时出错: {str(e)}")
        return jsonify({"error": "更新课程失败"}), 500
    

# @app.route('/dashboard/study_situation/get_current_course')
# def get_current_course():
#     """获取session中当前选中的课程"""
#     current_course = session.get('current_course', {})
    
#     # 如果没有当前课程，使用第一个课程
#     if not current_course:
#         user_course = session.get('user_course', [])
#         if user_course:
#             first_course = user_course[0]
#             current_course = {
#                 'course_id': first_course.get('course_id'),
#                 'course_name': first_course.get('name', '未命名课程')
#             }
    
#     return jsonify({
#         "current_course": current_course,
#         "has_course": bool(current_course)
#     })
    
    
@app.route('/dashboard/study_situation/course/search')
def search_course():
    """查询课程信息 - 获取当前课程的知识点学习统计"""
    # 获取查询参数
    query = request.args.get('query', '').strip()
    studentUid = request.args.get('studentUid', '').strip()
    
    print(f"search_course 接收参数 - query: {query}, studentUid: {studentUid}")
    
    # 1. 根据studentUid从全局字典中查找对应的current_course
    current_course = None
    
    if studentUid and studentUid in user_global_store:
        user_info = user_global_store[studentUid]
        current_course = user_info.get('current_course')
        print(f"从全局字典中找到用户 {studentUid} 的当前课程: {current_course}")
    else:
        print(f"警告: 用户 {studentUid} 不在全局字典中或未提供studentUid")
    
    # 如果没有从全局字典找到当前课程，尝试从session获取
    if not current_course:
        current_course = session.get('current_course')
        print(f"从session获取当前课程: {current_course}")
    
    # 如果仍然没有当前课程，返回错误
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": "请先在学情分析页面选择一门课程"
        }), 400
    
    # 获取当前课程的信息
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', '未命名课程')
    
    # 2. 进行课程匹配检查
    if query:
        # 判断query是否能与当前课程的course_id或course_name匹配
        is_match = False
        
        # 检查是否与course_id匹配（精确匹配）
        if str(current_course_id).strip() == query:
            is_match = True
            print(f"query '{query}' 与当前课程ID '{current_course_id}' 匹配")
        
        # 检查是否与course_name匹配（模糊匹配，包含关系）
        elif query in str(current_course_name).strip():
            is_match = True
            print(f"query '{query}' 在当前课程名称 '{current_course_name}' 中找到匹配")
        
        # 如果query存在但不能匹配，返回权限错误
        if not is_match:
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
    
    # 3. 使用当前课程的course_id查询相关课程信息
    print(f"使用当前课程ID查询: {current_course_id}")
    
    # 4. 从courses表查找课程信息
    course = db.courses.find_one({"courses_list.class_list.id": int(current_course_id)}, {"_id": 0})
    print("course?", course)
    
    if not course:
        # 如果没有在class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": "未找到课程信息",
            "message": f"未找到ID为 {current_course_id} 的课程",
            "current_course": {
                "course_id": current_course_id,
                "course_name": current_course_name
            }
        })
    
    # 5. 从classes表查找班级信息（获取学生名单）
    class_info = db.classes.find_one({"id": int(current_course_id)}, {"_id": 0})
    print("class_info", class_info)
    
    if not class_info:
        return jsonify({
            "error": "未找到班级信息",
            "message": f"未找到ID为 {current_course_id} 的班级信息",
            "current_course": {
                "course_id": current_course_id,
                "course_name": current_course_name
            }
        })
    
    # 获取班级学生名单
    student_list = class_info.get('student_list', [])
    
    # 6. 从course中提取知识点列表
    knowledge_stats = {}
    
    # 如果课程有knowledge_list，使用它
    if 'knowledge_list' in course and course['knowledge_list']:
        for knowledge in course['knowledge_list']:
            knowledge_id = knowledge.get('knowledge_id')
            knowledge_name = knowledge.get('knowledge_name')
            if knowledge_id:
                knowledge_stats[str(knowledge_id)] = {
                    'knowledge_id': knowledge_id,
                    'knowledge_name': knowledge_name,
                    'total_students': len(student_list),
                    'not_learned': 0,
                    'in_progress': 0,
                    'learned': 0,
                    'review_needed': 0,
                    'completion_rate': 0.0,
                    'course_id': current_course_id
                }
    else:
        # 如果课程没有knowledge_list，返回空的知识点列表
        print("警告: 课程没有knowledge_list字段")
    
    # 7. 统计每个知识点的学习状态
    for student in student_list:
        student_id = student.get('id')
        sis_user_id = student.get('sis_user_id')
        
        if not student_id and not sis_user_id:
            continue
        
        # 查找学生信息
        student_query = {}
        if student_id:
            student_query['id'] = student_id
        if sis_user_id:
            student_query['sis_user_id'] = sis_user_id
        
        student_info = db.students.find_one(student_query, {"_id": 0})
        if not student_info:
            continue
        
        # 查找学生选修的当前课程
        enrolled_courses = student_info.get('enrolled_courses', [])
        current_enrolled_course = None
        
        for enrolled_course in enrolled_courses:
            if str(enrolled_course.get('id')).strip() == str(current_course_id).strip():
                current_enrolled_course = enrolled_course
                break
        
        if not current_enrolled_course:
            # 学生没有选修这门课
            for knowledge_id in knowledge_stats.keys():
                knowledge_stats[knowledge_id]['not_learned'] += 1
            continue
        
        # 统计学生在该课程的知识点状态
        student_knowledge_list = current_enrolled_course.get('knowledge_list', [])
        
        # 遍历所有知识点，统计状态
        for knowledge_id, stats in knowledge_stats.items():
            knowledge_found = False
            
            for student_knowledge in student_knowledge_list:
                if str(student_knowledge.get('knowledge_id')).strip() == str(knowledge_id).strip():
                    knowledge_found = True
                    state = student_knowledge.get('state', 'not_learned')
                    
                    if state == 'not_learned':
                        stats['not_learned'] += 1
                    elif state == 'in_progress':
                        stats['in_progress'] += 1
                    elif state == 'learned':
                        stats['learned'] += 1
                    elif state == 'review_needed':
                        stats['review_needed'] += 1
                    else:
                        stats['not_learned'] += 1
                    
                    break
            
            if not knowledge_found:
                # 学生没有这个知识点的记录
                stats['not_learned'] += 1
    
    # 8. 计算完成率
    total_knowledge_completion = 0
    knowledge_list_with_stats = []
    
    for knowledge_id, stats in knowledge_stats.items():
        total_students = stats['total_students']
        if total_students > 0:
            # 完成率 = (已完成人数 + 需复习人数) / 总人数
            completed_and_reviewed = stats['learned'] + stats['review_needed']
            completion_rate = round(completed_and_reviewed / total_students * 100, 2)
            stats['completion_rate'] = completion_rate
        
        knowledge_list_with_stats.append(stats)
        total_knowledge_completion += stats['completion_rate']
    
    # 计算课程整体完成率
    overall_completion_rate = 0
    if knowledge_list_with_stats:
        overall_completion_rate = round(total_knowledge_completion / len(knowledge_list_with_stats), 2)
    
    # 9. 准备返回数据
    course_data = {
        'course_id': current_course_id,
        'course_name': current_course_name,
        'actual_course_name': course.get('course_name', current_course_name),
        'class_code': class_info.get('course_code', ''),
        'class_sis_id': class_info.get('sis_course_id', ''),
        'term_id': class_info.get('enrollment_term_id', ''),
        'total_students': len(student_list),
        'knowledge_count': len(knowledge_list_with_stats),
        'overall_completion_rate': overall_completion_rate,
        'knowledge_stats': knowledge_list_with_stats,
        'query_matched': bool(query),  # 标记是否进行了query匹配
        'original_query': query if query else None
    }
    
    # 如果有学生名单，添加学生分布信息
    if student_list:
        course_data['student_distribution'] = {
            'total': len(student_list),
            'by_knowledge_completion': calculate_student_completion_distribution(knowledge_stats, student_list)
        }
    
    return jsonify({
        "course": course_data,
        "count": 1,
        "current_course_id": current_course_id,
        "current_course_name": current_course_name,
        "message": "查询成功",
        "studentUid": studentUid if studentUid else "未提供"
    })
    
def calculate_student_completion_distribution(knowledge_stats, student_list):
    """计算学生按知识点完成情况的分布"""
    if not student_list or not knowledge_stats:
        return {}
    
    knowledge_count = len(knowledge_stats)
    if knowledge_count == 0:
        return {}
    
    # 初始化分布
    distribution = {
        'all_completed': 0,  # 全部完成
        'most_completed': 0,  # 完成大部分 (>80%)
        'half_completed': 0,  # 完成一半左右 (40%-80%)
        'few_completed': 0,   # 完成很少 (<40%)
        'none_completed': 0   # 没有完成
    }
    
    knowledge_ids = list(knowledge_stats.keys())
    
    # 为每个学生统计完成的知识点数量
    for student in student_list:
        student_id = student.get('id')
        sis_user_id = student.get('sis_user_id')
        
        if not student_id and not sis_user_id:
            continue
        
        # 查找学生信息
        student_query = {}
        if student_id:
            student_query['id'] = student_id
        if sis_user_id:
            student_query['sis_user_id'] = sis_user_id
        
        student_info = db.students.find_one(student_query, {"_id": 0})
        if not student_info:
            distribution['none_completed'] += 1
            continue
        
        # 查找学生选修的当前课程
        enrolled_courses = student_info.get('enrolled_courses', [])
        current_enrolled_course = None
        
        for enrolled_course in enrolled_courses:
            # 需要匹配当前课程ID
            if enrolled_course.get('id') == int(list(knowledge_stats.values())[0]['course_id']):
                current_enrolled_course = enrolled_course
                break
        
        if not current_enrolled_course:
            distribution['none_completed'] += 1
            continue
        
        # 统计学生完成的知识点
        completed_count = 0
        student_knowledge_list = current_enrolled_course.get('knowledge_list', [])
        
        for knowledge_id in knowledge_ids:
            for student_knowledge in student_knowledge_list:
                if str(student_knowledge.get('knowledge_id')) == str(knowledge_id):
                    state = student_knowledge.get('state', 'not_learned')
                    if state in ['learned', 'review_needed']:
                        completed_count += 1
                    break
        
        # 计算完成百分比
        completion_percentage = completed_count / knowledge_count
        
        # 分类
        if completion_percentage == 1.0:
            distribution['all_completed'] += 1
        elif completion_percentage > 0.8:
            distribution['most_completed'] += 1
        elif completion_percentage >= 0.4:
            distribution['half_completed'] += 1
        elif completion_percentage > 0:
            distribution['few_completed'] += 1
        else:
            distribution['none_completed'] += 1
    
    return distribution    


# 查询某门课程所有学生的学习状况
@app.route('/dashboard/study_situation/course/students')
def get_course_student_status():
    """
    查询某门课程所有学生的学习情况，支持：
    - studentUid为必填参数，用于查找当前课程
    - course_query为可选参数，如果未提供则使用当前课程
    - completion_lt / completion_gt 筛选
    - 多个 knowledge_not_learned（ID 或名称，模糊匹配）
    - 返回每个学生的 已完成/未完成 知识点详情（含名称）
    """
    # Step 1: 获取studentUid参数
    studentUid = request.args.get('studentUid', '').strip()
    
    # 1. 根据studentUid从全局字典中查找对应的current_course
    current_course = None
    
    if studentUid and studentUid in user_global_store:
        user_info = user_global_store[studentUid]
        current_course = user_info.get('current_course')
        print(f"从全局字典中找到用户 {studentUid} 的当前课程: {current_course}")
    else:
        print(f"警告: 用户 {studentUid} 不在全局字典中或未提供studentUid")
    
    # 如果没有从全局字典找到当前课程，尝试从session获取
    if not current_course:
        current_course = session.get('current_course')
        print(f"从session获取当前课程: {current_course}")
    
    # 如果仍然没有当前课程，返回错误
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": "请先在学情分析页面选择一门课程"
        }), 400
    
    # 获取当前课程的信息
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', '未命名课程')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({
            "error": "当前课程信息不完整",
            "message": "当前课程缺少course_id字段",
            "current_course": current_course
        }), 400
    
    # Step 3: 获取course_query参数并进行匹配
    course_query = request.args.get('course_query', '').strip()
    
    # 如果提供了course_query，进行模糊匹配
    if course_query:
        is_matched = False
        
        # 检查课程ID是否匹配
        if str(current_course_id) == str(course_query):
            is_matched = True
            print(f"通过课程ID匹配: {course_query}")
        
        # 检查课程名称是否匹配（模糊匹配）
        elif current_course_name and course_query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {course_query} 匹配 {current_course_name}")
        
        # 检查sis_course_id是否匹配
        elif current_sis_course_id and course_query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {course_query} 匹配 {current_sis_course_id}")
        
        # 如果都没有匹配，尝试在数据库中查找是否有该课程
        if not is_matched:
            print(f"未匹配到课程: {course_query}")
            return jsonify({
                "error": f"无权限查询课程 '{course_query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
            # # 在数据库中查找匹配的课程
            # regex_pattern = f".*{re.escape(course_query)}.*"
            
            # matching_courses = list(db.courses.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.class_list.sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "courses_list": 1}
            # ))
            
            # # 检查classes表中是否有匹配的班级
            # matching_classes = list(db.classes.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "course_code": 1, "id": 1}
            # ))
            
            # matched_courses_info = []
            
            # for match_course in matching_courses:
            #     course_name = match_course.get("course_name", "")
            #     for course_item in match_course.get('courses_list', []):
            #         course_code = course_item.get('course_code', "")
            #         for class_item in course_item.get('class_list', []):
            #             matched_courses_info.append({
            #                 "course_name": course_name,
            #                 "course_code": course_code,
            #                 "class_id": class_item.get('id'),
            #                 "sis_course_id": class_item.get('sis_course_id'),
            #                 "type": "班级",
            #                 "reason": f"数据库查询匹配: {course_query}"
            #             })
            
            # for match_class in matching_classes:
            #     matched_courses_info.append({
            #         "course_name": match_class.get("course_name"),
            #         "course_code": match_class.get("course_code"),
            #         "class_id": match_class.get("id"),
            #         "type": "班级",
            #         "reason": f"数据库查询匹配: {course_query}"
            #     })
            
            # return jsonify({
            #     "error": f"您无权限查询课程 '{course_query}' 相关的信息",
            #     "message": "您只能查询您当前选中的课程",
            #     "current_course": {
            #         "course_id": current_course_id,
            #         "course_name": current_course_name,
            #         "sis_course_id": current_sis_course_id,
            #         "studentUid": studentUid
            #     },
            #     "matched_courses_in_db": matched_courses_info if matched_courses_info else [],
            #     "suggestion": f"您可查询的课程是: {current_course_name} (ID: {current_course_id})"
            # }), 403
    
    # Step 4: 使用current_course的course_id查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    print(f"开始查询课程信息 - course_id: {current_course_id}")
    
    # 获取当前课程信息
    course = db.courses.find_one(
        {"courses_list.class_list.id": current_course_id},
        {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}
    )
    
    if not course:
        # 如果没有在courses_list.class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的课程信息",
            "current_course_id": current_course_id
        }), 404
    
    # 提取当前课程的具体信息
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    # 从courses_list中提取具体的课程代码和班级信息
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code:
            break
    
    # Step 5: 获取班级信息
    class_info = db.classes.find_one(
        {"id": current_course_id},
        {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    # 使用classes表中的课程名称（如果存在）
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    
    # 确保course_code正确
    if not course_code:
        course_code = class_info.get("course_code", "")
    
    if not student_list:
        return jsonify({
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "total_knowledge_count": 0,
            "students": [],
            "query_key": course_query if course_query else "当前课程",
            "query_matched": True,
            "studentUid": studentUid,
            "message": "班级中没有学生"
        }), 200

    # Step 6: 获取该课程的所有知识点
    knowledges = list(db.knowledges.find(
        {"course_code": course_code},
        {"_id": 0, "knowledge_id": 1, "knowledge_name": 1}
    ))
    
    knowledge_map = {
        k["knowledge_id"]: {
            "knowledge_name": k.get("knowledge_name", str(k["knowledge_id"])),
            "knowledge_id": k["knowledge_id"]
        }
        for k in knowledges
    }
    
    # 合并课程表中的knowledge_list
    course_knowledge_list = course.get('knowledge_list', [])
    if course_knowledge_list:
        for knowledge in course_knowledge_list:
            knowledge_id = knowledge.get('knowledge_id')
            knowledge_name = knowledge.get('knowledge_name')
            if knowledge_id and knowledge_id not in knowledge_map:
                knowledge_map[knowledge_id] = {
                    'knowledge_name': knowledge_name or str(knowledge_id),
                    'knowledge_id': knowledge_id
                }
    
    total_knowledge = len(knowledge_map)
    if total_knowledge == 0:
        return jsonify({
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "total_knowledge_count": 0,
            "students": [],
            "query_key": course_query if course_query else "当前课程",
            "query_matched": True,
            "studentUid": studentUid,
            "message": "课程中没有知识点"
        }), 200

    # Step 7: 处理筛选参数
    completion_lt = request.args.get('completion_lt', type=float)  # completion < value
    completion_gt = request.args.get('completion_gt', type=float)  # completion > value
    
    not_learned_params = request.args.getlist('knowledge_not_learned')
    not_learned_params = [param.strip() for param in not_learned_params if param.strip()]
    
    target_knowledge_ids = set()
    if not_learned_params:
        knowledge_queries = []
        for param in not_learned_params:
            if param.isdigit():
                try:
                    kid = int(param)
                    knowledge_queries.append({"knowledge_id": kid})
                except:
                    pass
            else:
                # 模糊匹配知识点ID或名称
                regex_pattern_param = f".*{re.escape(param)}.*"
                knowledge_queries.append({"knowledge_id": {"$regex": regex_pattern_param, "$options": "i"}})
                knowledge_queries.append({"knowledge_name": {"$regex": regex_pattern_param, "$options": "i"}})
        
        if knowledge_queries:
            matched_knowledges = db.knowledges.find(
                {"$or": knowledge_queries, "course_code": course_code},
                {"_id": 0, "knowledge_id": 1}
            )
            target_knowledge_ids = {k["knowledge_id"] for k in matched_knowledges}
        
        # 如果没有找到匹配的知识点，返回提示信息但不返回错误
        if not target_knowledge_ids:
            return jsonify({
                "warning": "未找到匹配的知识点",
                "queries": not_learned_params,
                "course_code": course_code,
                "course_id": current_course_id,
                "course_name": actual_course_name,
                "query_key": course_query if course_query else "当前课程",
                "query_matched": True,
                "studentUid": studentUid,
                "available_knowledges": list(knowledge_map.values())
            }), 200

    # Step 8: 统计每个学生的学习情况
    students_data = []
    
    for student_info in student_list:
        student_id = student_info.get("id")
        sis_user_id = student_info.get("sis_user_id")
        
        if not student_id and not sis_user_id:
            continue
        
        # 查找学生信息
        student_query = {}
        if student_id:
            student_query["id"] = student_id
        if sis_user_id:
            student_query["sis_user_id"] = sis_user_id
        
        student = db.students.find_one(student_query, {"_id": 0})
        if not student:
            # 学生不存在或数据不完整
            continue
        
        # 查找学生选修的当前课程
        enrolled_courses = student.get("enrolled_courses", [])
        current_enrolled_course = None
        
        for enrolled_course in enrolled_courses:
            # 匹配课程ID
            if enrolled_course.get("id") == current_course_id:
                current_enrolled_course = enrolled_course
                break
        
        if not current_enrolled_course:
            # 学生没有选修这门课或课程信息不完整
            continue
        
        # 获取学生的知识点列表
        knowledge_list = current_enrolled_course.get("knowledge_list", [])
        
        # 统计完成和未完成的知识点
        completed_knowledges = []
        incomplete_knowledges = []
        student_knowledge_map = {k.get("knowledge_id"): k for k in knowledge_list}
        
        for knowledge_id, knowledge_info in knowledge_map.items():
            student_knowledge = student_knowledge_map.get(knowledge_id, {})
            state = student_knowledge.get("state", "not_learned")
            
            k_detail = {
                "knowledge_id": knowledge_id,
                "knowledge_name": knowledge_info["knowledge_name"],
                "state": state
            }
            
            if state in ["learned", "review_needed"]:
                completed_knowledges.append(k_detail)
            else:
                incomplete_knowledges.append(k_detail)
        
        # 计算完成率
        completion_rate = round((len(completed_knowledges) / total_knowledge) * 100, 2)
        
        # 应用筛选条件
        match = True
        
        # 完成率筛选
        if completion_lt is not None and completion_rate >= completion_lt:
            match = False
        if completion_gt is not None and completion_rate <= completion_gt:
            match = False
        
        # 未学习知识点筛选
        if target_knowledge_ids:
            has_unlearned_target = any(
                item["knowledge_id"] in target_knowledge_ids
                for item in incomplete_knowledges
            )
            if not has_unlearned_target:
                match = False
        
        if match:
            students_data.append({
                "student_id": student_id,
                "sis_user_id": sis_user_id,
                "student_name": student_info.get("name") or student.get("student_name", "未知学生"),
                "completed_knowledge_count": len(completed_knowledges),
                "total_knowledge_count": total_knowledge,
                "completion_rate": completion_rate,
                "completed_knowledges": completed_knowledges,
                "incomplete_knowledges": incomplete_knowledges,
                "enrollment_status": current_enrolled_course.get("enrollment_status", "active")
            })
    
    # Step 9: 返回结果
    return jsonify({
        "course_id": current_course_id,
        "course_name": actual_course_name,
        "course_code": course_code,
        "class_sis_id": class_info.get("sis_course_id", ""),
        "term_id": term_id,
        "total_students": len(student_list),
        "matched_students": len(students_data),
        "total_knowledge_count": total_knowledge,
        "studentUid": studentUid,
        "query_key": course_query if course_query else "当前课程",
        "query_matched": True,
        "note": f"查询用户 {studentUid} 的课程 '{actual_course_name}' 的学生状态",
        "filters": {
            "completion_lt": completion_lt,
            "completion_gt": completion_gt,
            "knowledge_not_learned_queries": not_learned_params,
            "matched_knowledge_ids": list(target_knowledge_ids) if target_knowledge_ids else None
        },
        "knowledge_overview": {
            "total_count": total_knowledge,
            "knowledge_list": list(knowledge_map.values())
        },
        "students": students_data
    }), 200



# 辅助函数：获取某个知识点的学习状态分布
@app.route('/dashboard/study_situation/course/<course_id>/knowledge/<knowledge_id>/stats')
def get_knowledge_stats(course_id, knowledge_id):
    """获取特定知识点在课程中的学习状态分布"""
    try:
        course_id = int(course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    try:
        knowledge_id = int(knowledge_id)
    except ValueError:
        # 如果knowledge_id不是数字，按原样处理
        pass
    
    # 获取班级信息
    class_info = db.classes.find_one(
        {"id": course_id},
        {"_id": 0, "course_code": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({"error": "未找到班级信息"}), 404
    
    course_code = class_info.get("course_code")
    student_list = class_info.get("student_list", [])
    
    if not course_code:
        return jsonify({"error": "班级缺少课程代码"}), 400
    
    # 获取知识点信息
    knowledge = db.knowledges.find_one(
        {"course_code": course_code, "knowledge_id": knowledge_id},
        {"_id": 0, "knowledge_name": 1}
    )
    
    if not knowledge:
        return jsonify({"error": "未找到知识点信息"}), 404
    
    # 统计学习状态
    stats = {
        "total_students": len(student_list),
        "not_learned": 0,
        "in_progress": 0,
        "learned": 0,
        "review_needed": 0,
        "unknown": 0
    }
    
    student_details = []
    
    for student_info in student_list:
        student_id = student_info.get("id")
        sis_user_id = student_info.get("sis_user_id")
        
        if not student_id and not sis_user_id:
            continue
        
        # 查找学生
        student_query = {}
        if student_id:
            student_query["id"] = student_id
        if sis_user_id:
            student_query["sis_user_id"] = sis_user_id
        
        student = db.students.find_one(student_query, {"_id": 0})
        if not student:
            stats["unknown"] += 1
            continue
        
        # 查找课程和知识点
        enrolled_courses = student.get("enrolled_courses", [])
        current_course = None
        
        for enrolled_course in enrolled_courses:
            if enrolled_course.get("id") == course_id:
                current_course = enrolled_course
                break
        
        if not current_course:
            stats["not_learned"] += 1
            student_details.append({
                "student_id": student_id,
                "sis_user_id": sis_user_id,
                "student_name": student_info.get("name", "未知"),
                "state": "not_enrolled"
            })
            continue
        
        # 查找知识点状态
        knowledge_list = current_course.get("knowledge_list", [])
        knowledge_state = "not_learned"
        
        for knowledge_item in knowledge_list:
            if knowledge_item.get("knowledge_id") == knowledge_id:
                knowledge_state = knowledge_item.get("state", "not_learned")
                break
        
        # 更新统计
        if knowledge_state == "not_learned":
            stats["not_learned"] += 1
        elif knowledge_state == "in_progress":
            stats["in_progress"] += 1
        elif knowledge_state == "learned":
            stats["learned"] += 1
        elif knowledge_state == "review_needed":
            stats["review_needed"] += 1
        else:
            stats["unknown"] += 1
        
        student_details.append({
            "student_id": student_id,
            "sis_user_id": sis_user_id,
            "student_name": student_info.get("name", "未知"),
            "state": knowledge_state
        })
    
    # 计算百分比
    if stats["total_students"] > 0:
        for key in ["not_learned", "in_progress", "learned", "review_needed", "unknown"]:
            stats[f"{key}_percentage"] = round(stats[key] / stats["total_students"] * 100, 2)
    
    return jsonify({
        "course_id": course_id,
        "course_code": course_code,
        "knowledge_id": knowledge_id,
        "knowledge_name": knowledge.get("knowledge_name", str(knowledge_id)),
        "stats": stats,
        "student_details": student_details
    }), 200
    

# 查询某个课程所有知识点的学习情况
@app.route('/dashboard/study_situation/course/knowledges')
def get_course_knowledge_status():
    """
    查询某门课程中知识点的学习情况，支持：
    - studentUid为必填参数，用于查找当前课程
    - course_query为可选参数，如果未提供则使用当前课程
    - completion_rate_gte / completion_rate_lte 筛选
    - 返回每个知识点的掌握学生名单（已完成 / 未完成）
    注意：直接使用courses表中的knowledge_list作为课程的全部知识点
    """
    # Step 1: 获取studentUid参数
    studentUid = request.args.get('studentUid', '').strip()
    
    # 1. 根据studentUid从全局字典中查找对应的current_course
    current_course = None
    
    if studentUid and studentUid in user_global_store:
        user_info = user_global_store[studentUid]
        current_course = user_info.get('current_course')
        print(f"get_course_knowledge_status从全局字典中找到用户 {studentUid} 的当前课程: {current_course}")
    else:
        print(f"警告: 用户 {studentUid} 不在全局字典中或未提供studentUid")
    
    # 如果没有从全局字典找到当前课程，尝试从session获取
    if not current_course:
        current_course = session.get('current_course')
        print(f"从session获取当前课程: {current_course}")
    
    # 如果仍然没有当前课程，返回错误
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": "请先在学情分析页面选择一门课程"
        }), 400
    
    # 获取当前课程的信息
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('name', '未命名课程')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({
            "error": "当前课程信息不完整",
            "message": "当前课程缺少course_id字段",
            "current_course": current_course
        }), 400
    
    # Step 3: 获取course_query参数并进行匹配
    course_query = request.args.get('course_query', '').strip()
    
    # 如果提供了course_query，进行模糊匹配
    if course_query:
        is_matched = False
        
        # 检查课程ID是否匹配
        if str(current_course_id) == str(course_query):
            is_matched = True
            print(f"通过课程ID匹配: {course_query}")
        
        # 检查课程名称是否匹配（模糊匹配）
        elif current_course_name and course_query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {course_query} 匹配 {current_course_name}")
        
        # 检查sis_course_id是否匹配
        elif current_sis_course_id and course_query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {course_query} 匹配 {current_sis_course_id}")
        
        # 如果都没有匹配，尝试在数据库中查找是否有该课程
        if not is_matched:
            print(f"未匹配到课程: {course_query}")
            return jsonify({
                "error": f"无权限查询课程 '{course_query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
    
    # Step 4: 使用current_course的course_id查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    print(f"开始查询课程知识点状态 - course_id: {current_course_id} (类型: {type(current_course_id)})")
    
    # 获取当前课程信息
    course = db.courses.find_one(
        {"courses_list.class_list.id": current_course_id},
        {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}
    )
    
    if not course:
        # 如果没有在courses_list.class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的课程信息",
            "current_course_id": current_course_id
        }), 404
    
    # 提取当前课程的具体信息
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    # 从courses_list中提取具体的课程代码和班级信息
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code:
            break
    
    # Step 5: 获取班级信息
    class_info = db.classes.find_one(
        {"id": current_course_id},
        {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    # 使用classes表中的课程名称（如果存在）
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    
    # 确保course_code正确
    if not course_code:
        course_code = class_info.get("course_code", "")
    
    total_students = len(student_list)
    print(f"班级学生总数: {total_students}")
    
    if total_students == 0:
        return jsonify({
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "total_students": 0,
            "query_key": course_query if course_query else "当前课程",
            "query_matched": True,
            "studentUid": studentUid,
            "message": "班级中没有学生"
        }), 200

    # Step 6: 处理筛选参数
    try:
        completion_rate_gte = request.args.get('completion_rate_gte')
        completion_rate_lte = request.args.get('completion_rate_lte')
        
        print(f"原始筛选参数: gte={completion_rate_gte} (类型: {type(completion_rate_gte)}), lte={completion_rate_lte} (类型: {type(completion_rate_lte)})")
        
        # 转换为浮点数
        if completion_rate_gte is not None:
            try:
                completion_rate_gte = float(completion_rate_gte)
                if completion_rate_gte < 0 or completion_rate_gte > 100:
                    return jsonify({"error": "completion_rate_gte 必须在 0~100 之间"}), 400
                print(f"转换后gte: {completion_rate_gte} (类型: {type(completion_rate_gte)})")
            except (ValueError, TypeError):
                return jsonify({"error": "completion_rate_gte 必须是 0~100 之间的数字"}), 400
        
        if completion_rate_lte is not None:
            try:
                completion_rate_lte = float(completion_rate_lte)
                if completion_rate_lte < 0 or completion_rate_lte > 100:
                    return jsonify({"error": "completion_rate_lte 必须在 0~100 之间"}), 400
                print(f"转换后lte: {completion_rate_lte} (类型: {type(completion_rate_lte)})")
            except (ValueError, TypeError):
                return jsonify({"error": "completion_rate_lte 必须是 0~100 之间的数字"}), 400

    except Exception as e:
        print(f"参数解析错误: {e}")
        return jsonify({"error": "筛选参数格式错误"}), 400

    # Step 7: 获取课程的知识点列表（直接从course表中获取）
    knowledge_list = course.get('knowledge_list', [])
    print(f"课程知识点数量: {len(knowledge_list)}")
    
    if not knowledge_list:
        return jsonify({
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "total_students": total_students,
            "query_key": course_query if course_query else "当前课程",
            "query_matched": True,
            "studentUid": studentUid,
            "message": "课程中没有知识点",
            "knowledge_count_from_course": course.get('knowledge_count', 0)
        }), 200

    # Step 8: 统计每个知识点的学习情况
    result_knowledges = []
    
    print(f"开始统计知识点学习情况...")
    print(f"筛选条件: gte={completion_rate_gte}, lte={completion_rate_lte}")

    for idx, knowledge in enumerate(knowledge_list):
        knowledge_id = knowledge.get('knowledge_id')
        knowledge_name = knowledge.get('knowledge_name', f"知识点{knowledge_id}")
        
        print(f"\n处理知识点 [{idx+1}/{len(knowledge_list)}]: ID={knowledge_id}, 名称={knowledge_name}")
        
        # 如果知识点缺少必要字段，跳过
        if knowledge_id is None:
            print(f"知识点ID为None，跳过")
            continue

        # 统一将knowledge_id转为字符串以便比较
        knowledge_id_str = str(knowledge_id)
        
        completed_students = []
        incomplete_students = []

        # 查询每个学生是否掌握该知识点
        for student_idx, student_info in enumerate(student_list):
            student_id = student_info.get("id")
            sis_user_id = student_info.get("sis_user_id")
            student_name = student_info.get("name", "未知")
            
            if not student_id and not sis_user_id:
                continue
            
            # 查找学生信息
            student_query = {}
            if student_id is not None:
                student_query["id"] = student_id
            if sis_user_id:
                student_query["sis_user_id"] = sis_user_id
            
            student = db.students.find_one(student_query, {"_id": 0})
            
            if student:
                # 查找学生选修的当前课程
                enrolled_courses = student.get("enrolled_courses", [])
                current_enrolled_course = None
                
                for enrolled_course in enrolled_courses:
                    enrolled_id = enrolled_course.get("id")
                    # 统一转为字符串比较
                    if enrolled_id is not None and str(enrolled_id) == str(current_course_id):
                        current_enrolled_course = enrolled_course
                        break
                
                if current_enrolled_course:
                    # 检查学生是否掌握了该知识点
                    student_knowledge_list = current_enrolled_course.get("knowledge_list", [])
                    is_completed = False
                    
                    for k_item in student_knowledge_list:
                        k_id = k_item.get("knowledge_id")
                        if k_id is not None:
                            # 统一转为字符串进行比较
                            if str(k_id) == knowledge_id_str:
                                state = k_item.get("state", "not_learned")
                                if state in ["learned", "review_needed"]:
                                    is_completed = True
                                break
                    
                    if is_completed:
                        completed_students.append({
                            "student_id": student_id,
                            "sis_user_id": sis_user_id,
                            "student_name": student.get("student_name") or student_name
                        })
                    else:
                        incomplete_students.append({
                            "student_id": student_id,
                            "sis_user_id": sis_user_id,
                            "student_name": student.get("student_name") or student_name
                        })
                else:
                    # 学生没有选修这门课
                    incomplete_students.append({
                        "student_id": student_id,
                        "sis_user_id": sis_user_id,
                        "student_name": student_name
                    })
            else:
                # 学生不存在
                incomplete_students.append({
                    "student_id": student_id,
                    "sis_user_id": sis_user_id,
                    "student_name": student_name
                })

        # 计算完成率（确保是数字）
        completion_rate = 0.0
        if total_students > 0:
            try:
                completion_rate = round((len(completed_students) / total_students) * 100, 2)
                completion_rate = float(completion_rate)  # 确保是浮点数
            except (ZeroDivisionError, TypeError, ValueError) as e:
                print(f"计算完成率时出错: {e}")
                completion_rate = 0.0
        
        print(f"  完成情况: 已掌握{len(completed_students)}人, 未掌握{len(incomplete_students)}人, 总人数{total_students}, 完成率={completion_rate}% (类型: {type(completion_rate)})")

        # 应用筛选条件
        skip = False
        
        # 处理gte筛选
        if completion_rate_gte is not None:
            print(f"  检查gte筛选: 要求>={completion_rate_gte}%, 当前={completion_rate}%")
            try:
                gte_value = float(completion_rate_gte)
                current_rate = float(completion_rate)
                
                if current_rate < gte_value:
                    skip = True
                    print(f"    → 跳过: {current_rate}% < {gte_value}%")
                else:
                    print(f"    → 通过: {current_rate}% >= {gte_value}%")
            except (ValueError, TypeError) as e:
                print(f"    → gte筛选错误: {e}")
        
        # 处理lte筛选（只有在没有跳过且lte有值时）
        if not skip and completion_rate_lte is not None:
            print(f"  检查lte筛选: 要求<={completion_rate_lte}%, 当前={completion_rate}%")
            try:
                lte_value = float(completion_rate_lte)
                current_rate = float(completion_rate)
                
                if current_rate > lte_value:
                    skip = True
                    print(f"    → 跳过: {current_rate}% > {lte_value}%")
                else:
                    print(f"    → 通过: {current_rate}% <= {lte_value}%")
            except (ValueError, TypeError) as e:
                print(f"    → lte筛选错误: {e}")
        
        if skip:
            print(f"  知识点被筛选条件跳过")
            continue

        result_knowledges.append({
            "knowledge_id": knowledge_id,
            "knowledge_name": knowledge_name,
            "completed_students_count": len(completed_students),
            "incomplete_students_count": len(incomplete_students),
            "completion_rate": completion_rate,
            "total_students": total_students,
            "completed_students": completed_students[:10],  # 限制返回数量
            "incomplete_students": incomplete_students[:10],  # 限制返回数量
        })

    print(f"\n统计完成，共处理{len(result_knowledges)}个知识点（原始{len(knowledge_list)}个）")

    # Step 9: 返回结果
    return jsonify({
        "course_id": current_course_id,
        "course_name": actual_course_name,
        "course_code": course_code,
        "class_sis_id": class_info.get("sis_course_id", ""),
        "term_id": term_id,
        "total_students": total_students,
        "total_knowledge_points": len(result_knowledges),
        "knowledge_count_from_course": course.get('knowledge_count', 0),
        "studentUid": studentUid,
        "query_key": course_query if course_query else "当前课程",
        "query_matched": True,
        "note": f"查询用户 {studentUid} 的课程 '{actual_course_name}' 的知识点状态",
        "data_source": {
            "knowledge_source": "course.knowledge_list",
            "student_source": "course.student_list"
        },
        "filters": {
            "completion_rate_gte": completion_rate_gte,
            "completion_rate_lte": completion_rate_lte
        },
        "knowledge_list": result_knowledges
    }), 200


# 查询单个学生的学习情况
@app.route('/dashboard/study_situation/course/student/<path:student_query>')
def get_student_progress(student_query=None):
    """
    查询某学生在某课程中的学习进度
    - studentUid: 必填参数，用于从全局存储获取当前课程
    - query: 可选参数，支持 course_id 或 course_name 模糊匹配，如未提供则使用当前课程
    - student_query: 路径参数，支持 student_id 或 student_name 模糊匹配
    
    适应新的数据库设计：
    - 课程表(courses): course_name, courses_list[{course_code, class_list[{id, sis_course_id}]}]
    - 班级表(classes): id, course_code, student_list[{id, sis_user_id, name}]
    - 学生表(students): sis_user_id, enrolled_courses[{id, knowledge_list[{knowledge_id, state}]}]
    """
    # Step 1: 获取studentUid参数
    student_uid = request.args.get('studentUid', '').strip()
    if not student_uid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供studentUid参数以确定当前用户"
        }), 400
    
    print(f"获取学生进度请求 - studentUid: {student_uid}, student_query: {student_query}")
    
    # Step 2: 从全局存储查找当前课程
    current_course = None
    if student_uid in user_global_store:
        user_data = user_global_store[student_uid]
        current_course = user_data.get('current_course')
        print(f"从全局存储找到用户数据: {student_uid}")
        print(f"当前课程: {current_course}")
    else:
        print(f"studentUid {student_uid} 不在全局存储中")
    
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": f"用户 {student_uid} 尚未在学情分析页面选择课程",
            "studentUid": student_uid,
            "suggestion": "请先在学情分析页面选择课程"
        }), 404
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', '')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({
            "error": "当前课程信息不完整",
            "message": "当前课程缺少course_id字段",
            "current_course": current_course
        }), 400
    
    # Step 3: 获取query参数并进行匹配
    course_query = request.args.get('course_query', '').strip()
    print("course_query????", course_query)
    
    # 如果提供了query，进行模糊匹配
    if course_query:
        is_matched = False
        
        # 检查课程ID是否匹配
        if str(current_course_id) == str(course_query):
            is_matched = True
            print(f"通过课程ID匹配: {course_query}")
        
        # 检查课程名称是否匹配（模糊匹配）
        elif current_course_name and course_query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {course_query} 匹配 {current_course_name}")
        
        # 检查sis_course_id是否匹配
        elif current_sis_course_id and course_query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {course_query} 匹配 {current_sis_course_id}")
        
        # 如果都没有匹配，尝试在数据库中查找是否有该课程
        if not is_matched:
            print(f"未匹配到课程: {course_query}")
            
            # # 在数据库中查找匹配的课程
            # regex_pattern = f".*{re.escape(course_query)}.*"
            
            # matching_courses = list(db.courses.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.class_list.sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "courses_list": 1}
            # ))
            
            # # 检查classes表中是否有匹配的班级
            # matching_classes = list(db.classes.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "course_code": 1, "id": 1}
            # ))
            
            # matched_courses_info = []
            
            # for match_course in matching_courses:
            #     course_name = match_course.get("course_name", "")
            #     for course_item in match_course.get('courses_list', []):
            #         course_code = course_item.get('course_code', "")
            #         for class_item in course_item.get('class_list', []):
            #             matched_courses_info.append({
            #                 "course_name": course_name,
            #                 "course_code": course_code,
            #                 "class_id": class_item.get('id'),
            #                 "sis_course_id": class_item.get('sis_course_id'),
            #                 "type": "班级",
            #                 "reason": f"数据库查询匹配: {course_query}"
            #             })
            
            # for match_class in matching_classes:
            #     matched_courses_info.append({
            #         "course_name": match_class.get("course_name"),
            #         "course_code": match_class.get("course_code"),
            #         "class_id": match_class.get("id"),
            #         "type": "班级",
            #         "reason": f"数据库查询匹配: {course_query}"
            #     })
            
            # return jsonify({
            #     "error": f"您无权限查询课程 '{course_query}' 相关的信息",
            #     "message": "您只能查询您当前选中的课程",
            #     "current_course": {
            #         "course_id": current_course_id,
            #         "course_name": current_course_name,
            #         "sis_course_id": current_sis_course_id,
            #         "studentUid": student_uid
            #     },
            #     "matched_courses_in_db": matched_courses_info if matched_courses_info else [],
            #     "suggestion": f"您可查询的课程是: {current_course_name} (ID: {current_course_id})"
            # }), 403
            return jsonify({
                "error": f"无权限查询课程 '{course_query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
    
    # Step 4: 使用current_course的course_id查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    print(f"开始查询学生进度 - course_id: {current_course_id}, student_query: {student_query}")
    
    # 获取当前课程信息
    course = db.courses.find_one(
        {"courses_list.class_list.id": current_course_id},
        {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}
    )
    
    if not course:
        # 如果没有在courses_list.class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的课程信息",
            "current_course_id": current_course_id
        }), 404
    
    # 提取当前课程的具体信息
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    # 从courses_list中提取具体的课程代码和班级信息
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code:
            break
    
    # Step 5: 获取班级信息以验证学生是否在班级中
    class_info = db.classes.find_one(
        {"id": current_course_id},
        {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    # 使用classes表中的课程名称（如果存在）
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    
    # 确保course_code正确
    if not course_code:
        course_code = class_info.get("course_code", "")
    
    # ========== Step 6: 优化后的学生匹配逻辑 ==========
    print(f"\n{'='*60}")
    print(f"学生查询调试信息")
    print(f"{'='*60}")
    print(f"输入的student_query: {student_query} (类型: {type(student_query)})")
    print(f"班级中学生数量: {len(student_list)}")
    print(f"课程信息: {actual_course_name} (ID: {current_course_id})")
    
    student = None
    matched_student_in_class = None
    match_reason = ""
    match_debug_info = []
    
    # 首先尝试在班级学生列表中查找
    for idx, student_info in enumerate(student_list):
        student_id = student_info.get("id")
        sis_user_id = student_info.get("sis_user_id")
        student_name = student_info.get("student_name", "")
        
        # 调试信息
        debug_line = f"检查学生[{idx}]: name={student_name}, id={student_id}({type(student_id)}), sis={sis_user_id}({type(sis_user_id)})"
        match_debug_info.append(debug_line)
        
        # 1. 按姓名匹配（模糊）
        if student_name and student_query.lower() in student_name.lower():
            matched_student_in_class = student_info
            match_reason = f"姓名模糊匹配: '{student_query}' in '{student_name}'"
            print(f"✓ {match_reason}")
            break
        
        # 2. 按id匹配（多种方式）
        if student_id is not None:
            query_str = str(student_query).strip()
            id_str = str(student_id).strip()
            
            # 完全匹配（字符串）
            if query_str == id_str:
                matched_student_in_class = student_info
                match_reason = f"id精确匹配: {query_str} == {id_str}"
                print(f"✓ {match_reason}")
                break
            
            # 数字比较（如果都是数字）
            if query_str.isdigit() and id_str.isdigit():
                if int(query_str) == int(id_str):
                    matched_student_in_class = student_info
                    match_reason = f"id数字匹配: {int(query_str)} == {int(id_str)}"
                    print(f"✓ {match_reason}")
                    break
            
            # 部分匹配（id包含查询字符串）
            if query_str in id_str:
                matched_student_in_class = student_info
                match_reason = f"id包含匹配: '{query_str}' in '{id_str}'"
                print(f"✓ {match_reason}")
                break
        
        # 3. 按sis_user_id匹配（多种方式）
        if sis_user_id:
            query_str = str(student_query).strip()
            sis_str = str(sis_user_id).strip()
            
            # 完全匹配（字符串）
            if query_str == sis_str:
                matched_student_in_class = student_info
                match_reason = f"sis_user_id精确匹配: {query_str} == {sis_str}"
                print(f"✓ {match_reason}")
                break
            
            # 部分匹配
            if query_str in sis_str:
                matched_student_in_class = student_info
                match_reason = f"sis_user_id包含匹配: '{query_str}' in '{sis_str}'"
                print(f"✓ {match_reason}")
                break
    
    print(f"班级列表匹配结果: {match_reason if matched_student_in_class else '未匹配'}")
    
    # 如果班级列表中找到，查询学生详细信息
    if matched_student_in_class:
        print(f"在班级列表中找到学生: {matched_student_in_class}")
        student_id = matched_student_in_class.get("id")
        sis_user_id = matched_student_in_class.get("sis_user_id")
        
        # 构建查询条件（优先使用id，其次使用sis_user_id）
        query_conditions = {}
        if student_id is not None:
            # 尝试多种id格式查询
            query_conditions["$or"] = [
                {"id": student_id},  # 原始格式
                {"id": str(student_id)},  # 字符串格式
            ]
            # 如果是数字，也尝试数字格式
            if isinstance(student_id, (int, float)) or (isinstance(student_id, str) and student_id.isdigit()):
                query_conditions["$or"].append({"id": int(student_id) if str(student_id).isdigit() else student_id})
        elif sis_user_id:
            query_conditions["sis_user_id"] = sis_user_id
        
        print(f"数据库查询条件: {query_conditions}")
        
        if query_conditions:
            student = db.students.find_one(query_conditions, {"_id": 0})
            if student:
                print(f"✓ 通过班级列表匹配找到学生: {student.get('student_name')} (ID: {student.get('id')})")
            else:
                print(f"✗ 班级列表匹配但数据库中未找到对应学生")
    
    # 方式4: 如果未在班级列表中找到，尝试在学生表中直接查找
    if not student:
        print(f"尝试在学生表中直接查找: {student_query}")
        
        # 尝试多种查询条件
        query_conditions = {
            "$or": [
                # 按姓名模糊匹配
                {"student_name": {"$regex": f".*{re.escape(student_query)}.*", "$options": "i"}},
                
                # 按sis_user_id模糊匹配
                {"sis_user_id": {"$regex": f".*{re.escape(student_query)}.*", "$options": "i"}},
            ]
        }
        
        # 如果是数字，也尝试按id精确和模糊匹配
        if str(student_query).strip().isdigit():
            query_num = int(str(student_query).strip())
            query_conditions["$or"].extend([
                {"id": query_num},  # 精确匹配数字
                {"id": str(query_num)},  # 精确匹配字符串
                {"id": {"$regex": f".*{str(query_num)}.*"}}  # 模糊匹配
            ])
        
        print(f"直接数据库查询条件: {query_conditions}")
        
        student = db.students.find_one(query_conditions, {"_id": 0})
        
        if student:
            print(f"✓ 通过直接数据库查询找到学生: {student.get('student_name')}")
            # 检查找到的学生是否在班级中
            student_id = student.get("id")
            sis_user_id = student.get("sis_user_id")
            
            is_in_class = False
            for s in student_list:
                s_id = s.get("id")
                s_sis = s.get("sis_user_id")
                if (student_id is not None and s_id is not None and str(student_id) == str(s_id)) or \
                   (sis_user_id and s_sis and sis_user_id == s_sis):
                    is_in_class = True
                    matched_student_in_class = s
                    break
            
            if not is_in_class:
                print(f"⚠ 警告: 数据库中找到了学生，但不在班级列表中")
        else:
            print(f"✗ 数据库中未找到匹配的学生")
    
    # 打印详细调试信息
    if len(match_debug_info) > 0:
        print(f"\n班级学生列表前{min(5, len(match_debug_info))}条记录:")
        for info in match_debug_info[:5]:
            print(f"  {info}")
    
    if not student:
        return jsonify({
            "error": f"未找到与 '{student_query}' 匹配的学生",
            "course_name": actual_course_name,
            "course_id": current_course_id,
            "studentUid": student_uid,
            "debug_info": {
                "student_query": student_query,
                "query_type": type(student_query).__name__,
                "class_student_count": len(student_list),
                "match_attempted": True,
                "match_reason": match_reason or "无",
                "suggestion": "请检查输入的学生ID或姓名是否正确，确保该学生在该班级中"
            }
        }), 404
    
    # 获取学生信息
    student_id = student.get("id")
    sis_user_id = student.get("sis_user_id")
    student_name = student.get("student_name") or student.get("student_name", "未知学生")
    
    # Step 7: 检查学生是否选修了当前课程
    enrolled_courses = student.get("enrolled_courses", [])
    matched_enrolled_course = None
    
    for enrolled_course in enrolled_courses:
        if enrolled_course.get("id") == current_course_id:
            matched_enrolled_course = enrolled_course
            break
    
    if not matched_enrolled_course:
        # 检查学生是否在班级学生列表中
        is_in_class = any(
            (student_id is not None and s.get("id") is not None and str(student_id) == str(s.get("id"))) or 
            (sis_user_id and s.get("sis_user_id") and sis_user_id == s.get("sis_user_id"))
            for s in student_list
        )
        
        if is_in_class:
            # 学生在班级中但未选修课程
            return jsonify({
                "warning": f"学生 {student_name} 在班级 '{actual_course_name}' 中，但未选修该课程",
                "student": {
                    "student_id": student_id,
                    "sis_user_id": sis_user_id,
                    "student_name": student_name
                },
                "course": {
                    "course_id": current_course_id,
                    "course_name": actual_course_name,
                    "course_code": course_code
                },
                "studentUid": student_uid,
                "query_key": course_query if course_query else "当前课程",
                "is_in_class": True,
                "has_enrolled": False,
                "suggestion": "该学生在班级名单中，但尚未在系统中选修此课程"
            }), 200
        else:
            # 学生既不在班级中，也未选修课程
            return jsonify({
                "error": f"学生 {student_name} 未选修课程 '{actual_course_name}' (ID: {current_course_id})",
                "student": {
                    "student_id": student_id,
                    "sis_user_id": sis_user_id,
                    "student_name": student_name
                },
                "course": {
                    "course_id": current_course_id,
                    "course_name": actual_course_name
                },
                "studentUid": student_uid,
                "query_key": course_query if course_query else "当前课程",
                "is_in_class": False,
                "has_enrolled": False,
                "suggestion": "请确认学生是否在正确的班级中，并已选修该课程"
            }), 404
    
    # Step 8: 获取学生的知识点学习情况
    knowledge_list = matched_enrolled_course.get("knowledge_list", [])
    
    # 如果课程有knowledge_list，获取知识点的名称
    course_knowledge_list = course.get('knowledge_list', [])
    knowledge_name_map = {
        str(k.get('knowledge_id')): k.get('knowledge_name', f"知识点{k.get('knowledge_id')}")
        for k in course_knowledge_list
    }
    
    # 统计学习进度
    completed_knowledges = []
    uncompleted_knowledges = []
    in_progress_knowledges = []
    review_needed_knowledges = []
    
    for k_item in knowledge_list:
        knowledge_id = k_item.get("knowledge_id")
        state = k_item.get("state", "not_learned")
        knowledge_name = knowledge_name_map.get(str(knowledge_id), f"知识点{knowledge_id}")
        
        knowledge_detail = {
            "knowledge_id": knowledge_id,
            "knowledge_name": knowledge_name,
            "state": state
        }
        
        if state == "learned":
            completed_knowledges.append(knowledge_detail)
        elif state == "review_needed":
            review_needed_knowledges.append(knowledge_detail)
        elif state == "in_progress":
            in_progress_knowledges.append(knowledge_detail)
        else:  # not_learned or other
            uncompleted_knowledges.append(knowledge_detail)
    
    total_knowledge = len(course_knowledge_list) if course_knowledge_list else len(knowledge_list)
    completed_count = len(completed_knowledges) + len(review_needed_knowledges)  # 将需复习的也计入完成
    progress_percentage = round((completed_count / total_knowledge * 100), 2) if total_knowledge > 0 else 0
    
    # Step 9: 返回结果
    return jsonify({
        "student": {
            "student_id": student_id,
            "sis_user_id": sis_user_id,
            "student_name": student_name,
            "is_in_class": True,  # 如果走到这里，说明学生在班级中且选修了课程
            "enrollment_status": matched_enrolled_course.get("enrollment_status", "active"),
            "match_method": match_reason
        },
        "course": {
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "class_sis_id": sis_course_id,
            "term_id": term_id,
            "query_key": course_query if course_query else "当前课程",
            "query_matched": True,
            "note": f"查询用户 {student_uid} 的课程 '{actual_course_name}' 中的学生进度"
        },
        "studentUid": student_uid,
        "progress": {
            "total_knowledges": total_knowledge,
            "completed_knowledges_count": len(completed_knowledges),
            "review_needed_knowledges_count": len(review_needed_knowledges),
            "in_progress_knowledges_count": len(in_progress_knowledges),
            "uncompleted_knowledges_count": len(uncompleted_knowledges),
            "progress_percentage": progress_percentage,
            "completion_percentage": round(len(completed_knowledges) / total_knowledge * 100, 2) if total_knowledge > 0 else 0,
            "review_needed_percentage": round(len(review_needed_knowledges) / total_knowledge * 100, 2) if total_knowledge > 0 else 0
        },
        "knowledge_details": {
            "completed_knowledges": completed_knowledges,
            "review_needed_knowledges": review_needed_knowledges,
            "in_progress_knowledges": in_progress_knowledges,
            "uncompleted_knowledges": uncompleted_knowledges
        },
        "debug_info": {
            "student_query": student_query,
            "match_reason": match_reason,
            "search_method": "班级列表匹配" if matched_student_in_class else "数据库直接查询",
            "class_matched": bool(matched_student_in_class)
        },
        "last_updated": datetime.now().isoformat()
    }), 200
    
    
    
# 查询单个知识点的学习情况
@app.route('/dashboard/study_situation/course/knowledge/<path:knowledge_query>')
def get_knowledge_status(knowledge_query=None):
    """
    查询某个知识点在指定课程中的学习情况
    - studentUid: 必填参数，用于从全局存储获取当前课程
    - query: 可选参数，支持 course_id 或 course_name 模糊匹配，如未提供则使用当前课程
    - knowledge_query: 路径参数，支持 knowledge_id 或 knowledge_name 模糊匹配
    
    适应新的数据库设计：
    - 课程表(courses): course_name, courses_list[{course_code, class_list[{id, sis_course_id}]}], knowledge_list
    - 班级表(classes): id, course_code, student_list[{id, sis_user_id, name}]
    - 学生表(students): sis_user_id, enrolled_courses[{id, knowledge_list[{knowledge_id, state}]}]
    """
    # Step 1: 获取studentUid参数
    student_uid = request.args.get('studentUid', '').strip()
    if not student_uid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供studentUid参数以确定当前用户"
        }), 400
    
    print(f"获取知识点状态请求 - studentUid: {student_uid}, knowledge_query: {knowledge_query}")
    
    # Step 2: 从全局存储查找当前课程
    current_course = None
    if student_uid in user_global_store:
        user_data = user_global_store[student_uid]
        current_course = user_data.get('current_course')
        print(f"从全局存储找到用户数据: {student_uid}")
        print(f"当前课程: {current_course}")
    else:
        print(f"studentUid {student_uid} 不在全局存储中")
    
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": f"用户 {student_uid} 尚未在学情分析页面选择课程",
            "studentUid": student_uid,
            "suggestion": "请先在学情分析页面选择课程"
        }), 404
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', '')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({
            "error": "当前课程信息不完整",
            "message": "当前课程缺少course_id字段",
            "current_course": current_course
        }), 400
    
    # Step 3: 获取query参数并进行匹配
    query = request.args.get('course_query', '').strip()
    
    # 如果提供了query，进行模糊匹配
    if query:
        is_matched = False
        
        # 检查课程ID是否匹配
        if str(current_course_id) == str(query):
            is_matched = True
            print(f"通过课程ID匹配: {query}")
        
        # 检查课程名称是否匹配（模糊匹配）
        elif current_course_name and query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {query} 匹配 {current_course_name}")
        
        # 检查sis_course_id是否匹配
        elif current_sis_course_id and query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {query} 匹配 {current_sis_course_id}")
        
        # 如果都没有匹配，尝试在数据库中查找是否有该课程
        if not is_matched:
            print(f"未匹配到课程: {query}")
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
            # # 在数据库中查找匹配的课程
            # regex_pattern = f".*{re.escape(query)}.*"
            
            # matching_courses = list(db.courses.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"courses_list.class_list.sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "courses_list": 1}
            # ))
            
            # # 检查classes表中是否有匹配的班级
            # matching_classes = list(db.classes.find(
            #     {
            #         "$or": [
            #             {"course_name": {"$regex": regex_pattern, "$options": "i"}},
            #             {"course_code": {"$regex": regex_pattern, "$options": "i"}},
            #             {"sis_course_id": {"$regex": regex_pattern, "$options": "i"}}
            #         ]
            #     },
            #     {"_id": 0, "course_name": 1, "course_code": 1, "id": 1}
            # ))
            
            # matched_courses_info = []
            
            # for match_course in matching_courses:
            #     course_name = match_course.get("course_name", "")
            #     for course_item in match_course.get('courses_list', []):
            #         course_code = course_item.get('course_code', "")
            #         for class_item in course_item.get('class_list', []):
            #             matched_courses_info.append({
            #                 "course_name": course_name,
            #                 "course_code": course_code,
            #                 "class_id": class_item.get('id'),
            #                 "sis_course_id": class_item.get('sis_course_id'),
            #                 "type": "班级",
            #                 "reason": f"数据库查询匹配: {query}"
            #             })
            
            # for match_class in matching_classes:
            #     matched_courses_info.append({
            #         "course_name": match_class.get("course_name"),
            #         "course_code": match_class.get("course_code"),
            #         "class_id": match_class.get("id"),
            #         "type": "班级",
            #         "reason": f"数据库查询匹配: {query}"
            #     })
            
            # return jsonify({
            #     "error": f"您无权限查询课程 '{query}' 相关的信息",
            #     "message": "您只能查询您当前选中的课程",
            #     "current_course": {
            #         "course_id": current_course_id,
            #         "course_name": current_course_name,
            #         "sis_course_id": current_sis_course_id,
            #         "studentUid": student_uid
            #     },
            #     "matched_courses_in_db": matched_courses_info if matched_courses_info else [],
            #     "suggestion": f"您可查询的课程是: {current_course_name} (ID: {current_course_id})"
            # }), 403
            
    
    # Step 4: 使用current_course的course_id查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    print(f"开始查询知识点状态 - course_id: {current_course_id}, knowledge_query: {knowledge_query}")
    
    # 获取当前课程信息
    course = db.courses.find_one(
        {"courses_list.class_list.id": current_course_id},
        {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}
    )
    
    if not course:
        # 如果没有在courses_list.class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的课程信息",
            "current_course_id": current_course_id
        }), 404
    
    # 提取当前课程的具体信息
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    # 从courses_list中提取具体的课程代码和班级信息
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code:
            break
    
    # Step 5: 获取班级信息
    class_info = db.classes.find_one(
        {"id": current_course_id},
        {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    # 使用classes表中的课程名称（如果存在）
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    
    # 确保course_code正确
    if not course_code:
        course_code = class_info.get("course_code", "")
    
    total_students = len(student_list)
    if total_students == 0:
        return jsonify({
            "knowledge_query": knowledge_query,
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "total_students": 0,
            "query_key": query if query else "当前课程",
            "query_matched": True,
            "studentUid": student_uid,
            "message": "班级中没有学生"
        }), 200

    # Step 6: 查找知识点信息
    knowledge = None
    knowledge_id = None
    knowledge_name = None
    
    # 首先在课程的知识点列表中查找
    course_knowledge_list = course.get('knowledge_list', [])
    
    # 尝试按knowledge_id精确匹配
    for k in course_knowledge_list:
        k_id = k.get('knowledge_id')
        if str(k_id) == knowledge_query:
            knowledge = k
            knowledge_id = k_id
            knowledge_name = k.get('knowledge_name', f"知识点{k_id}")
            break
    
    # 如果未找到，尝试按knowledge_name模糊匹配
    if not knowledge:
        knowledge_regex = re.compile(f".*{re.escape(knowledge_query)}.*", re.IGNORECASE)
        for k in course_knowledge_list:
            k_name = k.get('knowledge_name', '')
            if knowledge_regex.search(str(k.get('knowledge_id'))) or knowledge_regex.search(k_name):
                knowledge = k
                knowledge_id = k.get('knowledge_id')
                knowledge_name = k.get('knowledge_name', f"知识点{knowledge_id}")
                break
    
    # 如果课程知识点列表中未找到，尝试在knowledges表中查找
    if not knowledge:
        try:
            if knowledge_query.isdigit():
                knowledge = db.knowledges.find_one({
                    "knowledge_id": int(knowledge_query),
                    "course_code": course_code
                }, {"_id": 0})
        
        except ValueError:
            pass
        
        if not knowledge:
            k_id_regex = re.compile(f".*{re.escape(knowledge_query)}.*", re.IGNORECASE)
            knowledge = db.knowledges.find_one({
                "$or": [
                    {"knowledge_id": {"$regex": k_id_regex.pattern, "$options": "i"}},
                    {"knowledge_name": {"$regex": k_id_regex.pattern, "$options": "i"}}
                ],
                "course_code": course_code
            }, {"_id": 0})
    
    if not knowledge:
        return jsonify({
            "error": f"在课程 '{actual_course_name}' 中未找到与 '{knowledge_query}' 匹配的知识点",
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "knowledge_query": knowledge_query,
            "studentUid": student_uid,
            "query_key": query if query else "当前课程",
            "available_knowledges": [
                {"knowledge_id": k.get('knowledge_id'), "knowledge_name": k.get('knowledge_name', '')}
                for k in course_knowledge_list[:10]  # 只返回前10个知识点作为参考
            ]
        }), 404
    
    # 获取知识点信息
    if 'knowledge_id' not in knowledge:
        knowledge_id = knowledge.get('knowledge_id')
    if 'knowledge_name' not in knowledge:
        knowledge_name = knowledge.get('knowledge_name', f"知识点{knowledge_id}")
    
    # Step 7: 统计学生掌握情况
    completed_students = []
    incomplete_students = []
    
    for student_info in student_list:
        student_id = student_info.get("id")
        sis_user_id = student_info.get("sis_user_id")
        student_name = student_info.get("student_name", "未知")
        
        if not student_id and not sis_user_id:
            continue
        
        # 查找学生信息
        student_query_conditions = {}
        if student_id:
            student_query_conditions["id"] = student_id
        if sis_user_id:
            student_query_conditions["sis_user_id"] = sis_user_id
        
        student = db.students.find_one(student_query_conditions, {"_id": 0})
        
        if student:
            # 查找学生选修的当前课程
            enrolled_courses = student.get("enrolled_courses", [])
            current_enrolled_course = None
            
            for enrolled_course in enrolled_courses:
                if enrolled_course.get("id") == current_course_id:
                    current_enrolled_course = enrolled_course
                    break
            
            if current_enrolled_course:
                # 检查学生是否掌握了该知识点
                knowledge_list = current_enrolled_course.get("knowledge_list", [])
                is_completed = False
                
                for k_item in knowledge_list:
                    if str(k_item.get("knowledge_id")) == str(knowledge_id):
                        state = k_item.get("state", "not_learned")
                        if state in ["learned", "review_needed"]:
                            is_completed = True
                        break
                
                if is_completed:
                    completed_students.append({
                        "student_id": student_id,
                        "sis_user_id": sis_user_id,
                        "student_name": student.get("student_name") or student.get("student_name") or student_name
                    })
                else:
                    incomplete_students.append({
                        "student_id": student_id,
                        "sis_user_id": sis_user_id,
                        "student_name": student.get("student_name") or student.get("student_name") or student_name
                    })
            else:
                # 学生没有选修这门课
                incomplete_students.append({
                    "student_id": student_id,
                    "sis_user_id": sis_user_id,
                    "student_name": student_name
                })
        else:
            # 学生不存在
            incomplete_students.append({
                "student_id": student_id,
                "sis_user_id": sis_user_id,
                "student_name": student_name
            })
    
    # Step 8: 获取访问记录统计
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    one_week_ago = now - timedelta(weeks=1)
    one_month_ago = now - timedelta(days=30)

    daily_visits = set()
    weekly_visits = set()
    monthly_visits = set()
    
    # 从knowledges表获取访问记录
    knowledge_doc = db.knowledges.find_one(
        {"knowledge_id": knowledge_id, "course_code": course_code},
        {"_id": 0, "access_records": 1}
    )
    
    if knowledge_doc and "access_records" in knowledge_doc:
        for record in knowledge_doc["access_records"]:
            try:
                # 获取学生ID
                record_sis_user_id = record.get("sis_user_id")
                if not record_sis_user_id:
                    continue
                
                # 检查访问学生是否在班级中
                is_student_in_class = any(
                    s.get("sis_user_id") == record_sis_user_id for s in student_list
                )
                
                if not is_student_in_class:
                    continue
                
                # 解析访问时间
                access_time = None
                access_time_data = record.get("access_time", {})
                
                if isinstance(access_time_data, dict) and "$date" in access_time_data:
                    date_str = access_time_data["$date"]
                    if isinstance(date_str, str):
                        try:
                            t = parser.isoparse(date_str.replace("Z", "+00:00"))
                            access_time = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
                        except:
                            pass
                elif isinstance(access_time_data, str):
                    try:
                        t = parser.isoparse(access_time_data.replace("Z", "+00:00"))
                        access_time = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
                    except:
                        pass
                
                if access_time:
                    if access_time > one_day_ago:
                        daily_visits.add(record_sis_user_id)
                    if access_time > one_week_ago:
                        weekly_visits.add(record_sis_user_id)
                    if access_time > one_month_ago:
                        monthly_visits.add(record_sis_user_id)
                        
            except Exception as e:
                print(f"处理访问记录时出错: {e}")
                continue

    # Step 9: 返回结果
    return jsonify({
        "knowledge": {
            "knowledge_id": knowledge_id,
            "knowledge_name": knowledge_name,
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "source": "course_knowledge_list" if any(k.get('knowledge_id') == knowledge_id for k in course_knowledge_list) else "knowledges_table"
        },
        "total_students": total_students,
        "completed_students_count": len(completed_students),
        "completed_students": completed_students[:100],  # 限制返回数量
        "uncompleted_students_count": len(incomplete_students),
        "uncompleted_students": incomplete_students[:100],  # 限制返回数量
        "completion_rate": round(len(completed_students) / total_students * 100, 2) if total_students > 0 else 0,
        "recent_visits": {
            "last_day": len(daily_visits),
            "last_week": len(weekly_visits),
            "last_month": len(monthly_visits),
            "daily_visits_rate": round(len(daily_visits) / total_students * 100, 2) if total_students > 0 else 0,
            "weekly_visits_rate": round(len(weekly_visits) / total_students * 100, 2) if total_students > 0 else 0,
            "monthly_visits_rate": round(len(monthly_visits) / total_students * 100, 2) if total_students > 0 else 0
        },
        "query_info": {
            "knowledge_query": knowledge_query,
            "course_query": query if query else "当前课程",
            "query_matched": True,
            "note": f"查询用户 {student_uid} 的课程 '{actual_course_name}' 中的知识点状态"
        },
        "studentUid": student_uid,
        "course_info": {
            "class_sis_id": sis_course_id,
            "term_id": term_id
        },
        "last_updated": datetime.now().isoformat()
    }), 200


#####仅给学生调用的接口：

# 查询单个学生的学习情况
@app.route('/dashboard/study_situation/course/student/myprogress')
def get_student_myprogress():
    """
    查询学生在某课程中的学习进度（学生自查询接口）
    
    参数说明：
    - studentUid: 必填参数，当前用户的ID
    - course_query: 可选参数，课程ID或名称，如未提供则使用当前课程
    - student_query: 可选路径参数，要查询的目标学生信息，如未提供则查询当前用户自己
    
    权限验证逻辑：
    1. 验证当前用户(studentUid)在当前课程中
    2. 如果提供了student_query，验证其与当前用户信息匹配
    3. 只有匹配成功才能查看学习情况
    """
    # Step 1: 获取studentUid参数（当前用户的ID）
    student_uid = request.args.get('studentUid', '').strip()
    student_query = request.args.get('student_query', '').strip()
    if not student_uid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供当前用户的studentUid参数"
        }), 400
    
    print(f"获取学生进度请求 - 当前用户ID: {student_uid}, 目标学生查询: {student_query}")
    
    # Step 2: 从全局存储查找当前课程
    current_course = None
    if student_uid in user_global_store:
        user_data = user_global_store[student_uid]
        current_course = user_data.get('current_course')
        print(f"从全局存储找到当前用户数据: {student_uid}")
        print(f"当前课程: {current_course}")
    else:
        print(f"studentUid {student_uid} 不在全局存储中")
    
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": f"用户 {student_uid} 尚未在学情分析页面选择课程",
            "studentUid": student_uid,
            "suggestion": "请先在学情分析页面选择课程"
        }), 404
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', '')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({
            "error": "当前课程信息不完整",
            "message": "当前课程缺少course_id字段",
            "current_course": current_course
        }), 400
    
    # Step 3: 获取course_query参数并进行匹配（如果存在）
    course_query_param = request.args.get('course_query', '').strip()
    print(f"课程查询参数: {course_query_param}")
    
    # 如果提供了course_query，进行模糊匹配
    if course_query_param:
        is_matched = False
        
        # 检查课程ID是否匹配
        if str(current_course_id) == str(course_query_param):
            is_matched = True
            print(f"通过课程ID匹配: {course_query_param}")
        
        # 检查课程名称是否匹配（模糊匹配）
        elif current_course_name and course_query_param.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {course_query_param} 匹配 {current_course_name}")
        
        # 检查sis_course_id是否匹配
        elif current_sis_course_id and course_query_param in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {course_query_param} 匹配 {current_sis_course_id}")
        
        # 如果都没有匹配，返回权限错误
        if not is_matched:
            print(f"未匹配到课程: {course_query_param}")
            return jsonify({
                "error": f"无权限查询课程 '{course_query_param}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
    
    # Step 4: 使用current_course的course_id查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    print(f"开始查询学生进度 - 课程ID: {current_course_id}")
    
    # 获取当前课程信息
    course = db.courses.find_one(
        {"courses_list.class_list.id": current_course_id},
        {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}
    )
    
    if not course:
        # 如果没有在courses_list.class_list中找到，尝试直接匹配id字段
        course = db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的课程信息",
            "current_course_id": current_course_id
        }), 404
    
    # 提取当前课程的具体信息
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    # 从courses_list中提取具体的课程代码和班级信息
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code:
            break
    
    # Step 5: 获取班级信息以验证学生是否在班级中
    class_info = db.classes.find_one(
        {"id": current_course_id},
        {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1}
    )
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    # 使用classes表中的课程名称（如果存在）
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    
    # 确保course_code正确
    if not course_code:
        course_code = class_info.get("course_code", "")
    
    print(f"班级信息: {actual_course_name}, 学生数量: {len(student_list)}")
    
    # ========== Step 6: 验证当前用户在当前课程中 ==========
    print(f"\n{'='*60}")
    print(f"验证当前用户权限")
    print(f"{'='*60}")
    
    # 查找当前用户(student_uid)在班级列表中的信息
    current_user_info = None
    for student_info in student_list:
        student_id = student_info.get("id")
        sis_user_id = student_info.get("sis_user_id")
        
        # 主要匹配sis_user_id（根据你的要求）
        if sis_user_id and str(sis_user_id) == str(student_uid):
            current_user_info = student_info
            print(f"✓ 找到当前用户: {sis_user_id} (通过sis_user_id匹配)")
            break
        
        # 也可以匹配id
        if student_id and str(student_id) == str(student_uid):
            current_user_info = student_info
            print(f"✓ 找到当前用户: {student_id} (通过id匹配)")
            break
    
    if not current_user_info:
        print(f"✗ 当前用户 {student_uid} 不在当前课程的学生列表中")
        return jsonify({
            "error": f"用户 {student_uid} 不在课程 '{actual_course_name}' 的学生列表中",
            "message": "您没有权限查询此课程中的学生信息",
            "course_name": actual_course_name,
            "course_id": current_course_id,
            "studentUid": student_uid
        }), 403
    
    # 获取当前用户的详细信息
    current_user_id = current_user_info.get("id")
    current_user_sis_id = current_user_info.get("sis_user_id")
    current_user_name = current_user_info.get("student_name", "")
    
    print(f"当前用户信息: 姓名={current_user_name}, ID={current_user_id}, SIS={current_user_sis_id}")
    
    # ========== Step 7: 查询当前用户的详细信息 ==========
    # 在数据库中查找当前用户的完整信息
    user_query_conditions = {}
    if current_user_id:
        user_query_conditions["$or"] = [
            {"id": current_user_id},
            {"id": str(current_user_id)}
        ]
    elif current_user_sis_id:
        user_query_conditions["sis_user_id"] = current_user_sis_id
    
    current_user = db.students.find_one(user_query_conditions, {"_id": 0})
    
    if not current_user:
        print(f"✗ 数据库中未找到当前用户的详细信息")
        return jsonify({
            "error": "用户信息不完整",
            "message": f"未找到用户 {student_uid} 的详细信息",
            "studentUid": student_uid
        }), 404
    
    # ========== Step 8: 验证student_query参数（如果存在） ==========
    print(f"\n{'='*60}")
    print(f"验证目标学生查询")
    print(f"{'='*60}")
    
    # 如果提供了student_query，验证其与当前用户信息匹配
    if student_query and student_query.strip():
        print(f"验证student_query: {student_query}")
        
        # 获取当前用户的各种标识信息
        current_user_db_id = current_user.get("id")
        current_user_db_sis = current_user.get("sis_user_id")
        current_user_db_name = current_user.get("student_name", "")
        
        print(f"当前用户数据库信息: ID={current_user_db_id}, SIS={current_user_db_sis}, 姓名={current_user_db_name}")
        
        is_matched = False
        match_reason = ""
        
        # 1. 检查姓名匹配（模糊）
        if current_user_db_name and student_query.lower() in current_user_db_name.lower():
            is_matched = True
            match_reason = f"姓名模糊匹配: '{student_query}' in '{current_user_db_name}'"
            print(f"✓ {match_reason}")
        
        # 2. 检查ID匹配
        elif current_user_db_id is not None:
            query_str = str(student_query).strip()
            id_str = str(current_user_db_id).strip()
            
            # 完全匹配（字符串）
            if query_str == id_str:
                is_matched = True
                match_reason = f"ID精确匹配: {query_str} == {id_str}"
                print(f"✓ {match_reason}")
            
            # 数字比较（如果都是数字）
            elif query_str.isdigit() and id_str.isdigit():
                if int(query_str) == int(id_str):
                    is_matched = True
                    match_reason = f"ID数字匹配: {int(query_str)} == {int(id_id_str)}"
                    print(f"✓ {match_reason}")
        
        # 3. 检查SIS匹配
        elif current_user_db_sis:
            query_str = str(student_query).strip()
            sis_str = str(current_user_db_sis).strip()
            
            if query_str == sis_str:
                is_matched = True
                match_reason = f"SIS精确匹配: {query_str} == {sis_str}"
                print(f"✓ {match_reason}")
        
        # 如果没有匹配，返回权限错误
        if not is_matched:
            print(f"✗ student_query不匹配当前用户")
            return jsonify({
                "error": "无权查看该学生信息",
                "message": f"您只能查看自己的学习进度，无法查看 '{student_query}' 的信息",
                "current_user": {
                    "student_name": current_user_db_name,
                    "student_id": current_user_db_id,
                    "sis_user_id": current_user_db_sis
                },
                "student_query": student_query,
                "suggestion": "如果您想查看其他同学的信息，请联系教师"
            }), 403
    else:
        # 如果没有提供student_query，默认是查询自己
        print(f"未提供student_query，默认查询当前用户自己")
        match_reason = "默认查询当前用户"
    
    # ========== Step 9: 检查当前用户是否选修了当前课程 ==========
    print(f"\n{'='*60}")
    print(f"检查课程选修情况")
    print(f"{'='*60}")
    
    enrolled_courses = current_user.get("enrolled_courses", [])
    matched_enrolled_course = None
    
    for enrolled_course in enrolled_courses:
        enrolled_id = enrolled_course.get("id")
        if enrolled_id is not None and str(enrolled_id) == str(current_course_id):
            matched_enrolled_course = enrolled_course
            print(f"✓ 用户已选修当前课程")
            break
    
    if not matched_enrolled_course:
        print(f"✗ 用户未选修当前课程")
        # 用户在班级中但未选修课程
        return jsonify({
            "warning": f"学生 {current_user_name} 在班级 '{actual_course_name}' 中，但未选修该课程",
            "student": {
                "student_id": current_user_id,
                "sis_user_id": current_user_sis_id,
                "student_name": current_user_name
            },
            "course": {
                "course_id": current_course_id,
                "course_name": actual_course_name,
                "course_code": course_code
            },
            "studentUid": student_uid,
            "query_key": course_query_param if course_query_param else "当前课程",
            "is_in_class": True,
            "has_enrolled": False,
            "suggestion": "您在班级名单中，但尚未在系统中选修此课程"
        }), 200
    
    # ========== Step 10: 获取用户的知识点学习情况 ==========
    print(f"\n{'='*60}")
    print(f"获取学习进度")
    print(f"{'='*60}")
    
    knowledge_list = matched_enrolled_course.get("knowledge_list", [])
    
    # 如果课程有knowledge_list，获取知识点的名称
    course_knowledge_list = course.get('knowledge_list', [])
    knowledge_name_map = {
        str(k.get('knowledge_id')): k.get('knowledge_name', f"知识点{k.get('knowledge_id')}")
        for k in course_knowledge_list
    }
    
    # 统计学习进度
    completed_knowledges = []
    uncompleted_knowledges = []
    in_progress_knowledges = []
    review_needed_knowledges = []
    
    for k_item in knowledge_list:
        knowledge_id = k_item.get("knowledge_id")
        state = k_item.get("state", "not_learned")
        knowledge_name = knowledge_name_map.get(str(knowledge_id), f"知识点{knowledge_id}")
        
        knowledge_detail = {
            "knowledge_id": knowledge_id,
            "knowledge_name": knowledge_name,
            "state": state
        }
        
        if state == "learned":
            completed_knowledges.append(knowledge_detail)
        elif state == "review_needed":
            review_needed_knowledges.append(knowledge_detail)
        elif state == "in_progress":
            in_progress_knowledges.append(knowledge_detail)
        else:  # not_learned or other
            uncompleted_knowledges.append(knowledge_detail)
    
    total_knowledge = len(course_knowledge_list) if course_knowledge_list else len(knowledge_list)
    completed_count = len(completed_knowledges) + len(review_needed_knowledges)  # 将需复习的也计入完成
    progress_percentage = round((completed_count / total_knowledge * 100), 2) if total_knowledge > 0 else 0
    
    # Step 11: 返回结果
    return jsonify({
        "student": {
            "student_id": current_user_id,
            "sis_user_id": current_user_sis_id,
            "student_name": current_user_name,
            "is_in_class": True,
            "enrollment_status": matched_enrolled_course.get("enrollment_status", "active"),
            "match_method": match_reason if 'match_reason' in locals() else "默认查询"
        },
        "course": {
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "class_sis_id": sis_course_id,
            "term_id": term_id,
            "query_key": course_query_param if course_query_param else "当前课程",
            "query_matched": True if not course_query_param else True,
            "note": f"查询用户 {student_uid} 在课程 '{actual_course_name}' 中的学习进度"
        },
        "studentUid": student_uid,
        "progress": {
            "total_knowledges": total_knowledge,
            "completed_knowledges_count": len(completed_knowledges),
            "review_needed_knowledges_count": len(review_needed_knowledges),
            "in_progress_knowledges_count": len(in_progress_knowledges),
            "uncompleted_knowledges_count": len(uncompleted_knowledges),
            "progress_percentage": progress_percentage,
            "completion_percentage": round(len(completed_knowledges) / total_knowledge * 100, 2) if total_knowledge > 0 else 0,
            "review_needed_percentage": round(len(review_needed_knowledges) / total_knowledge * 100, 2) if total_knowledge > 0 else 0
        },
        "knowledge_details": {
            "completed_knowledges": completed_knowledges,
            "review_needed_knowledges": review_needed_knowledges,
            "in_progress_knowledges": in_progress_knowledges,
            "uncompleted_knowledges": uncompleted_knowledges
        },
        "permission_info": {
            "is_self_query": True,
            "query_validated": True,
            "student_query_provided": bool(student_query and student_query.strip()),
            "course_query_provided": bool(course_query_param)
        },
        "last_updated": datetime.now().isoformat()
    }), 200


#############canvas接口
BASE_URL = "https://eiecanvas.cqu.edu.cn/api/v1"
HEADERS = {
    "Authorization": "Bearer vJHBrNPVBkEKkDGa4DyvntFtXK3m7kKP3tUfx4EDfBzfRUBxa2a2LDJGvR3CveQG"
}

# 基础数据获取函数（保持不变）
def get_course_assignments(course_id, per_page=100):
    """获取课程所有作业（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/assignments"
    params = {
        "per_page": per_page
    }
    all_assignments = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                # 如果next_url已经包含参数，就不需要传递params
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_assignments = response.json()
            all_assignments.extend(page_assignments)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_assignments
    except requests.exceptions.RequestException as e:
        print(f"获取课程作业失败: {e}")
        return []

def get_assignment_submissions(course_id, assignment_id, per_page=100):
    """获取作业提交情况（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/assignments/{assignment_id}/submissions"
    params = {
        "per_page": per_page
    }
    all_submissions = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_submissions = response.json()
            all_submissions.extend(page_submissions)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_submissions
    except requests.exceptions.RequestException as e:
        print(f"获取作业提交失败: {e}")
        return []

def get_assignment_submission_summary(course_id, assignment_id):
    """获取作业提交摘要"""
    url = f"{BASE_URL}/courses/{course_id}/assignments/{assignment_id}/submission_summary"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取作业提交摘要失败: {e}")
        return {}

def get_gradeable_students(course_id, assignment_id, per_page=100):
    """获取有资格提交作业的学生名单（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/assignments/{assignment_id}/gradeable_students"
    params = {
        "per_page": per_page
    }
    all_students = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_students = response.json()
            all_students.extend(page_students)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_students
    except requests.exceptions.RequestException as e:
        print(f"获取可评分学生失败: {e}")
        return []

def get_course_enrollments(course_id, per_page=100):
    """获取课程注册信息（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/enrollments"
    params = {
        "per_page": per_page
    }
    all_enrollments = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_enrollments = response.json()
            all_enrollments.extend(page_enrollments)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_enrollments
    except requests.exceptions.RequestException as e:
        print(f"获取课程注册信息失败: {e}")
        return []

def get_course_quizzes(course_id, per_page=100):
    """获取课程测验（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/quizzes"
    params = {
        "per_page": per_page
    }
    all_quizzes = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_quizzes = response.json()
            all_quizzes.extend(page_quizzes)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_quizzes
    except requests.exceptions.RequestException as e:
        print(f"获取课程测验失败: {e}")
        return []

#单元模块分析
# 新增单元（模块）相关的基础数据获取函数
def get_course_modules(course_id, include_items=False, include_content_details=False, per_page=100):
    """获取课程所有单元（模块）（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/modules"
    params = {
        "per_page": per_page
    }
    
    if include_items:
        params['include[]'] = ['items']
        if include_content_details:
            params['include[]'].append('content_details')
    
    all_modules = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                # 如果next_url已经包含参数，就不需要传递params
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_modules = response.json()
            all_modules.extend(page_modules)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_modules
    except requests.exceptions.RequestException as e:
        print(f"获取课程单元失败: {e}")
        return []

def get_module_items(course_id, module_id, include_content_details=False, per_page=100):
    """获取单元内的项目列表（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/modules/{module_id}/items"
    params = {
        "per_page": per_page
    }
    
    if include_content_details:
        params['include[]'] = ['content_details']
    
    all_items = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_items = response.json()
            all_items.extend(page_items)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_items
    except requests.exceptions.RequestException as e:
        print(f"获取单元项目失败: {e}")
        return []

def get_quiz_submissions(course_id, quiz_id, per_page=100):
    """获取测验的所有提交内容（支持分页）"""
    url = f"{BASE_URL}/courses/{course_id}/quizzes/{quiz_id}/submissions"
    params = {
        "per_page": per_page,
        "include[]": ["user"]
    }
    
    all_submissions = []
    
    try:
        next_url = url
        while next_url:
            if '?' in next_url:
                response = requests.get(next_url, headers=HEADERS)
            else:
                response = requests.get(next_url, headers=HEADERS, params=params)
            
            response.raise_for_status()
            page_submissions = response.json()
            all_submissions.extend(page_submissions)
            
            # 检查是否有下一页
            if 'Link' in response.headers:
                links = response.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
        return all_submissions
    except requests.exceptions.RequestException as e:
        print(f"获取测验提交失败: {e}")
        return []
    
    
    
 #教师版学情分析   

@app.route('/dashboard/study_situation/comprehensive/overview')
def get_comprehensive_overview():
    """获取班级整体学习情况综合分析"""
    # 从session获取教师课程信息
    user_courses = session.get('user_courses', [])
    print("user_courses:", user_courses)
    
    if not user_courses:
        return jsonify({"error": "未找到课程信息"}), 400
    
    # 筛选符合条件的课程
    filtered_courses = []
    for course in user_courses:
        course_name = course.get('name', '')
        term_id = course.get('enrollment_term_id')
        
        # 检查课程名称是否在COURSES_LIST中
        is_valid_name = any(allowed_name in course_name for allowed_name in COURSES_LIST)
        
        # 检查学期ID是否在允许的列表中
        is_valid_term = term_id in ALLOWED_TERM_IDS
        
        if is_valid_name and is_valid_term:
            # 添加课程ID到筛选后的列表
            filtered_courses.append({
                'course_id': course.get('course_id'),
                'name': course.get('name', '未命名课程'),
                'sis_course_id': course.get('sis_course_id', ''),
                'enrollment_term_id': term_id,
                'workflow_state': course.get('workflow_state', '')
            })
    
    print("筛选后的课程:", filtered_courses)
    
    if not filtered_courses:
        return jsonify({"error": "未找到符合条件的课程"}), 400
    
    # 获取课程ID，优先级：URL参数 > session中的当前课程 > 第一个课程
    course_id = request.args.get('course_id')
    
    # 如果URL中没有参数，尝试从session中获取当前课程
    if not course_id and 'current_course' in session:
        course_id = session['current_course'].get('course_id')
    
    # 如果还没有课程ID，使用第一个筛选后的课程
    if not course_id and filtered_courses:
        course_id = filtered_courses[0]['course_id']
    
    if not course_id:
        return jsonify({"error": "未指定课程ID"}), 400
    
    try:
        course_id = int(course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    # 验证课程是否在筛选后的列表中
    is_valid_course = any(
        str(course.get('course_id')) == str(course_id) 
        for course in filtered_courses
    )
    
    if not is_valid_course:
        # 如果课程不在筛选后的列表中，使用第一个课程
        if filtered_courses:
            course_id = filtered_courses[0]['course_id']
        else:
            return jsonify({"error": "未找到有效的课程信息"}), 400
    
    # 获取基础数据
    assignments = get_course_assignments(course_id)
    quizzes = get_course_quizzes(course_id)
    modules = get_course_modules(course_id, include_items=True, include_content_details=True)
    enrollments = get_course_enrollments(course_id)
    
    # 学生统计
    students = [e for e in enrollments if e.get('type') == 'StudentEnrollment']
    total_students = len(students)
    
    # 作业分析
    assignment_stats = analyze_assignments_comprehensive(assignments, course_id)
    
    # 测验分析
    quiz_stats = analyze_quizzes_comprehensive(quizzes, course_id)
    
    # 单元分析
    module_stats = analyze_modules_comprehensive(modules, total_students, course_id)
    
    # 学生表现分析
    student_performance = analyze_students_performance(students)
    
    # 获取当前课程信息
    current_course = next((course for course in filtered_courses if str(course.get('course_id')) == str(course_id)), None)
    
    # 标准化课程数据，确保字段名一致
    standardized_courses = []
    for course in filtered_courses:
        standardized_course = {
            'course_id': course.get('course_id'),
            'course_name': course.get('name', '未命名课程'),  # 注意这里从'name'映射到'course_name'
            'sis_course_id': course.get('sis_course_id', ''),
            'enrollment_term_id': course.get('enrollment_term_id'),
            'workflow_state': course.get('workflow_state', '')
        }
        standardized_courses.append(standardized_course)
    
    return jsonify({
        "course_info": {
            "current_course_id": course_id,
            "current_course_name": current_course.get('name') if current_course else "未知课程",
            "user_course": standardized_courses,
            "total_courses": len(standardized_courses)
        },
        "course_overview": {
            "total_students": total_students,
            "total_assignments": len(assignments),
            "total_quizzes": len(quizzes),
            "total_modules": len(modules),
            "active_students": len([s for s in students if s.get('enrollment_state') == 'active'])
        },
        "assignment_analysis": assignment_stats,
        "quiz_analysis": quiz_stats,
        "module_analysis": module_stats,
        "student_performance": student_performance,
        "overall_score_distribution": calculate_score_distribution_class(students)
    })

    
def analyze_assignments_comprehensive(assignments,course_id):
    """综合分析作业情况"""
    # total_points = 0
    published_count = 0
    graded_count = 0
    submission_stats = {
        "total_submitted": 0,
        "total_graded": 0,
        "average_submission_rate": 0
    }
    
    assignment_categories = {
        "individual": [],
        "group": [],
        "late_submissions": 0,
        "upcoming_deadlines": []
    }
    
    # 获取课程注册信息
    enrollments = get_course_enrollments(course_id)
    total_students = len([e for e in enrollments if e.get('type') == 'StudentEnrollment'])
    
    for assignment in assignments:
        assignment_id = assignment.get('id')
        assignment_name = assignment.get('name')
        # total_points += assignment.get('points_possible', 0)
        
        if assignment.get('published'):
            published_count += 1
        
        if assignment.get('graded_submissions_exist'):
            graded_count += 1
        
        # 判断是否为小组作业
        is_group_assignment = assignment.get('grade_group_students_individually') == False
        if is_group_assignment:
            assignment_categories["group"].append(assignment)
        else:
            assignment_categories["individual"].append(assignment)
        
        # 获取提交摘要和详细提交信息
        summary = get_assignment_submission_summary(course_id, assignment_id)
        submissions = get_assignment_submissions(course_id, assignment_id)
        gradeable_students = get_gradeable_students(course_id, assignment_id)
        
        # 统计提交情况
        submitted_count = summary.get('graded', 0) + summary.get('ungraded', 0)
        ungraded_count = summary.get('ungraded', 0)
        not_submitted_count = summary.get('not_submitted', 0)
        
        submission_stats["total_submitted"] += submitted_count
        submission_stats["total_graded"] += summary.get('graded', 0)
        
        # 计算每个作业的提交率
        if total_students > 0:
            submission_rate = round((submitted_count / total_students) * 100, 2)
        else:
            submission_rate = 0
        
        # 检查即将截止的作业（离截止日期还剩两天）
        due_at = assignment.get('due_at')
        upcoming_deadline_info = None
        
        if due_at:
            due_date = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
            now = datetime.now().replace(tzinfo=due_date.tzinfo)
            days_remaining = (due_date - now).days
            
            if 0 <= days_remaining <= 2:  # 还剩0-2天
                # 获取未提交的学生/小组名单
                unsubmitted_list = get_unsubmitted_students(assignment_id, gradeable_students, submissions, is_group_assignment)
                
                upcoming_deadline_info = {
                    "assignment_id": assignment_id,
                    "assignment_name": assignment_name,
                    "due_at": due_at,
                    "days_remaining": days_remaining,
                    "submission_status": {
                        "submitted_count": submitted_count,
                        "not_submitted_count": not_submitted_count,
                        "submission_rate": submission_rate,
                        "all_submitted": not_submitted_count == 0,
                        "ungraded_count": ungraded_count
                    },
                    "unsubmitted_students": unsubmitted_list
                }
                
                assignment_categories["upcoming_deadlines"].append(upcoming_deadline_info)
        
        # 为每个作业添加详细的提交和评分信息
        assignment['submission_analysis'] = {
            "submission_rate": submission_rate,
            "submitted_count": submitted_count,
            "not_submitted_count": not_submitted_count,
            "ungraded_count": ungraded_count,
            "has_ungraded_submissions": ungraded_count > 0,
            "total_students": total_students,
            "is_group_assignment": is_group_assignment
        }
    
    # 计算所有作业的平均提交率
    if published_count > 0:
        submission_stats["average_submission_rate"] = round(
            submission_stats["total_submitted"] / (published_count * total_students) * 100, 2
        )
    
    # 统计待评分作业
    assignments_with_ungraded = []
    for assignment in assignments:
        if assignment.get('submission_analysis', {}).get('has_ungraded_submissions'):
            assignments_with_ungraded.append({
                "assignment_id": assignment.get('id'),
                "assignment_name": assignment.get('name'),
                "ungraded_count": assignment.get('submission_analysis', {}).get('ungraded_count', 0)
            })
    
    return {
        "total_assignments": len(assignments),
        "published_assignments": published_count,
        "graded_assignments": graded_count,
        # "total_points": total_points,
        "submission_stats": submission_stats,
        "assignment_categories": assignment_categories,
        "ungraded_analysis": {
            "total_ungraded_submissions": submission_stats["total_submitted"] - submission_stats["total_graded"],
            "assignments_with_ungraded": assignments_with_ungraded,
            "count_assignments_with_ungraded": len(assignments_with_ungraded)
        }
    }

#小组是否提交
#获取未提交名单可以直接获取该作业的所有提交，检查状态，显示unsubmitted后获取该提交的user_id，该id对应的学生未提交
def get_unsubmitted_students(assignment_id, gradeable_students, submissions, is_group_assignment):
    """获取未提交作业的学生/小组名单"""
    # 获取已提交学生的ID
    submitted_user_ids = set()
    for submission in submissions:
        if submission.get('workflow_state') in ['submitted', 'graded']:
            submitted_user_ids.add(submission.get('user_id'))
    
    # 获取未提交学生名单
    unsubmitted_students = []
    
    for student in gradeable_students:
        user_id = student.get('id')
        
        # 排除测试学生
        if student.get('fake_student'):
            continue
            
        if user_id not in submitted_user_ids:
            unsubmitted_students.append({
                "user_id": user_id,
                "display_name": student.get('display_name'),
                "anonymous_id": student.get('anonymous_id')
            })
    
    # 如果是小组作业，尝试获取小组信息（这里需要根据实际情况调整）
    if is_group_assignment and unsubmitted_students:
        # 这里可以添加获取小组信息的逻辑
        # 由于API限制，可能需要额外的接口来获取小组信息
        pass
    
    return unsubmitted_students

def analyze_quizzes_comprehensive(quizzes,course_id):
    """综合分析测验情况"""
    quiz_stats = {
        "total_quizzes": len(quizzes),
        "published_quizzes": len([q for q in quizzes if q.get('published')]),
        "quiz_types": {},
        # "total_points": 0,
        "quiz_analysis": [],
        "completion_stats": {
            "completed_quizzes": 0,
            "incomplete_quizzes": 0,
            "expired_quizzes": 0,
            "not_started_quizzes": 0
        },
        "score_analysis": {
            "average_score_all_quizzes": 0,
            "highest_score": 0,
            "lowest_score": 100,
            "score_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        }
    }
    #所有测验平均分总和
    total_quiz_score = 0
    #有提交评分的测验数量
    quiz_count_with_submissions = 0
    
    for quiz in quizzes:
        quiz_id = quiz.get('id')
        quiz_title = quiz.get('title', '未知测验')
        quiz_type = quiz.get('quiz_type', 'unknown')
        points_possible = quiz.get('points_possible', 0)
        
        # 统计测验类型
        quiz_stats["quiz_types"][quiz_type] = quiz_stats["quiz_types"].get(quiz_type, 0) + 1
        # quiz_stats["total_points"] += points_possible
        
        # 获取测验提交情况
        quiz_submissions = get_quiz_submissions(course_id, quiz_id)
        
        # 分析单个测验
        quiz_analysis = analyze_single_quiz(quiz, quiz_submissions)
        quiz_stats["quiz_analysis"].append(quiz_analysis)
        
        # 更新完成状态统计
        if quiz_analysis["status"] == "completed":
            quiz_stats["completion_stats"]["completed_quizzes"] += 1
        elif quiz_analysis["status"] == "incomplete":
            quiz_stats["completion_stats"]["incomplete_quizzes"] += 1
        elif quiz_analysis["status"] == "expired":
            quiz_stats["completion_stats"]["expired_quizzes"] += 1
        else:
            quiz_stats["completion_stats"]["not_started_quizzes"] += 1
        
        # 更新分数分析
        if quiz_analysis["submission_analysis"]["average_score"] > 0:
            total_quiz_score += quiz_analysis["submission_analysis"]["average_score"]
            quiz_count_with_submissions += 1
            
            # 更新最高分和最低分
            quiz_stats["score_analysis"]["highest_score"] = max(
                quiz_stats["score_analysis"]["highest_score"], 
                quiz_analysis["submission_analysis"]["max_score"]
            )
            quiz_stats["score_analysis"]["lowest_score"] = min(
                quiz_stats["score_analysis"]["lowest_score"], 
                quiz_analysis["submission_analysis"]["min_score"]
            )
            
            # 更新分数分布
            avg_score = quiz_analysis["submission_analysis"]["average_score"]
            if avg_score >= 90:
                quiz_stats["score_analysis"]["score_distribution"]["A"] += 1
            elif avg_score >= 80:
                quiz_stats["score_analysis"]["score_distribution"]["B"] += 1
            elif avg_score >= 70:
                quiz_stats["score_analysis"]["score_distribution"]["C"] += 1
            elif avg_score >= 60:
                quiz_stats["score_analysis"]["score_distribution"]["D"] += 1
            else:
                quiz_stats["score_analysis"]["score_distribution"]["F"] += 1
    
    # 计算所有测验的平均分
    if quiz_count_with_submissions > 0:
        quiz_stats["score_analysis"]["average_score_all_quizzes"] = round(
            total_quiz_score / quiz_count_with_submissions, 2
        )
    
    return quiz_stats

def analyze_single_quiz(quiz, submissions):
    """分析单个测验的详细情况"""
    quiz_id = quiz.get('id')
    quiz_title = quiz.get('title', '未知测验')
    due_at = quiz.get('due_at')
    lock_at = quiz.get('lock_at')
    unlock_at = quiz.get('unlock_at')
    allowed_attempts = quiz.get('allowed_attempts', 1)
    points_possible = quiz.get('points_possible', 0)
    
    # 检查测验状态
    quiz_status = check_quiz_status(due_at, lock_at, unlock_at)
    
    # 分析提交数据
    submission_analysis = analyze_quiz_submissions(submissions, points_possible, allowed_attempts)
    
    # 获取未完成测验的学生
    incomplete_students = get_incomplete_quiz_students(submissions, quiz_status)
    
    # 获取测验报告（如果可用）
    quiz_reports = get_quiz_reports(COURSE_ID, quiz_id)

    return {
        "quiz_id": quiz_id,
        "quiz_title": quiz_title,
        "quiz_type": quiz.get('quiz_type'),
        "points_possible": points_possible,
        "status": quiz_status,
        "due_at": due_at,
        "lock_at": lock_at,
        "unlock_at": unlock_at,
        "allowed_attempts": allowed_attempts,
        "submission_analysis": submission_analysis,
        "incomplete_students": incomplete_students,
        "quiz_reports_available": len(quiz_reports) > 0,
        "time_analysis": analyze_quiz_timing(submissions, due_at)
    }
    
def analyze_modules_comprehensive(modules, total_students,course_id):
    """综合分析单元情况"""
    module_stats = {
        "total_modules": len(modules),
        "published_modules": 0,
        "locked_modules": 0,
        "completed_modules": 0,
        "in_progress_modules": 0,
        "total_items": 0,
        "module_progress": [],
        "prerequisite_analysis": {},
        "completion_requirements_analysis": {}
    }
    
    for module in modules:
        module_id = module.get('id')
        module_name = module.get('name')
        items_count = module.get('items_count', 0)
        published = module.get('published', True)
        workflow_state = module.get('workflow_state')
        state = module.get('state')
        require_sequential_progress = module.get('require_sequential_progress', False)
        prerequisite_module_ids = module.get('prerequisite_module_ids', [])
        
        # 统计基本信息
        module_stats["total_items"] += items_count
        if published:
            module_stats["published_modules"] += 1
        
        # 分析模块状态
        if state == 'completed':
            module_stats["completed_modules"] += 1
        elif state == 'started':
            module_stats["in_progress_modules"] += 1
        elif state == 'locked':
            module_stats["locked_modules"] += 1
        
        # 获取模块项目详情
        items = module.get('items', [])
        if not items:
            items = get_module_items(course_id, module_id, include_content_details=True)
        
        # 分析模块项目
        item_analysis = analyze_module_items(items, module_id)
        

        
        module_stats["module_progress"].append({
            "module_id": module_id,
            "module_name": module_name,
            "position": module.get('position'),
            "state": state,
            "published": published,
            "items_count": items_count,
            "require_sequential_progress": require_sequential_progress,
            "completion_rate": calculate_module_completion_rate(items),
            "item_analysis": item_analysis,
            "unlock_at": module.get('unlock_at'),
            "completed_at": module.get('completed_at')
        })
    
    # 计算平均完成率
    completed_modules = [m for m in module_stats["module_progress"] if m['state'] == 'completed']
    if module_stats["module_progress"]:
        module_stats["average_completion_rate"] = round(
            len(completed_modules) / len(module_stats["module_progress"]) * 100, 2
        )
    
    return module_stats

def analyze_module_items(items, module_id):
    """分析单元项目"""
    item_analysis = {
        "total_items": len(items),
        "item_types": {},
        "completion_status": {
            "completed": 0,
            "incomplete": 0,
            "locked": 0
        },
        "content_breakdown": {},
        "items_with_requirements": 0
    }
    
    for item in items:
        item_type = item.get('type')
        title = item.get('title')
        published = item.get('published', True)
        completion_requirement = item.get('completion_requirement')
        content_details = item.get('content_details', {})
        
        # 统计项目类型
        item_analysis["item_types"][item_type] = item_analysis["item_types"].get(item_type, 0) + 1
        
        # 统计内容类型细分
        if item_type in ['Assignment', 'Quiz']:
            content_type = 'assessment'
        elif item_type in ['Page', 'File']:
            content_type = 'learning_material'
        elif item_type in ['Discussion', 'ExternalUrl', 'ExternalTool']:
            content_type = 'interactive'
        else:
            content_type = 'other'
        
        item_analysis["content_breakdown"][content_type] = item_analysis["content_breakdown"].get(content_type, 0) + 1
        
        # 分析完成状态
        if completion_requirement:
            item_analysis["items_with_requirements"] += 1
            completed = completion_requirement.get('completed', False)
            if completed:
                item_analysis["completion_status"]["completed"] += 1
            else:
                item_analysis["completion_status"]["incomplete"] += 1
        else:
            item_analysis["completion_status"]["incomplete"] += 1
        
        # 检查锁定状态
        if content_details.get('locked_for_user', False):
            item_analysis["completion_status"]["locked"] += 1
    
    return item_analysis

def calculate_module_completion_rate(items):
    """计算单元完成率"""
    if not items:
        return 0
    
    completed_items = 0
    for item in items:
        completion_requirement = item.get('completion_requirement')
        if completion_requirement and completion_requirement.get('completed', False):
            completed_items += 1
    
    return round(completed_items / len(items) * 100, 2)

#用current_score判断学生表现
def analyze_students_performance(students):
    """分析学生表现"""
    performance_stats = {
        "score_distribution": {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0},
        "average_score": 0,
        "submission_rate": 0,
        "top_performers": [],
        "need_attention": []
    }
    
    total_score = 0
    total_submission_rate = 0
    valid_students = 0

    for student in students:
        current_score = student.get('grades', {}).get('current_score')
        if current_score is not None:
            total_score += current_score
            valid_students += 1
            
            # 成绩分布
            if current_score >= 90:
                performance_stats["score_distribution"]["A"] += 1
            elif current_score >= 80:
                performance_stats["score_distribution"]["B"] += 1
            elif current_score >= 70:
                performance_stats["score_distribution"]["C"] += 1
            elif current_score >= 60:
                performance_stats["score_distribution"]["D"] += 1
            else:
                performance_stats["score_distribution"]["F"] += 1
            
            # 识别优秀学生和需要关注的学生
            user_info = student.get('user', {})
            student_data = {
                "user_id": user_info.get('id'),
                "name": user_info.get('name'),
                "score": current_score,
                "sis_user_id": user_info.get('sis_user_id')
            }
            
            if current_score >= 85:
                performance_stats["top_performers"].append(student_data)
            elif current_score < 60:
                performance_stats["need_attention"].append(student_data)
    
    if valid_students > 0:
        performance_stats["average_score"] = round(total_score / valid_students, 2)
    
    return performance_stats

def calculate_score_distribution_class(students):
    """计算成绩分布"""
    scores = [s.get('grades', {}).get('current_score') for s in students 
              if s.get('grades', {}).get('current_score') is not None]
    
    if not scores:
        return {}
    
    return {
        "average": round(sum(scores) / len(scores), 2),
        "max": max(scores),
        "min": min(scores),
        "median": sorted(scores)[len(scores) // 2],
        "std_dev": round((sum((x - (sum(scores) / len(scores))) ** 2 for x in scores) / len(scores)) ** 0.5, 2)
    }



########学生接口
# 学生版学情分析接口
@app.route('/dashboard/study_situation/student/overview')
def get_student_overview():
    """获取学生个人学情综合分析"""
    # 获取学生基本信息
    sis_user_id = session.get('username')
    if not sis_user_id:
        return jsonify({"error": "未登录或session信息不完整"}), 401
    
    # 从session获取学生课程信息
    user_courses = session.get('user_courses', [])
    print("学生课程信息:", user_courses)
    
    if not user_courses:
        return jsonify({"error": "未找到课程信息"}), 400
    
    # 筛选符合条件的课程
    filtered_courses = []
    for course in user_courses:
        course_name = course.get('name', '')
        term_id = course.get('enrollment_term_id')
        
        # 检查课程名称是否在COURSES_LIST中
        is_valid_name = any(allowed_name in course_name for allowed_name in COURSES_LIST)
        
        # 检查学期ID是否在允许的列表中
        is_valid_term = term_id in ALLOWED_TERM_IDS
        
        if is_valid_name and is_valid_term:
            # 添加课程ID到筛选后的列表
            filtered_courses.append({
                'course_id': course.get('course_id'),
                'name': course.get('name', '未命名课程'),
                'sis_course_id': course.get('sis_course_id', ''),
                'enrollment_term_id': term_id,
                'workflow_state': course.get('workflow_state', '')
            })
    
    print("筛选后的学生课程:", filtered_courses)
    
    if not filtered_courses:
        return jsonify({"error": "未找到符合条件的课程"}), 400
    
    # 获取课程ID，优先级：URL参数 > session中的当前课程 > 第一个课程
    course_id = request.args.get('course_id')
    
    # 如果URL中没有参数，尝试从session中获取当前课程
    if not course_id and 'current_course' in session:
        course_id = session['current_course'].get('course_id')
    
    # 如果还没有课程ID，使用第一个筛选后的课程
    if not course_id and filtered_courses:
        course_id = filtered_courses[0]['course_id']
    
    if not course_id:
        return jsonify({"error": "未指定课程ID"}), 400
    
    try:
        course_id = int(course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    # 验证课程是否在筛选后的列表中
    is_valid_course = any(
        str(course.get('course_id')) == str(course_id) 
        for course in filtered_courses
    )
    
    if not is_valid_course:
        # 如果课程不在学生的筛选列表中，使用第一个课程
        if filtered_courses:
            course_id = filtered_courses[0]['course_id']
        else:
            return jsonify({"error": "未找到有效的课程信息"}), 400
    
    # 获取学生在该课程中的信息
    student_info = get_student_by_sis_id_in_course(sis_user_id, course_id)
    if not student_info:
        return jsonify({"error": "学生不存在或未选此课程"}), 404
    
    user_id = student_info.get('user_id')
    
    # 获取基础数据
    assignments = get_course_assignments(course_id)
    quizzes = get_course_quizzes(course_id)
    modules = get_course_modules(course_id, include_items=True, include_content_details=True)
    enrollments = get_course_enrollments(course_id)
    
    # 学生个人数据分析
    student_assignments = analyze_student_assignments(user_id, course_id, assignments)
    student_quizzes = analyze_student_quizzes(user_id, course_id, quizzes)
    student_modules = analyze_student_modules(user_id, course_id, modules)
    student_ranking = analyze_student_ranking(user_id, course_id, enrollments)
    
    # 获取当前课程信息
    current_course = next((course for course in filtered_courses if str(course.get('course_id')) == str(course_id)), None)
    
    # 标准化课程数据
    standardized_courses = []
    for course in filtered_courses:
        standardized_course = {
            'course_id': course.get('course_id'),
            'course_name': course.get('name', '未命名课程'),
            'sis_course_id': course.get('sis_course_id', ''),
            'enrollment_term_id': course.get('enrollment_term_id'),
            'workflow_state': course.get('workflow_state', '')
        }
        standardized_courses.append(standardized_course)
    
    return jsonify({
        "course_info": {
            "current_course_id": course_id,
            "current_course_name": current_course.get('name') if current_course else "未知课程",
            "student_courses": standardized_courses,
            "total_courses": len(standardized_courses)
        },
        "student_info": {
            "user_id": user_id,
            "name": student_info.get('name'),
            "sis_user_id": sis_user_id,
            "sortable_name": student_info.get('sortable_name')
        },
        "assignment_analysis": student_assignments,
        "quiz_analysis": student_quizzes,
        "module_analysis": student_modules,
        "ranking_analysis": student_ranking,
        "overview_stats": {
            "total_assignments": len(assignments),
            "total_quizzes": len(quizzes),
            "total_modules": len(modules),
            "completion_rate": calculate_student_completion_rate(student_assignments, student_quizzes, student_modules)
        }
    })

def get_student_by_sis_id_in_course(sis_user_id, course_id):
    """根据sis_user_id在指定课程中获取学生信息"""
    enrollments = get_course_enrollments(course_id)
    for enrollment in enrollments:
        if enrollment.get('sis_user_id') == sis_user_id:
            user_info = enrollment.get('user', {})
            return {
                "user_id": user_info.get('id'),
                "name": user_info.get('name'),
                "sortable_name": user_info.get('sortable_name'),
                "sis_user_id": sis_user_id
            }
    return None

def analyze_student_assignments(user_id, course_id, assignments):
    """分析学生作业完成情况"""
    student_assignments = {
        "pending_assignments": [],
        "completed_assignments": [],
        "graded_assignments": [],
        "late_assignments": [],
        "submission_stats": {
            "total_assignments": len(assignments),
            "submitted_count": 0,
            "graded_count": 0,
            "pending_count": 0,
            "submission_rate": 0
        },
        "score_analysis": {
            "average_score": 0,
            "total_points_earned": 0,
            "total_points_possible": 0,
            "completion_rate": 0
        }
    }
    
    total_score = 0
    graded_count = 0
    submitted_count = 0
    
    for assignment in assignments:
        assignment_id = assignment.get('id')
        assignment_name = assignment.get('name')
        points_possible = assignment.get('points_possible', 0)
        due_at = assignment.get('due_at')
        published = assignment.get('published')
        
        if not published:
            continue
            
        # 获取学生该作业的提交情况
        submission = get_student_assignment_submission(course_id, assignment_id, user_id)
        
        assignment_data = {
            "assignment_id": assignment_id,
            "assignment_name": assignment_name,
            "due_at": due_at,
            "points_possible": points_possible,
            "submission_status": submission.get('workflow_state', 'unsubmitted'),
            "score": submission.get('score'),
            "grade": submission.get('grade'),
            "submitted_at": submission.get('submitted_at'),
            "late": submission.get('late', False),
            "missing": submission.get('missing', False)
        }
        
        # 分类作业
        if submission.get('workflow_state') in ['submitted', 'graded']:
            submitted_count += 1
            student_assignments["completed_assignments"].append(assignment_data)
            
            if submission.get('score') is not None:
                graded_count += 1
                total_score += submission.get('score', 0)
                student_assignments["graded_assignments"].append(assignment_data)
        
        elif submission.get('workflow_state') == 'unsubmitted':
            # 检查是否已过期
            if due_at and is_assignment_overdue(due_at):
                assignment_data["status"] = "overdue"
            else:
                assignment_data["status"] = "pending"
            student_assignments["pending_assignments"].append(assignment_data)
        
        # 迟交作业
        if submission.get('late', False):
            student_assignments["late_assignments"].append(assignment_data)
    
    # 统计信息
    student_assignments["submission_stats"]["submitted_count"] = submitted_count
    student_assignments["submission_stats"]["graded_count"] = graded_count
    student_assignments["submission_stats"]["pending_count"] = len(student_assignments["pending_assignments"])
    
    if len(assignments) > 0:
        student_assignments["submission_stats"]["submission_rate"] = round(
            submitted_count / len(assignments) * 100, 2
        )
    
    # 分数分析
    if graded_count > 0:
        student_assignments["score_analysis"]["average_score"] = round(total_score / graded_count, 2)
    
    # 按截止日期排序
    student_assignments["pending_assignments"].sort(key=lambda x: x.get('due_at') or '9999-12-31')
    student_assignments["completed_assignments"].sort(key=lambda x: x.get('submitted_at') or '', reverse=True)
    
    return student_assignments

def analyze_student_quizzes(user_id, course_id, quizzes):
    """分析学生测验情况"""
    student_quizzes = {
        "pending_quizzes": [],
        "completed_quizzes": [],
        "quiz_scores": [],
        "quiz_stats": {
            "total_quizzes": len(quizzes),
            "completed_count": 0,
            "average_score": 0,
            "highest_score": 0,
            "lowest_score": 100
        }
    }
    
    total_score = 0
    completed_count = 0
    
    for quiz in quizzes:
        quiz_id = quiz.get('id')
        quiz_title = quiz.get('title', '未知测验')
        points_possible = quiz.get('points_possible', 0)
        due_at = quiz.get('due_at')
        published = quiz.get('published')
        
        if not published:
            continue
            
        # 获取学生测验提交
        quiz_submissions = get_student_quiz_submissions(course_id, quiz_id, user_id)
        
        quiz_data = {
            "quiz_id": quiz_id,
            "quiz_title": quiz_title,
            "due_at": due_at,
            "points_possible": points_possible,
            "quiz_type": quiz.get('quiz_type'),
            "allowed_attempts": quiz.get('allowed_attempts', 1)
        }
        
        if quiz_submissions:
            # 取最新提交
            latest_submission = max(quiz_submissions, key=lambda x: x.get('finished_at') or '')
            score = latest_submission.get('score')
            kept_score = latest_submission.get('kept_score')
            final_score = kept_score if kept_score is not None else score
            
            quiz_data.update({
                "status": "completed",
                "score": final_score,
                "attempts": len(quiz_submissions),
                "finished_at": latest_submission.get('finished_at'),
                "time_spent": latest_submission.get('time_spent')
            })
            
            student_quizzes["completed_quizzes"].append(quiz_data)
            
            if points_possible is not None and isinstance(points_possible, (int, float)) and points_possible > 0:
                percentage = round((final_score / points_possible) * 100, 2)
            else:
                percentage = 0
            
            student_quizzes["quiz_scores"].append({
                "quiz_title": quiz_title,
                "score": final_score,
                "points_possible": points_possible,
                "percentage": percentage
            })
            
            if final_score is not None:
                completed_count += 1
                total_score += final_score
                student_quizzes["quiz_stats"]["highest_score"] = max(
                    student_quizzes["quiz_stats"]["highest_score"], final_score
                )
                student_quizzes["quiz_stats"]["lowest_score"] = min(
                    student_quizzes["quiz_stats"]["lowest_score"], final_score
                )
        else:
            # 检查测验状态
            quiz_status = check_quiz_status(due_at, quiz.get('lock_at'), quiz.get('unlock_at'))
            quiz_data.update({
                "status": quiz_status,
                "score": None
            })
            student_quizzes["pending_quizzes"].append(quiz_data)
    
    # 统计信息
    student_quizzes["quiz_stats"]["completed_count"] = completed_count
    if completed_count > 0:
        student_quizzes["quiz_stats"]["average_score"] = round(total_score / completed_count, 2)
    
    # 按截止日期排序
    student_quizzes["pending_quizzes"].sort(key=lambda x: x.get('due_at') or '9999-12-31')
    student_quizzes["completed_quizzes"].sort(key=lambda x: x.get('finished_at') or '', reverse=True)
    
    return student_quizzes

def analyze_student_modules(user_id, course_id, modules):
    """分析学生学习进度"""
    student_modules = {
        "completed_modules": [],
        "in_progress_modules": [],
        "locked_modules": [],
        "not_started_modules": [],
        "progress_stats": {
            "total_modules": len(modules),
            "completed_count": 0,
            "completion_rate": 0,
            "total_items": 0,
            "completed_items": 0
        }
    }
    
    total_items = 0
    completed_items = 0
    
    for module in modules:
        module_id = module.get('id')
        module_name = module.get('name')
        items_count = module.get('items_count', 0)
        state = module.get('state', 'unlocked')
        
        module_data = {
            "module_id": module_id,
            "module_name": module_name,
            "position": module.get('position'),
            "items_count": items_count,
            "state": state
        }
        
        # 获取模块项目详情
        items = module.get('items', [])
        if not items:
            items = get_module_items(course_id, module_id, include_content_details=True)
        
        # 分析模块项目完成情况
        item_completion = analyze_student_module_items(user_id, course_id, items)
        module_data["item_completion"] = item_completion
        module_data["completion_rate"] = item_completion["completion_rate"]
        
        total_items += items_count
        completed_items += item_completion["completed_items"]
        
        # 分类模块
        if state == 'completed':
            student_modules["completed_modules"].append(module_data)
            student_modules["progress_stats"]["completed_count"] += 1
        elif state == 'started':
            student_modules["in_progress_modules"].append(module_data)
        elif state == 'locked':
            student_modules["locked_modules"].append(module_data)
        else:
            student_modules["not_started_modules"].append(module_data)
    
    # 统计信息
    student_modules["progress_stats"]["total_items"] = total_items
    student_modules["progress_stats"]["completed_items"] = completed_items
    if total_items > 0:
        student_modules["progress_stats"]["completion_rate"] = round(completed_items / total_items * 100, 2)
    if len(modules) > 0:
        student_modules["progress_stats"]["module_completion_rate"] = round(
            len(student_modules["completed_modules"]) / len(modules) * 100, 2
        )
    
    return student_modules

def analyze_student_module_items(user_id, course_id, items):
    """分析学生模块项目完成情况"""
    completion_analysis = {
        "total_items": len(items),
        "completed_items": 0,
        "incomplete_items": 0,
        "locked_items": 0,
        "completion_rate": 0,
        "item_details": []
    }
    
    for item in items:
        item_type = item.get('type')
        title = item.get('title')
        completion_requirement = item.get('completion_requirement', {})
        content_details = item.get('content_details', {})
        
        item_data = {
            "title": title,
            "type": item_type,
            "completed": completion_requirement.get('completed', False),
            "locked": content_details.get('locked_for_user', False),
            "completion_requirement_type": completion_requirement.get('type')
        }
        
        completion_analysis["item_details"].append(item_data)
        
        if item_data["completed"]:
            completion_analysis["completed_items"] += 1
        elif item_data["locked"]:
            completion_analysis["locked_items"] += 1
        else:
            completion_analysis["incomplete_items"] += 1
    
    if completion_analysis["total_items"] > 0:
        completion_analysis["completion_rate"] = round(
            completion_analysis["completed_items"] / completion_analysis["total_items"] * 100, 2
        )
    
    return completion_analysis

def analyze_student_ranking(user_id, course_id, enrollments):
    """分析学生在班级中的排名"""
    students = [e for e in enrollments if e.get('type') == 'StudentEnrollment']
    
    # 获取所有学生的成绩
    student_scores = []
    for student in students:
        current_score = student.get('grades', {}).get('current_score')
        if current_score is not None:
            student_scores.append({
                "user_id": student.get('user', {}).get('id'),
                "name": student.get('user', {}).get('name'),
                "score": current_score
            })
    
    # 按成绩排序
    student_scores.sort(key=lambda x: x['score'], reverse=True)
    
    # 查找当前学生的排名
    current_ranking = None
    for index, student in enumerate(student_scores, 1):
        if student['user_id'] == user_id:
            current_ranking = index
            break
    
    return {
        "class_ranking": current_ranking,
        "total_students": len(student_scores),
        "average_class_score": round(sum(s['score'] for s in student_scores) / len(student_scores), 2) if student_scores else 0,
        "top_performers": student_scores[:5]
    }

# 辅助函数保持不变
def get_student_assignment_submission(course_id, assignment_id, user_id):
    """获取学生单个作业提交详情"""
    url = f"{BASE_URL}/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取学生作业提交失败: {e}")
        return {}

def get_student_quiz_submissions(course_id, quiz_id, user_id):
    """获取学生测验提交"""
    url = f"{BASE_URL}/courses/{course_id}/quizzes/{quiz_id}/submissions"
    params = {'include[]': ['user', 'submission']}
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        submissions = response.json().get('quiz_submissions', [])
        
        # 过滤出当前学生的提交
        student_submissions = [s for s in submissions if s.get('user_id') == user_id]
        return student_submissions
    except requests.exceptions.RequestException as e:
        print(f"获取学生测验提交失败: {e}")
        return []

def is_assignment_overdue(due_at):
    """检查作业是否过期"""
    if not due_at:
        return False
    
    due_date = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
    now = datetime.now().replace(tzinfo=due_date.tzinfo)
    return now > due_date

def check_quiz_status(due_at, lock_at, unlock_at):
    """检查测验状态"""
    now = datetime.now()
    
    if lock_at:
        lock_time = datetime.fromisoformat(lock_at.replace('Z', '+00:00'))
        if now > lock_time:
            return "expired"
    
    if due_at:
        due_time = datetime.fromisoformat(due_at.replace('Z', '+00:00'))
        if now > due_time:
            return "expired"
    
    return "pending"

def calculate_student_completion_rate(assignments, quizzes, modules):
    """计算学生总体完成率"""
    total_items = (
        assignments["submission_stats"]["total_assignments"] +
        quizzes["quiz_stats"]["total_quizzes"] +
        modules["progress_stats"]["total_items"]
    )
    
    completed_items = (
        assignments["submission_stats"]["submitted_count"] +
        quizzes["quiz_stats"]["completed_count"] +
        modules["progress_stats"]["completed_items"]
    )
    
    if total_items == 0:
        return 0
    
    return round(completed_items / total_items * 100, 2)

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
            ["python", "mcp_server.py"],
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
client = MongoClient(
        host=MONGO_URL,
        port=27027,
        username='root',
        password='123456',
        authSource='admin'
    )
db = client["education2"]
mcp_thread = threading.Thread(target=start_mcp_server, daemon=True)
mcp_thread.start()
# 预加载KG模块，确保可以正常导入
try:
    from KG.kg_json import KnowledgeGraphGenerator
    from KG.kg_json2graph import create_graph, load_json_data
    print("KG模块加载成功")
except Exception as e:
    print(f"KG模块加载失败: {str(e)}")

if __name__ == '__main__': 
    # 用户表名称——student
    # 如下4个字段
    # id
    # sid 学号
    # password 密码
    # email 邮箱
    # conn = pymysql.connect(
    #     host="180.85.206.21",
    #     user="root",
    #     password="123456",
    #     database="zgllm",
    #     charset="utf8mb4"
    # )
########################################################################
    # loop = asyncio.new_event_loop()

    # try:
    #     loop.run_until_complete(initialize_mcp_client())
    # except Exception as e:
    #     print("❌ MCP 初始化失败：", e)
    #     traceback.print_exc()
        
    app.run(debug=False, use_reloader=True, host='0.0.0.0', port=APP_PORT) 
