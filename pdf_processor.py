import os
import PyPDF2
import fitz  # PyMuPDF
import uuid
import json
from config import UPLOAD_FOLDER, CHUNK_SIZE, CHUNK_OVERLAP, IMAGE_FOLDER

class PDFProcessor:
    def __init__(self):
        # 确保上传目录存在
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)

    def save_pdf(self, file):
        """保存上传的PDF文件"""
        filename = str(uuid.uuid4()) + '.pdf'
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        return filename, file_path

    def extract_text(self, file_path):
        """从PDF文件中提取每页文本，返回列表"""
        texts = []
        try:
            with open(file_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    page_text = page.extract_text()
                    texts.append(page_text if page_text else "")
            return texts
        except Exception as e:
            print(f"提取PDF文本时出错: {e}")
            return []

    def chunk_text(self, text):
        """将文本分段"""
        chunks = []

        # 简单按段落分割
        paragraphs = text.split('\n\n')

        current_chunk = ""
        for paragraph in paragraphs:
            # 如果当前段落加上当前块不超过CHUNK_SIZE，则添加到当前块
            if len(current_chunk) + len(paragraph) <= CHUNK_SIZE:
                current_chunk += paragraph + "\n\n"
            else:
                # 否则，保存当前块并开始新块
                if current_chunk:
                    chunks.append(current_chunk.strip())

                # 如果段落本身超过CHUNK_SIZE，则需要进一步分割
                if len(paragraph) > CHUNK_SIZE:
                    words = paragraph.split()
                    current_chunk = ""
                    for word in words:
                        if len(current_chunk) + len(word) + 1 <= CHUNK_SIZE:
                            current_chunk += word + " "
                        else:
                            chunks.append(current_chunk.strip())
                            current_chunk = word + " "
                else:
                    current_chunk = paragraph + "\n\n"

        # 添加最后一个块
        if current_chunk:
            chunks.append(current_chunk.strip())

        # 添加重叠
        overlapped_chunks = []
        for i in range(len(chunks)):
            if i == 0:
                overlapped_chunks.append(chunks[i])
            else:
                # 从前一个块的末尾获取重叠部分
                prev_chunk = chunks[i-1]
                overlap_text = prev_chunk[-CHUNK_OVERLAP:] if len(prev_chunk) > CHUNK_OVERLAP else prev_chunk
                overlapped_chunks.append(overlap_text + chunks[i])

        return overlapped_chunks

    def extract_images(self, file_path):
        """从PDF文件中提取所有图片，按页保存，返回每页图片文件名列表"""
        if not os.path.exists(IMAGE_FOLDER):
            os.makedirs(IMAGE_FOLDER)
        doc = fitz.open(file_path)
        page_images = []  # 每页图片文件名列表
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images(full=True)
            image_files = []
            for img_index, img in enumerate(image_list):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                if pix.n < 5:  # this is GRAY or RGB
                    img_filename = f"{os.path.splitext(os.path.basename(file_path))[0]}_page{page_num+1}_img{img_index+1}.png"
                    img_path = os.path.join(IMAGE_FOLDER, img_filename)
                    pix.save(img_path)
                    image_files.append(img_filename)
                else:  # CMYK: convert to RGB first
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    img_filename = f"{os.path.splitext(os.path.basename(file_path))[0]}_page{page_num+1}_img{img_index+1}.png"
                    img_path = os.path.join(IMAGE_FOLDER, img_filename)
                    pix.save(img_path)
                    image_files.append(img_filename)
                pix = None
            page_images.append(image_files)
        return page_images

    def process_pdf(self, file):
        """处理PDF文件：保存、提取文本、分段、提取图片"""
        filename, file_path = self.save_pdf(file)
        page_texts = self.extract_text(file_path)  # 每页文本
        page_images = self.extract_images(file_path)  # 每页图片
        document_chunks = []
        for i, text in enumerate(page_texts):
            images = page_images[i] if i < len(page_images) else []
            document_chunks.append({
                "id": f"{filename}-page-{i+1}",
                "text": text,
                "metadata": {
                    "filename": filename,
                    "page_index": i+1,
                    "total_pages": len(page_texts),
                    "images": images
                }
            })
        return document_chunks
