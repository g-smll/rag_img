# API配置
API_TOKEN = "sk-xkmpyoaangdwwjirbwajaifivchxeqarueggkgaafnauikkd"  # 请替换为您的实际token

# API端点
EMBEDDING_API_URL = "https://api.siliconflow.cn/v1/embeddings"
CHAT_API_URL = "https://api.siliconflow.cn/v1/chat/completions"

# 模型配置
EMBEDDING_MODEL = "BAAI/bge-m3"
CHAT_MODEL = "Pro/deepseek-ai/DeepSeek-V3"

# 文档处理配置
CHUNK_SIZE = 1000  # 文档分段大小（字符数）
CHUNK_OVERLAP = 200  # 分段重叠大小（字符数）

# 文件存储路径
UPLOAD_FOLDER = "uploads"
VECTOR_FOLDER = "vectors"
IMAGE_FOLDER = "images"

# MCP服务配置
MCP_SERVICE_URL = "http://127.0.0.1:9090/messages/"
