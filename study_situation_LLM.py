from flask import request, Blueprint,jsonify,session 
import os
import json
import re
import concurrent.futures
from datetime import datetime
from database_mongo import db, user_sessions_collection
from utils.canvas_utils import get_user_by_sis_id,get_courses_by_teacher_id,get_courses_by_student_id,get_course_assignments,get_assignment_submissions,get_assignment_submission_summary,get_gradeable_students,get_course_enrollments,get_course_quizzes,get_course_modules,get_module_items,get_quiz_submissions,get_student_assignment_submission,get_student_quiz_submissions
study_situation_LLM = Blueprint('study_situation_LLM', __name__)


@study_situation_LLM.route('/dashboard/study_situation/update_current_course', methods=['POST'])
def update_current_course():
    """更新session和全局存储中当前选中的课程"""
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
        
        # 2. 更新MongoDB中的当前课程
        if user_sessions_collection is not None:
            try:
                user_sessions_collection.update_one(
                    {'username': username},
                    {'$set': {'current_course': current_course}}
                )
                print(f"MongoDB已更新用户 {username} 的当前课程: {current_course}")
            except Exception as e:
                print(f"MongoDB更新失败: {e}")
        else:
            print(f"警告: MongoDB不可用，无法更新用户 {username} 的当前课程")
        
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
        })
    except Exception as e:
        print(f"更新当前课程时出错: {str(e)}")
        return jsonify({"error": "更新课程失败"}), 500

def get_user_current_course_from_db(studentUid):
    """从 MongoDB 获取用户的当前课程"""
    if user_sessions_collection is not None:
        try:
            user_session = user_sessions_collection.find_one(
                {'sis_id': studentUid},
                {'_id': 0, 'current_course': 1}
            )
            if user_session and 'current_course' in user_session:
                return user_session['current_course']
        except Exception as e:
            print(f"❌ 从 MongoDB 获取用户当前课程失败: {e}")
    return session.get('current_course')

def get_user_courses_from_db(studentUid):
    """从 MongoDB 获取用户的课程列表"""
    if user_sessions_collection is not None:
        try:
            user_session = user_sessions_collection.find_one(
                {'sis_id': studentUid},
                {'_id': 0, 'user_courses': 1}
            )
            if user_session and 'user_courses' in user_session:
                return user_session['user_courses']
        except Exception as e:
            print(f"❌ 从 MongoDB 获取用户课程列表失败: {e}")
    return session.get('user_courses', [])
   
@study_situation_LLM.route('/dashboard/study_situation/course/search_teacher')
def search_course_teacher():
    """查询课程信息 - 获取当前课程的知识点学习统计 (性能优化版)"""
    query = request.args.get('query', '').strip()
    studentUid = request.args.get('studentUid', '').strip()
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    # 1-4. 获取课程上下文
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程信息", "message": "请先选择课程"}), 400
    
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', '未命名课程')
    
    # 5-6. 验证 query 权限
    if query:
        is_match = str(current_course_id).strip() == query or query in str(current_course_name).strip()
        if not is_match:
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})"
            }), 403
    
    # 7. 获取课程与班级基础信息
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course or not class_info:
        return jsonify({"error": "未找到课程或班级信息"}), 404
        
    student_list = class_info.get('student_list', [])
    knowledge_stats = {}
    
    if course.get('knowledge_list'):
        for k in course['knowledge_list']:
            k_id = k.get('knowledge_id')
            if k_id:
                knowledge_stats[str(k_id)] = {
                    'knowledge_id': k_id,
                    'knowledge_name': k.get('knowledge_name'),
                    'total_students': len(student_list),
                    'not_learned': 0, 'in_progress': 0, 'learned': 0, 'review_needed': 0,
                    'completion_rate': 0.0, 'course_id': current_course_id
                }

    # ================= 优化点 1：MongoDB 批量查询 (解决 N+1) =================
    student_ids = [s.get('id') for s in student_list if s.get('id')]
    sis_user_ids = [s.get('sis_user_id') for s in student_list if s.get('sis_user_id')]
    
    # 一次性查出班级所有学生的详细信息
    students_db_data = {}
    if student_ids or sis_user_ids:
        db_query = {"$or": []}
        if student_ids: db_query["$or"].append({"id": {"$in": student_ids}})
        if sis_user_ids: db_query["$or"].append({"sis_user_id": {"$in": sis_user_ids}})
        
        all_students = db.students.find(db_query, {"_id": 0, "id": 1, "sis_user_id": 1, "enrolled_courses": 1})
        
        # 构建哈希表，实现 O(1) 内存检索
        for stu in all_students:
            if stu.get("id"): students_db_data[str(stu["id"])] = stu
            if stu.get("sis_user_id"): students_db_data[str(stu["sis_user_id"])] = stu

    # ================= 优化点 2：内存映射加速知识点统计 =================
    for student in student_list:
        stu_id = str(student.get('id'))
        sis_id = str(student.get('sis_user_id'))
        
        # O(1) 获取学生信息
        student_info = students_db_data.get(stu_id) or students_db_data.get(sis_id)
        if not student_info:
            for k_id in knowledge_stats: knowledge_stats[k_id]['not_learned'] += 1
            continue
            
        current_enrolled_course = next((c for c in student_info.get('enrolled_courses', []) 
                                      if str(c.get('id')).strip() == str(current_course_id).strip()), None)
                                      
        if not current_enrolled_course:
            for k_id in knowledge_stats: knowledge_stats[k_id]['not_learned'] += 1
            continue

        # 将该学生的知识点状态转为字典，避免双层嵌套循环 O(N*M)
        stu_k_map = {str(k.get('knowledge_id')).strip(): k.get('state', 'not_learned') 
                     for k in current_enrolled_course.get('knowledge_list', [])}
                     
        for k_id, stats in knowledge_stats.items():
            state = stu_k_map.get(k_id, 'not_learned')
            if state in ['in_progress', 'learned', 'review_needed']:
                stats[state] += 1
            else:
                stats['not_learned'] += 1

    # 8. 计算完成率
    total_knowledge_completion = 0
    knowledge_list_with_stats = []
    
    for k_id, stats in knowledge_stats.items():
        if stats['total_students'] > 0:
            completed_and_reviewed = stats['learned'] + stats['review_needed']
            stats['completion_rate'] = round(completed_and_reviewed / stats['total_students'] * 100, 2)
        knowledge_list_with_stats.append(stats)
        total_knowledge_completion += stats['completion_rate']
        
    overall_completion_rate = round(total_knowledge_completion / len(knowledge_list_with_stats), 2) if knowledge_list_with_stats else 0

    course_data = {
        'course_id': current_course_id,
        'course_name': current_course_name,
        'class_code': class_info.get('course_code', ''),
        'class_sis_id': class_info.get('sis_course_id', ''),
        'total_students': len(student_list),
        'knowledge_count': len(knowledge_list_with_stats),
        'overall_completion_rate': overall_completion_rate,
        'knowledge_stats': knowledge_list_with_stats
    }


    # ================= 优化点 3：多线程并发处理 Canvas API (解决串行阻塞) =================
    
    # 提取作业处理逻辑为一个独立函数
    def fetch_assignment_data(am):
        am_id = am.get('id')
        summary = get_assignment_submission_summary(current_course_id, am_id)
        all_gradable = get_gradeable_students(current_course_id, am_id)
        submissions = get_assignment_submissions(current_course_id, am_id)
        
        submitted_user_ids = {s.get('user_id') for s in submissions if s.get('workflow_state') != 'unsubmitted'}
        unsubmitted_students = [
            {"id": stu.get('id'), "display_name": stu.get('display_name')}
            for stu in all_gradable if stu.get('id') not in submitted_user_ids
        ]
        return {
            "assignment_id": am_id,
            "title": am.get('name'),
            "due_at": am.get('due_at'),
            "status": summary,
            "unsubmitted_list": unsubmitted_students
        }

    # 提取测验处理逻辑为一个独立函数
    def fetch_quiz_data(q):
        q_id = q.get('id')
        q_submissions = get_quiz_submissions(current_course_id, q_id)
        scores = [s.get('kept_score') for s in q_submissions if s.get('kept_score') is not None]
        return {
            "quiz_id": q_id,
            "title": q.get('title'),
            "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
            "submission_count": len(scores)
        }

    assignments = get_course_assignments(current_course_id)
    quizzes = get_course_quizzes(current_course_id)
    
    # 使用线程池并发请求 Canvas API（最大工作线程数建议设置在 10-20 之间）
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        canvas_assignments = list(executor.map(fetch_assignment_data, assignments))
        canvas_quizzes = list(executor.map(fetch_quiz_data, quizzes))

    # 单元学习进度 (这个API通常较快，暂保持原样)
    modules = get_course_modules(current_course_id)
    canvas_modules = [
        {"module_id": m.get('id'), "name": m.get('name'), "items_count": m.get('items_count'), "state": m.get('workflow_state')}
        for m in modules
    ]

    return jsonify({
        "course": course_data,
        "current_course_id": current_course_id,
        "current_course_name": current_course_name,
        "canvas_data": {
            "assignments": canvas_assignments,
            "quizzes": canvas_quizzes,
            "modules": canvas_modules
        },
    }), 200


