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
