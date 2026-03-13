import requests
from urllib.parse import quote
from config import CANVAS_AUTH_KEY

def get_user_by_sis_id(sis_id: str, timeout: int = 10):
    """
    Fetch a Canvas user by SIS user id.

    Args:
        sis_id: e.g. "20243334"
        token: Canvas API token (if required), e.g. "12345..."
        timeout: request timeout in seconds

    Returns:
        Parsed JSON (dict/list) if response is JSON, otherwise raw text.
    """
    # Endpoint pattern: /api/v1/users/sis_user_id:<ID>
    key = f"sis_user_id:{sis_id}"
    url = f"https://eiecanvas.cqu.edu.cn/api/v1/users/{quote(key, safe=':')}"

    headers = {"Accept": "application/json"}
    headers["Authorization"] = f"Bearer {CANVAS_AUTH_KEY}"

    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()

    try:
        return resp.json()
    except ValueError:
        return resp.text

def search_courses_by_teacher(search_term: str, timeout: int = 10):
    """
    Search courses in a Canvas account by teacher name (search_term) and get ALL results.
    
    Args:
        search_term: teacher name, e.g. "刘凯"
        timeout: request timeout in seconds
    
    Returns:
        List of all courses
    """
    all_courses = []
    base_url = "https://eiecanvas.cqu.edu.cn/api/v1/accounts/3/courses"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {CANVAS_AUTH_KEY}"
    }
    
    params = {
        "search_term": search_term,
        "search_by": "teacher",
        "per_page": 100 
    }
    
    next_url = base_url
    
    try:
        while next_url:
            resp = requests.get(next_url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            page_courses = resp.json()
            all_courses.extend(page_courses)
            if 'Link' in resp.headers:
                links = resp.headers['Link']
                next_url = None
                for link in links.split(','):
                    if 'rel="next"' in link:
                        next_url = link[link.find('<')+1:link.find('>')]
                        break
                if next_url and '?' in next_url:
                    params = {}
            else:
                next_url = None
                
    except Exception as e:
        print(f"获取课程数据时出错: {e}")
    
    return all_courses

def get_courses_by_teacher_id(sis_id: str, timeout: int = 10):
    """
    Return a deduplicated list of course names taught by the teacher with the given SIS id.

    Args:
        sis_id: SIS user id, e.g. "33087".
        timeout: Request timeout in seconds for Canvas API calls.

    Returns:
        List of unique course names taught by the teacher.
    """
    teacher = get_user_by_sis_id(sis_id, timeout=timeout)
    courses = search_courses_by_teacher(teacher["name"], timeout=timeout) or []

    seen = set()
    unique_courses = []
    for course in courses:
        course_id = course.get("id")
        name = course.get("name")
        sis_course_id = course.get("sis_course_id")
        if course_id not in seen:
            seen.add(course_id)
            unique_courses.append({
                "course_id":course_id,
                "name": name,
                "sis_course_id": sis_course_id,
                "enrollment_term_id":course.get("enrollment_term_id"),
                "workflow_state":course.get("workflow_state") 
            })
    return unique_courses

def get_courses_by_student_id(sis_id: str, timeout: int = 10, base_url: str = "https://eiecanvas.cqu.edu.cn"):
    """
    根据SIS ID获取用户的所有课程列表（已去重）

    Args:
        sis_id: SIS用户ID，例如 "469"
        timeout: 请求超时时间（秒）
        base_url: Canvas API的基础URL

    Returns:
        去重后的课程列表，每个课程包含course_id, name, sis_course_id
    """
    # 构建API请求URL
    url = f"{base_url}/api/v1/users/sis_user_id:{sis_id}/courses"
    
    # 设置请求参数
    params = {
        "state": "unpublished",  # 获取未发布的课程
        "per_page": 100 
    }
    
    # 设置请求头（根据需要添加认证信息）
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {CANVAS_AUTH_KEY}"
    }
    
    try:
        # 发送GET请求
        response = requests.get(
            url, 
            params=params, 
            headers=headers, 
            timeout=timeout
        )
        
        # 检查响应状态
        response.raise_for_status()
        
        # 解析JSON响应
        courses = response.json()
        
    except requests.exceptions.RequestException as e:
        print(f"获取课程数据时出错: {e}")
        return []
    except ValueError as e:
        print(f"解析JSON响应时出错: {e}")
        return []
    
    # 去重处理
    seen = set()
    unique_courses = []
    
    for course in courses:
        course_id = course.get("id")
        
        # 确保course_id存在且不在已见集合中
        if course_id is not None and course_id not in seen:
            seen.add(course_id)
            
            unique_courses.append({
                "course_id": course_id,
                "name": course.get("name"),
                "sis_course_id": course.get("sis_course_id"),
                "enrollment_term_id":course.get("enrollment_term_id"),
                "workflow_state":course.get("workflow_state")
            })
    
    return unique_courses


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
if __name__=="__main__":
    print(get_courses_by_teacher_id("test"))
