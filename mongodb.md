数据库（education2）
- 课程表（courses）：
    - 课程名称（course_name）、课程列表courses_list [{课程号（course_code）、class_list[{学期enrollment_term _id、id，班级号sis_course_id）}]}]
    - 知识点数量（knowledge_count）、知识点列表knowledge_list[{知识点ID（knowledge_id）、知识点名称（knowledge_name）}]

- 知识点表（knowledges）：
    - 知识点ID（knowledge_id）、所属课程号（course_code）、知识点名称（knowledge_name）
    - 访问记录access_records[{学号（sis_user_id）、访问时间（access_time）}]

- 学生表（students）：
    - 学号（sis_user_id）、id,学生姓名（student_name）、
    - 选修课程列表enrolled_courses [{课程号（course_code），id,学期enrollment_term _id 、班级号sis_course_id，知识点列表knowledge_list[{知识点ID（knowledge_id）、知识点名称（knowledge_name），状态（state）}]}]
    - 每个知识点的学习状态（未开始notLearned、学习中in_progress、已完成learned、需复习review_needed）

- 教师表（teachers）：
    - 教师工号（sis_user_id）、id、教师姓名（teacher_name）、负责班级responsible_classes [{课程号（course_code），id、课程名称course_name、学期enrollment_term _id 、班级号sis_course_id}]

- 班级表（classes）：
    - 课程号（course_code）、id、课程名称（course_name）、课程SIS ID（sis_course_id）、学期enrollment_term _id
    - 教师人数（teacher _count）、教师名单teacher_list[{教师工号sis_user_id， id、教师姓名（teacher_name）}]
    - 学生人数（student _count）、学生名单student_list[{学号sis_user_id， id、学生姓名（student_name）}]

- 人员表（persons）：
    - id、sis_user_id，姓名name，身份（identity）

=== Collection: knowledges | docs: 0 ===
(empty)

=== Collection: students | docs: 408 ===
{'_id': ObjectId('69324b7d295c2e23b1bebed9'),
 'sis_user_id': '20222371',
 'enrolled_courses': [],
 'id': 381,
 'student_name': '鲍文浩'}

=== Collection: teachers | docs: 68 ===
{'_id': ObjectId('69324b7d295c2e23b1bebed6'),
 'sis_user_id': '31998',
 'id': 1119,
 'responsible_classes': [{'course_code': '*EIE40302',
                          'id': 30,
                          'course_name': '机器人技术',
                          'enrollment_term_id': 10,
                          'sis_course_id': '*EIE40302_992370-001'},
                         {'course_code': '*ED21603',
                          'id': 48,
                          'course_name': '机器人基础',
                          'enrollment_term_id': 11,
                          'sis_course_id': '*ED21603_992002-001'},
                         {'course_code': '*EIE40307',
                          'id': 104,
                          'course_name': '机器人技术',
                          'enrollment_term_id': 5,
                          'sis_course_id': '*EIE40307_993960-001'},
                         {'course_code': '*EIE40302',
                          'id': 135,
                          'course_name': '机器人技术',
                          'enrollment_term_id': 12,
                          'sis_course_id': '*EIE40302_993083-001'}],
 'teacher_name': '柏龙'}

=== Collection: persons | docs: 477 ===
{'_id': ObjectId('69324b7d295c2e23b1bebb17'), 'sis_user_id': '31998', 'id': 1119, 'identity': 'teacher', 'name': '柏龙'}

=== Collection: courses | docs: 10 ===
{'_id': ObjectId('69324b7b295c2e23b1bebad4'),
 'course_name': '定量工程设计方法',
 'courses_list': [{'course_code': '*SCI11501',
                   'class_list': [{'id': 4, 'enrollment_term_id': 9, 'sis_course_id': '*SCI11501_991382-001'},
                                  {'id': 71, 'enrollment_term_id': 11, 'sis_course_id': '*SCI11501_991382-002'}]},
                  {'course_code': '*SCI11506',
                   'class_list': [{'id': 47, 'enrollment_term_id': 6, 'sis_course_id': '*SCI11506_993344-001'},
                                  {'id': 49, 'enrollment_term_id': 6, 'sis_course_id': '*SCI11506_993344-002'}]},
                  {'course_code': '*SCI11503',
                   'class_list': [{'id': 108, 'enrollment_term_id': 5, 'sis_course_id': '*SCI11503_993950-001'},
                                  {'id': 110, 'enrollment_term_id': 5, 'sis_course_id': '*SCI11503_993950-002'}]},
                  {'course_code': '*SCI21502',
                   'class_list': [{'id': 112, 'enrollment_term_id': 5, 'sis_course_id': '*SCI21502_992029-002'},
                                  {'id': 171, 'enrollment_term_id': 3, 'sis_course_id': '*SCI21502_992029-001'}]}],
 'knowledge_count': 0,
 'knowledge_list': []}

=== Collection: classes | docs: 29 ===
{'_id': ObjectId('69324b7b295c2e23b1bebac4'),
 'sis_course_id': '*SCI11501_991382-001',
 'course_code': '*SCI11501',
 'course_name': '定量工程设计方法',
 'enrollment_term_id': 9,
 'id': 4,
 'student_count': 0,
 'student_list': [],
 'teacher_count': 3,
 'teacher_list': [{'id': 1137, 'sis_user_id': '30800', 'teacher_name': '凌睿'},
                  {'id': 104, 'sis_user_id': '31557', 'teacher_name': '罗远新'},
                  {'id': 108, 'sis_user_id': '32083', 'teacher_name': '宋朝省'}]}