@study_situation_LLM.route('/dashboard/study_situation/course/search_student')
def search_course_student():
    """查询课程信息 - 获取当前课程的知识点学习统计 (性能优化版)"""
    query = request.args.get('query', '').strip()
    studentUid = request.args.get('studentUid', '').strip()
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    # 1-4. 获取课程上下文
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程信息", "message": "请先选择课程"}), 400
    
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', '未命名课程')
    
    # 5-6. 验证 query 权限
    if query:
        is_match = str(current_course_id).strip() == query or query in str(current_course_name).strip()
        if not is_match:
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})"
            }), 403
    
    # 7. 获取课程与班级基础信息
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course or not class_info:
        return jsonify({"error": "未找到课程或班级信息"}), 404
        
    student_list = class_info.get('student_list', [])
    knowledge_stats = {}
    
    # 初始化知识点统计字典
    if course.get('knowledge_list'):
        for k in course['knowledge_list']:
            k_id = k.get('knowledge_id')
            if k_id:
                knowledge_stats[str(k_id)] = {
                    'knowledge_id': k_id,
                    'knowledge_name': k.get('knowledge_name'),
                    'total_students': len(student_list),
                    'not_learned': 0, 'in_progress': 0, 'learned': 0, 'review_needed': 0,
                    'completion_rate': 0.0, 'course_id': current_course_id
                }

    # ================= 优化点 1：MongoDB 批量查询 (解决 N+1 问题) =================
    student_ids = [s.get('id') for s in student_list if s.get('id')]
    sis_user_ids = [s.get('sis_user_id') for s in student_list if s.get('sis_user_id')]
    
    # 一次性查出班级所有学生的详细信息，存储在内存中
    students_db_data = {}
    if student_ids or sis_user_ids:
        db_query = {"$or": []}
        if student_ids: db_query["$or"].append({"id": {"$in": student_ids}})
        if sis_user_ids: db_query["$or"].append({"sis_user_id": {"$in": sis_user_ids}})
        
        all_students = db.students.find(db_query, {"_id": 0, "id": 1, "sis_user_id": 1, "enrolled_courses": 1})
        
        # 构建哈希表，实现 O(1) 内存极速检索
        for stu in all_students:
            if stu.get("id"): students_db_data[str(stu["id"])] = stu
            if stu.get("sis_user_id"): students_db_data[str(stu["sis_user_id"])] = stu

    # ================= 优化点 2：内存映射加速知识点统计 =================
    for student in student_list:
        stu_id = str(student.get('id')) if student.get('id') else None
        sis_id = str(student.get('sis_user_id')) if student.get('sis_user_id') else None
        
        # O(1) 获取学生信息，不再查询数据库
        student_info = students_db_data.get(stu_id) or students_db_data.get(sis_id)
        if not student_info:
            for k_id in knowledge_stats: knowledge_stats[k_id]['not_learned'] += 1
            continue
            
        current_enrolled_course = next((c for c in student_info.get('enrolled_courses', []) 
                                      if str(c.get('id')).strip() == str(current_course_id).strip()), None)
                                      
        if not current_enrolled_course:
            for k_id in knowledge_stats: knowledge_stats[k_id]['not_learned'] += 1
            continue

        # 将该学生的知识点状态转为字典，避免双层嵌套循环导致 O(N*M) 的时间复杂度
        stu_k_map = {str(k.get('knowledge_id')).strip(): k.get('state', 'not_learned') 
                     for k in current_enrolled_course.get('knowledge_list', [])}
                     
        for k_id, stats in knowledge_stats.items():
            state = stu_k_map.get(k_id, 'not_learned')
            if state == 'not_learned': stats['not_learned'] += 1
            elif state == 'in_progress': stats['in_progress'] += 1
            elif state == 'learned': stats['learned'] += 1
            elif state == 'review_needed': stats['review_needed'] += 1
            else: stats['not_learned'] += 1

    # 计算知识点完成率
    total_knowledge_completion = 0
    knowledge_list_with_stats = []
    
    for k_id, stats in knowledge_stats.items():
        if stats['total_students'] > 0:
            completed_and_reviewed = stats['learned'] + stats['review_needed']
            stats['completion_rate'] = round(completed_and_reviewed / stats['total_students'] * 100, 2)
        knowledge_list_with_stats.append(stats)
        total_knowledge_completion += stats['completion_rate']
        
    overall_completion_rate = round(total_knowledge_completion / len(knowledge_list_with_stats), 2) if knowledge_list_with_stats else 0

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
        'query_matched': bool(query),
        'original_query': query if query else None
    }

    if student_list:
        course_data['student_distribution'] = {
            'total': len(student_list),
            'by_knowledge_completion': calculate_student_completion_distribution(knowledge_stats, student_list)
        }

    # ================= 优化点 3：多线程并发处理 Canvas API (解决串行阻塞) =================
    
    assignments = get_course_assignments(current_course_id)
    quizzes = get_course_quizzes(current_course_id)

    # 定义提取作业的子线程任务
    def fetch_personal_assignment(am):
        am_id = am.get('id')
        submission = get_student_assignment_submission(current_course_id, am_id, studentUid) or {}
        wf_state = submission.get('workflow_state')
        return {
            "title": am.get('name'),
            "due_at": am.get('due_at'),
            "submitted": wf_state not in ['unsubmitted', 'deleted', None],
            "grade": submission.get('grade'),
            "late": submission.get('late', False)
        }

    # 定义提取测验的子线程任务
    def fetch_personal_quiz(q):
        q_id = q.get('id')
        q_sub = get_student_quiz_submissions(current_course_id, q_id, studentUid)
        score = q_sub[0].get('score') if q_sub and isinstance(q_sub, list) else None
        return {
            "title": q.get('title'),
            "score": score,
            "status": "已完成" if q_sub else "未尝试"
        }

    # 使用线程池并发发出所有 Canvas 网络请求（最大并发数为 15）
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        personal_assignments = list(executor.map(fetch_personal_assignment, assignments))
        personal_quizzes = list(executor.map(fetch_personal_quiz, quizzes))

    return jsonify({
        "course": course_data,
        "count": 1,
        "current_course_id": current_course_id,
        "current_course_name": current_course_name,
        "message": "查询成功",
        "studentUid": studentUid if studentUid else "未提供",
        "canvas_personal_data": {
            "todo_assignments": [a for a in personal_assignments if not a['submitted']],
            "finished_assignments": [a for a in personal_assignments if a['submitted']],
            "quiz_scores": personal_quizzes
        },
    }), 200

##############################################################################################################################################################








    
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
@study_situation_LLM.route('/dashboard/study_situation/course/students')
def get_course_student_status():
    """
    查询某门课程所有学生的学习情况，支持：
    - studentUid为必填参数，用于查找当前课程
    - course_query为可选参数，如果未提供则使用当前课程
    - completion_lt / completion_gt 筛选
    - 多个 knowledge_not_learned（ID 或名称，模糊匹配）
    - 返回每个学生的 已完成/未完成 知识点详情（含名称）
    """
    """查询某门课程所有学生的学习情况 (性能优化版)"""
    studentUid = request.args.get('studentUid', '').strip()
    course_query = request.args.get('course_query', '').strip()
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数", "message": "请提供用户账号"}), 400

    # 1-4. 获取并验证课程上下文
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程信息", "message": "请先在学情分析页面选择一门课程"}), 400
    
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', current_course.get('course_name', '未命名课程'))
    current_sis_course_id = current_course.get('sis_course_id', '')
    current_term_id = current_course.get('enrollment_term_id', '')
    # 5. 验证 course_query
    if course_query:
        is_matched = str(current_course_id) == course_query or \
                     (current_course_name and course_query.lower() in current_course_name.lower()) or \
                     (current_sis_course_id and course_query in current_sis_course_id)
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}'",
                "message": f"您当前可查询的课程是: {current_course_name}"
            }), 403

    # 6. 获取课程与班级信息
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course or not class_info:
        return jsonify({"error": "未找到课程或班级信息"}), 404
        
    course_code = class_info.get("course_code", "")
    actual_course_name = class_info.get("course_name", current_course_name)
    student_list = class_info.get("student_list", [])
    
    if not student_list:
        return jsonify({
            "course_id": current_course_id, "course_name": actual_course_name, "course_code": course_code,
            "total_knowledge_count": 0, "students": [], "query_matched": True,
            "studentUid": studentUid, "message": "班级中没有学生"
        }), 200

    # ================= 优化点 1：预构建知识点 Hash Map =================
    # 获取全局知识点库
    knowledges = list(db.knowledges.find({"course_code": course_code}, {"_id": 0, "knowledge_id": 1, "knowledge_name": 1}))
    knowledge_map = {str(k["knowledge_id"]): {"knowledge_name": k.get("knowledge_name", str(k["knowledge_id"])), "knowledge_id": k["knowledge_id"]} for k in knowledges}
    
    # 合并课程专有知识点
    for k in course.get('knowledge_list', []):
        k_id = str(k.get('knowledge_id'))
        if k_id and k_id not in knowledge_map:
            knowledge_map[k_id] = {'knowledge_name': k.get('knowledge_name') or k_id, 'knowledge_id': k.get('knowledge_id')}
            
    total_knowledge = len(knowledge_map)
    if total_knowledge == 0:
        return jsonify({
            "course_id": current_course_id, "course_name": actual_course_name, "course_code": course_code,
            "total_knowledge_count": 0, "students": [], "studentUid": studentUid, "message": "课程中没有知识点"
        }), 200

    # 7. 处理筛选参数 (未变，保持正则搜索逻辑)
    completion_lt = request.args.get('completion_lt', type=float)
    completion_gt = request.args.get('completion_gt', type=float)
    not_learned_params = [p.strip() for p in request.args.getlist('knowledge_not_learned') if p.strip()]
    
    target_knowledge_ids = set()
    if not_learned_params:
        knowledge_queries = []
        for param in not_learned_params:
            if param.isdigit():
                knowledge_queries.append({"knowledge_id": int(param)})
            else:
                regex_pattern = f".*{re.escape(param)}.*"
                knowledge_queries.append({"knowledge_id": {"$regex": regex_pattern, "$options": "i"}})
                knowledge_queries.append({"knowledge_name": {"$regex": regex_pattern, "$options": "i"}})
        
        if knowledge_queries:
            matched_knowledges = db.knowledges.find({"$or": knowledge_queries, "course_code": course_code}, {"_id": 0, "knowledge_id": 1})
            target_knowledge_ids = {k["knowledge_id"] for k in matched_knowledges}
            
        if not target_knowledge_ids:
            return jsonify({
                "warning": "未找到匹配的知识点", "queries": not_learned_params, "course_code": course_code,
                "course_id": current_course_id, "course_name": actual_course_name, "studentUid": studentUid,
                "available_knowledges": list(knowledge_map.values())
            }), 200

    # ================= 优化点 2：批量查询数据库 (消灭 N+1 问题) =================
    student_ids = [s.get("id") for s in student_list if s.get("id")]
    sis_user_ids = [s.get("sis_user_id") for s in student_list if s.get("sis_user_id")]
    
    db_query = {"$or": []}
    if student_ids: db_query["$or"].append({"id": {"$in": student_ids}})
    if sis_user_ids: db_query["$or"].append({"sis_user_id": {"$in": sis_user_ids}})

    # 一次性提取全班所有学生的详细数据
    all_students_db = db.students.find(db_query, {"_id": 0}) if db_query["$or"] else []
    
    # 构建内存索引 (Hash Map)，查询时间复杂度降至 O(1)
    student_db_map = {}
    for stu in all_students_db:
        if stu.get("id"): student_db_map[str(stu["id"])] = stu
        if stu.get("sis_user_id"): student_db_map[str(stu["sis_user_id"])] = stu

    # ================= 优化点 3：内存数据处理 =================
    students_data = []
    
    for student_info in student_list:
        stu_id = str(student_info.get("id")) if student_info.get("id") else None
        sis_id = str(student_info.get("sis_user_id")) if student_info.get("sis_user_id") else None
        
        if not stu_id and not sis_id: continue
        
        # 极速 O(1) 内存检索，不再向数据库发请求
        student = student_db_map.get(stu_id) or student_db_map.get(sis_id)
        if not student: continue
        
        current_enrolled_course = next((c for c in student.get("enrolled_courses", []) 
                                      if str(c.get("id")).strip() == str(current_course_id).strip()), None)
        if not current_enrolled_course: continue
        
        # 预构建该学生的知识点状态字典 O(K)
        stu_k_state_map = {str(k.get("knowledge_id")): k.get("state", "not_learned") 
                           for k in current_enrolled_course.get("knowledge_list", [])}
        
        completed_knowledges = []
        incomplete_knowledges = []
        
        # 遍历全量知识点字典，直接映射状态
        for k_id, k_info in knowledge_map.items():
            state = stu_k_state_map.get(k_id, "not_learned")
            k_detail = {"knowledge_id": k_info["knowledge_id"], "knowledge_name": k_info["knowledge_name"], "state": state}
            
            if state in ["learned", "review_needed"]:
                completed_knowledges.append(k_detail)
            else:
                incomplete_knowledges.append(k_detail)
                
        completion_rate = round((len(completed_knowledges) / total_knowledge) * 100, 2) if total_knowledge else 0
        
        # 筛选逻辑
        if completion_lt is not None and completion_rate >= completion_lt: continue
        if completion_gt is not None and completion_rate <= completion_gt: continue
        if target_knowledge_ids and not any(item["knowledge_id"] in target_knowledge_ids for item in incomplete_knowledges):
            continue
            
        students_data.append({
            "student_id": student_info.get("id"),
            "sis_user_id": student_info.get("sis_user_id"),
            "student_name": student_info.get("name") or student.get("student_name", "未知学生"),
            "completed_knowledge_count": len(completed_knowledges),
            "completion_rate": completion_rate,
            "enrollment_status": current_enrolled_course.get("enrollment_status", "active")
        })
            # "completed_knowledges": completed_knowledges,
            # "incomplete_knowledges": incomplete_knowledges,
    # 8. 返回结果
    return jsonify({
        "course_id": current_course_id,
        "course_name": actual_course_name,
        "course_code": course_code,
        "class_sis_id": class_info.get("sis_course_id", ""),
        "term_id": current_term_id,
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
        "knowledge_overview": {"total_count": total_knowledge, "knowledge_list": list(knowledge_map.values())},
        "students": students_data
    }), 200


