from util.n4j import *
from util.mongodb import *
from flask import request, jsonify,make_response, Blueprint
import re
import os
import json
from datetime import datetime

serverKG = Blueprint('serverKG',__name__)

# TODO:修改为OS路径
JSON_PATH="./classKG"

@serverKG.route('/save_kg_json', methods=['POST'])
def save_json():
    """
    {
        "class_name":"定量工程设计",
        "data": [],
        "links": []
    }
    """
    try:
        data = request.get_json()
        if data is None:
            return jsonify({"error": "Invalid JSON"}), 400
        
        # 获取当前时间并格式化为“到分钟”的时间戳
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        filename = f"{timestamp}.json"

        # 构建目录并确保存在
        save_dir = os.path.join(JSON_PATH, data['class_name'])
        os.makedirs(save_dir, exist_ok=True)

        filepath = os.path.join(JSON_PATH,data['class_name'], filename)

        # 写入 JSON 文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

        # 更新mongodb数据库
        modify_knowledge_list(data['class_name'],[item["name"] for item in data["data"]])
        return jsonify({"message": "JSON saved", "filename": filename}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@serverKG.route('/list_class', methods=['GET'])
def list_courses():
    try:
        # 获取所有一级子目录名称
        folders = [
            name for name in os.listdir(JSON_PATH)
            if os.path.isdir(os.path.join(JSON_PATH, name))
        ]
        return jsonify({"courses": folders}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@serverKG.route('/list_class_kgs', methods=['GET'])
def list_course_files():
    try:
        # 获取请求参数
        class_name = request.args.get('class_name')
        if not class_name:
            return jsonify({"error": "Missing 'class_name' parameter"}), 400
        
        # 构建课程目录路径
        course_dir = os.path.join(JSON_PATH, class_name)
        if not os.path.exists(course_dir) or not os.path.isdir(course_dir):
            return jsonify({"error": f"Course '{class_name}' not found"}), 404

        # 获取文件名列表
        filenames = [
            f for f in os.listdir(course_dir)
            if os.path.isfile(os.path.join(course_dir, f))
        ]

        return jsonify({
            "class_name": class_name,
            "files": filenames
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@serverKG.route('/get_all_kg_jsons', methods=['GET'])
def get_all_kg_jsons():
    """获取指定课程目录下的所有JSON文件内容，按文件名（时间戳）降序排序"""
    try:
        # 获取请求参数
        class_name = request.args.get('class_name')
        
        # 验证参数是否存在
        if not class_name:
            return jsonify({"error": "缺少必要参数: class_name"}), 400
        
        # 构建文件路径
        dir_path = os.path.join(JSON_PATH, class_name)
        
        # 验证路径安全性 - 防止路径遍历攻击
        abs_json_path = os.path.abspath(JSON_PATH)
        abs_dir_path = os.path.abspath(dir_path)
        
        if not abs_dir_path.startswith(abs_json_path):
            return jsonify({"error": "非法文件路径"}), 400
        
        # 检查目录是否存在
        if not os.path.exists(dir_path):
            return jsonify({"error": f"课程目录 '{class_name}' 未找到"}), 404
        
        # 检查是否为目录
        if not os.path.isdir(dir_path):
            return jsonify({"error": f"'{class_name}' 不是有效的课程目录"}), 400
        
        # 获取目录中所有JSON文件
        all_files = [
            filename for filename in os.listdir(dir_path)
            if os.path.isfile(os.path.join(dir_path, filename)) 
            and filename.lower().endswith('.json')
        ]
        
        # 按文件名（时间戳）降序排序 - 最近的在前
        # 文件名格式为：YYYYMMDD_HHMMSS.json（或类似）
        try:
            all_files.sort(key=lambda x: os.path.splitext(x)[0], reverse=True)
        except:
            # 如果文件名不符合时间戳格式，按默认顺序
            all_files.sort(reverse=True)
        
        # 存储所有JSON文件内容的列表
        all_json_data = []
        
        # 遍历排序后的文件列表
        for filename in all_files:
            file_path = os.path.join(dir_path, filename)
            
            try:
                # 读取并解析JSON文件
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_content = json.load(f)
                    
                # 添加到结果列表
                all_json_data.append({
                    "json_name": filename,
                    "kg": file_content
                })
                
            except json.JSONDecodeError as e:
                # 记录JSON解析错误
                all_json_data.append({
                    "json_name": filename,
                    "error": "无效JSON文件",
                    "details": str(e)
                })
            except Exception as e:
                # 记录其他错误
                all_json_data.append({
                    "json_name": filename,
                    "error": "读取文件失败",
                    "details": str(e)
                })
        
        # 返回所有JSON文件内容
        return jsonify({
            "class_name": class_name,
            "files": all_json_data
        })

    except Exception as e:
        # 处理其他异常
        return jsonify({
            "error": "服务器错误",
            "details": str(e)
        }), 500
        
@serverKG.route("/update_kg_learn_state", methods=["POST"])
def update_kg_learn_state_api():
    data = request.json
    try:
        student_id = data["student_id"]
        course_name = data["course_name"]
        point_name = data["point_name"]
        state = data["state"]
    except (KeyError, ValueError):
        return jsonify({"status": "fail", "message": "参数错误"}), 400

    result = update_kg_learn_state(student_id, course_name, point_name, state)
    return jsonify(result)


@serverKG.route("/get_kg_learn_state", methods=["GET"])
def get_kg_learn_state_api():
    student_id = request.args.get("student_id")
    course_name = request.args.get("course_name")

    # 校验参数
    if not student_id or not course_name:
        return jsonify({"success": False, "message": "缺少参数 student_id 或 course_name"}), 400

    # try:
    #     student_id = int(student_id)
    # except ValueError:
    #     return jsonify({"success": False, "message": "student_id 应为整数"}), 400

    knowledge_list = get_learn_state(student_id, course_name)

    # 转换格式为 {knowledge_name: state}
    result = {k["knowledge_name"]: k["state"] for k in knowledge_list}

    return jsonify(result)


#if __name__ == '__main__':
#    serverKG.config['JSON_AS_ASCII'] = False
#    serverKG.run(debug=False,host='0.0.0.0',port=4999)
