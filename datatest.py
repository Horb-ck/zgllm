import pymysql
from pymongo import MongoClient
from config import MYSQL_URL,MONGO_URL
# --- 数据库连接配置 ---
MYSQL_CONFIG = {
    "host": "MYSQL_URL",
    "user": "root",
    "password": "123456",
    "database": "zgllm",
    "charset": "utf8mb4"
}

MONGO_CONFIG = {
    "host": "localhost",
    "port": 27027,
    "username": "root",
    "password": "123456",
    "authSource": "admin"
}

def sync_data():
    # 1. 连接 MongoDB
    mongo_client = MongoClient(
        host=MONGO_CONFIG['host'],
        port=MONGO_CONFIG['port'],
        username=MONGO_CONFIG['username'],
        password=MONGO_CONFIG['password'],
        authSource=MONGO_CONFIG['authSource']
    )
    mongo_db = mongo_client['education2']
    persons_col = mongo_db['persons']

    # 2. 连接 MySQL
    mysql_conn = pymysql.connect(
        host=MYSQL_URL,
        user="root",
        password="123456",
        database="zgllm",
        charset="utf8mb4"
    )
    
    try:
        with mysql_conn.cursor() as cursor:
            # Step A: 从 MySQL 获取所有需要匹配的 sid
            print("正在读取 MySQL 数据...")
            cursor.execute("SELECT sid FROM student WHERE sid IS NOT NULL")
            mysql_students = cursor.fetchall()
            # 将结果转换为列表，方便 MongoDB 查询
            sids = [str(row[0]) for row in mysql_students]

            # Step B: 在 MongoDB 中批量查询对应的 login_id
            # 使用 $in 操作符提高性能
            print(f"正在 MongoDB 中查询 {len(sids)} 条记录...")
            mongo_results = persons_col.find(
                {"login_id": {"$in": sids}},
                {"login_id": 1, "sis_user_id": 1, "_id": 0}
            )

            # 建立 login_id -> sis_user_id 的映射字典
            mapping = {item['login_id']: item['sis_user_id'] for item in mongo_results}

            # Step C: 批量更新 MySQL
            print("正在更新 MySQL student 表...")
            update_sql = "UPDATE student SET sis_id = %s WHERE sid = %s"
            
            update_data = []
            for sid, sis_id in mapping.items():
                update_data.append((sis_id, sid))

            if update_data:
                # 使用 executemany 进行批量更新，效率远高于循环执行单个 update
                cursor.executemany(update_sql, update_data)
                mysql_conn.commit()
                print(f"同步成功！共更新 {len(update_data)} 条记录。")
            else:
                print("未匹配到任何对应数据，无需更新。")

    except Exception as e:
        print(f"发生错误: {e}")
        mysql_conn.rollback()
    finally:
        mysql_conn.close()
        mongo_client.close()

if __name__ == "__main__":
    sync_data()


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

