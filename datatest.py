# from pymongo import MongoClient
# import requests
# import json
# import time
# from typing import List, Dict, Any

# client = MongoClient(
#         host='localhost',
#         port=27027,
#         username='root',
#         password='123456',
#         authSource='admin' 
#     )
# db = client['education2']

# BASE_URL = "https://eiecanvas.cqu.edu.cn/api/v1"
# HEADERS = {
#     "Authorization": "Bearer vJHBrNPVBkEKkDGa4DyvntFtXK3m7kKP3tUfx4EDfBzfRUBxa2a2LDJGvR3CveQG" 
# }

# COURSES_LIST = [
#     "定量工程设计方法", "自动控制原理", "程序设计实践", 
#     "软件系统架构技术", "移动机器人应用与开发", "线性代数",
#     "机器人基础", "概率论与数理统计", "人类文明史", "科技发展史"
# ]

# """根据课程名称查询课程信息"""
# def get_courses_by_name(course_name: str) -> List[Dict]:
#     url = f"{BASE_URL}/accounts/3/courses"
#     params = {
#         "search_term": course_name,
#         "per_page": 50
#     }
    
#     try:
#         response = requests.get(url, headers=HEADERS, params=params)
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print(f"获取课程 {course_name} 班级信息失败: {e}")
#         return []


# """填充课程表和班级表"""
# def populate_courses_and_classes():
#     courses_collection = db['courses']
#     classes_collection = db['classes']
    
#     for course_name in COURSES_LIST:
#         print(f"处理课程: {course_name}")
#         courses_data = get_courses_by_name(course_name)
        
#         if not courses_data:
#             print(f"未找到课程: {course_name}")
#             continue
        
#         # 按课程号分组，同一个课程号可能有多个班级
#         courses_by_code = {}
#         for classitem in courses_data:
#             course_code = classitem.get('course_code')
#             if course_code not in courses_by_code:
#                 courses_by_code[course_code] = []
#             courses_by_code[course_code].append(classitem)
        
#         for course_code, class_instances in courses_by_code.items():
#             # 构建班级列表
#             class_list = []
#             for class_instance in class_instances:
#                 class_info = {
#                     'enrollment_term_id': class_instance.get('enrollment_term_id'),
#                     'sis_course_id': class_instance.get('sis_course_id')
#                 }
#                 class_list.append(class_info)
                
#                 # 填充班级表
#                 class_doc = {
#                     'course_code': course_code,
#                     'course_name': class_instance.get('name'),
#                     'sis_course_id': class_instance.get('sis_course_id'),
#                     'teacher_count': 0,
#                     'teacher_list': [],
#                     'student_count': 0,
#                     'student_list': []
#                 }
#                 classes_collection.update_one(
#                     {'sis_course_id': class_instance.get('sis_course_id')},
#                     {'$set': class_doc},
#                     upsert=True
#                 )
#                 print(f"  添加班级: {class_instance.get('sis_course_id')}")
            
#             # 填充课程表
#             course_doc = {
#                 'course_code': course_code,
#                 'course_name': class_instance.get('name'),
#                 'class_list': class_list,
#                 'knowledge_count': 0,
#                 'knowledge_list': []
#             }
#             courses_collection.update_one(
#                 {'course_code': course_code},
#                 {'$set': course_doc},
#                 upsert=True
#             )
#             print(f"  添加课程: {course_code} - {course_name}, 包含 {len(class_list)} 个班级")




# """获取系统中所有用户信息"""
# def get_all_users_paginated() -> List[Dict]:
#     users = []
#     page = 1
#     per_page = 100
    
#     while True:
#         url = f"{BASE_URL}/accounts/3/users"
#         params = {
#             "per_page": per_page,
#             "page": page
#         }
        
#         try:
#             response = requests.get(url, headers=HEADERS, params=params)
#             response.raise_for_status()
#             page_users = response.json()
            
#             # 如果返回空数组，说明没有更多数据
#             if not page_users:
#                 print(f"第 {page} 页返回空数据，结束分页")
#                 break
            
#             users.extend(page_users)
#             print(f"已获取第 {page} 页用户，本页 {len(page_users)} 条，当前总数: {len(users)}")
            
#             # 如果返回数量少于请求数量，说明是最后一页
#             if len(page_users) < per_page:
#                 print(f"第 {page} 页只有 {len(page_users)} 条数据，少于 {per_page}，结束分页")
#                 break
            
#             page += 1
            
#             # 添加延迟避免请求过快
#             time.sleep(0.1)
            
