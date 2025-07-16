document.addEventListener('DOMContentLoaded', function() {
    // 获取DOM元素
    const dropArea = document.getElementById('dropArea');
    const fileInput = document.getElementById('fileInput');
    const uploadButton = document.getElementById('uploadButton');
    const uploadForm = document.getElementById('uploadForm');
    const uploadProgress = document.getElementById('uploadProgress');
    const progressBar = uploadProgress.querySelector('.progress');
    const uploadStatus = document.getElementById('uploadStatus');
    const documentsList = document.getElementById('documentsList');
    const chatMessages = document.getElementById('chatMessages');
    const questionInput = document.getElementById('questionInput');
    const askButton = document.getElementById('askButton');

    // 初始化
    loadDocuments();

    // 文件上传相关事件
    uploadButton.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', () => {
        if (fileInput.files.length > 0) {
            uploadFile(fileInput.files[0]);
        }
    });

    // 拖放功能
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.classList.add('dragover');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, () => {
            dropArea.classList.remove('dragover');
        });
    });

    dropArea.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        const files = dt.files;

        if (files.length > 0) {
            uploadFile(files[0]);
        }
    });

    // 问答功能
    questionInput.addEventListener('input', () => {
        askButton.disabled = questionInput.value.trim() === '';
    });

    askButton.addEventListener('click', askQuestion);

    questionInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (questionInput.value.trim() !== '') {
                askQuestion();
            }
        }
    });

    // 上传文件函数
    function uploadFile(file) {
        // 检查是否为PDF文件
        if (!file.name.toLowerCase().endsWith('.pdf')) {
            showUploadStatus('错误：只能上传PDF文件', 'error');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        // 显示上传进度
        uploadProgress.style.display = 'block';
        progressBar.style.width = '0%';
        showUploadStatus('正在上传...', 'info');

        // 模拟上传进度
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 5;
            if (progress <= 90) {
                progressBar.style.width = progress + '%';
            }
        }, 300);

        // 发送上传请求
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            clearInterval(progressInterval);
            progressBar.style.width = '100%';

            if (data.success) {
                showUploadStatus(`文件 ${file.name} 上传成功！已处理 ${data.chunks} 个文本段落。`, 'success');
                loadDocuments();
                enableQA();
            } else {
                showUploadStatus(`错误：${data.error}`, 'error');
            }

            // 重置文件输入
            fileInput.value = '';

            // 3秒后隐藏进度条
            setTimeout(() => {
                uploadProgress.style.display = 'none';
            }, 3000);
        })
        .catch(error => {
            clearInterval(progressInterval);
            showUploadStatus(`上传失败：${error.message}`, 'error');
            fileInput.value = '';
            uploadProgress.style.display = 'none';
        });
    }

    // 显示上传状态
    function showUploadStatus(message, type) {
        uploadStatus.textContent = message;
        uploadStatus.className = '';
        uploadStatus.classList.add(type);
    }

    // 加载已上传的文档
    function loadDocuments() {
        fetch('/documents')
        .then(response => response.json())
        .then(documents => {
            if (documents.length === 0) {
                documentsList.innerHTML = '<p class="empty-message">暂无上传的文档</p>';
                return;
            }

            documentsList.innerHTML = '';
            documents.forEach(doc => {
                const docItem = document.createElement('div');
                docItem.className = 'document-item';
                docItem.innerHTML = `
                    <div class="document-info">
                        <span class="document-icon">📄</span>
                        <div>
                            <div class="document-name">${doc.name}</div>
                            <div class="document-meta">${doc.chunks} 个文本段落</div>
                        </div>
                    </div>
                `;
                documentsList.appendChild(docItem);
            });

            enableQA();
        })
        .catch(error => {
            console.error('加载文档失败:', error);
            documentsList.innerHTML = '<p class="empty-message">加载文档失败</p>';
        });
    }

    // 启用问答功能
    function enableQA() {
        askButton.disabled = questionInput.value.trim() === '';
    }

    // 提问功能
    function askQuestion() {
        const question = questionInput.value.trim();
        if (question === '') return;

        // 添加用户问题到聊天区域
        addMessage('user', question);

        // 清空输入框并禁用按钮
        questionInput.value = '';
        askButton.disabled = true;

        // 添加AI思考中的消息
        const thinkingMsgId = addThinkingMessage();

        // 发送问题到服务器
        fetch('/ask', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify({ question })
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            return response.json();
        })
        .then(data => {
            // 移除思考中的消息
            removeMessage(thinkingMsgId);

            if (data.success) {
                // 添加AI回答
                addMessage('ai', data.answer);
            } else {
                addMessage('system', `错误：${data.error}`);
            }
        })
        .catch(error => {
            // 移除思考中的消息
            removeMessage(thinkingMsgId);
            addMessage('system', `发生错误：${error.message}`);
        });
    }

    // 添加消息到聊天区域
    function addMessage(type, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        messageDiv.innerHTML = `
            <div class="message-content">
                <p>${formatMessage(content)}</p>
            </div>
        `;

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageDiv.id;
    }

    // 添加"思考中"的消息
    function addThinkingMessage() {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message ai';
        messageDiv.id = 'thinking-message';
        messageDiv.innerHTML = `
            <div class="message-content">
                <p><span class="loading"></span>AI正在思考...</p>
            </div>
        `;

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return messageDiv.id;
    }

    // 移除指定ID的消息
    function removeMessage(messageId) {
        const message = document.getElementById(messageId);
        if (message) {
            message.remove();
        }
    }

    // 格式化消息内容（处理换行和图片）
    function formatMessage(content) {
        // 支持图片内嵌：将[图片:xxx.png]替换为<img src="/images/xxx.png" style="max-width:100%;height:auto;">，并处理换行
        return content
            .replace(/\[图片:([^\]]+)\]/g, '<img src="/images/$1" style="max-width:100%;height:auto;" alt="图片">')
            .replace(/\n/g, '<br>');
    }
});
