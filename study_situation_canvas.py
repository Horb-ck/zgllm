from flask import request, Blueprint,jsonify,session
import os
import json
from datetime import datetime, timedelta, timezone
from utils.canvas_utils import get_courses_by_teacher_id,get_courses_by_student_id,get_course_assignments,get_assignment_submissions,get_assignment_submission_summary,get_gradeable_students,get_course_enrollments,get_course_quizzes,get_course_modules,get_module_items,get_quiz_submissions,get_student_assignment_submission,get_student_quiz_submissions
study_situation_canvas = Blueprint('study_situation_canvas', __name__)
# 定义课程白名单
COURSES_LIST = [
    "定量工程设计方法", "自动控制原理", "程序设计实践", 
    "移动机器人应用与开发", "线性代数",
    "机器人基础", "概率论与数理统计", "人类文明史", "科技发展史","软件设计","机器人动力学与控制"
]

# 允许的学期ID列表
# ALLOWED_TERM_IDS = [3, 5, 11, 12]
ALLOWED_TERM_IDS = [13]
 #教师版学情分析   

@study_situation_canvas.route('/dashboard/study_situation/comprehensive/overview')
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


# 学生版学情分析接口
@study_situation_canvas.route('/dashboard/study_situation/student/overview')
def get_student_overview():
    """获取学生个人学情综合分析"""
    # 获取学生基本信息
    sis_user_id = session.get('sis_id')
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
    print(f"作业：{assignments}")
    quizzes = get_course_quizzes(course_id)
    print(f"作业：{quizzes}")
    modules = get_course_modules(course_id, include_items=True, include_content_details=True)
    enrollments = get_course_enrollments(course_id)
    
    # 学生个人数据分析
    student_assignments = analyze_student_assignments(sis_user_id, course_id, assignments)
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

def analyze_student_assignments(sis_user_id, course_id, assignments):
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
        submission = get_student_assignment_submission(course_id, assignment_id, sis_user_id)
        
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