#         except requests.exceptions.RequestException as e:
#             print(f"获取用户列表第 {page} 页失败: {e}")
#             # 如果是404错误，说明页码超出范围
#             if response.status_code == 404:
#                 print("页码超出范围，结束分页")
#                 break
#             else:
#                 # 其他错误可以重试或退出
#                 break
    
#     return users


# """填充人员表（只填充基础信息，身份后续确定）"""
# def populate_persons():
    
#     persons_collection = db['persons']
    
#     # 获取所有用户
#     all_users = get_all_users_paginated()
    
#     print(f"总共获取到 {len(all_users)} 个用户")
    
#     for user in all_users:
#         person_doc = {
#             'sis_user_id': user.get('sis_user_id'),
#             'name': user.get('name'),
#             'identity': 'unknown'  # 初始身份设为unknown
#         }
#         persons_collection.update_one(
#             {'sis_user_id': user.get('sis_user_id')},
#             {'$set': person_doc},
#             upsert=True
#         )
        

# """填充班级详情并更新身份信息"""
# def populate_class_details_and_identities():
#     classes_collection = db['classes']
#     persons_collection = db['persons']
#     students_collection = db['students']
#     teachers_collection = db['teachers']
#     courses_collection = db['courses']
    
#     # 获取所有班级
#     all_classes = list(classes_collection.find())
    
#     print(f"开始处理 {len(all_classes)} 个班级的身份信息...")
    
#     for class_info in all_classes:
#         sis_course_id = class_info['sis_course_id']
#         course_code = class_info['course_code']
#         course_name = class_info['course_name']
        
#         print(f"处理班级: {sis_course_id}")
        
#         # 获取学生名单
#         students = get_course_users(sis_course_id, include_enrollments=False)
        
#         # 获取教师名单（包含enrollments信息）
#         teachers = get_teachers_for_course(sis_course_id)
        
#         # 更新班级表
#         student_list = []
#         for student in students:
#             if student.get('sis_user_id'):
#                 student_list.append({
#                     'sis_user_id': student.get('sis_user_id'),
#                     'student_name': student.get('name')
#                 })
        
#         teacher_list = []
#         for teacher in teachers:
#             if teacher.get('sis_user_id'):
#                 teacher_list.append({
#                     'sis_user_id': teacher.get('sis_user_id'),
#                     'teacher_name': teacher.get('name')
#                 })
        
#         # 更新班级信息
#         classes_collection.update_one(
#             {'sis_course_id': sis_course_id},
#             {'$set': {
#                 'teacher_count': len(teacher_list),
#                 'teacher_list': teacher_list,
#                 'student_count': len(student_list),
#                 'student_list': student_list
#             }}
#         )
        
#         # 更新学生身份和课程信息
#         for student in students:
#             sis_user_id = student.get('sis_user_id')
#             if sis_user_id:
#                 # 更新人员身份
#                 persons_collection.update_one(
#                     {'sis_user_id': sis_user_id},
#                     {'$set': {'identity': 'student'}}
#                 )
                
#                 # 更新学生表 - 使用$addToSet避免重复课程
#                 student_course_info = {
#                     'course_code': course_code,
#                     'enrollment_term_id': class_info.get('enrollment_term_id', ''),
#                     'sis_course_id': sis_course_id,
#                     'knowledge_list': []
#                 }
                
#                 students_collection.update_one(
#                     {'sis_user_id': sis_user_id},
#                     {
#                         '$setOnInsert': {
#                             'sis_user_id': sis_user_id,
#                             'student_name': student.get('name')
#                         },
#                         '$addToSet': {'enrolled_courses': student_course_info}
#                     },
#                     upsert=True
#                 )
        
#         # 更新教师身份和负责课程信息
#         for teacher in teachers:
#             sis_user_id = teacher.get('sis_user_id')
#             if sis_user_id:
#                 # 更新人员身份
#                 persons_collection.update_one(
#                     {'sis_user_id': sis_user_id},
#                     {'$set': {'identity': 'teacher'}}
#                 )
                
#                 # # 更新教师表 - 使用$addToSet避免重复课程
#                 # teacher_class_info = {
#                 #     'course_code': course_code,
#                 #     'course_name': course_name,
#                 #     'enrollment_term_id': class_info.get('enrollment_term_id', ''),
#                 #     'sis_course_id': sis_course_id
#                 # }
                