# 查询某个课程所有知识点的学习情况
@study_situation_LLM.route('/dashboard/study_situation/course/knowledges')
def get_course_knowledge_status():
    """
    查询某门课程中知识点的学习情况，支持：
    - studentUid为必填参数，用于查找当前课程
    - course_query为可选参数，如果未提供则使用当前课程
    - completion_rate_gte / completion_rate_lte 筛选
    - 返回每个知识点的掌握学生名单（已完成 / 未完成）
    注意：直接使用courses表中的knowledge_list作为课程的全部知识点
    """
    studentUid = request.args.get('studentUid', '').strip()
    # 1. 验证 studentUid 参数
    if not studentUid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供用户账号(studentUid)以识别用户身份"
        }), 400
    # 2. 从 MongoDB 中获取用户会话信息
    current_course = None
    current_course = get_user_current_course_from_db(studentUid)
    print("!!!!get_course_knowledge_status:current_course:",current_course)
    # 未从MongoDB中找到当前课程，尝试从session获取
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
        if str(current_course_id) == str(course_query):
            is_matched = True
            print(f"通过课程ID匹配: {course_query}")
        elif current_course_name and course_query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {course_query} 匹配 {current_course_name}")
        elif current_sis_course_id and course_query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {course_query} 匹配 {current_sis_course_id}")
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
    # Step 8: 统计每个知识点的学习情况 (极致优化版)
    print("开始统计知识点学习情况...")
    print(f"筛选条件: gte={completion_rate_gte}, lte={completion_rate_lte}")
    # 1. 提取全班所有有效的 sis_user_id
    sis_user_ids = [str(s.get("sis_user_id")) for s in student_list if s.get("sis_user_id")]
    # 2. 批量查询：一次性从数据库获取所有这些学生的信息，避免在循环中查库
    students_db_data = list(db.students.find(
        {"sis_user_id": {"$in": sis_user_ids}},
        {"_id": 0, "sis_user_id": 1, "student_name": 1, "enrolled_courses": 1}
    ))
    # 3. 构建内存哈希表，实现 O(1) 查找速度
    # 格式: {'sis_user_id': student_doc}
    student_map = {str(s.get("sis_user_id")): s for s in students_db_data if s.get("sis_user_id")}

    # 4. 初始化知识点统计骨架
    knowledge_stats = {}
    for k in knowledge_list:
        k_id_str = str(k.get('knowledge_id'))
        if k_id_str == 'None':
            continue
        knowledge_stats[k_id_str] = {
            "knowledge_id": k.get('knowledge_id'),
            "knowledge_name": k.get('knowledge_name', f"知识点{k_id_str}"),
            "completed": [],
            "incomplete": []
        }

    # 5. 核心逻辑：只遍历一次学生列表，将状态分发到对应的知识点中
    for student_info in student_list:
        sis_id = str(student_info.get("sis_user_id"))
        base_name = student_info.get("name", "未知")
        # 构造一个基础的学生信息对象用于追加
        stu_record = {"sis_user_id": sis_id, "student_name": base_name}
        # 如果数据库里没有这个学生，全都算作未掌握
        if not sis_id or sis_id not in student_map:
            for k_id_str in knowledge_stats:
                knowledge_stats[k_id_str]["incomplete"].append(stu_record)
            continue
        # 获取该学生的数据库记录和姓名
        student_doc = student_map[sis_id]
        stu_record["student_name"] = student_doc.get("student_name") or base_name
        # 寻找该学生当前课程的学习记录
        enrolled_courses = student_doc.get("enrolled_courses", [])
        current_course_data = next((c for c in enrolled_courses if str(c.get("id")) == str(current_course_id)), None)
        if not current_course_data:
            # 如果没选这门课，全部知识点算作未完成
            for k_id_str in knowledge_stats:
                knowledge_stats[k_id_str]["incomplete"].append(stu_record)
            continue
        # 将该学生在该课的知识点状态转为字典，方便 O(1) 查询
        stu_k_states = {str(k.get("knowledge_id")): k.get("state", "not_learned")
                        for k in current_course_data.get("knowledge_list", [])}
        # 将该学生的状态分发给所有的知识点
        for k_id_str, stats_dict in knowledge_stats.items():
            state = stu_k_states.get(k_id_str, "not_learned")
            if state in ["learned", "review_needed"]:
                stats_dict["completed"].append(stu_record)
            else:
                stats_dict["incomplete"].append(stu_record)
    # 6. 计算完成率并应用过滤条件
    result_knowledges = []
    for k_id_str, stats_dict in knowledge_stats.items():
        comp_count = len(stats_dict["completed"])
        incomp_count = len(stats_dict["incomplete"])
        completion_rate = 0.0
        if total_students > 0:
            completion_rate = round((comp_count / total_students) * 100, 2)

        # 处理筛选逻辑 (如果被跳过则不加入最终结果)
        skip = False
        if completion_rate_gte is not None and completion_rate < float(completion_rate_gte):
            skip = True
        if not skip and completion_rate_lte is not None and completion_rate > float(completion_rate_lte):
            skip = True
        if not skip:
            result_knowledges.append({
                "knowledge_id": stats_dict["knowledge_id"],
                "knowledge_name": stats_dict["knowledge_name"],
                "completed_students_count": comp_count,
                "incomplete_students_count": incomp_count,
                "completion_rate": completion_rate,
                "total_students": total_students,
                "completed_students": stats_dict["completed"][:10], # 截断处理，防止MCP返回包过大
                "incomplete_students": stats_dict["incomplete"][:10]
            })
    print(f"统计完成，共处理{len(result_knowledges)}个符合条件的知识点")

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
        "filters": {
            "completion_rate_gte": completion_rate_gte,
            "completion_rate_lte": completion_rate_lte
        },
        "knowledge_list": result_knowledges
    }), 200


