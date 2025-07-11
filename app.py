from flask import Flask, request, render_template, jsonify, session, send_from_directory
import os
import secrets
from pdf_processor import PDFProcessor
from vector_store import VectorStore
from qa_model import QAModel
from config import UPLOAD_FOLDER

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# 初始化组件
pdf_processor = PDFProcessor()
vector_store = VectorStore()
qa_model = QAModel(vector_store)

@app.route('/')
def index():
    """渲染主页"""
    return render_template('index.html')

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

@app.route('/ask', methods=['POST'])
def ask_question():
    """处理用户问题"""
    data = request.json

    if not data or 'question' not in data:
        return jsonify({'error': '没有提供问题'}), 400

    question = data['question']

    try:
        # 生成回答
        answer = qa_model.generate_answer(question)

        return jsonify({
            'success': True,
            'question': question,
            'answer': answer
        })
    except Exception as e:
        return jsonify({'error': f'生成回答时出错: {str(e)}'}), 500

@app.route('/documents')
def list_documents():
    """列出已上传的文档"""
    if 'documents' not in session:
        return jsonify([])

    return jsonify(session['documents'])

@app.route('/images/<path:filename>')
def serve_image(filename):
    """提供图片静态访问"""
    from config import IMAGE_FOLDER
    return send_from_directory(IMAGE_FOLDER, filename)

if __name__ == '__main__':
    app.run(debug=True)