# # 知识点原始数据
# KNOWLEDGE_DATA = [
#     {"course_name": "科技发展史", "knowledge_points": ["科技发展史", "Classical Civilizations", "Prehistory&Ancient", "Islamic Golden Age", "Medieval Europe", "Renaissance", "Scientific Revolution", "Industrial Revolution", "19th Century", "20th Century", "21st Century", "Stone Tools", "Fire", "Language", "Agriculture", "Wheel", "Writing systems", "Archimedes", "Pythagoras", "Aristotle", "Roman Aqueducts", "Chinese Papermaking", "Indian Numerals", "Al-Khwarizmi (Algebra)", "Avicenna(Mdicine)", "lbn al-Haytham(Optics)", "Translation movement", "House of Wisdom", "Monastic Libraries", "Windmill", "Heavy Plow", "University of Bologna", "Scholasticism", "Leonardo da Vinci", "Copernicus", "Vesalius", "Printing Press", "Human Anatomy studies", "Galileo", "Kepler", "Newton", "Boyle", "Leeuwenhoek", "Scientific Method", "James Watt", "Steam Engine", "Factory system", "Faraday", "Volta", "Mechanical Loom", "Darwin", "Mendeleev", "Tesla", "Edison", "Pasteur", "Maxwell", "Internet", "Moon Landing", "Transistor", "Internal Combustion Engine", "Einstein", "Bohr", "Turing", "Sputnik", "von Neumann", "Watson & Crick", "Heisenberg", "Schrödinger", "CRISPR", "Quantum Computing", "Reusable Rockets", "SpaceX", "Human Genome Project", "Deep Learning", "Renewable Energy"]},
#     {"course_name": "人类文明史", "knowledge_points": ["人类文明史", "Unit 1 - Dawn of Civilization", "Unit 2 - Rise of Empires", "Unit 3 - Classical Warfare and Diplomacy", "Unit 4 - Byzantium and the Middle Ages", "Unit 5 - Golden Age of Islam", "Unit 6 - Renaissance, Revolution & Enlightenment", "Unit 7 - The Industrial Revolution & Its Foundations", "Unit 8 - World War I", "Human Origins & Early Societies", "The Neolithic Revolution", "Characteristics of Civilization", "The Bronze Age Collapse", "Case Study: Classical China", "Legacy & Foundations", "Hunter-Gatherer Societies", "Nomadic lifestyle", "Advent of Agriculture", "Sedentary Lifestyle", "Food Surplus", "Social Stratification", "Urban centers", "Centralized government", "System of writing", "First-Wave Civilizations", "River valley civilizations", "Event", "Major civilization collapse", "Invasions", "Systems collapse", "Greek Dark Age", "Transition to Iron Age", "Bronze Age Culture", "Warring States Period", "Military Revolution", "Philosophical Development", "Legal Systems", "Technological Progress", "State Formation", "The Achaemenid Empire", "Classical Greece", "Alexander the Great", "The Roman Empire", "Classical China", "Cross-Civilizational Themes", "Imperial Administration", "Policy of Tolerance", "Model for administration", "Polis system", "Persian Wars", "Peloponnesian War", "Thucydides Trap", "Conquests", "Created vast empire", "Spread of Greek culture", "Expansion", "Mediterranean dominance", "Transition to Empire", "Division and fall", "Law and engineering", "Unification", "Qin and Han Dynasties", "Silk Road", "State Structure", "Imperial Models", "Causes of Decline", "Enduring Legacies", "The Greco-Persian Wars", "The Peloponnesian War", "Rise of Macedonia", "Legacy & Later Developments", "Major Battles", "Greek alliance", "Opposing Alliances", "Athenian vs Spartan leagues", "Weakening of Greece", "Philip II of Macedon", "Unified Greece", "Shift to empires", "Herodotus and Thucydides", "Balance of Power", "The Byzantine Empire", "Medieval Europe", "Key Connections", "Roman continuation", "Capital: Constantinople", "Great Schism", "Preserved classical knowledge", "Feudalism", "Manorialism", "Catholic Church dominance", "Decentralized states", "Byzantium as bridge", "1453 as turning point", "Origins & Expansion", "Caliphates", "Golden Age", "Intellectual Achievements", "Crusades", "Decline & End", "Rise of Islam", "Spread through Arabia", "Major caliphates", "Religious-political system", "Timeframe: 8th-13th centuries", "Center: Baghdad", "House of Wisdom", "Translation Movement", "Scientific advancements", "Preservation of Greek texts", "Christian campaigns", "Cultural tensions", "Mongol invasion", "The Renaissance", "Scientific Revolution", "Major Effects", "Age of Discovery", "Humanism", "Printing Press", "Classical revival", "Paradigm Shift", "Observation and reason", "Copernicus, Galileo, Newton", "Conflict with Religion", "New Worldview", "Gold, Glory, God", "Columbus's Voyage", "Columbian Exchange", "Colonialism", "Foundations", "Industrial Revolution", "Societal Impact", "Military Evolution", "Global Consequences", "Enlightenment", "American and French", "Steam Engine", "Agrarian to industrial", "Bourgeoisie and proletariat", "Urbanization", "Technological Advancements", "Mass mobilization", "European Supremacy", "Spread of Ideals", "Causes", "Nature of the War", "Major Events", "Consequences & Legacy", "Militarism", "Alliance System", "Imperialism", "Nationalism", "The Spark", "Trench Warfare", "Technological Warfare", "Total War", "1914: War Begins", "1915-1916: Stalemate", "1917: Turning Point", "1918: Endgame", "Human Cost", "Empire collapses", "Treaty of Versailles", "Psychological Impact"]},
#     {"course_name": "线性代数", "knowledge_points": ["线性代数", "矩阵的基本概念和基本运算", "线性空间和线性变换", "特征值理论及其应用", "人脸识别项目", "编程计算工具", "矩阵的基本概念", "矩阵的初等变换", "矩阵的基本运算", "线性空间的基本理论", "线性变换的基本理论", "线性方程组的通解", "方阵的特征值和特征向量", "方阵的相似对角化", "对称阵的正定性", "矩阵的奇异值分解", "人脸数字图像的预处理", "基于PCA的人脸数字图像特征提取和降维算法", "人脸识别分类器和系统GUI设计", "MATLAB", "python"]},
#     {"course_name": "移动机器人应用与开发", "knowledge_points": ["移动机器人应用与开发", "机器人定义与组成", "执行机构", "驱动系统", "传感系统", "控制系统", "ROS", "ROS系统架构", "ROS节点通信", "ROS调试工具", "ROS开发", "Linux", "vscode", "C++", "python", "git", "rqt", "RViz", "机器人底盘运动控制", "底盘运动学模型", "两轮差速模型", "四轮差速模型", "阿克曼模型", "全向模型", "底盘系统搭建", "机器人速度控制", "机器视觉", "数字图像处理", "OpenCV", "图像特征点提取与匹配", "点云提取与匹配", "图像视觉应用", "SLAM", "机器人定位", "刚体位pose描述", "刚体坐标变换", "SLAM分类", "视觉SLAM", "激光雷达SLAM", "卫星定位", "SLAM融合方案", "路径规划", "地图处理", "语义地图", "高精度地图", "运动空间与控制空间", "路径搜索", "轨迹优化与轨迹跟踪", "轨迹优化", "Min-Jerk", "轨迹跟踪", "PID", "Navigation2", "NAV2的组成结构", "Navigation2重要模块", "Navigation2运行流程", "深度学习理论", "图像分类", "神经网络基础", "卷积神经网络"]},
#     {"course_name": "定量工程设计方法", "knowledge_points": ["定量工程设计方法", "三维建模与仿真工具", "SolidWorks", "ANSYS/COMSOL", "编程计算工具", "Matlab", "Python", "嵌入式开发工具", "STM32", "ESP32", "物理相关知识点", "离散/连续物体的质心分布", "非对称结构的质心偏移", "动态系统的等效质心", "浮力与浮心", "重心/浮心计算", "蒙特卡洛随机采样法", "有限元离散化方法", "网格划分与加权平均法", "力与力矩系统", "稳心与扶正力矩", "数学相关知识点", "曲线下面积计算", "解析方法", "数值方法", "离散化与微积分", "离散化思想", "工程数学", "船体设计", "船型设计基础", "型线图要素", "性能优化", "结构设计", "构件计算", "材料选择", "动力系统", "推进系统", "螺旋桨理论", "匹配设计", "控制系统", "遥控系统", "自主控制", "制造工艺", "传统工艺", "现代工艺", "测试与优化", "实验方法", "优化设计", "项目管理", "工程文档", "BOM表", "技术报告", "团队协作", "任务分配", "质量管控", "测试"]},
#     {"course_name": "机器人基础", "knowledge_points": ["机器人数学基础", "数学符号与证明技术", "抽象线性空间与线性变换", "抽象内积空间", "三类矩阵分解", "概率统计基础与卡尔曼滤波", "序列极限及函数极值", "优化方法", "编程计算工具", "数学符号及术语", "验证技术回顾", "真值表", "否定逻辑陈述", "实数的关键属性", "数域", "线性空间", "基和维度", "线性变换", "线性变换的矩阵表示", "特征值与特征向量", "范数空间", "内积空间", "施密特正交化", "投影定理", "对称与正定阵", "QR分解", "SV分解", "LU&Cholesky分解", "概率空间", "随机变量", "随机向量", "BLUE&MVE理论", "卡尔曼滤波", "赋范空间中的开闭集", "牛顿迭代算法", "序列", "柯西序列与完备性", "收缩映射定理", "紧集与函数极值的存在性", "凸集和凸函数", "表示法", "二次规划", "线性规划", "最小化", "优化算法", "Matlab"]},
#     {"course_name": "程序设计实践", "knowledge_points": ["程序设计实践", "基础语法和控制语句", "数组和函数", "面向对象编程", "动态内存管理和文件操作", "程序设计语言概述", "C/C++语言基础", "内存模型与变量", "运算符与表达式", "控制语句", "数组", "函数基础", "存储类型与作用域", "递归函数", "多文件结构", "结构体与类", "继承与多态", "模板编程", "C++标准库(STL)", "指针基础", "动态内存分配", "文件操作基础", "C++文件流", "机器语言、汇编语言、高级语言的定义与区别", "C/C++语言的应用领域", "TIOBE编程语言排行榜", "程序结构", "注释", "预处理指令", "主函数main()", "标识符与关键字", "命名规则", "大小写敏感", "数据类型", "基本类型", "类型转换", "内存分区", "代码区", "数据区", "变量定义与初始化", "作用域与生存期", "常量", "符号常量", "字面常量", "算术运算符", "加减乘除取模运算符", "自增/自减", "关系与逻辑运算符", "位运算符", "赋值运算符与复合赋值", "运算符优先级与结合性", "顺序结构", "表达式语句", "空语句", "复合语句", "选择结构", "if语句", "switch语句", "循环结构", "while", "do-while", "for循环", "跳转语句", "break", "continue", "return", "一维数组", "定义", "初始化", "内存存储", "多维数组", "二维/三维数组", "行优先存储原则", "字符数组与字符串", "字符串结束符", "strcpy/strlen等库函数", "函数定义", "返回值类型", "参数列表", "函数体", "函数调用", "值传递", "地址传递", "函数原型声明", "作用", "格式", "局部变量", "自动变量", "静态局部变量", "全局变量", "作用域", "静态全局变量", "变量的可见性", "作用域屏蔽规则", "作用域符号", "递归定义", "函数自调用", "终止条件", "经典递归问题", "阶乘", "汉诺塔", "斐波那契数列", "头文件", "头文件中的函数原型声明", "宏定义", "结构体/类定义", "源文件", "函数实现", "主函数调用", "#include", "#define", "条件编译", "结构体", "复合数据类型", "成员访问", "类的定义", "成员变量", "成员函数", "构造函数与析构函数", "类与结构体的区别", "默认访问权限", "结构体的成员函数", "继承机制", "基类与派生类", "公有继承", "虚函数与多态", "virtual关键字", "动态绑定", "纯虚函数与抽象类", "模板函数", "泛型编程", "类型参数化", "模板类", "容器类模板", "成员函数模板", "序列容器", "vector", "deque", "list", "关联容器", "map", "set", "unordered_map", "字符串处理", "std::string与C-String的区别", "常用成员函数", "指针定义与初始化", "空指针", "指针运算", "解引用", "地址运算", "指针加减", "指针与数组", "数组名作为指针", "指针数组与数组指针", "C语言方式", "malloc/free", "内存泄漏问题", "C++方式", "new/delete", "数组动态分配", "智能指针", "unique_ptr", "shared_ptr", "文件类型", "文本文件", "二进制文件", "C语言文件操作", "fopen/fclose", "fprintf/fscanf", "fgets/fputs", "ifstream/ofstream/fstream类", "文件打开模式", "读写操作", "<<和>>运算符", "getline函数", "二进制读写"]},
#     {"course_name": "自动控制原理", "knowledge_points": ["自动控制原理", "工程对象数学建模", "时域分析", "根轨迹法", "频域分析", "PID控制", "基本建模方法", "微分方程", "状态空间方程", "传递函数", "建模案例-Buck变换器", "建模案例-H桥逆变器", "控制系统性能", "控制系统稳定性分析", "控制系统性能指标", "主导极点", "阶跃响应", "线性定常系统稳定", "劳斯判据", "峰值时间", "最大超调量", "调节时间", "闭环传递函数", "闭环特征方程式", "开环传递函数", "根轨迹的绘制法则", "频率特性基本概念", "频率特性法", "频率特性求取", "频率特性的图示方法", "奈奎斯特稳定判据", "波特图频域指标计算", "对数稳定判据", "相对稳定性", "稳定裕度", "校正设计基本方法", "PID控制基本思想", "PI控制直流Buck变换器", "PID控制规律", "综合法", "分析法", "频率响应设计法", "串联超前校正", "串联滞后校正"]},
#     {"course_name": "概率论与数理统计", "knowledge_points": ["概率论与数理统计", "随机事件及其概率", "随机变量及其分布", "随机向量及其分布", "大数定律与中心极限定理", "统计量及其分布", "参数估计", "假设检验", "现代产品质量管理项目", "人工智能分类算法项目", "编程计算工具", "随机事件及其运算", "概率的定义与性质", "计算概率的几个公式", "随机变量的整体刻画", "随机变量的局部刻画", "离散型随机变量", "连续型随机变量", "随机向量的“整体刻画”", "随机向量的“局部刻画”", "离散型随机向量", "连续型随机向量", "随机变量序列的收敛性", "特征函数", "大数定律", "中心极限定理", "样本数据及其可视化", "常见的几大统计量", "抽样分布定理", "点估计及其评价准则", "区间估计及其评价准则", "假设检验的基本原理", "小样本假设检验", "大样本假设检验", "产品质量管理概述", "产品工序能力指数", "产品过程控制", "现代产品质量管理项目具体任务", "Logistic分类模型", "支持向量机分类模型", "人工智能分类算法项目具体任务", "MATLAB"]},
#     {"course_name": "软件设计", "knowledge_points": ["软件系统架构技术", "C端产品数据模拟器", "上传数据到服务器", "数据存储到数据库", "用户设备管理（微信小程序）", "数据分析与可视化", "随机数", "让随机数符合统计规律", "将结果和日志写入文件", "多线程", "GUI界面", "用Git管理代码", "在Linux系统上部署模拟器", "Docker容器技术", "Socket通信", "Flask框架", "API接口设计", "加密与鉴权", "计算机网络", "服务器端高并发技术", "数据库", "关系型数据库", "NoSQL数据库", "软件开发过程", "微信公共号", "服务号", "订阅号", "服务号与订阅号的差异", "微信小程序操作", "Web开发技术介绍", "Vue开发环境配置", "Vue组件开发Web前端", "Web后端（Flask）", "前后端程序在服务器上的部署", "Web前端图表（EChart）", "高并发处理", "伪随机数生成算法", "真随机数生成原理", "分布转换方法", "常用分布实现", "多元随机数生成", "蒙特卡洛积分", "分布拟合验证", "日志分级管理", "多目标输出技术", "结构化日志格式", "日志轮转机制", "结果持久化方案", "协议栈实现差异", "并发模型设计", "粘包处理方案", "NAT穿透技术", "路由高级特性", "请求生命周期", "扩展集成方案", "WSGI优化", "版本控制策略", "认证鉴权方案", "限流保护机制", "文档自动化", "对称加密应用", "非对称体系实践", "密码存储安全", "传输层安全", "数字签名机制", "协议栈核心原理", "路由寻址机制", "应用层协议分析", "网络诊断工具", "IO模型演进", "连接复用优化", "负载均衡方案", "容灾降级机制", "数据库的由来", "数据库分类", "数据库的优势", "关系型数据库与NoSQL数据库的区分与应用", "关系模型", "关系代数", "事务", "实体联系", "MySQL的基本概念", "SQL操作", "连接数据库", "执行SQL操作", "MySQL的安全性设置", "NoSQL的概念", "键值对数据库", "文档型数据库", "图形数据库", "MongoDB的基本概念", "MongoDB的安装", "MongoDB连接", "写入数据", "检索数据", "需求分析", "软件设计", "软件测试", "UI设计", "微信小程序开发者申请", "创建微信小程序", "开发环境IDE介绍", "文件结构", "小程序的路由管理", "小程序的数据绑定", "小程序的基础组件", "小程序的表单组件", "小程序的导航组件", "小程序的媒体组件", "小程序的地图组件", "小程序的画布组件", "微信小程序的API", "Restful API之间的调用", "web开发核心要素", "前端开发技术", "前端框架", "后端开发技术", "环境搭建", "项目结构", "路由配置", "开发工具", "常用组件库", "View UI开发流程", "组件开发基础", "实战案例", "Flask基础", "跨域处理", "前端调用后端", "实战练习", "Docker部署优势", "云服务器配置", "前端部署流程", "后端部署流程", "镜像管理", "ECharts基础", "Vue中使用ECharts", "前后端整合", "后端高并发策略", "前端高并发策略", "负载均衡实现"]},
#     {"course_name": "机器人动力学与控制", "knowledge_points": ["机器人动力学与控制", "机器人导论", "机器人分类", "机器人组成", "技术参数", "应用趋势", "项目化课程", "机器人位姿及齐次变换", "位姿表示", "齐次变换", "正运动学", "逆运动学", "变换应用", "旋转变换通式和四元数", "旋转表示", "四元数代数", "四元数矩阵转换", "四元数插值", "四元数轨迹规划", "机器人运动学与轨迹规划", "PUMA560运动学", "XB7运动学", "轨迹约束", "轨迹生成", "笛卡尔空间规划", "笛卡尔轨迹", "末端轨迹", "计算复杂度", "适用场景", "关节空间规划", "轨迹映射", "时间参数化", "运动约束", "时间分配", "关节避障", "机器人动力学", "力-运动关系", "动力学正问题", "动力学逆问题", "模型耦合", "系统分析", "机器人关节传动系统", "关节传动系统", "等效转动惯量", "电机驱动特性", "关节转动动力学", "控制性能", "动力学参数辨识", "质量参数", "质心参数", "惯性参数", "摩擦参数", "建模仿真应用", "控制优化应用", "机器人运动控制", "嵌入式控制系统", "电机控制", "关节驱动", "机械臂控制", "移动机器人控制", "闭环反馈", "PID控制", "伺服控制", "机器人直流电机双闭环控制Matlab仿真", "双闭环控制", "电流环", "速度环", "Matlab仿真", "机器人系统架构", "机器人系统集成", "机器人应用开发"]}
# ]

