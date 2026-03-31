   
# if __name__ == "__main__":
#     mcp.run()

from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
import httpx
import uvicorn
from fastapi import HTTPException
import asyncio
from config import *

mcp = FastMCP (name="study",
    host="0.0.0.0",
    port=MCP_TEST_PORT,
    description="获取学习信息",
    sse_path='/sse'
     )
    

# LOCAL_API_BASE = "http://180.85.206.21:7777/dashboard/study_situation"

LOCAL_API_BASE = "http://180.85.206.21:"+str(APP_PORT)+"/dashboard/study_situation"

@mcp.tool()
async def search_course(
    query: Any = None,
    studentUid: Optional[str] = None
) -> Dict[str, Any]:
    """
    This tool can query specific information about a course based on the course name or course ID.
    IMPORTANT: This tool will only search within the currently selected course in the dashboard.
    If no course is selected, it will use the teacher's first course.
    
    Args:
    query: The query condition, which can be part of the course ID or course name (optional). If provided, it will be matched against the currently selected course.
           If not provided or an empty string, it defaults to querying the currently selected course.
    studentUid: User account (required), used to identify the user and retrieve their currently selected course.

    Returns:
        Returns detailed information about the currently selected course, including knowledge point learning statistics, etc.

    Example:
        search_course(query="Mathematics", studentUid="Zhang San") - Queries the current course containing "Mathematics"
        search_course(studentUid="Zhang San") - Queries the currently selected course
        search_course(query="", studentUid="Zhang San") - Queries the currently selected course (same as not providing query)
    """
    print(f"MCP工具接收参数 - query: {query}, studentUid: {studentUid}")
    
    # 检查必填参数
    if not studentUid:
        return {
            "error": "studentUid是必填参数",
            "message": "请提供用户账号(studentUid)以识别用户身份"
        }
    # 处理query参数：如果query是列表，则取第一个元素
    query_str = None
    if query is not None:
        if isinstance(query, list):
            # 如果是列表，取第一个非空元素
            for item in query:
                if item is not None and str(item).strip() != "":
                    query_str = str(item).strip()
                    break
            if query_str is None:
                query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            query_str = str(query).strip()
    
    print(f"处理后的query参数: {query_str}")
    
    # 构建查询URL
    url = f"{LOCAL_API_BASE}/course/search"
    
    # 构建查询参数
    params = {}
    params['studentUid'] = studentUid
    
    # 如果提供了query参数且不为空字符串，添加到查询中
    if query is not None and query_str != "":
        params['query'] = query_str
    
    # 构建完整的URL
    url_with_params = url
    if params:
        query_string = '&'.join([f"{key}={value}" for key, value in params.items()])
        url_with_params = f"{url}?{query_string}"
    
    print(f"MCP工具调用URL: {url_with_params}")
    
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询课程信息: {url_with_params}")
            response = await client.get(url_with_params)
            response.raise_for_status()
            
            result = response.json()
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            # 尝试获取更详细的错误信息
            try:
                error_detail = e.response.json() if e.response else str(e)
            except:
                error_detail = str(e)
            
            return {
                "error": f"查询课程时发生错误: {str(e)}",
                "detail": error_detail,
                "studentUid": studentUid,
                "query": query if query else "未提供"
            }
        except Exception as e:
            print(f"其他错误: {e}")
            return {
                "error": f"处理请求时发生错误: {str(e)}",
                "studentUid": studentUid,
                "query": query if query else "未提供"
            }

# @mcp.tool()
# async def get_course_overview(
#     course_id: int
# ) -> Dict[str, Any]:
#     """
#     Get an overview of a course (number of students, progress of knowledge points, etc.).
    
#     Args:
#         course_id: Course ID
#     """
#     url = f"{LOCAL_API_BASE}/course/{course_id}"
#     async with httpx.AsyncClient() as client:
#         response = await client.get(url)
#         response.raise_for_status()
#         return response.json()
def _to_float(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, (list, tuple)):
        if not val:
            return None
        return _to_float(val[0])
    if isinstance(val, str):
        val = val.strip()
        if val == "":
            return None
        return float(val)
    raise TypeError(f"Unsupported type for float: {type(val)}")
  