# 查询单个学生的学习情况
@study_situation_LLM.route('/dashboard/study_situation/course/student/<path:student_query>')
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
    """
    查询某学生在某课程中的学习进度 (并发与内存映射优化版)
    """
    # Step 1: 获取基础参数
    studentUid = request.args.get('studentUid', '').strip()
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数", "message": "请提供用户账号"}), 400

    # Step 2: 获取当前课程上下文
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程信息", "message": "请先选择课程"}), 404
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', current_course.get('name', ''))
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    # Step 3: 验证 course_query
    course_query = request.args.get('course_query', '').strip()
    if course_query:
        is_matched = str(current_course_id) == str(course_query) or \
                     (current_course_name and course_query.lower() in current_course_name.lower()) or \
                     (current_sis_course_id and course_query in current_sis_course_id)
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}'",
                "message": f"您当前可查询的课程是: {current_course_name}",
                "current_course": {"course_id": current_course_id, "course_name": current_course_name}
            }), 403

    try:
        current_course_id = int(current_course_id)
    except (ValueError, TypeError):
        return jsonify({"error": "课程ID格式错误"}), 400

    # Step 4-5: 获取课程与班级信息
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0})

    if not course or not class_info:
        return jsonify({"error": f"未找到ID为 {current_course_id} 的课程或班级信息"}), 404

    actual_course_name = class_info.get("course_name", course.get("course_name", f"课程 {current_course_id}"))
    course_code = class_info.get("course_code", "")
    student_list = class_info.get("student_list", [])

    # Step 6: 优化后的学生匹配逻辑 (寻找目标学生)
    matched_student_in_class = None
    student_query_lower = student_query.lower() if student_query else ""
    
    for s in student_list:
        s_id = str(s.get("id", "")).strip()
        s_sis = str(s.get("sis_user_id", "")).strip()
        s_name = s.get("student_name", "").lower()
        
        if (s_name and student_query_lower in s_name) or \
           (s_id and (student_query == s_id or student_query in s_id)) or \
           (s_sis and (student_query == s_sis or student_query in s_sis)):
            matched_student_in_class = s
            break

    student = None
    if matched_student_in_class:
        s_id = matched_student_in_class.get("id")
        s_sis = matched_student_in_class.get("sis_user_id")
        query_cond = {"$or": []}
        if s_id is not None: query_cond["$or"].extend([{"id": s_id}, {"id": str(s_id)}])
        if s_sis: query_cond["$or"].append({"sis_user_id": s_sis})
        if query_cond["$or"]:
            student = db.students.find_one(query_cond, {"_id": 0})
            
    if not student:
        # 降级：直接去库里全局搜
        fallback_query = {"$or": [
            {"student_name": {"$regex": f".*{re.escape(student_query)}.*", "$options": "i"}},
            {"sis_user_id": {"$regex": f".*{re.escape(student_query)}.*", "$options": "i"}}
        ]}
        if student_query.isdigit():
            fallback_query["$or"].extend([{"id": int(student_query)}, {"id": str(student_query)}])
        student = db.students.find_one(fallback_query, {"_id": 0})

    if not student:
        return jsonify({"error": f"未找到与 '{student_query}' 匹配的学生"}), 404

    # 提取最终的学生标识
    db_student_id = student.get("id")
    sis_user_id = student.get("sis_user_id")
    student_name = student.get("student_name", "未知学生")

    # Step 7: 检查学生是否选修了当前课程
    matched_enrolled_course = next((c for c in student.get("enrolled_courses", []) 
                                  if str(c.get("id")) == str(current_course_id)), None)
    
    if not matched_enrolled_course:
        return jsonify({
            "error": f"学生 {student_name} 未选修此课程或数据不完整",
            "student": {"student_id": db_student_id, "sis_user_id": sis_user_id, "student_name": student_name}
        }), 404

    # ================= 优化点 1：知识点映射处理 (O(1) 字典查找) =================
    # 获取课程的全局标准知识点字典
    course_k_list = course.get('knowledge_list', [])
    knowledge_name_map = {str(k.get('knowledge_id')): k.get('knowledge_name', f"知识点{k.get('knowledge_id')}") 
                          for k in course_k_list}

    # 预分配数组，单次遍历归类
    completed, review, in_progress, uncompleted = [], [], [], []
    student_k_list = matched_enrolled_course.get("knowledge_list", [])
    
    for k in student_k_list:
        k_id = str(k.get("knowledge_id"))
        state = k.get("state", "not_learned")
        detail = {
            "knowledge_id": k_id,
            "knowledge_name": knowledge_name_map.get(k_id, f"知识点{k_id}"),
            "state": state
        }
        if state == "learned": completed.append(detail)
        elif state == "review_needed": review.append(detail)
        elif state == "in_progress": in_progress.append(detail)
        else: uncompleted.append(detail)

    total_knowledge = len(course_k_list) if course_k_list else len(student_k_list)
    completed_count = len(completed) + len(review)
    progress_percentage = round((completed_count / total_knowledge * 100), 2) if total_knowledge > 0 else 0

    # ================= 优化点 2：多线程并发请求 Canvas API =================
    canvas_data = {
        "assignments": {"todo": [], "submitted": [], "summary": {"total": 0, "completed": 0, "late": 0}},
        "quizzes": {"todo": [], "finished": [], "summary": {"total": 0, "completed": 0}}
    }

    if sis_user_id:
        try:
            now = datetime.now()
            all_assignments = get_course_assignments(current_course_id)
            all_quizzes = get_course_quizzes(current_course_id)
            
            # 子线程函数：处理单个作业
            def fetch_assignment(assign):
                am_id = assign.get("id")
                # 彻底修复Bug：统一使用 sis_user_id (前提是底层函数无 sis_user_id: 前缀且通过内部ID请求，或底层带有该前缀支持学号)
                # 按照前文沟通，这里统一使用 sis_user_id
                submission = get_student_assignment_submission(current_course_id, am_id, sis_user_id) or {}
                
                wf_state = submission.get("workflow_state", "unsubmitted")
                is_submitted = wf_state in ["submitted", "graded"]
                
                due_at_str = assign.get("due_at")
                remaining_time, is_late = "无截止日期", False
                
                if due_at_str:
                    try:
                        due_date = datetime.fromisoformat(due_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        diff = due_date - now
                        if diff.total_seconds() > 0:
                            remaining_time = f"剩余 {diff.days} 天 {diff.seconds // 3600} 小时"
                        else:
                            remaining_time = "已逾期"
                            is_late = True
                    except Exception:
                        remaining_time = "格式错误"

                return {
                    "id": am_id,
                    "title": assign.get("name"),
                    "due_at": due_at_str,
                    "remaining_time": remaining_time,
                    "points_possible": assign.get("points_possible"),
                    "score": submission.get("score"),
                    "status": "已提交" if is_submitted else ("已逾期" if is_late else "待完成"),
                    "is_submitted": is_submitted,
                    "is_late": is_late
                }

            # 子线程函数：处理单个测验
            def fetch_quiz(quiz):
                q_id = quiz.get("id")
                # 修复Bug：使用 sis_user_id 替换未定义的 target_canvas_id
                q_subs = get_student_quiz_submissions(current_course_id, q_id, sis_user_id)
                latest_sub = q_subs[0] if q_subs and isinstance(q_subs, list) else None
                is_done = bool(latest_sub)
                
                due_at_str = quiz.get("due_at")
                remaining_time = "无截止日期"
                if due_at_str:
                    try:
                        due_date = datetime.fromisoformat(due_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        remaining_time = f"剩余 {(due_date - now).days} 天" if (due_date - now).total_seconds() > 0 else "已截止"
                    except Exception:
                        remaining_time = "格式错误"

                return {
                    "id": q_id,
                    "title": quiz.get("title"),
                    "due_at": due_at_str,
                    "remaining_time": remaining_time,
                    "score": latest_sub.get("kept_score") if is_done else None,
                    "points_possible": quiz.get("points_possible"),
                    "status": "已参加" if is_done else "未参加",
                    "is_done": is_done
                }

            # 启动线程池并发拉取 (极大缩短网络等待时间)
            with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
                processed_assignments = list(executor.map(fetch_assignment, all_assignments))
                processed_quizzes = list(executor.map(fetch_quiz, all_quizzes))

            # 将并发处理的结果分类存入 canvas_data
            for am_data in processed_assignments:
                canvas_data["assignments"]["summary"]["total"] += 1
                if am_data.pop("is_submitted"):  # 移除控制标记
                    canvas_data["assignments"]["submitted"].append(am_data)
                    canvas_data["assignments"]["summary"]["completed"] += 1
                else:
                    if am_data.pop("is_late"): canvas_data["assignments"]["summary"]["late"] += 1
                    canvas_data["assignments"]["todo"].append(am_data)

            for q_data in processed_quizzes:
                canvas_data["quizzes"]["summary"]["total"] += 1
                if q_data.pop("is_done"):
                    canvas_data["quizzes"]["finished"].append(q_data)
                    canvas_data["quizzes"]["summary"]["completed"] += 1
                else:
                    canvas_data["quizzes"]["todo"].append(q_data)

        except Exception as e:
            import traceback
            print(f"Canvas API 并发整合异常:\n{traceback.format_exc()}")
            canvas_data["error"] = "教学平台数据同步失败"

    # Step 9: 返回结果
    return jsonify({
        "student": {
            "student_id": db_student_id,
            "sis_user_id": sis_user_id,
            "student_name": student_name,
            "is_in_class": True,
            "enrollment_status": matched_enrolled_course.get("enrollment_status", "active")
        },
        "course": {
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code
        },
        "progress": {
            "total_knowledges": total_knowledge,
            "completed_knowledges_count": len(completed),
            "review_needed_knowledges_count": len(review),
            "in_progress_knowledges_count": len(in_progress),
            "uncompleted_knowledges_count": len(uncompleted),
            "progress_percentage": progress_percentage
        },
        "knowledge_details": {
            "completed_knowledges": completed,
            "review_needed_knowledges": review,
            "in_progress_knowledges": in_progress,
            "uncompleted_knowledges": uncompleted
        },
        "canvas_learning": canvas_data,
        "last_updated": datetime.now().isoformat()
    }), 200
    
    
    
# 查询单个知识点的学习情况
@study_situation_LLM.route('/dashboard/study_situation/course/knowledge/<path:knowledge_query>')
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
    """
    查询某个知识点在指定课程中的学习情况 (极速优化版)
    """
    studentUid = request.args.get('studentUid', '').strip()
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数", "message": "请提供用户账号"}), 400

    # 1-4. 获取并验证课程上下文
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程信息", "message": "请先在学情分析页面选择一门课程"}), 400
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', '')
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    if not current_course_id:
        return jsonify({"error": "当前课程信息不完整"}), 400
    
    # Step 3: 验证 course_query
    query = request.args.get('course_query', '').strip()
    if query:
        is_matched = str(current_course_id) == str(query) or \
                     (current_course_name and query.lower() in current_course_name.lower()) or \
                     (current_sis_course_id and query in current_sis_course_id)
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name}"
            }), 403
            
    # Step 4: 查询课程信息
    try:
        current_course_id = int(current_course_id)
    except ValueError:
        return jsonify({"error": "课程ID格式错误"}), 400
    
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_list": 1}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({"error": f"未找到ID为 {current_course_id} 的课程信息"}), 404
    
    actual_course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code: break
    
    # Step 5: 获取班级信息
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1})
    if not class_info:
        return jsonify({"error": f"未找到ID为 {current_course_id} 的班级信息"}), 404
    
    actual_course_name = class_info.get("course_name", actual_course_name)
    student_list = class_info.get("student_list", [])
    course_code = course_code or class_info.get("course_code", "")
    
    total_students = len(student_list)
    if total_students == 0:
        return jsonify({
            "knowledge_query": knowledge_query, "course_id": current_course_id, "course_name": actual_course_name,
            "total_students": 0, "query_matched": True, "studentUid": studentUid, "message": "班级中没有学生"
        }), 200

    # Step 6: 查找知识点信息
    knowledge = None
    knowledge_id = None
    knowledge_name = None
    course_knowledge_list = course.get('knowledge_list', [])
    
    for k in course_knowledge_list:
        k_id = k.get('knowledge_id')
        if str(k_id) == knowledge_query:
            knowledge = k
            break
            
    if not knowledge:
        knowledge_regex = re.compile(f".*{re.escape(knowledge_query)}.*", re.IGNORECASE)
        for k in course_knowledge_list:
            if knowledge_regex.search(str(k.get('knowledge_id'))) or knowledge_regex.search(k.get('knowledge_name', '')):
                knowledge = k
                break
                
    if not knowledge:
        k_query = {"course_code": course_code}
        if knowledge_query.isdigit():
            k_query["knowledge_id"] = int(knowledge_query)
            knowledge = db.knowledges.find_one(k_query, {"_id": 0})
        if not knowledge:
            k_id_regex = re.compile(f".*{re.escape(knowledge_query)}.*", re.IGNORECASE)
            knowledge = db.knowledges.find_one({
                "$or": [{"knowledge_id": {"$regex": k_id_regex.pattern, "$options": "i"}},
                        {"knowledge_name": {"$regex": k_id_regex.pattern, "$options": "i"}}],
                "course_code": course_code
            }, {"_id": 0})
    
    if not knowledge:
        return jsonify({"error": f"在课程中未找到与 '{knowledge_query}' 匹配的知识点"}), 404
        
    knowledge_id = knowledge.get('knowledge_id')
    knowledge_name = knowledge.get('knowledge_name', f"知识点{knowledge_id}")

    # ================= 优化点 1：预构建 O(1) 的班级集合 =================
    # 用于加速访问记录检查，避免 O(N*M) 的双重嵌套循环
    class_sis_ids_set = {str(s.get("sis_user_id")) for s in student_list if s.get("sis_user_id")}

    # ================= 优化点 2：MongoDB 批量查询 + $elemMatch =================
    # 消除 N+1 查询炸弹，同时过滤掉不相关的课程以节省大量内存
    student_ids = [s.get("id") for s in student_list if s.get("id")]
    sis_user_ids = list(class_sis_ids_set)
    
    db_query = {"$or": []}
    if student_ids: db_query["$or"].append({"id": {"$in": student_ids}})
    if sis_user_ids: db_query["$or"].append({"sis_user_id": {"$in": sis_user_ids}})

    # 使用 $elemMatch 仅拉取当前课程的数据
    students_db_data = list(db.students.find(
        db_query, 
        {"_id": 0, "id": 1, "sis_user_id": 1, "student_name": 1, 
         "enrolled_courses": {"$elemMatch": {"id": current_course_id}}}
    )) if db_query["$or"] else []

    # ================= 优化点 3：内存哈希映射 =================
    student_map = {}
    for stu in students_db_data:
        if stu.get("id"): student_map[str(stu["id"])] = stu
        if stu.get("sis_user_id"): student_map[str(stu["sis_user_id"])] = stu

    # Step 7: 统计学生掌握情况 (极速版 O(N))
    completed_students = []
    incomplete_students = []
    
    for student_info in student_list:
        stu_id = str(student_info.get("id")) if student_info.get("id") else None
        sis_id = str(student_info.get("sis_user_id")) if student_info.get("sis_user_id") else None
        
        if not stu_id and not sis_id: continue
        
        # O(1) 内存直接读取
        student_doc = student_map.get(stu_id) or student_map.get(sis_id)
        
        display_name = student_info.get("student_name") or "未知"
        if student_doc and student_doc.get("student_name"):
            display_name = student_doc.get("student_name")
            
        record = {
            "student_id": student_info.get("id"),
            "sis_user_id": student_info.get("sis_user_id"),
            "student_name": display_name
        }
        
        is_completed = False
        if student_doc and student_doc.get("enrolled_courses"):
            # 由于使用了 $elemMatch，这里只会有1门课，或者为空
            course_data = student_doc["enrolled_courses"][0]
            
            for k_item in course_data.get("knowledge_list", []):
                if str(k_item.get("knowledge_id")) == str(knowledge_id):
                    if k_item.get("state") in ["learned", "review_needed"]:
                        is_completed = True
                    break
                    
        if is_completed:
            completed_students.append(record)
        else:
            incomplete_students.append(record)
            
    # Step 8: 获取访问记录统计
    now = datetime.now(timezone.utc)
    one_day_ago = now - timedelta(days=1)
    one_week_ago = now - timedelta(weeks=1)
    one_month_ago = now - timedelta(days=30)

    daily_visits, weekly_visits, monthly_visits = set(), set(), set()
    
    knowledge_doc = db.knowledges.find_one(
        {"knowledge_id": knowledge_id, "course_code": course_code},
        {"_id": 0, "access_records": 1}
    )
    
    if knowledge_doc and "access_records" in knowledge_doc:
        for record in knowledge_doc["access_records"]:
            try:
                record_sis_user_id = str(record.get("sis_user_id", ""))
                if not record_sis_user_id: continue
                
                # ================= 优化点 4：O(1) 极速校验 =================
                if record_sis_user_id not in class_sis_ids_set:
                    continue
                
                access_time = None
                access_time_data = record.get("access_time", {})
                
                date_str = None
                if isinstance(access_time_data, dict) and "$date" in access_time_data:
                    date_str = access_time_data["$date"]
                elif isinstance(access_time_data, str):
                    date_str = access_time_data
                    
                if date_str:
                    t = parser.isoparse(date_str.replace("Z", "+00:00"))
                    access_time = t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t
                
                if access_time:
                    if access_time > one_day_ago: daily_visits.add(record_sis_user_id)
                    if access_time > one_week_ago: weekly_visits.add(record_sis_user_id)
                    if access_time > one_month_ago: monthly_visits.add(record_sis_user_id)
                        
            except Exception as e:
                continue

    # Step 9: 返回结果
    return jsonify({
        "knowledge": {
            "knowledge_id": knowledge_id, "knowledge_name": knowledge_name,
            "course_id": current_course_id, "course_name": actual_course_name, "course_code": course_code
        },
        "total_students": total_students,
        "completed_students_count": len(completed_students),
        "completed_students": completed_students[:100], 
        "uncompleted_students_count": len(incomplete_students),
        "uncompleted_students": incomplete_students[:100], 
        "completion_rate": round(len(completed_students) / total_students * 100, 2) if total_students > 0 else 0,
        "recent_visits": {
            "last_day": len(daily_visits), "last_week": len(weekly_visits), "last_month": len(monthly_visits),
            "daily_visits_rate": round(len(daily_visits) / total_students * 100, 2) if total_students > 0 else 0,
            "weekly_visits_rate": round(len(weekly_visits) / total_students * 100, 2) if total_students > 0 else 0,
            "monthly_visits_rate": round(len(monthly_visits) / total_students * 100, 2) if total_students > 0 else 0
        },
        "studentUid": studentUid,
        "last_updated": datetime.now().isoformat()
    }), 200


