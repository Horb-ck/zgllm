from flask import Flask, request, jsonify, send_from_directory, render_template_string, abort
import os
import json
import uuid
from kg_json import KnowledgeGraphGenerator
from kg_json2graph import create_graph, load_json_data
# from cource_resource.search import VectorDatabase
import requests
import hashlib
from bs4 import BeautifulSoup
from flask_cors import CORS
from serverKG import serverKG

KGGEN_SHAREID="j0EwhUVVf3ZjC17uZKFCunrb"
kg_generator = KnowledgeGraphGenerator()

### 课程与shareid的映射
course2shareid = {
    "nn_output_enhanced1.html": "jm42v93u3ase8go5ekzo5jks",
    "nn_output_enhanced2.html": "ytln4c6g30jgcl99z2wjms1q",
    "nn_output_enhanced3.html": "ytln4c6g30jgcl99z2wjms1q",
    "nn_output_enhanced4.html": "ytln4c6g30jgcl99z2wjms1q",
}

# 课程名称与shareid的映射
courseName2shareid={
    "定量工程设计":"oT4Vpv11jYd77GzAS183GGau"
}

#尝试将该文件做成app.py的蓝图文件
#app = Flask(__name__, template_folder='course_graph_html') # 指定模板文件夹
#app.register_blueprint(serverKG)
server_bp = Blueprint('server_bp', __name__, template_folder='course_graph_html')

EXTERNAL_URL="http://mingyueai.cqu.edu.cn"
INTERNAL_URL="http://180.85.206.21:5000"

#为了创建蓝图对象，移除CORS配置，将其转移至app.py
# 添加CORS支持
#CORS_WHITELIST = [
#    EXTERNAL_URL,
#    INTERNAL_URL,
#    "http://180.85.206.21:5002"
#]
#CORS(app,
#     resources={r"/*": {"origins": CORS_WHITELIST}},
#     vary_header=True)

# 配置静态文件和输出目录
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
OUTPUT_DIR = os.path.join(STATIC_DIR, 'output')
COURSE_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'course_graph_html')
CACHE_DIR = os.path.join(STATIC_DIR, 'kg_cache')

# 创建必要的目录
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)


# 向量数据库加载
# vec_db = VectorDatabase()
# file_path = "/home/zgllm/workspace/elite_server/KG/cource_resource/txt_file/dlgc.jsonl"
# vec_db.load("/home/zgllm/workspace/elite_server/KG/cource_resource/pkl_file/learning_resources_db_faiss.pkl")