@mcp.tool()
async def get_course_student_status(
    course_query: Any = None, 
    completion_lt: Any = None,
    completion_gt: Any = None,
    knowledge_not_learned: Optional[List[str]] = None,
    studentUid: Optional[str] = None
) -> Dict[str, Any]:
    """
    Query the learning status of all students in a specific course.
    Supports fuzzy matching by course name, filtering by completion rate, and filtering by unlearned knowledge points.
    
    Args:
        course_query: (Optional) Course query keyword, which can be a course ID, course name, etc., for fuzzy matching.
                If not provided, the user's currently selected course is used by default.
        completion_lt: (Optional) Filter students with a completion rate less than this value (0-100).
                Example: 60 → Completion rate < 60%
        completion_gt: (Optional) Filter students with a completion rate greater than this value (0-100).
                Example: 80 → Completion rate > 80%
        knowledge_not_learned: (Optional) List of unlearned knowledge points, which can be knowledge point IDs or names, supporting fuzzy matching.
                Returns students who have not learned at least one of the specified knowledge points.
                Example: ["K101", "Linked List", "Binary Tree"]
        studentUid: (Required) Student/teacher user ID, used to determine the currently selected course.

    Returns:
        A dictionary containing course information, filter conditions, and a list of matching students.
    """
    
    # 检查必填参数
    if not studentUid:
        return {"error": "studentUid是必填参数"}
    completion_lt = _to_float(completion_lt)
    completion_gt = _to_float(completion_gt)
    # 构建查询URL和参数
    url = f"{LOCAL_API_BASE}/course/students"
    params = {
        "studentUid": studentUid
    }
    # 处理query参数：如果query是列表，则取第一个元素
    query_str = None
    if course_query is not None:
        if isinstance(course_query, list):
            # 如果是列表，取第一个非空元素
            for item in course_query:
                if item is not None and str(item).strip() != "":
                    query_str = str(item).strip()
                    break
            if query_str is None:
                query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            query_str = str(query).strip()
    
    print(f"处理后的query参数: {query_str}")
    # 添加course_query参数（可选）
    if query_str is not None and query_str != "":
        params["course_query"] = query_str
    
    # 添加完成率筛选参数
    if completion_lt is not None:
        if not (0 <= completion_lt <= 100):
            raise ValueError("completion_lt必须在0到100之间")
        params["completion_lt"] = completion_lt
    
    if completion_gt is not None:
        if not (0 <= completion_gt <= 100):
            raise ValueError("completion_gt必须在0到100之间")
        params["completion_gt"] = completion_gt
    
    # 添加未学习知识点参数
    if knowledge_not_learned:
        if not isinstance(knowledge_not_learned, list):
            raise TypeError("knowledge_not_learned必须是字符串列表")
        params["knowledge_not_learned"] = knowledge_not_learned
        # # 添加每个知识点参数
        # for item in knowledge_not_learned:
        #     if isinstance(item, str) and item.strip():
        #         params["knowledge_not_learned"] = item.strip()
    
    # 发起异步请求
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询课程学生状态 - URL: {url}")
            print(f"查询参数: {params}")
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            return {"error": f"查询课程学生状态时发生错误: {str(e)}"}
        except Exception as e:
            print(f"其他错误: {e}")
            return {"error": f"处理请求时发生错误: {str(e)}"}

@mcp.tool()
async def get_course_knowledge_status(
    course_query: Any = None, 
    completion_rate_gte: Any = None,
    completion_rate_lte: Any = None,
    studentUid: Optional[str] = None  # 新增：从MCP调用中接收studentUid
) -> Dict[str, Any]:
    """
    Query the mastery status of knowledge points in a course.
    Supports fuzzy matching by course ID or name, and filtering by completion rate (min/max). 
    Returns detailed lists of mastered/pending students per knowledge point.

    Args:
        course_key: (Optional) Course ID or course name keyword (fuzzy match supported). 
                   Example: "CS-101", "高等数学".
        completion_rate_gte: Minimum completion rate threshold (0-100). 
                           Only return knowledge points with completion ≥ this value.
        completion_rate_lte: Maximum completion rate threshold (0-100). 
                           Only return knowledge points with completion ≤ this value.

    Returns:
        A dictionary containing knowledge points mastery status.
    """
    
    # 检查必填参数
    if not studentUid:
        print("工具get_course_knowledge_status，studentUid",studentUid)
        return {"error": "studentUid是必填参数"}
    
    # 构建查询URL和参数
    url = f"{LOCAL_API_BASE}/course/knowledges"
    params = {
        "studentUid": studentUid
    }
    # 处理course_query参数：如果course_query是列表，则取第一个元素
    course_query_str = None
    if course_query is not None:
        if isinstance(course_query, list):
            # 如果是列表，取第一个非空元素
            for item in course_query:
                if item is not None and str(item).strip() != "":
                    course_query_str = str(item).strip()
                    break
            if course_query_str is None:
                course_query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            course_query_str = str(course_query).strip()
    
    print(f"处理后的course_query参数: {course_query_str}")
    # 添加course_query参数（可选）
    # 如果提供了course_query参数且不为空字符串，添加到查询中
    if course_query_str is not None and course_query_str != "":
        params['course_query'] = course_query_str
        
    completion_rate_gte = _to_float(completion_rate_gte)
    completion_rate_lte = _to_float(completion_rate_lte)
    
    if completion_rate_gte is not None and not (0 <= completion_rate_gte <= 100):
        raise ValueError("completion_rate_gte must be between 0 and 100")
    if completion_rate_lte is not None and not (0 <= completion_rate_lte <= 100):
        raise ValueError("completion_rate_lte must be between 0 and 100")
    if completion_rate_gte is not None:
        params["completion_rate_gte"] = completion_rate_gte
    if completion_rate_lte is not None:
        params["completion_rate_lte"] = completion_rate_lte
    # 发起异步请求
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询课程知识点状态 - URL: {url}")
            print(f"查询参数: {params}")
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            return {"error": f"查询课程知识点状态时发生错误: {str(e)}"}
        except Exception as e:
            print(f"其他错误: {e}")
            return {"error": f"处理请求时发生错误: {str(e)}"}