# 查询单个学生的学习情况
@study_situation_LLM.route('/dashboard/study_situation/course/student/myprogress')
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
    """
    查询学生在某课程中的学习进度（学生自查询接口 - 并发优化版）
    """
    # Step 1: 获取studentUid参数（当前用户的ID）
    studentUid = request.args.get('studentUid', '').strip()
    student_query = request.args.get('student_query', '').strip()
    
    if not studentUid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供当前用户的studentUid参数"
        }), 400
    
    print(f"获取学生进度请求 - 当前用户ID: {studentUid}, 目标学生查询: {student_query}")
    
    # 2. 从 MongoDB 中获取用户会话信息
    current_course = get_user_current_course_from_db(studentUid) or session.get('current_course')
    
    # 4. 如果仍然没有当前课程，返回错误
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": "请先在学情分析页面选择一门课程"
        }), 400
    
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
    if course_query_param:
        is_matched = False
        if str(current_course_id) == str(course_query_param) or \
           (current_course_name and course_query_param.lower() in current_course_name.lower()) or \
           (current_sis_course_id and course_query_param in current_sis_course_id):
            is_matched = True
            
        if not is_matched:
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
    
    course = db.courses.find_one({"courses_list.class_list.id": current_course_id}, {"_id": 0, "course_name": 1, "courses_list": 1, "knowledge_count": 1, "knowledge_list": 1}) or \
             db.courses.find_one({"id": current_course_id}, {"_id": 0})
    
    if not course:
        return jsonify({"error": f"未找到ID为 {current_course_id} 的课程信息", "current_course_id": current_course_id}), 404
    
    course_name = course.get("course_name", f"课程 {current_course_id}")
    course_code = None
    sis_course_id = None
    term_id = None
    
    for course_item in course.get('courses_list', []):
        for class_item in course_item.get('class_list', []):
            if class_item.get('id') == current_course_id:
                course_code = course_item.get('course_code')
                sis_course_id = class_item.get('sis_course_id')
                term_id = class_item.get('enrollment_term_id')
                break
        if course_code: break
    
    # Step 5: 获取班级信息以验证学生是否在班级中
    class_info = db.classes.find_one({"id": current_course_id}, {"_id": 0, "course_code": 1, "course_name": 1, "sis_course_id": 1, "student_list": 1})
    
    if not class_info:
        return jsonify({
            "error": f"未找到ID为 {current_course_id} 的班级信息",
            "course_id": current_course_id,
            "course_name": course_name,
            "course_code": course_code
        }), 404
    
    actual_course_name = class_info.get("course_name", course_name)
    student_list = class_info.get("student_list", [])
    course_code = course_code or class_info.get("course_code", "")
    
    # ========== Step 6: 验证当前用户在当前课程中 ==========
    current_user_info = None
    for student_info in student_list:
        if str(student_info.get("sis_user_id")) == str(studentUid) or str(student_info.get("id")) == str(studentUid):
            current_user_info = student_info
            break
    
    if not current_user_info:
        return jsonify({
            "error": f"用户 {studentUid} 不在课程 '{actual_course_name}' 的学生列表中",
            "message": "您没有权限查询此课程中的学生信息",
            "course_name": actual_course_name,
            "course_id": current_course_id,
            "studentUid": studentUid
        }), 403

    current_user_id = current_user_info.get("id")
    current_user_sis_id = current_user_info.get("sis_user_id")
    current_user_name = current_user_info.get("student_name", "")
    
    # ========== Step 7: 查询当前用户的详细信息 ==========
    user_query_conditions = {}
    if current_user_id:
        user_query_conditions["$or"] = [{"id": current_user_id}, {"id": str(current_user_id)}]
    elif current_user_sis_id:
        user_query_conditions["sis_user_id"] = current_user_sis_id
    
    current_user = db.students.find_one(user_query_conditions, {"_id": 0})
    
    if not current_user:
        return jsonify({
            "error": "用户信息不完整",
            "message": f"未找到用户 {studentUid} 的详细信息",
            "studentUid": studentUid
        }), 404
    
    # ========== Step 8: 验证student_query参数（如果存在） ==========
    match_reason = "默认查询当前用户"
    if student_query and student_query.strip():
        current_user_db_id = current_user.get("id")
        current_user_db_sis = current_user.get("sis_user_id")
        current_user_db_name = current_user.get("student_name", "")
        
        is_matched = False
        query_str = str(student_query).strip()
        
        if current_user_db_name and query_str.lower() in current_user_db_name.lower():
            is_matched, match_reason = True, "姓名模糊匹配"
        elif current_user_db_id is not None and (query_str == str(current_user_db_id).strip() or (query_str.isdigit() and str(current_user_db_id).isdigit() and int(query_str) == int(current_user_db_id))):
            is_matched, match_reason = True, "ID精确匹配"
        elif current_user_db_sis and query_str == str(current_user_db_sis).strip():
            is_matched, match_reason = True, "SIS精确匹配"
        
        if not is_matched:
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
    
    # ========== Step 9: 检查当前用户是否选修了当前课程 ==========
    matched_enrolled_course = next((c for c in current_user.get("enrolled_courses", []) if str(c.get("id")) == str(current_course_id)), None)
    
    if not matched_enrolled_course:
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
            "studentUid": studentUid,
            "query_key": course_query_param if course_query_param else "当前课程",
            "is_in_class": True,
            "has_enrolled": False,
            "suggestion": "您在班级名单中，但尚未在系统中选修此课程"
        }), 200
    
    # ========== Step 10: 获取用户的知识点学习情况 (字典映射加速) ==========
    knowledge_list = matched_enrolled_course.get("knowledge_list", [])
    knowledge_name_map = {str(k.get('knowledge_id')): k.get('knowledge_name', f"知识点{k.get('knowledge_id')}") 
                          for k in course.get('knowledge_list', [])}
    
    completed_knowledges, uncompleted_knowledges, in_progress_knowledges, review_needed_knowledges = [], [], [], []
    
    for k_item in knowledge_list:
        k_id = k_item.get("knowledge_id")
        state = k_item.get("state", "not_learned")
        detail = {
            "knowledge_id": k_id,
            "knowledge_name": knowledge_name_map.get(str(k_id), f"知识点{k_id}"),
            "state": state
        }
        if state == "learned": completed_knowledges.append(detail)
        elif state == "review_needed": review_needed_knowledges.append(detail)
        elif state == "in_progress": in_progress_knowledges.append(detail)
        else: uncompleted_knowledges.append(detail)
    
    total_knowledge = len(course.get('knowledge_list', [])) if course.get('knowledge_list') else len(knowledge_list)
    completed_count = len(completed_knowledges) + len(review_needed_knowledges)
    progress_percentage = round((completed_count / total_knowledge * 100), 2) if total_knowledge > 0 else 0
    
    # ========== Step 11: 整合 Canvas 个人实时数据 (多线程并发优化) ==========
    canvas_personal_data = {
        "assignments": {"todo": [], "submitted": [], "summary": {"total": 0, "completed": 0, "late": 0, "late_unsubmitted": 0}},
        "quizzes": {"todo": [], "finished": [], "summary": {"total": 0, "completed": 0}}
    }
    
    if studentUid and current_course_id:
        try:
            now = datetime.now()
            all_assignments = get_course_assignments(current_course_id)
            all_quizzes = get_course_quizzes(current_course_id)

            # --- 定义并行处理作业的函数 ---
            def process_assignment(assign):
                am_id = assign.get("id")
                # 严格使用 studentUid (sis_user_id) 进行请求
                submission = get_student_assignment_submission(current_course_id, am_id, studentUid) or {}
                
                wf_state = submission.get("workflow_state", "unsubmitted")
                is_submitted = wf_state not in ["unsubmitted", "deleted"]
                
                due_at_str = assign.get("due_at")
                remaining_time, is_late = "无截止日期", False
                
                if due_at_str:
                    try:
                        due_date = datetime.fromisoformat(due_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                        diff = due_date - now
                        if diff.total_seconds() > 0:
                            remaining_time = f"剩余 {diff.days} 天 {diff.seconds // 3600} 小时"
                        else:
                            remaining_time = "已逾期"
                            is_late = True
                    except Exception:
                        pass

                return {
                    "id": am_id,
                    "title": assign.get("name"),
                    "due_at": due_at_str,
                    "remaining_time": remaining_time,
                    "points_possible": assign.get("points_possible"),
                    "score": submission.get("score"),
                    "status": "已提交" if is_submitted else ("已逾期" if is_late else "待完成"),
                    "is_submitted": is_submitted,
                    "is_late": is_late
                }

            # --- 定义并行处理测验的函数 ---
            def process_quiz(quiz):
                q_id = quiz.get("id")
                # 严格使用 studentUid (sis_user_id) 替换错误的 target_canvas_id
                q_subs = get_student_quiz_submissions(current_course_id, q_id, studentUid)
                latest_sub = q_subs[0] if q_subs and isinstance(q_subs, list) else None
                is_done = bool(latest_sub)
                
                q_due_at = quiz.get("due_at")
                q_remaining = "无截止日期"
                if q_due_at:
                    try:
                        q_due_date = datetime.fromisoformat(q_due_at.replace('Z', '+00:00')).replace(tzinfo=None)
                        q_diff = q_due_date - now
                        q_remaining = f"剩余 {q_diff.days} 天 {q_diff.seconds // 3600} 小时" if q_diff.total_seconds() > 0 else "已截止"
                    except Exception:
                        pass

                return {
                    "id": q_id,
                    "title": quiz.get("title"),
                    "due_at": q_due_at,
                    "remaining_time": q_remaining,
                    "score": latest_sub.get("kept_score") if is_done else None,
                    "points_possible": quiz.get("points_possible"),
                    "status": "已参加" if is_done else "未参加",
                    "is_done": is_done
                }

            # --- 启动线程池并发请求 ---
            with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
                processed_assignments = list(executor.map(process_assignment, all_assignments))
                processed_quizzes = list(executor.map(process_quiz, all_quizzes))

            # --- 汇总结果 ---
            for am in processed_assignments:
                canvas_personal_data["assignments"]["summary"]["total"] += 1
                if am.pop("is_submitted"):
                    canvas_personal_data["assignments"]["submitted"].append(am)
                    canvas_personal_data["assignments"]["summary"]["completed"] += 1
                else:
                    if am.pop("is_late"): canvas_personal_data["assignments"]["summary"]["late_unsubmitted"] += 1
                    canvas_personal_data["assignments"]["todo"].append(am)

            for q in processed_quizzes:
                canvas_personal_data["quizzes"]["summary"]["total"] += 1
                if q.pop("is_done"):
                    canvas_personal_data["quizzes"]["finished"].append(q)
                    canvas_personal_data["quizzes"]["summary"]["completed"] += 1
                else:
                    canvas_personal_data["quizzes"]["todo"].append(q)

        except Exception as e:
            import traceback
            print(f"Canvas 并发处理解析失败:\n{traceback.format_exc()}")
            canvas_personal_data["error"] = "Canvas数据部分同步失败"

    # Step 12: 返回结果
    return jsonify({
        "student": {
            "student_id": current_user_id,
            "sis_user_id": current_user_sis_id,
            "student_name": current_user_name,
            "is_in_class": True,
            "enrollment_status": matched_enrolled_course.get("enrollment_status", "active"),
            "match_method": match_reason
        },
        "course": {
            "course_id": current_course_id,
            "course_name": actual_course_name,
            "course_code": course_code,
            "class_sis_id": sis_course_id,
            "term_id": term_id,
            "query_key": course_query_param if course_query_param else "当前课程",
            "query_matched": True if not course_query_param else True,
            "note": f"查询用户 {studentUid} 在课程 '{actual_course_name}' 中的学习进度"
        },
        "studentUid": studentUid,
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
        "canvas_stats": canvas_personal_data,
        "last_updated": datetime.now().isoformat()
    }), 200



@study_situation_LLM.route('/dashboard/study_situation/chat_archive')
def get_chat_archive_status():
    """
    查询用户在当前课程下的交互档案
    - studentUid: 必填，传入的是用户的教务 ID (sis_id)
    
    业务流：
    1. 使用 studentUid 匹配 user_sessions 表中的 sis_id，获取其系统内部唯一 username 以及当前课程。
    2. 使用解析出的 username 去匹配 chat_records 表中的 student_id。
    3. 提取对应的课程智能体交互数据。
    """
    # 这里的参数名保持跟之前一致，但物理意义上它是 sis_id
    sis_id_query = request.args.get('studentUid', '').strip()

    # 1. 验证参数
    if not sis_id_query:
        return jsonify({
            "error": "缺少必要参数",
            "message": "请提供 studentUid 参数以识别用户身份"
        }), 400

    try:
        # ================= 🚀 核心逻辑 1：通过 sis_id 换取内部系统的唯一 username =================
        # 同时从 session 集合记录里拿出来他当前的 current_course 信息
        user_session_doc = db.user_sessions.find_one(
            {"sis_id": sis_id_query},
            {"_id": 0, "username": 1, "current_course": 1}
        )

        if not user_session_doc:
            return jsonify({
                "error": "未找到用户会话",
                "message": f"未在活跃会话库中检索到教务学号为 '{sis_id_query}' 的用户，请确认该用户是否已登录系统"
            }), 444

        target_username = user_session_doc.get("username")
        current_course = user_session_doc.get("current_course", {})
        course_title = current_course.get('name') or current_course.get('course_name')

        if not target_username:
            return jsonify({
                "error": "用户信息不完整",
                "message": "在会话记录中未找到关联的系统内部用户名(username)"
            }), 500

        if not course_title:
            return jsonify({
                "error": "当前课程未指定",
                "message": f"未识别到用户账号({target_username})当前的活跃课程，请让其先在学情页面选择一门课程"
            }), 404

        core_course_name = str(course_title).strip()
        print(f"🔗 账号映射对齐成功: 教务学号({sis_id_query}) -> 内部用户名({target_username}) | 当前核心课程: '{core_course_name}'")

        # ================= 🚀 核心逻辑 2：安全可靠的正则模糊匹配资源 =================
        # 构造不区分大小写的正则表达式：匹配包含“核心课程名”的任意资源名称 (解决带书名号/版本号不匹配问题)
        resource_regex = re.compile(f".*{re.escape(core_course_name)}.*", re.IGNORECASE)

        # 使用映射出来的 target_username 作为 student_id 查库
        archive_doc = db.chat_records.find_one(
            {
                "student_id": target_username,
                "chat_record.resource_name": {"$regex": resource_regex}
            },
            {"_id": 0}
        )

        if not archive_doc or not archive_doc.get('chat_record'):
            return jsonify({
                "error": "未找到相关学情档案",
                "message": f"用户({target_username})在课程 '{core_course_name}' 下暂无任何智能体聊天交互历史",
                "studentUid": sis_id_query,
                "username": target_username,
                "core_course_name": core_course_name
            }), 404

        # ================= 🚀 核心逻辑 3：内存动态精准过滤 =================
        target_record = None
        for record in archive_doc.get('chat_record', []):
            r_name = record.get('resource_name', '')
            if core_course_name.lower() in r_name.lower():
                target_record = record
                break

        if not target_record:
            return jsonify({
                "error": "匹配失效",
                "message": f"在数据库交互列表中未找到与核心词 '{core_course_name}' 精准匹配的资源项"
            }), 404

        # 4. 提取匹配的数据节点结构
        raw_interactions = target_record.get('raw_interactions', [])
        processed_insights = target_record.get('processed_insights', {})
        resource_history = target_record.get('resource', [])

        knowledge_points = processed_insights.get('knowledge_points', [])
        intents = processed_insights.get('intents', [])

        # 计算概要统计摘要
        summary = {
            "total_questions": len(raw_interactions),
            "unique_knowledge_count": len(knowledge_points),
            "total_resource_clicks": sum(item.get('click_count', 0) for item in resource_history),
            "is_analysis_ready": archive_doc.get('has_unprocessed') == "No"
        }

        # 5. 整合并组装格式化返回
        return jsonify({
            "sis_id": sis_id_query,
            "student_id": target_username,                               # 系统聊天室对应的真正的独立加密/数字 username
            "derived_course_name": core_course_name,                     # 系统自动推导出的课程名
            "matched_resource_name": target_record.get('resource_name'), # 数据库中带书名号/版本号的真实名称
            "summary": summary,
            "last_processed_time": archive_doc.get('last_processed_time'),
            "has_unprocessed": archive_doc.get('has_unprocessed'),
            
            "details": {
                "raw_interactions": raw_interactions[-20:], # 截断处理，防止大模型/前端包体过大
                "knowledge_points": knowledge_points,
                "intents": intents,
                "resource": resource_history
            },
            
            "query_info": {
                "note": f"成功跨会话表打通教务标识并对齐学情交互档案",
                "timestamp": datetime.now().isoformat()
            }
        }), 200

    except Exception as e:
        print(f"查询 chat_records 核心链路异常:\n{traceback.format_exc()}")
        return jsonify({
            "error": "服务器内部错误",
            "message": str(e)
        }), 500
# @study_situation_LLM.route('/dashboard/study_situation/chat_archive')
# def get_chat_archive_status():
#     """
#     查询用户在特定资源来源(resource_name)下的所有交互档案
#     - studentUid: 必填，用户ID
#     - resource_name: 必填，课程名称/来源名称 (例如: '流程图')
    
#     返回数据包括：
#     - raw_interactions: 原始对话列表
#     - processed_insights: AI提取的知识点统计和意图分布
#     - resource: 资料查看历史、点击数及反馈
#     """
#     student_uid = request.args.get('studentUid', '').strip()
#     resource_name = request.args.get('resource_name', '').strip()

#     # 1. 参数验证
#     if not student_uid or not resource_name:
#         return jsonify({
#             "error": "缺少必要参数",
#             "message": "请同时提供 studentUid 和 resource_name"
#         }), 400

#     print(f"查询用户档案交互 - UID: {student_uid}, 来源: {resource_name}")

#     try:
#         # 2. 从 MongoDB 查询 chat_records 集合
#         # 使用 $elemMatch 过滤出特定的 student_id 和对应的 resource_name
#         archive = db.chat_records.find_one(
#             {
#                 "student_id": student_uid,
#                 "chat_record.resource_name": resource_name
#             },
#             {
#                 "_id": 0,
#                 "has_unprocessed": 1,
#                 "last_processed_time": 1,
#                 "chat_record.$": 1  # 关键：只返回匹配 resource_name 的那一个数组元素
#             }
#         )

#         if not archive or not archive.get('chat_record'):
#             return jsonify({
#                 "error": "未找到相关档案",
#                 "message": f"用户 {student_uid} 在来源 '{resource_name}' 下暂无交互记录",
#                 "studentUid": student_uid,
#                 "resource_name": resource_name
#             }), 404

#         # 3. 提取匹配的数据节点
#         # 因为使用了 "chat_record.$"，匹配的项在数组的第一位
#         target_record = archive['chat_record'][0]
        
#         raw_interactions = target_record.get('raw_interactions', [])
#         processed_insights = target_record.get('processed_insights', {})
#         resource_history = target_record.get('resource', [])

#         # 4. 数据统计与格式化
#         knowledge_points = processed_insights.get('knowledge_points', [])
#         intents = processed_insights.get('intents', [])

#         # 计算一些摘要信息
#         summary = {
#             "total_questions": len(raw_interactions),
#             "unique_knowledge_count": len(knowledge_points),
#             "total_resource_clicks": sum(item.get('click_count', 0) for item in resource_history),
#             "is_analysis_ready": archive.get('has_unprocessed') == "No"
#         }

#         # 5. 返回结果
#         return jsonify({
#             "student_id": student_uid,
#             "resource_name": resource_name,
#             "summary": summary,
#             "last_processed_time": archive.get('last_processed_time'),
#             "has_unprocessed": archive.get('has_unprocessed'),
            
#             # 详细数据部分
#             "details": {
#                 "raw_interactions": raw_interactions[-20:], # 默认只返回最近20条原始记录，防止数据量过大
#                 "knowledge_points": knowledge_points,
#                 "intents": intents,
#                 "resource": resource_history
#             },
            
#             "query_info": {
#                 "note": f"成功获取学生 {student_uid} 关于 '{resource_name}' 的学情档案",
#                 "timestamp": datetime.now().isoformat()
#             }
#         }), 200

#     except Exception as e:
#         print(f"查询 chat_records 时出错: {str(e)}")
#         return jsonify({
#             "error": "服务器内部错误",
#             "message": str(e)
#         }), 500



##############################################################################################################
@study_situation_LLM.route('/dashboard/study_situation/assignment/search')
def search_assignments_detail():
    """查询作业详细情况接口"""
    studentUid = request.args.get('studentUid', '').strip()
    query = request.args.get('query', '').strip()  # 作业名称模糊匹配
    course_query = request.args.get('course_query', '').strip() # 课程匹配
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    # 1. 获取当前课程上下文
    current_course = get_user_current_course_from_db(studentUid)
    if not current_course:
        current_course = session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程，请先选择课程"}), 400
    
    # 优先使用 sis_course_id (Canvas ID)，如果没有则用 course_id
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', current_course.get('name', ''))
    current_sis_course_id = current_course.get('sis_course_id', '')
    # 2. 验证 course_query (逻辑参考知识点查询)
    if course_query:
        is_matched = False
        if str(current_course_id) == str(course_query):
            is_matched = True
        elif current_course_name and course_query.lower() in current_course_name.lower():
            is_matched = True
        elif current_sis_course_id and course_query in current_sis_course_id:
            is_matched = True
            
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}' 的作业信息",
                "message": f"您当前可查询的课程是: {current_course_name}",
                "current_course": {"course_id": current_course_id, "course_name": current_course_name}
            }), 403
    try:
        # 2. 获取课程所有作业
        all_assignments = get_course_assignments(current_course_id)
        
        # 3. 根据 query 进行过滤
        matched_assignments = []
        if query:
            matched_assignments = [a for a in all_assignments if query.lower() in a.get('name', '').lower()]
            if not matched_assignments:
                return jsonify({"message": f"未找到匹配 '{query}' 的作业"}), 404
        else:
            matched_assignments = all_assignments

        # 4. 组装详细数据
        results = []
        # 获取全班注册名单用于比对未提交人数
        enrollments = get_course_enrollments(current_course_id)
        all_students = [e for e in enrollments if e.get('type') == 'StudentEnrollment']
        
        for am in matched_assignments:
            am_id = am.get('id')
            # 获取提交摘要
            summary = get_assignment_submission_summary(current_course_id, am_id)
            # 获取所有提交详情
            submissions = get_assignment_submissions(current_course_id, am_id)
            
            # 统计名单
            submitted_ids = {s.get('user_id') for s in submissions if s.get('workflow_state') != 'unsubmitted'}
            unsubmitted_students = [
                {"name": s.get('user', {}).get('short_name') or s.get('user_id'), "id": s.get('user_id')}
                for s in all_students if s.get('user_id') not in submitted_ids
            ]
            
            # 统计得分与低分名单 (假设满分60%以下为低分)
            scores = [s.get('score') for s in submissions if s.get('score') is not None]
            points_possible = am.get('points_possible') or 100
            low_score_students = [
                {"name": s.get('user', {}).get('short_name'), "score": s.get('score')}
                for s in submissions if s.get('score') is not None and s.get('score') < points_possible * 0.6
            ]

            results.append({
                "assignment_id": am_id,
                "title": am.get('name'),
                "created_at": am.get('created_at'),
                "due_at": am.get('due_at'),
                "description": am.get('description'), # 主要内容
                "rubric": am.get('rubric'),           # 考察方向（如果Canvas设置了量规）
                "points_possible": points_possible,
                "statistics": {
                    "total_students": len(all_students),
                    "submitted_count": len(submitted_ids),
                    "unsubmitted_count": len(unsubmitted_students),
                    "average_score": round(sum(scores)/len(scores), 2) if scores else 0
                },
                "unsubmitted_list": unsubmitted_students,
                "low_score_list": low_score_students,
                "workflow_state": am.get('workflow_state')
            })

        return jsonify({
            "course_name": current_course.get('course_name'),
            "count": len(results),
            "assignments": results
        }), 200

    except Exception as e:
        return jsonify({"error": "Canvas接口查询失败", "details": str(e)}), 500
    
    