# COURSES_LIST = [
#     "定量工程设计方法", "自动控制原理", "程序设计实践", 
#     "移动机器人应用与开发", "线性代数",
#     "机器人基础", "概率论与数理统计", "人类文明史", "科技发展史","软件设计","机器人动力学与控制"
# ]

# def get_knowledge_points(course_name: str, with_state: bool = False):
#     """根据课程名获取知识点列表"""
#     for item in KNOWLEDGE_DATA:
#         if item["course_name"] == course_name:
#             points = []
#             for i, name in enumerate(item["knowledge_points"], 1):
#                 node = {"knowledge_id": i, "knowledge_name": name}
#                 if with_state:
#                     node["state"] = "notLearned"
#                 points.append(node)
#             return points
#     return []

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
#         # --- 核心逻辑：获取并处理该课程的知识点 ---
#         current_knowledge_list = []
#         # 在 KNOWLEDGE_DATA 中查找匹配的课程
#         for item in KNOWLEDGE_DATA:
#             if item["course_name"] == course_name:
#                 # 按序生成带有 ID 的知识点列表
#                 for index, kp_name in enumerate(item["knowledge_points"], 1):
#                     current_knowledge_list.append({
#                         "knowledge_id": index,
#                         "knowledge_name": kp_name
#                     })
#                 break
#         # ---------------------------------------
#         # 按课程号分组，同一个课程号可能有多个班级
#         courses_by_code = {}
#         for classitem in courses_data:
#             course_code = classitem.get('course_code')
#             if course_code not in courses_by_code:
#                 courses_by_code[course_code] = []
#             courses_by_code[course_code].append(classitem)
        