@mcp.tool()
async def get_student_progress(

    student_query: str,
    course_query: Any = None, 
    studentUid: Optional[str] = None  # 新增：从MCP调用中接收studentUid
) -> Dict[str, Any]:
    """
    Query a specific student's learning progress in a course.
    Supports fuzzy matching for both course (by ID or name) and student (by ID or name).

    Args:
        student_query: Student ID, student name, or SIS user ID (fuzzy match). 
                      Example: "2021001", "张三", "student123"
        course_query: (Optional) Course ID or course name keyword (fuzzy match). 
                     Example: "8", "个性化实践", "EIE24000".

    Returns:
        A dictionary containing student progress information.
    """
    # 检查必填参数
    if not studentUid:
        return {"error": "studentUid是必填参数"}
    
    if not student_query or not student_query.strip():
        return {"error": "student_query是必填参数，请输入要查询的学生信息"}
    
    student_query = student_query.strip()
    
    # 构建查询URL和参数
    # 注意：student_query是路径参数，需要包含在URL中
    url = f"{LOCAL_API_BASE}/course/student/{student_query}"
    params = {
        "studentUid": studentUid
    }
    # 处理course_query参数：如果course_query是列表，则取第一个元素
    course_query_str = None
    if course_query is not None:
        if isinstance(course_query, list):
            # 如果是列表，取第一个非空元素
            for item in course_query:
                if item is not None and str(item).strip() != "":
                    course_query_str = str(item).strip()
                    break
            if course_query_str is None:
                course_query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            course_query_str = str(course_query).strip()
    
    print(f"处理后的course_query参数: {course_query_str}")
    # 添加course_query参数（可选）
    if course_query_str is not None and course_query_str != "":
        params['course_query'] = course_query_str
    # 发起异步请求
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询学生进度 - URL: {url}")
            print(f"查询参数: {params}")
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            return {"error": f"查询学生进度时发生错误: {str(e)}"}
        except Exception as e:
            print(f"其他错误: {e}")
            return {"error": f"处理请求时发生错误: {str(e)}"}


@mcp.tool()
async def get_knowledge_status(
    knowledge_query: str,
    course_query: Any = None,
    studentUid: Optional[str] = None  # 新增：从MCP调用中接收studentUid
) -> Dict[str, Any]:
    """
    Query the learning status of a specific knowledge point in a course.
    Supports fuzzy matching for both course (by ID/name) and knowledge (by ID/name).

    Args:
        knowledge_query: Knowledge ID or knowledge name keyword (fuzzy match). 
                        Example: "101", "Python基础", "梯度下降"
        course_query: (Optional) Course ID or course name keyword (fuzzy match). 
                     Example: "8", "个性化实践", "EIE24000".

    Returns:
        A dictionary containing knowledge point status.
    """
    
    # 检查必填参数
    if not studentUid:
        return {"error": "studentUid是必填参数"}
    
    if not knowledge_query or not knowledge_query.strip():
        return {"error": "knowledge_query是必填参数，请输入要查询的知识点信息"}
    
    knowledge_query = knowledge_query.strip()
    
    # 构建查询URL和参数
    # 注意：knowledge_query是路径参数，需要包含在URL中
    url = f"{LOCAL_API_BASE}/course/knowledge/{knowledge_query}"
    params = {
        "studentUid": studentUid
    }
    # 处理course_query参数：如果course_query是列表，则取第一个元素
    course_query_str = None
    if course_query is not None:
        if isinstance(course_query, list):
            # 如果是列表，取第一个非空元素
            for item in course_query:
                if item is not None and str(item).strip() != "":
                    course_query_str = str(item).strip()
                    break
            if course_query_str is None:
                course_query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            course_query_str = str(course_query).strip()
    
    print(f"处理后的course_query参数: {course_query_str}")
    # 添加course_query参数（可选）
    if course_query_str is not None and course_query_str != "":
        params['course_query'] = course_query_str
    # 发起异步请求
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询知识点状态 - URL: {url}")
            print(f"查询参数: {params}")
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            return {"error": f"查询知识点状态时发生错误: {str(e)}"}
        except Exception as e:
            print(f"其他错误: {e}")
            return {"error": f"处理请求时发生错误: {str(e)}"}
        