@server_bp.route('/')
#@app.route('/')
#
#蓝图对象创建：将所有的 @app.route 改为 @server_bp.route
#
def index():
    """
    主页路由。
    动态地将课程名称、学生ID和源文件名注入到HTML模板中。
    """
    course_name = request.args.get('course_name', '线性代数')
    student_id = request.args.get('student_id', '2002')

    print(f"--- serving index page ---")
    print(f"Course Name: {course_name}, Student ID: {student_id}")
    
    # 定义要渲染的HTML文件名
    html_filename = 'nn_output_enhanced1_学生端.html'
    html_filepath = os.path.join(COURSE_FOLDER, html_filename)

    if not os.path.exists(html_filepath):
        abort(404, description="HTML template file not found.")

    # ✨✨✨【新增逻辑】定义与此HTML文件对应的逻辑源文件名 ✨✨✨
    # 这个值应该与 course2shareid 字典中的一个键匹配
    logical_source_file = "nn_output_enhanced1.html" 
    print(f"Logical Source File for this page: {logical_source_file}")
    print(f"--------------------------")

    try:
        with open(html_filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # 准备要注入的JavaScript代码, 新增了 sourceFile 字段
        injection_script = f"""
        <script>
            window.PAGE_DATA = {{
                courseName: '{course_name}',
                studentId: '{student_id}',
                sourceFile: '{logical_source_file}'
            }};
            console.log('页面核心数据已注入:', window.PAGE_DATA);
        </script>
        """

        if '</head>' in html_content:
            final_html = html_content.replace('</head>', f'{injection_script}</head>', 1)
        else:
            final_html = f'<html><head>{injection_script}</head><body>{html_content}</body></html>'

        return render_template_string(final_html)

    except Exception as e:
        print(f"Error processing index request: {e}")
        abort(500, description="Server error while preparing the page.")


@server_bp.route('/static/<path:path>')
#@app.route('/static/<path:path>')
def send_static(path):
    """提供静态文件服务"""
    return send_from_directory('static', path)

@server_bp.route('/generate_kg', methods=['POST'])
#@app.route('/generate_kg', methods=['POST'])
def generate_kg():
    """Generate knowledge graph; now with disk cache per keyword/share/source."""
    data = request.json
    print("收到请求数据:", data)
    print("正在生成知识图谱")
    keyword = data.get('keyword')
    display_mode = data.get('display_mode', 'new_page')  # 默认为新页面打开，实则当前页面打开

    print(f"收到生成知识图谱请求：关键词 = {keyword}, 显示模式 = {display_mode}")

    if not keyword:
        print("错误：关键词为空")
        return jsonify({'error': '关键词不能为空'}), 400

    try:
        source_file = data.get('source_file', 'unknown')
        cache_key = f"{keyword}|{source_file}"
        cache_name = hashlib.sha256(cache_key.encode('utf-8')).hexdigest() + ".json"
        cache_path = os.path.join(CACHE_DIR, cache_name)

        json_result = None
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached = json.load(f)
                if isinstance(cached, dict) and 'nodes' in cached and 'links' in cached:
                    json_result = cached
                    print(f"缓存命中，直接使用: {cache_path}")
                else:
                    print(f"缓存文件缺少必要字段，忽略: {cache_path}")
            except Exception as cache_err:
                print(f"读取缓存失败，忽略缓存: {cache_err}")

        if json_result is None:
            json_result = kg_generator.generate_knowledge_graph(keyword=keyword, share_id=KGGEN_SHAREID)
            if not json_result or 'nodes' not in json_result or 'links' not in json_result:
                raise ValueError("生成知识图谱失败，上游返回空数据或缺少必要字段")
            try:
                tmp_path = cache_path + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(json_result, f, ensure_ascii=False)
                os.replace(tmp_path, cache_path)
                print(f"已写入缓存: {cache_path}")
            except Exception as write_err:
                print(f"写入缓存失败（不影响主流程）: {write_err}")

        studentid = "202313131168"
        html_file = os.path.join(OUTPUT_DIR, f"{studentid}_kg_local_knowledge_{source_file}.html")         #每个学生对应一个html可以固定成一个

        c = create_graph(nodes=json_result['nodes'], links=json_result['links'])
        c.render(html_file)

        result = {
            'success': True,
            'keyword': keyword,
            'html_path': f'/static/output/{os.path.basename(html_file)}',
            'display_mode': display_mode,
            'nodes': json_result['nodes'],
            'links': json_result['links']
        }
        print(f"知识图谱生成成功：{result}")

        return jsonify(result)
    
    except Exception as e:
        error_msg = f"生成知识图谱时出错: {str(e)}"
        print(error_msg)
        import traceback
        print(traceback.format_exc())
        return jsonify({'error': str(e)}), 500

# @app.route('/search/<query>', methods=['GET'])
# def search(query):
#     result=[]
#     initial_results = vec_db.search(query, top_k=5)
#     reranked_results = vec_db.rerank_results(query, initial_results, top_k=5)
#     for res in reranked_results:
#         result.append({"name":res['metadata']['name'],"url":res['metadata']['url']})
#     ans = {
#         "query": query,
#         "result": result
#     }
#     return jsonify(ans)

@server_bp.route('/search/<query>', methods=['GET'])
#@app.route('/search/<query>', methods=['GET'])
def search(query):
    # 构造 B站搜索 URL
    url = f'https://search.bilibili.com/all?keyword={query}'
    
    # 发起 GET 请求获取页面内容
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        return jsonify({"error": "Failed to retrieve data from Bilibili"}), 500

    # 使用 BeautifulSoup 解析 HTML 页面
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # 结果列表
    result = []
    count = 0

    # 找到所有包含视频信息的 div，匹配 class="bili-video-card__wrap"
    video_items = soup.find_all('div', class_='bili-video-card__wrap')

    # 最多提取前 5 个视频
    for video in video_items:
        if count >= 5:
            break
         
        # 提取视频链接
        link = video.find('a', href=True)
        href = link['href'] if link else ''
        
        # 补全相对链接
        if href.startswith('//'):
            href = 'https:' + href
        
        # 提取视频标题（alt 属性）
        alt = video.find('img', alt=True)['alt'] if video.find('img', alt=True) else ''

        if href and alt:
            result.append({"name": alt, "url": href})
            count += 1

    # 构建返回的数据结构
    ans = {
        "query": query,
        "result": result  # 返回的结果列表
    }

    # 返回 JSON 格式的响应
    return jsonify(ans)

# ====================================================================
# ==================== 学生端和教师端7000端口的单独页面 开始 ====================
# ====================================================================

# 访问方式：
# 学生端
# 127.0.0.1:7000/student
# 180.85.206.21:7000/student
# <服务器的IP地址>:7000/student
# 教师端
# 127.0.0.1:7000/teacher
# 180.85.206.21:7000/teacher
# <服务器的IP地址>:7000/teacher


# @app.route('/student')
# def student_view():
#     """
#     学生端专属路由。
#     提供 "nn_output_enhanced1_学生端.html" 页面。
#     """
#     course_name = request.args.get('course_name', '线性代数')
#     student_id = request.args.get('student_id', '2002')

#     print(f"--- serving STUDENT page via /student ---")
#     print(f"Course Name: {course_name}, Student ID: {student_id}")
    
#     html_filename = 'nn_output_enhanced1_学生端.html'
#     html_filepath = os.path.join(COURSE_FOLDER, html_filename)

#     if not os.path.exists(html_filepath):
#         abort(404, description="Student HTML template file not found.")

#     logical_source_file = "nn_output_enhanced1.html" 
#     print(f"Logical Source File for this page: {logical_source_file}")
#     print(f"--------------------------")

#     try:
#         with open(html_filepath, 'r', encoding='utf-8') as f:
#             html_content = f.read()

#         injection_script = f"""
#         <script>
#             window.PAGE_DATA = {{
#                 courseName: '{course_name}',
#                 studentId: '{student_id}',
#                 sourceFile: '{logical_source_file}'
#             }};
#             console.log('页面核心数据已注入:', window.PAGE_DATA);
#         </script>
#         """

#         if '</head>' in html_content:
#             final_html = html_content.replace('</head>', f'{injection_script}</head>', 1)
#         else:
#             final_html = f'<html><head>{injection_script}</head><body>{html_content}</body></html>'

#         return render_template_string(final_html)

#     except Exception as e:
#         print(f"Error processing student_view request: {e}")
#         abort(500, description="Server error while preparing the student page.")


# @app.route('/teacher')
# def teacher_view():
#     """
#     教师端专属路由。
#     提供 "nn_output_enhanced1_教师端.html" 页面。
#     """
#     course_name = request.args.get('course_name', '线性代数')
#     teacher_id = request.args.get('student_id', 'teacher001') # 参数名保持 student_id 以便前端复用

#     print(f"--- serving TEACHER page via /teacher ---")
#     print(f"Course Name: {course_name}, Teacher ID: {teacher_id}")
    
#     html_filename = 'nn_output_enhanced1_教师端.html'
#     html_filepath = os.path.join(COURSE_FOLDER, html_filename)

#     if not os.path.exists(html_filepath):
#         abort(404, description="Teacher HTML template file not found.")

#     logical_source_file = "nn_output_enhanced1.html" 
#     print(f"Logical Source File for this page: {logical_source_file}")
#     print(f"--------------------------")

#     try:
#         with open(html_filepath, 'r', encoding='utf-8') as f:
#             html_content = f.read()

#         # JS对象中的键名仍使用 studentId 以保证前端代码一致性
#         injection_script = f"""
#         <script>
#             window.PAGE_DATA = {{
#                 courseName: '{course_name}',
#                 studentId: '{teacher_id}',
#                 sourceFile: '{logical_source_file}'
#             }};
#             console.log('页面核心数据已注入:', window.PAGE_DATA);
#         </script>
#         """

#         if '</head>' in html_content:
#             final_html = html_content.replace('</head>', f'{injection_script}</head>', 1)
#         else:
#             final_html = f'<html><head>{injection_script}</head><body>{html_content}</body></html>'

#         return render_template_string(final_html)

#     except Exception as e:
#         print(f"Error processing teacher_view request: {e}")
#         abort(500, description="Server error while preparing the teacher page.")

# ====================================================================
# ===================== 学生端和教师端7000端口的单独页面 结束 =====================
# ====================================================================

@server_bp.after_request
#@app.after_request
def add_header(response):
    """添加响应头，禁止缓存"""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

#if __name__ == '__main__':
#    app.config['JSON_AS_ASCII'] = False
#    app.run(debug=False, host='0.0.0.0', port=7000) 
