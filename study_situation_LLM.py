from flask import request, Blueprint,jsonify
import os
import json
import re
from database_mongo import db, user_sessions_collection
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
                {'username': studentUid},
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
                {'username': studentUid},
                {'_id': 0, 'user_courses': 1}
            )
            if user_session and 'user_courses' in user_session:
                return user_session['user_courses']
        except Exception as e:
            print(f"❌ 从 MongoDB 获取用户课程列表失败: {e}")
    return session.get('user_courses', [])
   
@study_situation_LLM.route('/dashboard/study_situation/course/search')
def search_course():
    """查询课程信息 - 获取当前课程的知识点学习统计"""
    # 获取查询参数
    query = request.args.get('query', '').strip()
    studentUid = request.args.get('studentUid', '').strip()
    
    print(f"search_course 接收参数 - query: {query}, studentUid: {studentUid}")
    
    # 1. 验证 studentUid 参数
    if not studentUid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供用户账号(studentUid)以识别用户身份"
        }), 400
    # 2. 从 MongoDB 中获取用户会话信息
    current_course = None
    current_course = get_user_current_course_from_db(studentUid)
    print("!!!!search_course:current_course:",current_course)
    
    # 3. 如果 MongoDB 中没有，尝试从 session 获取（作为后备方案）
    if not current_course:
        current_course = session.get('current_course')
        print(f"从session获取当前课程: {current_course}")

    # 4. 如果仍然没有当前课程，返回错误
    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": "请先在学情分析页面选择一门课程"
        }), 400
    
    # 5. 获取当前课程的信息
    current_course_id = int(current_course.get('course_id'))
    current_course_name = current_course.get('name', '未命名课程')
    
    # 6. 如果有 query 参数，验证用户是否有权限访问该课程(只有当与当前课程成功匹配才能查询)
    if query:
        # 判断query是否能与当前课程的course_id或course_name匹配
        is_match = False
        if str(current_course_id).strip() == query:
            is_match = True
            print(f"query '{query}' 与当前课程ID '{current_course_id}' 匹配")
        elif query in str(current_course_name).strip():
            is_match = True
            print(f"query '{query}' 在当前课程名称 '{current_course_name}' 中找到匹配")
        if not is_match:
            return jsonify({
                "error": f"无权限查询课程 '{query}'",
                "message": f"您当前可查询的课程是: {current_course_name} (ID: {current_course_id})",
                "current_course": {
                    "course_id": current_course_id,
                    "course_name": current_course_name
                }
            }), 403
    
    # 7. 使用当前课程的course_id查询相关课程信息
    print(f"使用当前课程ID查询: {current_course_id}")
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
    student_list = class_info.get('student_list', [])
    knowledge_stats = {}
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
            for knowledge_id in knowledge_stats.keys():
                knowledge_stats[knowledge_id]['not_learned'] += 1
            continue
        
        student_knowledge_list = current_enrolled_course.get('knowledge_list', [])
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
    print("!!!!get_course_student_status:current_course:",current_course)
    
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
    # Step 1: 获取studentUid参数
    studentUid = request.args.get('studentUid', '').strip()
    print(f"获取学生进度请求 - studentUid: {studentUid}, student_query: {student_query}")
    # 1. 验证 studentUid 参数
    if not studentUid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供用户账号(studentUid)以识别用户身份"
        }), 400
    # 2. 从 MongoDB 中获取用户会话信息
    current_course = None
    current_course = get_user_current_course_from_db(studentUid)
    print("!!!!get_student_progress:current_course:",current_course)

    if not current_course:
        return jsonify({
            "error": "未找到当前课程信息",
            "message": f"你尚未在学情分析页面选择课程",
            "studentUid": studentUid,
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
            "studentUid": studentUid,
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
                "studentUid": studentUid,
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
                "studentUid": studentUid,
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
            "note": f"查询用户 {studentUid} 的课程 '{actual_course_name}' 中的学生进度"
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
        "debug_info": {
            "student_query": student_query,
            "match_reason": match_reason,
            "search_method": "班级列表匹配" if matched_student_in_class else "数据库直接查询",
            "class_matched": bool(matched_student_in_class)
        },
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
    studentUid = request.args.get('studentUid', '').strip()
    print(f"获取知识点状态请求 - studentUid: {studentUid}, knowledge_query: {knowledge_query}")
    # 1. 验证 studentUid 参数
    if not studentUid:
        return jsonify({
            "error": "缺少studentUid参数",
            "message": "请提供用户账号(studentUid)以识别用户身份"
        }), 400
    # 2. 从 MongoDB 中获取用户会话信息
    current_course = None
    current_course = get_user_current_course_from_db(studentUid)
    print("!!!!get_knowledge_status:current_course:",current_course)
    
    # 3. 如果 MongoDB 中没有，尝试从 session 获取（作为后备方案）
    if not current_course:
        current_course = session.get('current_course')
        print(f"从session获取当前课程: {current_course}")

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
    
    # Step 3: 获取query参数并进行匹配
    query = request.args.get('course_query', '').strip()
    
    # 如果提供了query，进行模糊匹配
    if query:
        is_matched = False
        if str(current_course_id) == str(query):
            is_matched = True
            print(f"通过课程ID匹配: {query}")
        elif current_course_name and query.lower() in current_course_name.lower():
            is_matched = True
            print(f"通过课程名称模糊匹配: {query} 匹配 {current_course_name}")
        elif current_sis_course_id and query in current_sis_course_id:
            is_matched = True
            print(f"通过sis_course_id匹配: {query} 匹配 {current_sis_course_id}")
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
            "studentUid": studentUid,
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
            "studentUid": studentUid,
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
            "note": f"查询用户 {studentUid} 的课程 '{actual_course_name}' 中的知识点状态"
        },
        "studentUid": studentUid,
        "course_info": {
            "class_sis_id": sis_course_id,
            "term_id": term_id
        },
        "last_updated": datetime.now().isoformat()
    }), 200
