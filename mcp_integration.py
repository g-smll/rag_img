import requests
import json
from typing import Dict, List, Any
from config import API_TOKEN, CHAT_API_URL, MCP_SERVICE_URL
import asyncio
from langchain_mcp_adapters.client import MultiServerMCPClient


class MCPIntegration:
    """MCP服务集成类，负责与DeepSeek和MCP服务的交互"""
    
    def __init__(self, qa_model=None):
        self.qa_model = qa_model
        # 原hardcode方式，已废弃：
        # self.mcp_tools = [
        #     {
        #         "type": "function",
        #         "function": {
        #             "name": "execute_sql",
        #             "description": "在MySQL8.0数据库上执行SQL查询语句",
        #             "parameters": {
        #                 "type": "object",
        #                 "properties": {
        #                     "query": {
        #                         "type": "string",
        #                         "description": "要执行的SQL语句"
        #                     }
        #                 },
        #                 "required": ["query"]
        #             }
        #         }
        #     },
        #     {
        #         "type": "function",
        #         "function": {
        #             "name": "get_table_name",
        #             "description": "根据表的中文注释搜索数据库中对应的表名",
        #             "parameters": {
        #                 "type": "object",
        #                 "properties": {
        #                     "text": {
        #                         "type": "string",
        #                         "description": "要搜索的表中文名或关键词"
        #                     }
        #                 },
        #                 "required": ["text"]
        #             }
        #         }
        #     },
        #     {
        #         "type": "function",
        #         "function": {
        #             "name": "get_table_desc",
        #             "description": "获取指定表的字段结构信息，支持多表查询",
        #             "parameters": {
        #                 "type": "object",
        #                 "properties": {
        #                     "text": {
        #                         "type": "string",
        #                         "description": "要查询的表名，多个表名以逗号分隔"
        #                     }
        #                 },
        #                 "required": ["text"]
        #             }
        #         }
        #     },
        #     {
        #         "type": "function",
        #         "function": {
        #             "name": "get_lock_tables",
        #             "description": "获取当前MySQL服务器InnoDB的行级锁信息",
        #             "parameters": {
        #                 "type": "object",
        #                 "properties": {}
        #             }
        #         }
        #     }
        # ]
        self.mcp_tools = []
        asyncio.run(self.load_mcp_tools())

    async def load_mcp_tools(self):
        client = MultiServerMCPClient({
            "math-sse": {
                "url": "http://localhost:9090/sse/",
                "transport": "sse"
            }
        })
        self.mcp_tools = await client.get_tools()
    
    def call_deepseek_with_tools(self, question: str) -> str:
        """调用DeepSeek API，让其决定使用哪个MCP工具"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个数据库查询助手。用户会问你关于数据库的问题，你需要使用提供的工具来查询数据库并回答问题。请根据用户的问题选择合适的工具进行查询。"
                },
                {
                    "role": "user",
                    "content": question
                }
            ]
            
            payload = {
                "model": "Pro/deepseek-ai/DeepSeek-V3",
                "messages": messages,
                "tools": self.mcp_tools,
                "tool_choice": "auto",
                "max_tokens": 1024,
                "temperature": 0.1
            }
            
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(CHAT_API_URL, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                message = result["choices"][0]["message"]
                
                # 检查是否有工具调用
                if "tool_calls" in message and message["tool_calls"]:
                    tool_call = message["tool_calls"][0]
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])
                    
                    # 调用MCP服务
                    mcp_result = self.call_mcp_tool(function_name, function_args)
                    
                    # 将MCP结果返回给DeepSeek进行最终整理
                    return self.format_final_answer(question, function_name, function_args, mcp_result)
                else:
                    # 没有工具调用，直接返回回答
                    return message.get("content", "抱歉，我无法理解您的问题。")
            else:
                return f"DeepSeek API调用失败，状态码: {response.status_code}"
                
        except Exception as e:
            return f"调用DeepSeek时出错: {str(e)}"
    
    def call_mcp_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """调用MCP服务的具体工具"""
        try:
            import time
            import re
            import threading
            from queue import Queue, Empty
            
            print(f"调用MCP工具: {tool_name}, 参数: {arguments}")
            
            # 创建结果队列
            result_queue = Queue()
            session_id = None
            sse_response = None
            
            def sse_listener():
                """SSE监听线程"""
                nonlocal session_id, sse_response
                try:
                    sse_url = "http://127.0.0.1:9090/sse"
                    print(f"建立SSE连接: {sse_url}")
                    
                    sse_response = requests.get(
                        sse_url,
                        headers={
                            "Accept": "text/event-stream",
                            "Cache-Control": "no-cache"
                        },
                        timeout=60,  # 增加超时时间
                        stream=True
                    )
                    
                    if sse_response.status_code != 200:
                        result_queue.put(("error", f"SSE连接失败，状态码: {sse_response.status_code}"))
                        return
                    
                    print("SSE连接建立成功")
                    
                    # 监听SSE事件
                    initialization_received = False
                    for line in sse_response.iter_lines(decode_unicode=True):
                        if line and line.startswith('data:'):
                            data_content = line.replace('data: ', '').strip()
                            print(f"SSE接收数据: {data_content}")
                            
                            # 提取session_id
                            if session_id is None and '/messages/' in data_content and 'session_id=' in data_content:
                                match = re.search(r'session_id=([a-f0-9]+)', data_content)
                                if match:
                                    session_id = match.group(1)
                                    print(f"提取到session_id: {session_id}")
                                    result_queue.put(("session_ready", session_id))
                                    continue
                            
                            # 跳过路径信息
                            if data_content.startswith('/messages/'):
                                continue
                            
                            # 处理JSON-RPC响应
                            if data_content.startswith('{') and '"jsonrpc"' in data_content:
                                try:
                                    json_data = json.loads(data_content)
                                    
                                    # 初始化响应
                                    if json_data.get("id") == 1 and "result" in json_data:
                                        print("收到初始化响应，继续监听工具调用结果...")
                                        initialization_received = True
                                        result_queue.put(("init_complete", json_data["result"]))
                                        continue
                                    
                                    # 工具调用响应
                                    elif json_data.get("id") == 2:
                                        if "result" in json_data:
                                            result_data = json_data["result"]
                                            print(f"收到工具调用结果: {result_data}")
                                            
                                            # 处理MCP工具返回的content格式
                                            if isinstance(result_data, dict) and "content" in result_data:
                                                content = result_data["content"]
                                                if isinstance(content, list) and content:
                                                    # 提取文本内容
                                                    text_content = content[0].get("text", "")
                                                    if text_content:
                                                        print(f"提取到文本内容: {text_content}")
                                                        result_queue.put(("tool_result", text_content))
                                                        break
                                                else:
                                                    result_queue.put(("tool_result", str(result_data)))
                                                    break
                                            else:
                                                result_queue.put(("tool_result", result_data))
                                                break
                                        elif "error" in json_data:
                                            error_msg = json_data["error"].get("message", "未知错误")
                                            result_queue.put(("error", f"工具调用错误: {error_msg}"))
                                            break
                                    
                                    # 其他响应
                                    else:
                                        if "result" in json_data:
                                            result_queue.put(("result", json_data["result"]))
                                        elif "error" in json_data:
                                            error_msg = json_data["error"].get("message", "未知错误")
                                            result_queue.put(("error", f"MCP错误: {error_msg}"))
                                            break
                                            
                                except json.JSONDecodeError:
                                    print(f"无法解析JSON数据: {data_content}")
                            
                            # 处理直接的结果数据（非JSON-RPC格式）
                            elif initialization_received and data_content and len(data_content) > 5:
                                try:
                                    # 尝试解析为JSON数组或对象
                                    if data_content.startswith('[') or data_content.startswith('{'):
                                        json_data = json.loads(data_content)
                                        if isinstance(json_data, (list, dict)) and json_data:
                                            result_queue.put(("result", json_data))
                                            break
                                except json.JSONDecodeError:
                                    # 纯文本结果
                                    result_queue.put(("result", data_content))
                                    break
                    
                except Exception as e:
                    result_queue.put(("error", f"SSE监听出错: {str(e)}"))
                finally:
                    if sse_response:
                        try:
                            sse_response.close()
                        except:
                            pass
            
            # 启动SSE监听线程
            sse_thread = threading.Thread(target=sse_listener, daemon=True)
            sse_thread.start()
            
            # 等待session_id
            try:
                event_type, event_data = result_queue.get(timeout=15)
                if event_type == "error":
                    return str(event_data)
                elif event_type == "session_ready":
                    session_id = event_data
                else:
                    return "等待会话建立超时"
            except Empty:
                return "等待会话建立超时"
            
            if not session_id:
                return "无法获取session_id"
            
            # 步骤1: 发送初始化请求
            url_with_session = f"http://127.0.0.1:9090/messages/?session_id={session_id}"
            
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "roots": {
                            "listChanged": True
                        },
                        "sampling": {}
                    },
                    "clientInfo": {
                        "name": "rag_img_client",
                        "version": "1.0.0"
                    }
                }
            }
            
            print(f"发送MCP初始化请求到: {url_with_session}")
            print(f"初始化请求数据: {json.dumps(init_request, ensure_ascii=False, indent=2)}")
            
            # 发送初始化请求
            init_response = requests.post(
                url_with_session,
                headers={"Content-Type": "application/json"},
                json=init_request,
                timeout=30
            )
            
            print(f"初始化响应状态: {init_response.status_code}")
            print(f"初始化响应内容: {init_response.text}")
            
            if init_response.status_code not in [200, 202]:
                return f"MCP初始化失败，状态码: {init_response.status_code}, 内容: {init_response.text}"
            
            # 等待初始化完成响应
            initialization_complete = False
            try:
                while not initialization_complete:
                    event_type, event_data = result_queue.get(timeout=15)
                    if event_type == "init_complete":
                        print("收到初始化响应，发送initialized通知...")
                        initialization_complete = True
                        break
                    elif event_type == "error":
                        return str(event_data)
                    else:
                        print(f"等待初始化时收到其他事件: {event_type}")
                        continue
            except Empty:
                return "等待初始化完成超时"
            
            if not initialization_complete:
                return "初始化未完成，无法继续"
            
            # 发送initialized通知（MCP协议要求）
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {}
            }
            
            print(f"发送initialized通知到: {url_with_session}")
            print(f"通知数据: {json.dumps(initialized_notification, ensure_ascii=False, indent=2)}")
            
            # 发送initialized通知
            notify_response = requests.post(
                url_with_session,
                headers={"Content-Type": "application/json"},
                json=initialized_notification,
                timeout=30
            )
            
            print(f"通知响应状态: {notify_response.status_code}")
            print(f"通知响应内容: {notify_response.text}")
            
            # 等待一小段时间确保通知被处理
            time.sleep(1)
            
            # 步骤2: 发送工具调用请求
            # 确保参数格式正确，根据MCP协议规范
            if tool_name == "get_lock_tables":
                # get_lock_tables 不需要参数，但仍需要提供空的arguments对象
                tool_arguments = {}
            else:
                # 其他工具需要参数，确保参数是字典格式且包含必需字段
                tool_arguments = {}
                if isinstance(arguments, dict):
                    # 验证并清理参数
                    if tool_name in ["get_table_name", "get_table_desc"] and "text" in arguments:
                        tool_arguments["text"] = str(arguments["text"]).strip()
                    elif tool_name == "execute_sql" and "query" in arguments:
                        tool_arguments["query"] = str(arguments["query"]).strip()
                    else:
                        # 如果参数不匹配预期，使用原始参数
                        tool_arguments = arguments
                
                # 确保必需参数存在
                if not tool_arguments:
                    if tool_name in ["get_table_name", "get_table_desc"]:
                        return f"工具 {tool_name} 缺少必需的 'text' 参数"
                    elif tool_name == "execute_sql":
                        return f"工具 {tool_name} 缺少必需的 'query' 参数"
            
            tool_request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": tool_arguments
                }
            }
            
            print(f"发送MCP工具调用请求到: {url_with_session}")
            print(f"工具调用请求数据: {json.dumps(tool_request, ensure_ascii=False, indent=2)}")
            
            # 发送工具调用请求
            response = requests.post(
                url_with_session,
                headers={"Content-Type": "application/json"},
                json=tool_request,
                timeout=30
            )
            
            print(f"MCP响应状态: {response.status_code}")
            print(f"MCP响应内容: {response.text}")
            
            # 处理同步响应
            if response.status_code == 200:
                try:
                    result = response.json()
                    if "result" in result:
                        result_data = result["result"]
                        if isinstance(result_data, list) and result_data:
                            return self.format_query_result(result_data)
                        elif isinstance(result_data, dict):
                            return str(result_data)
                        else:
                            return str(result_data)
                    elif "content" in result and result["content"]:
                        return result["content"][0].get("text", "查询完成，但无结果")
                    else:
                        return "查询完成，但未返回结果"
                except json.JSONDecodeError:
                    return f"查询完成，响应: {response.text}"
            
            # 处理异步响应
            elif response.status_code == 202:
                print("收到202响应，等待异步结果...")
                try:
                    # 等待工具调用结果
                    while True:
                        event_type, event_data = result_queue.get(timeout=25)
                        
                        if event_type == "init_complete":
                            print("初始化完成，继续等待工具调用结果...")
                            continue
                        elif event_type == "tool_result":
                            print(f"处理工具调用结果: {event_data}")
                            if isinstance(event_data, str):
                                # 处理CSV格式的结果
                                return self.format_csv_result(event_data)
                            elif isinstance(event_data, list):
                                return self.format_query_result(event_data)
                            else:
                                return str(event_data)
                        elif event_type == "result":
                            if isinstance(event_data, list):
                                return self.format_query_result(event_data)
                            else:
                                return str(event_data)
                        elif event_type == "error":
                            return str(event_data)
                        else:
                            print(f"收到未知事件类型: {event_type}, 数据: {event_data}")
                            continue
                            
                except Empty:
                    return f"异步处理超时，工具: {tool_name}"
            
            else:
                return f"MCP工具调用失败，状态码: {response.status_code}, 内容: {response.text}"
                
        except Exception as e:
            return f"调用MCP工具时出错: {str(e)}"

    
    def format_query_result(self, data) -> str:
        """格式化查询结果"""
        if not data:
            return "查询完成，但没有找到相关数据。"
        
        # 如果是字符串（CSV格式）
        if isinstance(data, str):
            return self.format_csv_result(data)
        
        # 如果是列表
        elif isinstance(data, list):
            if not data:
                return "查询完成，但没有找到相关数据。"
            
            # 如果是表信息查询结果
            if all(isinstance(item, dict) and 'TABLE_NAME' in item for item in data):
                result = "找到以下相关表：\n"
                for item in data:
                    table_name = item.get('TABLE_NAME', '未知')
                    table_comment = item.get('TABLE_COMMENT', '无注释')
                    table_schema = item.get('TABLE_SCHEMA', '未知')
                    result += f"- 表名: {table_name} (数据库: {table_schema})\n  说明: {table_comment}\n"
                return result
            
            # 如果是普通查询结果
            elif all(isinstance(item, dict) for item in data):
                result = f"查询结果（共{len(data)}条记录）：\n"
                for i, item in enumerate(data[:10], 1):  # 最多显示10条
                    result += f"{i}. "
                    for key, value in item.items():
                        result += f"{key}: {value}, "
                    result = result.rstrip(', ') + "\n"
                
                if len(data) > 10:
                    result += f"... 还有{len(data) - 10}条记录未显示"
                return result
            
            # 其他列表格式
            else:
                return f"查询结果: {str(data)}"
        
        # 其他格式
        else:
            return f"查询结果: {str(data)}"
    
    def format_csv_result(self, csv_data: str) -> str:
        """格式化CSV格式的查询结果"""
        try:
            lines = csv_data.strip().split('\n')
            if len(lines) < 2:
                return csv_data
            
            # 解析CSV头部和数据
            headers = lines[0].split(',')
            rows = [line.split(',') for line in lines[1:]]
            
            # 特殊处理表信息查询
            if 'TABLE_NAME' in headers and 'TABLE_COMMENT' in headers:
                result = "找到以下相关表：\n"
                for row in rows:
                    if len(row) >= len(headers):
                        row_dict = dict(zip(headers, row))
                        table_name = row_dict.get('TABLE_NAME', '未知')
                        table_comment = row_dict.get('TABLE_COMMENT', '无注释')
                        table_schema = row_dict.get('TABLE_SCHEMA', '未知')
                        result += f"- 表名: {table_name} (数据库: {table_schema})\n  说明: {table_comment}\n"
                return result
            
            # 通用CSV格式化
            else:
                result = f"查询结果（共{len(rows)}条记录）：\n"
                for i, row in enumerate(rows[:10], 1):  # 最多显示10条
                    result += f"{i}. "
                    for j, value in enumerate(row):
                        if j < len(headers):
                            result += f"{headers[j]}: {value}, "
                    result = result.rstrip(', ') + "\n"
                
                if len(rows) > 10:
                    result += f"... 还有{len(rows) - 10}条记录未显示"
                return result
                
        except Exception as e:
            # 如果解析失败，返回原始数据
            return f"查询结果:\n{csv_data}"
    

    
    def format_final_answer(self, question: str, tool_name: str, arguments: Dict, mcp_result: str) -> str:
        """让DeepSeek整理最终答案"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个数据库查询助手。请根据用户的问题和查询结果，给出清晰、友好的回答。"
                },
                {
                    "role": "user",
                    "content": f"用户问题: {question}\n使用的工具: {tool_name}\n工具参数: {json.dumps(arguments, ensure_ascii=False)}\n查询结果: {mcp_result}\n\n请根据以上信息给出清晰的回答。"
                }
            ]
            
            payload = {
                "model": "Pro/deepseek-ai/DeepSeek-V3",
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.1
            }
            
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(CHAT_API_URL, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"].get("content", mcp_result)
            else:
                return mcp_result  # 如果格式化失败，返回原始结果
                
        except Exception as e:
            return mcp_result  # 如果格式化失败，返回原始结果    

    def tool_to_dict(self, tool):
        """将StructuredTool对象转换为dict结构"""
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.args_schema
            }
        }

    def intelligent_answer(self, question: str) -> str:
        """智能回答：完全由大模型决定使用数据库工具还是知识问答，不做本地硬编码判断"""
        try:
            print(f"开始处理问题: {question}")  # 调试日志

            # 将所有StructuredTool对象转为dict
            all_tools = [self.tool_to_dict(t) for t in self.mcp_tools]
            # 添加RAG知识搜索工具
            all_tools.append({
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "description": "在已上传的文档中搜索相关知识来回答问题，适用于文档内容、概念解释、技术问题等",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "要搜索的问题或关键词"
                            }
                        },
                        "required": ["query"]
                    }
                }
            })

            # 系统提示词，指导大模型如何选择工具
            messages = [
                {
                    "role": "system",
                    "content": """
你是一个智能助手，可以处理两类问题：
1. 数据库查询问题：使用数据库工具（execute_sql, get_table_name, get_table_desc, get_lock_tables）
2. 知识问答问题：使用知识搜索工具（knowledge_search）

数据库工具使用指南：
- execute_sql: 当用户要查询具体数据内容时使用。
- get_table_name: 仅当用户询问有哪些表或搜索表名时使用。
- get_table_desc: 当用户询问表结构或字段信息时使用。
- get_lock_tables: 当用户询问数据库锁信息时使用。

知识问答工具使用指南：
- knowledge_search: 当用户问题与数据库结构无关，而是需要查阅文档、解释概念、技术说明等时使用。

请根据用户问题，自动选择最合适的工具，并合理生成参数。
"""
                },
                {
                    "role": "user",
                    "content": question
                }
            ]

            payload = {
                "model": "Pro/deepseek-ai/DeepSeek-V3",
                "messages": messages,
                "tools": all_tools,
                "tool_choice": "auto",
                "max_tokens": 1024,
                "temperature": 0.1
            }

            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json"
            }

            response = requests.post(CHAT_API_URL, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                message = result["choices"][0]["message"]

                # 检查是否有工具调用
                if "tool_calls" in message and message["tool_calls"]:
                    tool_call = message["tool_calls"][0]
                    function_name = tool_call["function"]["name"]
                    function_args = json.loads(tool_call["function"]["arguments"])

                    # 根据工具类型调用不同的服务
                    if function_name == "knowledge_search":
                        # 调用RAG知识问答
                        if self.qa_model:
                            rag_result = self.qa_model.generate_answer(function_args.get("query", question))
                            return self.format_knowledge_answer(question, rag_result)
                        else:
                            return "知识搜索服务暂时不可用"
                    else:
                        # 调用MCP数据库工具
                        mcp_result = self.call_mcp_tool(function_name, function_args)
                        return self.format_final_answer(question, function_name, function_args, mcp_result)
                else:
                    # 没有工具调用，直接返回回答
                    return message.get("content", "抱歉，我无法理解您的问题。")
            else:
                return f"智能助手调用失败，状态码: {response.status_code}"

        except Exception as e:
            return f"智能问答时出错: {str(e)}"
    
    def format_knowledge_answer(self, question: str, rag_result: str) -> str:
        """格式化知识问答的结果"""
        try:
            messages = [
                {
                    "role": "system",
                    "content": "你是一个知识助手。请根据用户的问题和搜索到的相关内容，给出清晰、准确的回答。"
                },
                {
                    "role": "user",
                    "content": f"用户问题: {question}\n相关内容: {rag_result}\n\n请根据以上信息给出准确的回答。"
                }
            ]
            
            payload = {
                "model": "Pro/deepseek-ai/DeepSeek-V3",
                "messages": messages,
                "max_tokens": 1024,
                "temperature": 0.1
            }
            
            headers = {
                "Authorization": f"Bearer {API_TOKEN}",
                "Content-Type": "application/json"
            }
            
            response = requests.post(CHAT_API_URL, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                return result["choices"][0]["message"].get("content", rag_result)
            else:
                return rag_result  # 如果格式化失败，返回原始结果
                
        except Exception as e:
            return rag_result  # 如果格式化失败，返回原始结果