@study_situation_LLM.route('/dashboard/study_situation/quiz/search')
def search_quizzes_detail():
    """查询测验详细情况接口"""
    studentUid = request.args.get('studentUid', '').strip()
    query = request.args.get('query', '').strip()
    course_query = request.args.get('course_query', '').strip() # 课程匹配
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    current_course = get_user_current_course_from_db(studentUid)
    if not current_course:
        current_course = session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到课程上下文"}), 400
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', current_course.get('name', ''))
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    # 验证 course_query
    if course_query:
        is_matched = False
        if str(current_course_id) == str(course_query) or \
           (current_course_name and course_query.lower() in current_course_name.lower()) or \
           (current_sis_course_id and course_query in current_sis_course_id):
            is_matched = True
        
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}' 的测验信息",
                "message": f"您当前可查询的课程是: {current_course_name}"
            }), 403
            
    try:
        all_quizzes = get_course_quizzes(current_course_id)
        
        # 模糊匹配
        matched_quizzes = []
        if query:
            matched_quizzes = [q for q in all_quizzes if query.lower() in q.get('title', '').lower()]
            if not matched_quizzes:
                return jsonify({"message": f"未找到匹配 '{query}' 的测验"}), 404
        else:
            matched_quizzes = all_quizzes

        # 获取班级名单
        enrollments = get_course_enrollments(current_course_id)
        all_students = [e for e in enrollments if e.get('type') == 'StudentEnrollment']
        
        results = []
        for q in matched_quizzes:
            q_id = q.get('id')
            # 获取测验提交记录
            submissions = get_quiz_submissions(current_course_id, q_id)
            
            # 提交情况分析
            submitted_user_ids = {s.get('user_id') for s in submissions if s.get('workflow_state') == 'complete'}
            scores = [s.get('kept_score') for s in submissions if s.get('kept_score') is not None]
            points_possible = q.get('points_possible') or 0
            
            unsubmitted_students = [
                {"name": s.get('user', {}).get('short_name'), "id": s.get('user_id')}
                for s in all_students if s.get('user_id') not in submitted_user_ids
            ]
            
            low_score_students = [
                {"name": next((sub.get('user', {}).get('short_name') for sub in submissions if sub.get('user_id') == s.get('user_id')), "未知"), 
                 "score": s.get('kept_score')}
                for s in submissions if s.get('kept_score') is not None and s.get('kept_score') < points_possible * 0.6
            ]

            results.append({
                "quiz_id": q_id,
                "title": q.get('title'),
                "published_at": q.get('published_at'),
                "due_at": q.get('due_at'),
                "description": q.get('description'), # 主要考察内容
                "quiz_type": q.get('quiz_type'),
                "points_possible": points_possible,
                "statistics": {
                    "total_class_size": len(all_students),
                    "submitted_count": len(submitted_user_ids),
                    "unsubmitted_count": len(unsubmitted_students),
                    "average_score": round(sum(scores)/len(scores), 2) if scores else 0
                },
                "unsubmitted_list": unsubmitted_students,
                "low_score_list": low_score_students
            })

        return jsonify({
            "course_name": current_course.get('course_name'),
            "count": len(results),
            "quizzes": results
        }), 200

    except Exception as e:
        return jsonify({"error": "查询出错", "details": str(e)}), 500
    