@mcp.tool()
async def get_student_myprogress(

    student_query: Any =None,
    course_query: Any = None, 
    studentUid: Optional[str] = None  # 新增：从MCP调用中接收studentUid
) -> Dict[str, Any]:
    """
    Query a specific student's learning progress in a course.
    Supports fuzzy matching for both course (by ID or name) and student (by ID or name).

    Args:
        student_query: Student ID, student name, or SIS user ID (fuzzy match). 
                      Example: "2021001", "张三", "student123"
        course_query: (Optional) Course ID or course name keyword (fuzzy match). 
                     Example: "8", "个性化实践", "EIE24000".

    Returns:
        A dictionary containing student progress information.
    """
    # 检查必填参数
    if not studentUid:
        return {"error": "studentUid是必填参数"}
    
    # 构建查询URL和参数
    # 注意：student_query是路径参数，需要包含在URL中
    url = f"{LOCAL_API_BASE}/course/student/myprogress"
    params = {
        "studentUid": studentUid
    }
    # 处理student_query参数
    student_query_str = None
    if student_query is not None:
        if isinstance(student_query, list):
            # 如果是列表，取第一个非空元素
            for item in student_query:
                if item is not None and str(item).strip() != "":
                    student_query_str = str(item).strip()
                    break
            # 如果列表中没有非空元素，student_query_str保持为None
        elif isinstance(student_query, str):
            # 如果是字符串，去除空格
            student_query_str = student_query.strip()
        else:
            # 其他类型转换为字符串
            student_query_str = str(student_query).strip()
    
    print(f"处理后的student_query参数: {student_query_str}")
    # 处理course_query参数：如果course_query是列表，则取第一个元素
    course_query_str = None
    if course_query is not None:
        if isinstance(course_query, list):
            # 如果是列表，取第一个非空元素
            for item in course_query:
                if item is not None and str(item).strip() != "":
                    course_query_str = str(item).strip()
                    break
            if course_query_str is None:
                course_query_str = ""
        else:
            # 如果不是列表，直接转换为字符串
            course_query_str = str(course_query).strip()
    
    print(f"处理后的course_query参数: {course_query_str}")
    # 添加course_query参数（可选）
    if course_query_str is not None and course_query_str != "":
        params['course_query'] = course_query_str
    # 如果提供了student_query参数且不为空，添加到查询中
    if student_query_str is not None and student_query_str != "":
        params['student_query'] = student_query_str
    # 发起异步请求
    async with httpx.AsyncClient() as client:
        try:
            print(f"查询学生进度 - URL: {url}")
            print(f"查询参数: {params}")
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            result = response.json()
            
            return result
            
        except httpx.HTTPError as e:
            print(f"HTTP请求错误: {e}")
            return {"error": f"查询学生进度时发生错误: {str(e)}"}
        except Exception as e:
            print(f"其他错误: {e}")
            return {"error": f"处理请求时发生错误: {str(e)}"}

# import subprocess, threading, time, requests

# def run_ngrok():
#     subprocess.Popen(["ngrok", "http", str(MCP_TEST_PORT),"--authtoken", "30ZoZPiXlC7XlP5E7d6US3Y2YO6_2pAGWz7Rg68FFpLficvDJ","--hostname","subtly-ready-mudfish.ngrok-free.app"
#                       ])
# def get_ngrok_url():
#     for _ in range(5):          # 最多等 5 秒
#         time.sleep(1)
#         try:
#             r = requests.get("http://localhost:4040/api/tunnels", timeout=2)
#             tunnels = r.json()["tunnels"]
#             for t in tunnels:
#                 if t["proto"] == "https":
#                     print("🔗 MCP 公网地址：", t["public_url"] + "/sse")
#                     return
#         except Exception:
#             pass
#     print("❌ 无法获取 ngrok URL")
    
# mcp_server.py 末尾
if __name__ == "__main__":
    # 只有直接运行才启动服务器
    print(f"Starting MCP server on port {MCP_TEST_PORT}...")
    print(f"SSE endpoint: http://0.0.0.0:{MCP_TEST_PORT}/sse")
    mcp.run(transport='sse')
else:
    # 被其他模块导入时，只打印信息，不启动
    print("MCP server module imported (will be started as subprocess)")