#                 # teachers_collection.update_one(
#                 #     {'sis_user_id': sis_user_id},
#                 #     {
#                 #         '$setOnInsert': {
#                 #             'sis_user_id': sis_user_id,
#                 #             'teacher_name': teacher.get('name')
#                 #         },
#                 #         '$addToSet': {'responsible_classes': teacher_class_info}
#                 #     },
#                 #     upsert=True
#                 # )
                
                
# """获取课程中的学生名单"""
# def get_course_users(sis_course_id: str, include_enrollments: bool = False) -> List[Dict]:
#     users = []
#     page = 1
#     per_page = 100
    
#     while True:
#         if include_enrollments:
#             url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/users"
#             params = {
#                 "include[]": "enrollments",
#                 "per_page": per_page,
#                 "page": page
#             }
#         else:
#             url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/students"
#             params = {
#                 "per_page": per_page,
#                 "page": page
#             }
        
#         try:
#             response = requests.get(url, headers=HEADERS, params=params)
#             response.raise_for_status()
#             page_users = response.json()
            
#             # 如果返回空数组，说明没有更多数据
#             if not page_users:
#                 print(f"课程 {sis_course_id} 第 {page} 页返回空数据，结束分页")
#                 break
            
#             users.extend(page_users)
#             print(f"课程 {sis_course_id} 已获取第 {page} 页学生，本页 {len(page_users)} 条，当前总数: {len(users)}")
            
#             # 如果返回数量少于请求数量，说明是最后一页
#             if len(page_users) < per_page:
#                 print(f"课程 {sis_course_id} 第 {page} 页只有 {len(page_users)} 条数据，少于 {per_page}，结束分页")
#                 break
            
#             page += 1
            
#             # 添加延迟避免请求过快
#             time.sleep(0.1)
            
#         except requests.exceptions.RequestException as e:
#             print(f"获取课程 {sis_course_id} 第 {page} 页学生失败: {e}")
#             # 如果是404错误，说明页码超出范围
#             if response.status_code == 404:
#                 print(f"课程 {sis_course_id} 页码超出范围，结束分页")
#                 break
#             else:
#                 # 其他错误可以重试或退出
#                 break
    
#     print(f"课程 {sis_course_id} 总共获取 {len(users)} 名学生")
#     return users

# def get_teachers_for_course(sis_course_id: str) -> List[Dict]:
#     """获取课程的教师名单"""
#     url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/search_users"
#     params = {
#         "enrollment_type[]": "teacher",
#         "per_page": 100
#     }
    
#     try:
#         response = requests.get(url, headers=HEADERS, params=params)
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print(f"获取课程 {sis_course_id} 教师失败: {e}")
#         return []


# """根据教师姓名查询教师负责的课程"""
# def get_courses_by_teacher(teacher_name: str) -> List[Dict]:
#     """通过教师姓名查询其负责的所有课程"""
#     url = f"{BASE_URL}/accounts/3/courses"
#     params = {
#         "search_term": teacher_name,
#         "search_by": "teacher",
#         "per_page": 50
#     }
    
#     try:
#         response = requests.get(url, headers=HEADERS, params=params)
#         response.raise_for_status()
#         return response.json()
#     except requests.exceptions.RequestException as e:
#         print(f"获取教师 {teacher_name} 的课程失败: {e}")
#         return []
    
    
# """根据sis_user_id判断用户身份"""
# def identify_user_by_sis_id(sis_user_id: str) -> str:
#     """根据sis_user_id判断用户身份"""
#     if not sis_user_id:
#         return 'unknown'
    
#     # 教师的sis_user_id位数不到八位，学生的至少八位
#     if len(sis_user_id) < 8:
#         return 'teacher'
#     else:
#         return 'student'
    
    
# """更新未识别身份的用户"""
# def update_unknown_identities():
#     """根据sis_user_id规则更新persons表中身份为unknown的用户"""
#     persons_collection = db['persons']
#     students_collection = db['students']
#     teachers_collection = db['teachers']
    
#     # 查找所有身份为unknown的用户
#     unknown_users = list(persons_collection.find({'identity': 'unknown'}))
#     print(f"找到 {len(unknown_users)} 个未识别身份的用户")
    
#     for user in unknown_users:
#         sis_user_id = user.get('sis_user_id')
#         name = user.get('name')
        
#         if not sis_user_id:
#             continue
            
#         identity = identify_user_by_sis_id(sis_user_id)
        
#         if identity == 'student':
#             # 更新人员身份
#             persons_collection.update_one(
#                 {'sis_user_id': sis_user_id},
#                 {'$set': {'identity': 'student'}}
#             )
            