##########作业测验，针对学生
import traceback  # 确保在文件顶部导入

@study_situation_LLM.route('/dashboard/study_situation/assignment/search/student')
def search_assignments_student():
    """查询作业情况 - 学生版"""
    studentUid = request.args.get('studentUid', '').strip()
    query = request.args.get('query', '').strip()
    course_query = request.args.get('course_query', '').strip()
    
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    # 1. 获取课程上下文
    current_course = get_user_current_course_from_db(studentUid)
    if not current_course:
        current_course = session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到当前课程"}), 400
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', current_course.get('name', ''))
    current_sis_course_id = current_course.get('sis_course_id', '')
    
    # 2. 验证 course_query (课程匹配逻辑)
    if course_query:
        is_matched = False
        if str(current_course_id) == str(course_query) or \
           (current_course_name and course_query.lower() in current_course_name.lower()) or \
           (current_sis_course_id and course_query in current_sis_course_id):
            is_matched = True
            
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}' 的作业信息",
                "message": f"您当前绑定的课程是: {current_course_name}",
                "current_course": {"course_id": current_course_id, "course_name": current_course_name}
            }), 403
            
    try:
        # 3. 尝试获取该学生的 Canvas 内部 ID (增加错误捕获)
        
        canvas_user = get_user_by_sis_id(studentUid)
        canvas_internal_id = canvas_user.get("sis_user_id")
        # 4. 获取所有作业并过滤
        all_assignments = get_course_assignments(current_course_id)
        if query:
            matched = [a for a in all_assignments if query.lower() in a.get('name', '').lower()]
            if not matched: return jsonify({"message": f"未找到作业 '{query}'"}), 404
        else:
            matched = all_assignments

        results = []
        for am in matched:
            am_id = am.get('id')
            summary = get_assignment_submission_summary(current_course_id, am_id)
            personal_sub = get_student_assignment_submission(current_course_id, am_id, studentUid)
            print(f"提交情况：{personal_sub}")
            # C. 处理截止时间与状态 (更健壮的时间解析)
            now = datetime.now()
            due_at_str = am.get("due_at")
            remaining = "无截止日期"
            
            if due_at_str:
                try:
                    # 使用 fromisoformat 兼容性更好，去除末尾Z并替换为UTC偏移
                    due_date = datetime.fromisoformat(due_at_str.replace('Z', '+00:00')).replace(tzinfo=None)
                    diff = due_date - now
                    remaining = f"{diff.days}天{diff.seconds//3600}小时" if diff.total_seconds() > 0 else "已逾期"
                except Exception as date_e:
                    print(f"时间解析错误: {due_at_str} - {str(date_e)}")
                    remaining = "时间格式解析失败"

            # 安全提取 workflow_state
            wf_state = personal_sub.get("workflow_state", "unsubmitted")
            is_submitted = wf_state not in ["unsubmitted", "deleted"]

            results.append({
                "assignment_id": am_id,
                "title": am.get('name'),
                "due_at": due_at_str,
                "remaining_time": remaining,
                "description": am.get('description'),
                "points_possible": am.get('points_possible'),
                "class_statistics": {
                    "total_submissions": summary.get('scored', 0) + summary.get('submitted', 0),
                },
                "personal_submission": {
                    "status": "已提交" if is_submitted else "未提交",
                    "score": personal_sub.get("score"),
                    "grade": personal_sub.get("grade"),
                    "submitted_at": personal_sub.get("submitted_at"),
                    "feedback": personal_sub.get("submission_comments")
                }
            })

        return jsonify({
            "student_name": canvas_user.get('name'),
            "course_name": current_course_name,
            "assignments": results
        }), 200

    except Exception as e:
        # 在终端打印详细堆栈，方便排错
        print(f"作业查询抛出详细异常:\n{traceback.format_exc()}")
        return jsonify({"error": "查询作业详细信息失败", "details": str(e), "traceback": traceback.format_exc()}), 500
    
