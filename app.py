import time

from flask import Flask, request, render_template, jsonify, session, send_from_directory
import os
import secrets
from pdf_processor import PDFProcessor
from vector_store import VectorStore
from qa_model import QAModel
from mcp_integration import MCPIntegration
from config import UPLOAD_FOLDER, VECTOR_FOLDER
import json

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化组件
pdf_processor = PDFProcessor()
vector_store = VectorStore()
qa_model = QAModel(vector_store)
mcp_integration = MCPIntegration(qa_model)





@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')

@app.route('/ask', methods=['POST'])
def ask():
    try:
        # 优先从json获取，其次从form获取
        if request.is_json:
            data = request.get_json()
            question = data.get('question') if data else None
        else:
            question = request.form.get('question')
        
        if not question:
            return jsonify({
                'success': False,
                'error': '未检测到问题内容'
            }), 400
        
        # 使用智能问答：让DeepSeek决定是使用数据库工具还是知识问答
        answer = mcp_integration.intelligent_answer(question)
        
        # 确保answer不为None
        if answer is None:
            answer = "抱歉，处理您的问题时出现了问题，请稍后重试。"
        
        # 检查是否是AJAX请求（通过Content-Type判断）
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # AJAX请求返回JSON
            return jsonify({
                'success': True,
                'answer': answer,
                'question': question
            }), 200
        else:
            # 表单提交返回HTML页面
            return render_template('index.html', answer=answer, question=question)
        
    except Exception as e:
        print(f"处理问题时出错: {str(e)}")  # 添加日志
        # 检查是否是AJAX请求
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'error': f'处理问题时出错: {str(e)}'
            }), 500
        else:
            return render_template('index.html', error=str(e))

@app.route('/upload', methods=['POST'])
def upload_file():
    """处理文件上传"""
    if 'file' not in request.files:
        return jsonify({'error': '没有文件部分'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    if file and file.filename.endswith('.pdf'):
        try:
            # 处理PDF文件
            document_chunks = pdf_processor.process_pdf(file)

            # 向量化文档分段
            document_id = vector_store.vectorize_chunks(document_chunks)

            # 存储文档ID到会话
            if 'documents' not in session:
                session['documents'] = []

            session['documents'].append({
                'id': document_id,
                'name': file.filename,
                'chunks': len(document_chunks)
            })

            return jsonify({
                'success': True,
                'message': f'文件 {file.filename} 上传成功并处理完毕',
                'document_id': document_id,
                'chunks': len(document_chunks)
            })
        except Exception as e:
            return jsonify({'error': f'处理文件时出错: {str(e)}'}), 500
    else:
        return jsonify({'error': '只允许上传PDF文件'}), 400

@app.route('/documents')
def list_documents():
    """列出已上传的文档"""
    if 'documents' not in session:
        return jsonify([])

    return jsonify(session['documents'])

@app.route('/vector_data')
def vector_data():
    """分页获取所有向量分段数据"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 50))
    all_chunks = []
    # 加载所有向量化的分段
    for file in os.listdir(VECTOR_FOLDER):
        if file.endswith('.json'):
            with open(os.path.join(VECTOR_FOLDER, file), 'r', encoding='utf-8') as f:
                chunks = json.load(f)
                for chunk in chunks:
                    all_chunks.append({
                        'id': chunk['id'],
                        'text': chunk['text'],
                        'metadata': chunk['metadata']
                    })
    total = len(all_chunks)
    start = (page - 1) * page_size
    end = start + page_size
    page_data = all_chunks[start:end]
    return jsonify({
        'total': total,
        'page': page,
        'page_size': page_size,
        'data': page_data
    })

@app.route('/view_vectors')
def view_vectors():
    return render_template('vector_data.html')

@app.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片静态访问"""
    from config import IMAGE_FOLDER
    return send_from_directory(IMAGE_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True,use_reloader=False)