#         # 构建课程列表
#         courses_list = []
#         for course_code, class_instances in courses_by_code.items():
#             # 构建班级列表
#             class_list = []
#             for class_instance in class_instances:
#                 class_info = {
#                     'id': class_instance.get('id'),
#                     'enrollment_term_id': class_instance.get('enrollment_term_id'),
#                     'sis_course_id': class_instance.get('sis_course_id')
#                 }
#                 class_list.append(class_info)
                
#                 # 填充班级表
#                 class_doc = {
#                     'sis_course_id': class_instance.get('sis_course_id'),
#                     'course_code': course_code,
#                     'course_name': course_name,
#                     'id':class_instance.get('id'),
#                     'enrollment_term_id': class_instance.get('enrollment_term_id'),
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
            
#             # 构建课程信息
#             course_info = {
#                 'course_code': course_code,
#                 'class_list': class_list
#             }
#             courses_list.append(course_info)
#             print(f"  添加课程号: {course_code}, 包含 {len(class_list)} 个班级")
        
#         # 填充课程表（新的结构）
#         course_doc = {
#             'course_name': course_name,
#             'courses_list': courses_list,
#             'knowledge_count': 0,
#             'knowledge_list': current_knowledge_list
#         }
#         courses_collection.update_one(
#             {'course_name': course_name},
#             {'$set': course_doc},
#             upsert=True
#         )
#         print(f"  更新课程: {course_name}, 包含 {len(courses_list)} 个课程号,包含 {len(current_knowledge_list)} 个知识点")



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
#             'login_id': user.get('login_id'),
#             'name': user.get('name'),
#             'id': user.get('id'),
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
#         course_id = class_info['id']
        