#             # 添加到学生表
#             students_collection.update_one(
#                 {'sis_user_id': sis_user_id},
#                 {
#                     '$setOnInsert': {
#                         'sis_user_id': sis_user_id,
#                         'student_name': name,
#                         'enrolled_courses': []  # 初始为空，后续通过班级信息填充
#                     }
#                 },
#                 upsert=True
#             )
#             print(f"  识别为学生: {name} ({sis_user_id})")
            
#         elif identity == 'teacher':
#             # 更新人员身份
#             persons_collection.update_one(
#                 {'sis_user_id': sis_user_id},
#                 {'$set': {'identity': 'teacher'}}
#             )
            
#             # 添加到教师表
#             teachers_collection.update_one(
#                 {'sis_user_id': sis_user_id},
#                 {
#                     '$setOnInsert': {
#                         'sis_user_id': sis_user_id,
#                         'teacher_name': name,
#                         'responsible_classes': []  # 初始为空，后续通过查询填充
#                     }
#                 },
#                 upsert=True
#             )
#             print(f"  识别为教师: {name} ({sis_user_id})")


# """补全教师负责的课程信息"""
# def complete_teacher_courses():
#     """通过教师姓名查询并补全教师负责的课程信息"""
#     teachers_collection = db['teachers']
#     courses_collection = db['courses']
    
#     # 获取所有教师
#     all_teachers = list(teachers_collection.find())
#     print(f"开始补全 {len(all_teachers)} 名教师的课程信息...")
    
#     for teacher in all_teachers:
#         teacher_name = teacher.get('teacher_name')
#         sis_user_id = teacher.get('sis_user_id')
        
#         if not teacher_name:
#             continue
            
#         print(f"查询教师 {teacher_name} 的课程...")
#         teacher_courses = get_courses_by_teacher(teacher_name)
        
#         if not teacher_courses:
#             print(f"  教师 {teacher_name} 未找到负责的课程")
#             continue
        
#         # 处理找到的课程
#         for course in teacher_courses:
#             course_code = course.get('course_code')
#             course_name = course.get('name')
#             sis_course_id = course.get('sis_course_id')
#             enrollment_term_id = course.get('enrollment_term_id')
            
#             if not course_code or not sis_course_id:
#                 continue
                
#             # 构建课程信息
#             teacher_class_info = {
#                 'course_code': course_code,
#                 'course_name': course_name,
#                 'enrollment_term_id': enrollment_term_id,
#                 'sis_course_id': sis_course_id
#             }
            
#             # 使用addToSet避免重复
#             teachers_collection.update_one(
#                 {'sis_user_id': sis_user_id},
#                 {'$addToSet': {'responsible_classes': teacher_class_info}}
#             )
            
#             print(f"  添加课程: {course_name} ({course_code})")
        
#         # # 更新班级表中的教师信息（如果该班级已存在）
#         # classes_collection = db['classes']
#         # for course in teacher_courses:
#         #     sis_course_id = course.get('sis_course_id')
#         #     if sis_course_id:
#         #         # 检查班级是否存在，如果存在则更新教师信息
#         #         class_info = classes_collection.find_one({'sis_course_id': sis_course_id})
#         #         if class_info:
#         #             # 添加教师到班级的教师名单
#         #             classes_collection.update_one(
#         #                 {'sis_course_id': sis_course_id},
#         #                 {
#         #                     '$addToSet': {
#         #                         'teacher_list': {
#         #                             'sis_user_id': sis_user_id,
#         #                             'teacher_name': teacher_name
#         #                         }
#         #                     },
#         #                     '$inc': {'teacher_count': 1}
#         #                 }
#         #             )
        
                    
# def main():
#     print("开始填充数据库...")
    
#     # 步骤1: 填充课程表和班级表
#     print("步骤1: 填充课程表和班级表")
#     populate_courses_and_classes()
    
#     # 步骤2: 填充人员表（只填充基础信息）
#     print("步骤2: 填充人员表")
#     populate_persons()
    
#     # 步骤3: 根据sis_user_id规则识别身份
#     print("步骤3: 根据sis_user_id规则识别用户身份")
#     update_unknown_identities()
    
#     # 步骤4: 通过班级信息填充学生选课信息
#     print("步骤4: 填充班级详情和学生选课信息")
#     populate_class_details_and_identities()
    
#     # 步骤5: 补全教师负责的课程信息
#     print("步骤5: 补全教师负责的课程信息")
#     complete_teacher_courses()
    
#     print("数据库填充完成！")
    
#     # 验证数据
#     verify_data()