@study_situation_LLM.route('/dashboard/study_situation/quiz/search/student')
def search_quizzes_student():
    """查询测验情况 - 学生版"""
    studentUid = request.args.get('studentUid', '').strip()
    query = request.args.get('query', '').strip()
    course_query = request.args.get('course_query', '').strip()
    if not studentUid:
        return jsonify({"error": "缺少studentUid参数"}), 400

    current_course = get_user_current_course_from_db(studentUid)
    if not current_course:
        current_course = session.get('current_course')
    if not current_course:
        return jsonify({"error": "未找到课程上下文"}), 400
    
    current_course_id = current_course.get('course_id')
    current_course_name = current_course.get('course_name', current_course.get('name', ''))
    current_sis_course_id = current_course.get('sis_course_id', '')
    # 2. 验证 course_query (课程匹配逻辑)
    if course_query:
        is_matched = False
        if str(current_course_id) == str(course_query) or \
           (current_course_name and course_query.lower() in current_course_name.lower()) or \
           (current_sis_course_id and course_query in current_sis_course_id):
            is_matched = True
            
        if not is_matched:
            return jsonify({
                "error": f"无权限查询课程 '{course_query}' 的作业信息",
                "message": f"您当前绑定的课程是: {current_course_name}",
                "current_course": {"course_id": current_course_id, "course_name": current_course_name}
            }), 403
    try:
        # 获取身份
        canvas_user = get_user_by_sis_id(studentUid)
        canvas_internal_id = canvas_user.get("sis_user_id")

        all_quizzes = get_course_quizzes(current_course_id)
        if query:
            matched = [q for q in all_quizzes if query.lower() in q.get('title', '').lower()]
            if not matched: return jsonify({"message": f"未找到测验 '{query}'"}), 404
        else:
            matched = all_quizzes

        results = []
        for q in matched:
            q_id = q.get('id')
            # 获取个人在该测验下的提交
            q_subs = get_student_quiz_submissions(current_course_id, q_id, studentUid)
            personal_sub = q_subs[0] if q_subs else {}
            
            now = datetime.now()
            due_at_str = q.get("due_at")
            remaining = "无截止日期"
            if due_at_str:
                due_date = datetime.strptime(due_at_str, "%Y-%m-%dT%H:%M:%SZ")
                remaining = "已截止" if (due_date - now).total_seconds() <= 0 else f"剩余{(due_date - now).days}天"

            results.append({
                "quiz_id": q_id,
                "title": q.get('title'),
                "due_at": due_at_str,
                "remaining_time": remaining,
                "description": q.get('description'),
                "points_possible": q.get('points_possible'),
                "allowed_attempts": q.get('allowed_attempts'),
                "personal_attempt": {
                    "status": "已参加" if personal_sub else "未参加",
                    "kept_score": personal_sub.get('kept_score'),
                    "finished_at": personal_sub.get('finished_at'),
                    "attempt_count": personal_sub.get('attempt')
                }
            })

        return jsonify({
            "student_name": canvas_user.get('name'),
            "course_name": current_course.get('course_name'),
            "quizzes": results
        }), 200

    except Exception as e:
        return jsonify({"error": "查询测验失败", "details": str(e)}), 500
    
    
    
    



