from flask import request, Blueprint, render_template_string, abort
import os
import json

app_kg = Blueprint('app_kg', __name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# COURSE_FOLDER = os.path.join(BASE_DIR, 'KG', 'course_graph_html')
VISITOR_TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates', 'knowledge_graph', 'KG_for_vistor.html')


def _inject_page_data(html_content: str, page_data: dict) -> str:
    """Inject PAGE_DATA script into html content."""
    injection_script = f"""
    <script>
        window.PAGE_DATA = {json.dumps(page_data, ensure_ascii=False)};
        console.log('页面核心数据已注入:', window.PAGE_DATA);
    </script>
    """
    if '</head>' in html_content:
        return html_content.replace('</head>', f'{injection_script}</head>', 1)
    return f'<html><head>{injection_script}</head><body>{html_content}</body></html>'

@app_kg.route('/kg_page/visitor', methods=['GET'])
def visitor_view():
    """
    游客端知识图谱页面，注入课程信息用于前端展示。
    """
    course_name = request.args.get('course_name', '线性代数')
    visitor_id = request.args.get('visitor_id', 'guest')

    if not os.path.exists(VISITOR_TEMPLATE_PATH):
        abort(404, description="Visitor KG template not found.")

    try:
        with open(VISITOR_TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            html_content = f.read()

        page_data = {
            "courseName": course_name,
            "visitorId": visitor_id,
            "sourceFile": "KG_for_vistor.html"
        }
        final_html = _inject_page_data(html_content, page_data)
        return render_template_string(final_html)
    except Exception as e:
        print(f"Error processing visitor_page request: {e}")
        abort(500, description="Server error while preparing the visitor page.")

@app_kg.route('/kg_page/student')
def student_view():
    """
    学生端专属路由。
    提供 "nn_output_enhanced1_学生端.html" 页面。
    """
    course_name = request.args.get('course_name', '线性代数')
    student_id = request.args.get('student_id', '2002')

    print(f"--- serving STUDENT page via /student ---")
    print(f"Course Name: {course_name}, Student ID: {student_id}")
    
    html_filename = 'KG_for_student.html'
    html_filepath = os.path.join(BASE_DIR, 'templates', 'knowledge_graph', html_filename)

    if not os.path.exists(html_filepath):
        abort(404, description="Student HTML template file not found.")

    logical_source_file = "nn_output_enhanced1.html" 
    print(f"Logical Source File for this page: {logical_source_file}")
    print(f"--------------------------")

    try:
        with open(html_filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()

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
        print(f"Error processing student_view request: {e}")
        abort(500, description="Server error while preparing the student page.")


@app_kg.route('/kg_page/teacher')
def teacher_view():
    """
    教师端专属路由。
    提供 "nn_output_enhanced1_教师端.html" 页面。
    """
    course_name = request.args.get('course_name', '线性代数')
    teacher_id = request.args.get('student_id', 'teacher001') # 参数名保持 student_id 以便前端复用

    print(f"--- serving TEACHER page via /teacher ---")
    print(f"Course Name: {course_name}, Teacher ID: {teacher_id}")
    
    html_filename = 'KG_for_teacher.html'
    html_filepath = os.path.join(BASE_DIR, 'templates', 'knowledge_graph', html_filename)

    if not os.path.exists(html_filepath):
        abort(404, description="Teacher HTML template file not found.")

    logical_source_file = "nn_output_enhanced1.html" 
    print(f"Logical Source File for this page: {logical_source_file}")
    print(f"--------------------------")

    try:
        with open(html_filepath, 'r', encoding='utf-8') as f:
            html_content = f.read()

        # JS对象中的键名仍使用 studentId 以保证前端代码一致性
        injection_script = f"""
        <script>
            window.PAGE_DATA = {{
                courseName: '{course_name}',
                studentId: '{teacher_id}',
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
        print(f"Error processing teacher_view request: {e}")
        abort(500, description="Server error while preparing the teacher page.")