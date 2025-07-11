import os
import json
import requests
import numpy as np
from config import API_TOKEN, EMBEDDING_API_URL, EMBEDDING_MODEL, VECTOR_FOLDER

class VectorStore:
    def __init__(self):
        # 确保向量存储目录存在
        if not os.path.exists(VECTOR_FOLDER):
            os.makedirs(VECTOR_FOLDER)

    def get_embedding(self, text):
        """使用API获取文本的向量表示"""
        headers = {
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json"
        }

        data = {
            "model": EMBEDDING_MODEL,
            "input": text,
            "encoding_format": "float"
        }

        try:
            response = requests.post(EMBEDDING_API_URL, headers=headers, json=data)
            response.raise_for_status()  # 如果请求失败，抛出异常

            result = response.json()
            return result["data"][0]["embedding"]
        except Exception as e:
            print(f"获取嵌入向量时出错: {e}")
            return None

    def vectorize_chunks(self, document_chunks):
        """将文档每页转换为向量并存储"""
        document_id = document_chunks[0]["metadata"]["filename"].split('.')[0]
        vector_file = os.path.join(VECTOR_FOLDER, f"{document_id}.json")

        vectorized_chunks = []

        for chunk in document_chunks:
            embedding = self.get_embedding(chunk["text"])
            if embedding:
                vectorized_chunk = {
                    "id": chunk["id"],
                    "text": chunk["text"],
                    "metadata": chunk["metadata"],
                    "embedding": embedding
                }
                vectorized_chunks.append(vectorized_chunk)

        # 保存向量化的分段
        with open(vector_file, 'w', encoding='utf-8') as f:
            json.dump(vectorized_chunks, f, ensure_ascii=False, indent=2)

        return document_id

    def similarity_search(self, query, top_k=3):
        """根据查询检索最相关的文档分段"""
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return []

        all_chunks = []

        # 加载所有向量化的分段
        for file in os.listdir(VECTOR_FOLDER):
            if file.endswith('.json'):
                with open(os.path.join(VECTOR_FOLDER, file), 'r', encoding='utf-8') as f:
                    chunks = json.load(f)
                    all_chunks.extend(chunks)

        # 计算相似度并排序
        results = []
        for chunk in all_chunks:
            chunk_embedding = chunk["embedding"]
            similarity = self.cosine_similarity(query_embedding, chunk_embedding)
            results.append((chunk, similarity))

        # 按相似度降序排序
        results.sort(key=lambda x: x[1], reverse=True)

        # 返回前top_k个结果
        return [item[0] for item in results[:top_k]]

    def cosine_similarity(self, vec1, vec2):
        """计算两个向量的余弦相似度"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