# def verify_data():
#     """验证填充的数据"""
#     print("\n数据统计:")
#     print("课程数量:", db['courses'].count_documents({}))
#     print("班级数量:", db['classes'].count_documents({}))
#     print("人员数量:", db['persons'].count_documents({}))
#     print("学生数量:", db['students'].count_documents({}))
#     print("教师数量:", db['teachers'].count_documents({}))
    
#     # 查看身份分布
#     identity_stats = db['persons'].aggregate([
#         {"$group": {"_id": "$identity", "count": {"$sum": 1}}}
#     ])
#     print("\n身份分布:")
#     for stat in identity_stats:
#         print(f"  {stat['_id']}: {stat['count']}")

# if __name__ == "__main__":
#     main()


from pymongo import MongoClient
import requests
import json
import time
from typing import List, Dict, Any

client = MongoClient(
        host='localhost',
        port=27027,
        username='root',
        password='123456',
        authSource='admin' 
    )
db = client['education2']

BASE_URL = "https://eiecanvas.cqu.edu.cn/api/v1"
HEADERS = {
    "Authorization": "Bearer vJHBrNPVBkEKkDGa4DyvntFtXK3m7kKP3tUfx4EDfBzfRUBxa2a2LDJGvR3CveQG" 
}

COURSES_LIST = [
    "定量工程设计方法", "自动控制原理", "程序设计实践", 
    "移动机器人应用与开发", "线性代数",
    "机器人基础", "概率论与数理统计", "人类文明史", "科技发展史","软件设计","机器人动力学与控制"
]

