from utils.canvas_utils import (
    get_courses_by_teacher_id,
    get_courses_by_student_id,
    get_course_assignments,
    get_assignment_submissions,
    get_assignment_submission_summary,
    get_gradeable_students,
    get_course_enrollments,
    get_course_quizzes,
    get_course_modules,
    get_module_items,
    get_quiz_submissions,
)


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