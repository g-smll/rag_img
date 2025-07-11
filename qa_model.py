import requests
import json
from config import API_TOKEN, CHAT_API_URL, CHAT_MODEL
import re

class QAModel:
    def __init__(self, vector_store):
        self.vector_store = vector_store

    def generate_answer(self, question, top_k=3):
        """根据问题生成回答，支持图文混排，图片在总结前同一行展示，总结内容最后输出"""
        # 检索相关文档
        relevant_docs = self.vector_store.similarity_search(question, top_k=top_k)

        if not relevant_docs:
            return "抱歉，我无法找到与您问题相关的信息。"

        import re
        question_keywords = set(re.findall(r"[\u4e00-\u9fa5A-Za-z0-9]+", question))

        context_parts = []
        related_imgs = []
        shown_images = set()
        shown_pages = set()
        summary_lines = []
        main_lines = []
        for doc in relevant_docs:
            text = doc["text"]
            images = doc.get("metadata", {}).get("images", [])
            page_id = doc["id"]
            # 拆分总结内容（以“总结”或“结论”开头的段落）
            lines = text.split('\n')
            for line in lines:
                if line.strip().startswith(('总结', '结论')):
                    summary_lines.append(line)
                else:
                    main_lines.append(line)
            # 只要本页文本包含问题关键词，就展示本页图片，且每页只展示一次
            if page_id not in shown_pages:
                for kw in question_keywords:
                    if kw and kw in text:
                        for img in images:
                            if img not in shown_images:
                                related_imgs.append(img)
                                shown_images.add(img)
                        shown_pages.add(page_id)
                        break
        # 组织图片HTML
        img_html = ''
        if related_imgs:
            img_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;">' + \
                ''.join([f'<img src="/images/{img}" style="max-width:180px;max-height:120px;object-fit:contain;" alt="图片">' for img in related_imgs]) + '</div>'
        # 组织正文和总结
        main_text = '\n'.join(main_lines).strip()
        summary_text = '\n'.join(summary_lines).strip()
        # 调用API生成回答
        context = main_text
        prompt = self._build_prompt(context, question)
        response = self._call_chat_api(prompt)
        # 最终输出：正文+图片+总结
        final_answer = ''
        if main_text:
            final_answer += response.strip() + '\n\n'
        if img_html:
            final_answer += img_html + '\n'
        if summary_text:
            final_answer += summary_text
        return final_answer.strip()

    def _build_prompt(self, context, question):
        """构建提示"""
        return [
            {
                "role": "system",
                "content": "你是一个有用的AI助手。你将根据提供的文档内容回答用户的问题。如果问题无法从文档内容中回答，请诚实地说你不知道，不要编造信息。"
            },
            {
                "role": "user",
                "content": f"以下是一些文档内容：\n\n{context}\n\n根据上述文档内容，请回答我的问题：{question}"
            }
        ]

    def _call_chat_api(self, messages):
        """调用聊天API"""
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "model": CHAT_MODEL,
            "stream": False,
            "max_tokens": 512,
            "enable_thinking": True,
            "thinking_budget": 4096,
            "min_p": 0.05,
            "temperature": 0.7,
            "top_p": 0.7,
            "top_k": 50,
            "frequency_penalty": 0.5,
            "n": 1,
            "stop": [],
            "messages": messages
        }

        try:
            response = requests.post(CHAT_API_URL, headers=headers, json=data)
            response.raise_for_status()

            result = response.json()
            return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"调用聊天API时出错: {e}")
            return "抱歉，生成回答时出现错误。"