"""根据课程名称查询课程信息"""
def get_courses_by_name(course_name: str) -> List[Dict]:
    url = f"{BASE_URL}/accounts/3/courses"
    params = {
        "search_term": course_name,
        "per_page": 50
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取课程 {course_name} 班级信息失败: {e}")
        return []


"""填充课程表和班级表"""
def populate_courses_and_classes():
    courses_collection = db['courses']
    classes_collection = db['classes']
    
    for course_name in COURSES_LIST:
        print(f"处理课程: {course_name}")
        courses_data = get_courses_by_name(course_name)
        
        if not courses_data:
            print(f"未找到课程: {course_name}")
            continue
        
        # 按课程号分组，同一个课程号可能有多个班级
        courses_by_code = {}
        for classitem in courses_data:
            course_code = classitem.get('course_code')
            if course_code not in courses_by_code:
                courses_by_code[course_code] = []
            courses_by_code[course_code].append(classitem)
        
        # 构建课程列表
        courses_list = []
        for course_code, class_instances in courses_by_code.items():
            # 构建班级列表
            class_list = []
            for class_instance in class_instances:
                class_info = {
                    'enrollment_term_id': class_instance.get('enrollment_term_id'),
                    'sis_course_id': class_instance.get('sis_course_id')
                }
                class_list.append(class_info)
                
                # 填充班级表
                class_doc = {
                    'sis_course_id': class_instance.get('sis_course_id'),
                    'course_code': course_code,
                    'course_name': course_name,
                    'enrollment_term_id': class_instance.get('enrollment_term_id'),
                    'teacher_count': 0,
                    'teacher_list': [],
                    'student_count': 0,
                    'student_list': []
                }
                classes_collection.update_one(
                    {'sis_course_id': class_instance.get('sis_course_id')},
                    {'$set': class_doc},
                    upsert=True
                )
                print(f"  添加班级: {class_instance.get('sis_course_id')}")
            
            # 构建课程信息
            course_info = {
                'course_code': course_code,
                'class_list': class_list
            }
            courses_list.append(course_info)
            print(f"  添加课程号: {course_code}, 包含 {len(class_list)} 个班级")
        
        # 填充课程表（新的结构）
        course_doc = {
            'course_name': course_name,
            'courses_list': courses_list,
            'knowledge_count': 0,
            'knowledge_list': []
        }
        courses_collection.update_one(
            {'course_name': course_name},
            {'$set': course_doc},
            upsert=True
        )
        print(f"  更新课程: {course_name}, 包含 {len(courses_list)} 个课程号")




"""获取系统中所有用户信息"""
def get_all_users_paginated() -> List[Dict]:
    users = []
    page = 1
    per_page = 100
    
    while True:
        url = f"{BASE_URL}/accounts/3/users"
        params = {
            "per_page": per_page,
            "page": page
        }
        
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            page_users = response.json()
            
            # 如果返回空数组，说明没有更多数据
            if not page_users:
                print(f"第 {page} 页返回空数据，结束分页")
                break
            
            users.extend(page_users)
            print(f"已获取第 {page} 页用户，本页 {len(page_users)} 条，当前总数: {len(users)}")
            
            # 如果返回数量少于请求数量，说明是最后一页
            if len(page_users) < per_page:
                print(f"第 {page} 页只有 {len(page_users)} 条数据，少于 {per_page}，结束分页")
                break
            
            page += 1
            
            # 添加延迟避免请求过快
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            print(f"获取用户列表第 {page} 页失败: {e}")
            # 如果是404错误，说明页码超出范围
            if response.status_code == 404:
                print("页码超出范围，结束分页")
                break
            else:
                # 其他错误可以重试或退出
                break
    
    return users


"""填充人员表（只填充基础信息，身份后续确定）"""
def populate_persons():
    
    persons_collection = db['persons']
    
    # 获取所有用户
    all_users = get_all_users_paginated()
    
    print(f"总共获取到 {len(all_users)} 个用户")
    
    for user in all_users:
        person_doc = {
            'sis_user_id': user.get('sis_user_id'),
            'name': user.get('name'),
            'identity': 'unknown'  # 初始身份设为unknown
        }
        persons_collection.update_one(
            {'sis_user_id': user.get('sis_user_id')},
            {'$set': person_doc},
            upsert=True
        )
        

"""填充班级详情并更新身份信息"""
def populate_class_details_and_identities():
    classes_collection = db['classes']
    persons_collection = db['persons']
    students_collection = db['students']
    teachers_collection = db['teachers']
    courses_collection = db['courses']
    
    # 获取所有班级
    all_classes = list(classes_collection.find())
    
    print(f"开始处理 {len(all_classes)} 个班级的身份信息...")
    
    for class_info in all_classes:
        sis_course_id = class_info['sis_course_id']
        course_code = class_info['course_code']
        course_name = class_info['course_name']
        
        print(f"处理班级: {sis_course_id}")
        
        # 获取学生名单
        students = get_course_users(sis_course_id, include_enrollments=False)
        
        # 获取教师名单（包含enrollments信息）
        teachers = get_teachers_for_course(sis_course_id)
        
        # 更新班级表
        student_list = []
        for student in students:
            if student.get('sis_user_id'):
                student_list.append({
                    'sis_user_id': student.get('sis_user_id'),
                    'student_name': student.get('name')
                })
        
        teacher_list = []
        for teacher in teachers:
            if teacher.get('sis_user_id'):
                teacher_list.append({
                    'sis_user_id': teacher.get('sis_user_id'),
                    'teacher_name': teacher.get('name')
                })
        
        # 更新班级信息
        classes_collection.update_one(
            {'sis_course_id': sis_course_id},
            {'$set': {
                'teacher_count': len(teacher_list),
                'teacher_list': teacher_list,
                'student_count': len(student_list),
                'student_list': student_list
            }}
        )
        
        # 更新学生身份和课程信息
        for student in students:
            sis_user_id = student.get('sis_user_id')
            if sis_user_id:
                # 更新人员身份
                persons_collection.update_one(
                    {'sis_user_id': sis_user_id},
                    {'$set': {'identity': 'student'}}
                )
                
                # 更新学生表 - 使用$addToSet避免重复课程
                student_course_info = {
                    'course_name': course_name,
                    'course_code': course_code,
                    'enrollment_term_id': class_info.get('enrollment_term_id', ''),
                    'sis_course_id': sis_course_id,
                    'knowledge_list': []
                }
                
                students_collection.update_one(
                    {'sis_user_id': sis_user_id},
                    {
                        '$setOnInsert': {
                            'sis_user_id': sis_user_id,
                            'student_name': student.get('name')
                        },
                        '$addToSet': {'enrolled_courses': student_course_info}
                    },
                    upsert=True
                )
        
        # 更新教师身份和负责课程信息
        for teacher in teachers:
            sis_user_id = teacher.get('sis_user_id')
            if sis_user_id:
                # 更新人员身份
                persons_collection.update_one(
                    {'sis_user_id': sis_user_id},
                    {'$set': {'identity': 'teacher'}}
                )
                
                # # 更新教师表 - 使用$addToSet避免重复课程
                # teacher_class_info = {
                #     'course_code': course_code,
                #     'course_name': course_name,
                #     'enrollment_term_id': class_info.get('enrollment_term_id', ''),
                #     'sis_course_id': sis_course_id
                # }
                
                # teachers_collection.update_one(
                #     {'sis_user_id': sis_user_id},
                #     {
                #         '$setOnInsert': {
                #             'sis_user_id': sis_user_id,
                #             'teacher_name': teacher.get('name')
                #         },
                #         '$addToSet': {'responsible_classes': teacher_class_info}
                #     },
                #     upsert=True
                # )
                
                
"""获取课程中的学生名单"""
def get_course_users(sis_course_id: str, include_enrollments: bool = False) -> List[Dict]:
    users = []
    page = 1
    per_page = 100
    
    while True:
        if include_enrollments:
            url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/users"
            params = {
                "include[]": "enrollments",
                "per_page": per_page,
                "page": page
            }
        else:
            url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/students"
            params = {
                "per_page": per_page,
                "page": page
            }
        
        try:
            response = requests.get(url, headers=HEADERS, params=params)
            response.raise_for_status()
            page_users = response.json()
            
            # 如果返回空数组，说明没有更多数据
            if not page_users:
                print(f"课程 {sis_course_id} 第 {page} 页返回空数据，结束分页")
                break
            
            users.extend(page_users)
            print(f"课程 {sis_course_id} 已获取第 {page} 页学生，本页 {len(page_users)} 条，当前总数: {len(users)}")
            
            # 如果返回数量少于请求数量，说明是最后一页
            if len(page_users) < per_page:
                print(f"课程 {sis_course_id} 第 {page} 页只有 {len(page_users)} 条数据，少于 {per_page}，结束分页")
                break
            
            page += 1
            
            # 添加延迟避免请求过快
            time.sleep(0.1)
            
        except requests.exceptions.RequestException as e:
            print(f"获取课程 {sis_course_id} 第 {page} 页学生失败: {e}")
            # 如果是404错误，说明页码超出范围
            if response.status_code == 404:
                print(f"课程 {sis_course_id} 页码超出范围，结束分页")
                break
            else:
                # 其他错误可以重试或退出
                break
    
    print(f"课程 {sis_course_id} 总共获取 {len(users)} 名学生")
    return users

def get_teachers_for_course(sis_course_id: str) -> List[Dict]:
    """获取课程的教师名单"""
    url = f"{BASE_URL}/courses/sis_course_id:{sis_course_id}/search_users"
    params = {
        "enrollment_type[]": "teacher",
        "per_page": 100
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取课程 {sis_course_id} 教师失败: {e}")
        return []


"""根据教师姓名查询教师负责的课程"""
def get_courses_by_teacher(teacher_name: str) -> List[Dict]:
    """通过教师姓名查询其负责的所有课程"""
    url = f"{BASE_URL}/accounts/3/courses"
    params = {
        "search_term": teacher_name,
        "search_by": "teacher",
        "per_page": 50
    }
    
    try:
        response = requests.get(url, headers=HEADERS, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"获取教师 {teacher_name} 的课程失败: {e}")
        return []
    
    
"""根据sis_user_id判断用户身份"""
def identify_user_by_sis_id(sis_user_id: str) -> str:
    """根据sis_user_id判断用户身份"""
    if not sis_user_id:
        return 'unknown'
    
    # 教师的sis_user_id位数不到八位，学生的至少八位
    if len(sis_user_id) < 8:
        return 'teacher'
    else:
        return 'student'
    
    
"""更新未识别身份的用户"""
def update_unknown_identities():
    """根据sis_user_id规则更新persons表中身份为unknown的用户"""
    persons_collection = db['persons']
    students_collection = db['students']
    teachers_collection = db['teachers']
    
    # 查找所有身份为unknown的用户
    unknown_users = list(persons_collection.find({'identity': 'unknown'}))
    print(f"找到 {len(unknown_users)} 个未识别身份的用户")
    
    for user in unknown_users:
        sis_user_id = user.get('sis_user_id')
        name = user.get('name')
        
        if not sis_user_id:
            continue
            
        identity = identify_user_by_sis_id(sis_user_id)
        
        if identity == 'student':
            # 更新人员身份
            persons_collection.update_one(
                {'sis_user_id': sis_user_id},
                {'$set': {'identity': 'student'}}
            )
            
            # 添加到学生表
            students_collection.update_one(
                {'sis_user_id': sis_user_id},
                {
                    '$setOnInsert': {
                        'sis_user_id': sis_user_id,
                        'student_name': name,
                        'enrolled_courses': []  # 初始为空，后续通过班级信息填充
                    }
                },
                upsert=True
            )
            print(f"  识别为学生: {name} ({sis_user_id})")
            
        elif identity == 'teacher':
            # 更新人员身份
            persons_collection.update_one(
                {'sis_user_id': sis_user_id},
                {'$set': {'identity': 'teacher'}}
            )
            
            # 添加到教师表
            teachers_collection.update_one(
                {'sis_user_id': sis_user_id},
                {
                    '$setOnInsert': {
                        'sis_user_id': sis_user_id,
                        'teacher_name': name,
                        'responsible_classes': []  # 初始为空，后续通过查询填充
                    }
                },
                upsert=True
            )
            print(f"  识别为教师: {name} ({sis_user_id})")


"""补全教师负责的课程信息"""
def complete_teacher_courses():
    """通过教师姓名查询并补全教师负责的课程信息"""
    teachers_collection = db['teachers']
    courses_collection = db['courses']
    
    # 获取所有教师
    all_teachers = list(teachers_collection.find())
    print(f"开始补全 {len(all_teachers)} 名教师的课程信息...")
    
    for teacher in all_teachers:
        teacher_name = teacher.get('teacher_name')
        sis_user_id = teacher.get('sis_user_id')
        
        if not teacher_name:
            continue
            
        print(f"查询教师 {teacher_name} 的课程...")
        teacher_courses = get_courses_by_teacher(teacher_name)
        
        if not teacher_courses:
            print(f"  教师 {teacher_name} 未找到负责的课程")
            continue
        
        # 处理找到的课程
        for course in teacher_courses:
            course_code = course.get('course_code')
            course_name = course.get('name')
            sis_course_id = course.get('sis_course_id')
            enrollment_term_id = course.get('enrollment_term_id')
            
            if not course_code or not sis_course_id:
                continue
                
            # 构建课程信息
            teacher_class_info = {
                'course_code': course_code,
                'course_name': course_name,
                'enrollment_term_id': enrollment_term_id,
                'sis_course_id': sis_course_id
            }
            
            # 使用addToSet避免重复
            teachers_collection.update_one(
                {'sis_user_id': sis_user_id},
                {'$addToSet': {'responsible_classes': teacher_class_info}}
            )
            
            print(f"  添加课程: {course_name} ({course_code})")
        
        # # 更新班级表中的教师信息（如果该班级已存在）
        # classes_collection = db['classes']
        # for course in teacher_courses:
        #     sis_course_id = course.get('sis_course_id')
        #     if sis_course_id:
        #         # 检查班级是否存在，如果存在则更新教师信息
        #         class_info = classes_collection.find_one({'sis_course_id': sis_course_id})
        #         if class_info:
        #             # 添加教师到班级的教师名单
        #             classes_collection.update_one(
        #                 {'sis_course_id': sis_course_id},
        #                 {
        #                     '$addToSet': {
        #                         'teacher_list': {
        #                             'sis_user_id': sis_user_id,
        #                             'teacher_name': teacher_name
        #                         }
        #                     },
        #                     '$inc': {'teacher_count': 1}
        #                 }
        #             )
        
                    
def main():
    print("开始填充数据库...")
    
    # 步骤1: 填充课程表和班级表
    print("步骤1: 填充课程表和班级表")
    populate_courses_and_classes()
    
    # 步骤2: 填充人员表（只填充基础信息）
    print("步骤2: 填充人员表")
    populate_persons()
    
    # 步骤3: 根据sis_user_id规则识别身份
    print("步骤3: 根据sis_user_id规则识别用户身份")
    update_unknown_identities()
    
    # 步骤4: 通过班级信息填充学生选课信息
    print("步骤4: 填充班级详情和学生选课信息")
    populate_class_details_and_identities()
    
    # 步骤5: 补全教师负责的课程信息
    print("步骤5: 补全教师负责的课程信息")
    complete_teacher_courses()
    
    print("数据库填充完成！")
    
    # 验证数据
    verify_data()

def verify_data():
    """验证填充的数据"""
    print("\n数据统计:")
    print("课程数量:", db['courses'].count_documents({}))
    print("班级数量:", db['classes'].count_documents({}))
    print("人员数量:", db['persons'].count_documents({}))
    print("学生数量:", db['students'].count_documents({}))
    print("教师数量:", db['teachers'].count_documents({}))
    
    # 查看身份分布
    identity_stats = db['persons'].aggregate([
        {"$group": {"_id": "$identity", "count": {"$sum": 1}}}
    ])
    print("\n身份分布:")
    for stat in identity_stats:
        print(f"  {stat['_id']}: {stat['count']}")

if __name__ == "__main__":
    main()