#         print(f"处理班级: {sis_course_id}")
#         # 1. 获取该课程的基础知识点模版
#         # 从 KNOWLEDGE_DATA 中匹配，并初始化 state
#         initial_knowledge_list = []
#         for item in KNOWLEDGE_DATA:
#             if item["course_name"] == course_name:
#                 for index, kp_name in enumerate(item["knowledge_points"], 1):
#                     initial_knowledge_list.append({
#                         "knowledge_id": index,
#                         "knowledge_name": kp_name,
#                         "state": "notLearned"  # 初始化状态
#                     })
#                 break
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
#                     'login_id': student.get('login_id'),
#                     'id':student.get('id'),
#                     'student_name': student.get('name')
#                 })
        
#         teacher_list = []
#         for teacher in teachers:
#             if teacher.get('sis_user_id'):
#                 teacher_list.append({
#                     'sis_user_id': teacher.get('sis_user_id'),
#                     'login_id': teacher.get('login_id'),
#                     'id':teacher.get('id'),
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
#             student_id = student.get('id')
#             if sis_user_id:
#                 # 更新人员身份
#                 persons_collection.update_one(
#                     {'sis_user_id': sis_user_id},
#                     {'$set': {'identity': 'student'}}
#                 )
                
#                 # 更新学生表 - 使用$addToSet避免重复课程
#                 student_course_info = {
#                     'course_name': course_name,
#                     'course_code': course_code,
#                     'id':course_id,
#                     'enrollment_term_id': class_info.get('enrollment_term_id', ''),
#                     'sis_course_id': sis_course_id,
#                     'knowledge_list': initial_knowledge_list  # 填充带 state 的知识点
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
                
                
# """获取课程中的学生名单"""
# def get_course_users(sis_course_id: str, include_enrollments: bool = False) -> List[Dict]:
#     users = []
#     page = 1
#     per_page = 100
#     seen_ids = set() # 记录已经抓取过的用户 ID
    
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
#             # 统计这一页有多少是“新面孔”
#             new_count = 0
#             for u in page_users:
#                 u_id = u.get('id')
#                 if u_id not in seen_ids:
#                     users.append(u)
#                     seen_ids.add(u_id)
#                     new_count += 1
#             # 【核心改进】：如果这一页一个新人都没发现，说明在无限循环，直接退出
#             if new_count == 0:
#                 print(f"课程 {sis_course_id} 第 {page} 页全是重复数据，强制跳出防止死循环。")
#                 break        
            
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
#         user_id = user.get('id')
#         login_id = user.get('login_id')
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
#                         'login_id': login_id,
#                         'student_name': name,
#                         'id': user_id,
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
#                         'login_id': login_id,
#                         'id': user_id,
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
#             course_id = course.get('id')
#             sis_course_id = course.get('sis_course_id')
#             enrollment_term_id = course.get('enrollment_term_id')
            
#             if not course_code or not sis_course_id:
#                 continue
                
#             # 构建课程信息
#             teacher_class_info = {
#                 'course_code': course_code,
#                 'course_name': course_name,
#                 'id':course_id,
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
