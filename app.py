from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify, Response
from flask_cors import CORS
import os
import fitz
import base64
from io import BytesIO
import json
from datetime import datetime
import glob
import uuid

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Backend is running"})
UPLOAD_FOLDER = "uploads"
EDITED_FOLDER = "edited"
HTML_FOLDER = "saved_html"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EDITED_FOLDER, exist_ok=True)
os.makedirs(HTML_FOLDER, exist_ok=True)

def cleanup_session_files(session_id):
    """Clean up all HTML files for a specific session"""
    try:
        pattern = os.path.join(HTML_FOLDER, f"session_{session_id}_*.html")
        files_to_delete = glob.glob(pattern)
        deleted_count = 0
        
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                deleted_count += 1
                print(f"Deleted session file: {file_path}")
            except Exception as e:
                print(f"Error deleting file {file_path}: {e}")
        
        print(f"Cleaned up {deleted_count} files for session {session_id}")
        return deleted_count
    except Exception as e:
        print(f"Error in cleanup_session_files: {e}")
        return 0

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if "pdf" not in request.files:
            return "No file uploaded", 400
        file = request.files["pdf"]
        if file.filename == "":
            return "No selected file", 400

        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        return redirect(url_for("convert_pdf", filename=file.filename))
    return render_template("index.html")

@app.route("/get_page_count", methods=["POST"])
def get_page_count():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file to uploads folder for later use
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        print(f"DEBUG: Saved file as {file.filename}")
        
        # Open PDF and get page count
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()
        
        response_data = {"page_count": page_count, "filename": file.filename}
        print(f"DEBUG: Returning response: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"DEBUG: Error in get_page_count: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/pdf_preview", methods=["POST"])
def pdf_preview():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file temporarily
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Open PDF and get first page as image
        doc = fitz.open(filepath)
        page = doc[0]  # Get first page
        
        # Render page as image
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better quality
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        # Clean up temporary file
        os.remove(filepath)
        
        # Return base64 encoded image
        img_base64 = base64.b64encode(img_data).decode()
        return jsonify({"preview_image": f"data:image/png;base64,{img_base64}"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf_info/<filename>")
def get_pdf_info(filename):
    """Get PDF information including page count"""
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()
        return jsonify({
            "filename": filename,
            "page_count": page_count
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf_thumbnail/<filename>/<int:page_num>")
def get_pdf_thumbnail(filename, page_num):
    """Get thumbnail image for a specific page"""
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    try:
        doc = fitz.open(filepath)
        if page_num < 1 or page_num > len(doc):
            return jsonify({"error": "Invalid page number"}), 400
        
        page = doc[page_num - 1]  # Convert to 0-based index
        
        # Check if high quality is requested
        quality = request.args.get('quality', 'normal')
        
        if quality == 'high':
            # High quality for preview - use higher resolution
            mat = fitz.Matrix(2.0, 2.0)  # 2x resolution for crisp display
            pix = page.get_pixmap(matrix=mat)
            # If too large, scale down proportionally but keep it high quality
            if pix.width > 2000:
                scale = 2000 / pix.width
                mat = fitz.Matrix(2.0 * scale, 2.0 * scale)
                pix = page.get_pixmap(matrix=mat)
        else:
            # Normal thumbnail size
            mat = fitz.Matrix(0.3, 0.3)  # Scale down to 30% for thumbnail
        
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        
        doc.close()
        
        return Response(img_data, mimetype="image/png")
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/split_pdf", methods=["POST"])
def split_pdf():
    """Split PDF into individual pages"""
    try:
        data = request.get_json()
        filename = data.get('filename')
        pages = data.get('pages', [])
        
        if not filename or not pages:
            return jsonify({"error": "Filename and pages are required"}), 400
        
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        if not os.path.exists(filepath):
            return jsonify({"error": "PDF file not found"}), 404
        
        # Open the PDF
        doc = fitz.open(filepath)
        total_pages = len(doc)
        
        # Validate page numbers
        valid_pages = [p for p in pages if 1 <= p <= total_pages]
        if not valid_pages:
            return jsonify({"error": "No valid pages to split"}), 400
        
        download_urls = []
        
        # Create individual PDFs for each selected page
        for page_num in valid_pages:
            # Create a new PDF with just this page
            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=page_num-1, to_page=page_num-1)
            
            # Generate filename for this page
            base_name = os.path.splitext(filename)[0]
            page_filename = f"{base_name}_page_{page_num}.pdf"
            page_filepath = os.path.join(EDITED_FOLDER, page_filename)
            
            # Save the page
            new_doc.save(page_filepath)
            new_doc.close()
            
            # Add download URL
            download_urls.append(f"/download_split/{page_filename}")
        
        doc.close()
        
        # Generate view URLs for each split page
        base_name = os.path.splitext(filename)[0]
        view_urls = [f"/view_split/{base_name}_page_{page_num}.pdf" for page_num in valid_pages]
        
        return jsonify({
            "success": True,
            "message": f"PDF split into {len(valid_pages)} pages",
            "downloadUrls": download_urls,
            "viewUrls": view_urls,
            "pages": valid_pages
        })
        
    except Exception as e:
        print(f"Error splitting PDF: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download_split/<path:filename>")
def download_split_page(filename):
    """Download a split PDF page"""
    try:
        # URL decode the filename to handle spaces and special characters
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        filepath = os.path.join(EDITED_FOLDER, decoded_filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {decoded_filename}"}), 404
        
        return send_file(filepath, as_attachment=True, download_name=decoded_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/view_split/<path:filename>")
def view_split_page(filename):
    """View a split PDF page in browser"""
    try:
        # URL decode the filename to handle spaces and special characters
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        filepath = os.path.join(EDITED_FOLDER, decoded_filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": f"File not found: {decoded_filename}"}), 404
        
        return send_file(filepath, as_attachment=False, download_name=decoded_filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert/<filename>")
def convert_pdf(filename):
    print(f"DEBUG: Convert endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    page_num = request.args.get('page', type=int, default=None)  # No default page
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: Page number (0-based): {page_num}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        pages_data = []
        image_counter = 0
        
        # If page number is specified, only show that page, otherwise show all pages
        if page_num is not None and page_num >= 1 and page_num <= len(doc):
            page_range = [page_num - 1]  # Convert to 0-based index
            print(f"DEBUG: Showing specific page {page_num}")
        else:
            page_range = range(len(doc))
            print(f"DEBUG: Showing all pages, range: {list(range(1, len(doc) + 1))}")
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1}")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            page_html = f'<div class="pdf-page" data-page="{page_idx + 1}">'
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; font-size: {size}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span editable-text" data-text="{text}" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    image_counter += 1
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; width: {bbox[2] - bbox[0]}px; height: {bbox[3] - bbox[1]}px;"
                    page_html += f'<img class="editable-image" data-image-id="{image_counter}" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '</div>'
            pages_data.append({
                'html': page_html,
                'width': page.rect.width,
                'height': page.rect.height
            })
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        doc.close()
        print(f"DEBUG: Total pages processed: {len(pages_data)}")
        print(f"DEBUG: Rendering template with {len(pages_data)} pages")
        
        return render_template("converted.html", 
                             filename=filename, 
                             pages=pages_data)
    
    except Exception as e:
        return f"Error converting PDF: {str(e)}", 500

@app.route("/editor/<filename>")
def convert_pdf_for_editor(filename):
    print(f"DEBUG: Editor endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        pages_data = []
        image_counter = 0
        
        # Show all pages for editor
        page_range = range(len(doc))
        print(f"DEBUG: Showing all pages, range: {list(range(1, len(doc) + 1))}")
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1}")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            page_html = f'<div class="pdf-page" data-page="{page_idx + 1}">'
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; font-size: {size}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span editable-text" data-text="{text}" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    image_counter += 1
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0]}px; top: {bbox[1]}px; width: {bbox[2] - bbox[0]}px; height: {bbox[3] - bbox[1]}px;"
                    page_html += f'<img class="editable-image" data-image-id="{image_counter}" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '</div>'
            pages_data.append({
                'html': page_html,
                'width': page.rect.width,
                'height': page.rect.height
            })
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        doc.close()
        print(f"DEBUG: Total pages processed: {len(pages_data)}")
        print(f"DEBUG: Rendering editor template with {len(pages_data)} pages")
        
        return render_template("editor.html", 
                             filename=filename, 
                             pages=pages_data)
    
    except Exception as e:
        return f"Error converting PDF: {str(e)}", 500

@app.route("/convert_signature/<filename>")
def convert_pdf_for_signature(filename):
    print(f"DEBUG: Convert signature endpoint called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    try:
        doc = fitz.open(filepath)
        print(f"DEBUG: PDF opened successfully, total pages: {len(doc)}")
        
        # Always show all pages for signature positioning
        page_range = range(len(doc))
        print(f"DEBUG: Showing all pages, range: {list(page_range)}")
        
        # Create a multi-page HTML for signature positioning
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                    font-family: Arial, sans-serif;
                }
                .pdf-container {
                    display: flex;
                    flex-direction: column;
                    gap: 20px;
                    max-width: 1200px;
                    margin: 0 auto;
                }
                .pdf-page {
                    position: relative;
                    background: white;
                    transform-origin: top left;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                    border-radius: 4px;
                    overflow: hidden;
                }
                .page-header {
                    background: #e9ecef;
                    padding: 8px 12px;
                    font-size: 12px;
                    color: #6c757d;
                    border-bottom: 1px solid #dee2e6;
                    cursor: pointer;
                    user-select: none;
                }
                .page-header:hover {
                    background: #dee2e6;
                }
                .page-header.selected {
                    background: #007bff;
                    color: white;
                }
                .page-content {
                    position: relative;
                }
                .text-span {
                    position: absolute;
                    white-space: nowrap;
                }
                .editable-image {
                    position: absolute;
                }
            </style>
        </head>
        <body>
        <div class="pdf-container">
        """
        
        for page_idx in page_range:
            print(f"DEBUG: Processing page {page_idx + 1} for signature")
            page = doc[page_idx]
            page_dict = page.get_text("dict")
            print(f"DEBUG: Page {page_idx + 1} has {len(page_dict['blocks'])} blocks")
            
            # Scale factor to fit pages nicely (max width 800px)
            scale_factor = min(800 / page.rect.width, 1.0)
            scaled_width = page.rect.width * scale_factor
            scaled_height = page.rect.height * scale_factor
            
            page_html = f'''
            <div class="pdf-page" data-page="{page_idx + 1}" style="width: {scaled_width}px;">
                <div class="page-header" onclick="selectPage({page_idx + 1})">Page {page_idx + 1}</div>
                <div class="page-content" style="width: {scaled_width}px; height: {scaled_height}px;">
            '''
            
            for block in page_dict["blocks"]:
                if "lines" in block:
                    for line in block["lines"]:
                        line_html = '<div class="text-line">'
                        for span in line["spans"]:
                            text = span["text"]
                            if text.strip():
                                bbox = span["bbox"]
                                font = span["font"]
                                size = span["size"]
                                flags = span["flags"]
                                
                                style = f"position: absolute; left: {bbox[0] * scale_factor}px; top: {bbox[1] * scale_factor}px; font-size: {size * scale_factor}px; font-family: {font};"
                                if flags & 2**4:
                                    style += " font-weight: bold;"
                                if flags & 2**1:
                                    style += " font-style: italic;"
                                
                                line_html += f'<span class="text-span" style="{style}">{text}</span>'
                        line_html += '</div>'
                        page_html += line_html
                
                elif "image" in block:
                    bbox = block["bbox"]
                    image_data = block["image"]
                    image_base64 = base64.b64encode(image_data).decode()
                    
                    style = f"position: absolute; left: {bbox[0] * scale_factor}px; top: {bbox[1] * scale_factor}px; width: {(bbox[2] - bbox[0]) * scale_factor}px; height: {(bbox[3] - bbox[1]) * scale_factor}px;"
                    page_html += f'<img class="editable-image" src="data:image/png;base64,{image_base64}" style="{style}">'
            
            page_html += '''
                </div>
            </div>
            '''
            html_content += page_html
            print(f"DEBUG: Page {page_idx + 1} HTML length: {len(page_html)}")
        
        html_content += """
        </div>
        <script>
            function selectPage(pageNum) {
                // Remove previous selection
                document.querySelectorAll('.page-header').forEach(header => {
                    header.classList.remove('selected');
                });
                
                // Add selection to clicked page
                const clickedHeader = document.querySelector(`[data-page="${pageNum}"] .page-header`);
                clickedHeader.classList.add('selected');
                
                // Notify parent window about page selection
                window.parent.postMessage({
                    type: 'pageSelected',
                    page: pageNum
                }, '*');
            }
        </script>
        </body>
        </html>
        """
        
        doc.close()
        print(f"DEBUG: Returning multi-page HTML for signature positioning")
        
        return html_content
    
    except Exception as e:
        return f"Error converting PDF for signature: {str(e)}", 500

@app.route("/save_edits/<filename>", methods=["POST"])
def save_edits(filename):
    try:
        # Get the request data
        data = request.get_json()
        edits = data.get("edits", []) if data else []
        
        print(f"Received edits for {filename}: {len(edits)} edits")
        
        if not edits:
            return jsonify({"status": "success", "message": "No edits to save"})
            
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"status": "error", "message": f"Original file {filename} not found"}), 404
            
        edited_path = os.path.join(EDITED_FOLDER, f"edited_{filename}")

        doc = fitz.open(filepath)
        
        for edit in edits:
            try:
                if not isinstance(edit, dict):
                    print(f"Skipping invalid edit: {edit}")
                    continue
                    
                page_num = edit.get("page", 1) - 1
                edit_type = edit.get("type", "")
                
                if page_num < 0 or page_num >= len(doc):
                    print(f"Skipping edit for invalid page: {page_num}")
                    continue
                    
                page = doc[page_num]
                
                if edit_type == "text":
                    old_text = edit.get("old_text", "")
                    new_text = edit.get("new_text", "")
                    
                    if old_text and new_text:
                        text_instances = page.search_for(old_text)
                        for inst in text_instances:
                            rect = fitz.Rect(inst)
                            page.add_redact_annot(rect)
                            page.apply_redactions()
                            page.insert_text((inst.x0, inst.y1), new_text, fontsize=12)
                
                elif edit_type == "image":
                    image_id = edit.get("image_id")
                    new_image_data = edit.get("image_data")
                    
                    if image_id and new_image_data:
                        image_list = page.get_images()
                        if 1 <= image_id <= len(image_list):
                            xref = image_list[image_id - 1][0]
                            if ',' in new_image_data:
                                image_data = base64.b64decode(new_image_data.split(',')[1])
                                doc.update_stream(xref, image_data)
                        
            except Exception as edit_error:
                print(f"Error processing individual edit: {edit_error}")
                continue
        
        doc.save(edited_path)
        doc.close()
        
        return jsonify({"status": "success", "message": "Edits saved successfully"})
    
    except Exception as e:
        print(f"Error in save_edits: {str(e)}")  # Debug logging
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/save_html/<filename>", methods=["POST"])
def save_html(filename):
    try:
        data = request.json
        html_content = data.get("html_content")
        session_id = data.get("session_id")
        
        if not html_content:
            return jsonify({"status": "error", "message": "No HTML content provided"}), 400
        
        # Generate session ID if not provided
        if not session_id:
            session_id = str(uuid.uuid4())[:8]  # Short session ID
        
        # Create a clean filename with session ID
        base_name = os.path.splitext(filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        html_filename = f"session_{session_id}_{base_name}_{timestamp}.html"
        html_path = os.path.join(HTML_FOLDER, html_filename)
        
        # Save the HTML file
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return jsonify({
            "status": "success", 
            "message": "HTML saved successfully",
            "html_filename": html_filename,
            "session_id": session_id
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/cleanup_session/<session_id>", methods=["POST"])
def cleanup_session(session_id):
    """Clean up all HTML files for a specific session"""
    try:
        deleted_count = cleanup_session_files(session_id)
        return jsonify({
            "status": "success",
            "message": f"Cleaned up {deleted_count} files for session {session_id}",
            "deleted_count": deleted_count
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/view_html/<html_filename>")
def view_html(html_filename):
    try:
        html_path = os.path.join(HTML_FOLDER, html_filename)
        if not os.path.exists(html_path):
            return "HTML file not found", 404
        
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        return html_content
    
    except Exception as e:
        return f"Error loading HTML: {str(e)}", 500

@app.route("/download_pdf/<html_filename>")
def download_pdf(html_filename):
    try:
        html_path = os.path.join(HTML_FOLDER, html_filename)
        if not os.path.exists(html_path):
            return jsonify({"status": "error", "message": "HTML file not found"}), 404
        
        # Convert HTML to PDF
        pdf_filename = html_filename.replace('.html', '.pdf')
        pdf_path = os.path.join(HTML_FOLDER, pdf_filename)
        
        # Read HTML content
        with open(html_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
        
        # Parse HTML to extract page content using regex
        import re
        
        # Extract page divs with their content
        page_pattern = r'<div[^>]*class="[^"]*pdf-page[^"]*"[^>]*data-page="(\d+)"[^>]*>(.*?)</div>'
        pages = re.findall(page_pattern, html_content, re.IGNORECASE | re.DOTALL)
        
        # Create PDF with proper formatting
        doc = fitz.open()
        
        for page_num, page_content in pages:
            # Create a new page for each PDF page
            page = doc.new_page(width=595, height=842)  # A4 size
            y_position = 50
            
            # Extract text spans from this page
            text_span_pattern = r'<span[^>]*class="[^"]*editable-text[^"]*"[^>]*style="[^"]*left: ([^;]+)px; top: ([^;]+)px;[^"]*"[^>]*>([^<]*)</span>'
            text_spans = re.findall(text_span_pattern, page_content, re.IGNORECASE)
            
            # Extract images from this page
            image_pattern = r'<img[^>]*class="[^"]*editable-image[^"]*"[^>]*style="[^"]*left: ([^;]+)px; top: ([^;]+)px; width: ([^;]+)px; height: ([^;]+)px;[^"]*"[^>]*src="data:image/png;base64,([^"]*)"[^>]*>'
            images = re.findall(image_pattern, page_content, re.IGNORECASE)
            
            # Add text content to PDF page
            for left, top, text_content in text_spans:
                if text_content and text_content.strip():
                    try:
                        x_pos = float(left)
                        y_pos = float(top)
                        clean_text = text_content.strip()
                        # Decode HTML entities
                        clean_text = clean_text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"')
                        
                        # Convert PDF coordinates (top-left origin) to PyMuPDF coordinates
                        # Scale positions to fit A4 page
                        scale_x = 595 / 800  # Adjust based on your PDF page width
                        scale_y = 842 / 1000  # Adjust based on your PDF page height
                        
                        pdf_x = x_pos * scale_x
                        pdf_y = y_pos * scale_y
                        
                        # Ensure text fits within page bounds
                        if pdf_x < 0:
                            pdf_x = 50
                        if pdf_y < 0:
                            pdf_y = 50
                        if pdf_x > 545:
                            pdf_x = 545
                        if pdf_y > 792:
                            pdf_y = 792
                        
                        page.insert_text((pdf_x, pdf_y), clean_text, fontsize=10)
                    except (ValueError, TypeError):
                        # If position parsing fails, just add text sequentially
                        page.insert_text((50, y_position), clean_text, fontsize=10)
                        y_position += 15
            
            # Add images to PDF page
            for left, top, width, height, image_data in images:
                try:
                    x_pos = float(left)
                    y_pos = float(top)
                    img_width = float(width)
                    img_height = float(height)
                    
                    # Scale positions to fit A4 page
                    scale_x = 595 / 800
                    scale_y = 842 / 1000
                    
                    pdf_x = x_pos * scale_x
                    pdf_y = y_pos * scale_y
                    pdf_width = img_width * scale_x
                    pdf_height = img_height * scale_y
                    
                    # Ensure image fits within page bounds
                    if pdf_x < 0:
                        pdf_x = 50
                    if pdf_y < 0:
                        pdf_y = 50
                    if pdf_x + pdf_width > 545:
                        pdf_width = 545 - pdf_x
                    if pdf_y + pdf_height > 792:
                        pdf_height = 792 - pdf_y
                    
                    if pdf_width > 0 and pdf_height > 0:
                        # Decode base64 image and insert
                        import base64
                        image_bytes = base64.b64decode(image_data)
                        rect = fitz.Rect(pdf_x, pdf_y, pdf_x + pdf_width, pdf_y + pdf_height)
                        page.insert_image(rect, pixmap=fitz.Pixmap(fitz.csRGB, image_bytes))
                except (ValueError, TypeError, Exception):
                    # Skip problematic images
                    continue
        
        doc.save(pdf_path)
        doc.close()
        
        # Send PDF file for download
        return send_file(pdf_path, as_attachment=True, download_name=pdf_filename)
    
    except Exception as e:
        print(f"Error in download_pdf: {str(e)}")  # Debug logging
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/extract_text", methods=["POST"])
def extract_text():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        doc = fitz.open(filepath)
        extracted_text = ""
        page_count = len(doc)
        
        for page_num in range(page_count):
            page = doc[page_num]
            page_text = page.get_text()
            if page_text.strip():
                extracted_text += f"--- Page {page_num + 1} ---\n"
                extracted_text += page_text + "\n\n"
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "filename": filename,
            "text": extracted_text,
            "page_count": page_count
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/extract_images", methods=["POST"])
def extract_images():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        doc = fitz.open(filepath)
        images_data = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            image_list = page.get_images()
            
            for img_index, img in enumerate(image_list):
                xref = img[0]
                pix = fitz.Pixmap(doc, xref)
                
                if pix.n - pix.alpha < 4:  # GRAY or RGB
                    img_data = pix.tobytes("png")
                    img_base64 = base64.b64encode(img_data).decode()
                    
                    images_data.append({
                        "page": page_num + 1,
                        "image_index": img_index + 1,
                        "width": pix.width,
                        "height": pix.height,
                        "data": img_base64
                    })
                
                pix = None
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "filename": filename,
            "images": images_data,
            "total_images": len(images_data)
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/merge_pdfs", methods=["POST"])
def merge_pdfs():
    try:
        print(f"DEBUG: Merge endpoint called")
        print(f"DEBUG: Request files: {request.files}")
        print(f"DEBUG: Request form: {request.form}")
        print(f"DEBUG: Request content type: {request.content_type}")
        print(f"DEBUG: Request content length: {request.content_length}")
        
        files = request.files.getlist('files')
        print(f"DEBUG: Files list length: {len(files)}")
        
        # Debug each file
        for i, file in enumerate(files):
            print(f"DEBUG: File {i}: filename='{file.filename}', content_length={file.content_length}, content_type={file.content_type}")
            if hasattr(file, 'stream'):
                print(f"DEBUG: File {i} stream position: {file.stream.tell()}")
        
        # Check if files are empty or invalid
        valid_files = []
        for i, file in enumerate(files):
            print(f"DEBUG: File {i}: filename='{file.filename}', content_length={file.content_length}")
            if file and file.filename and file.filename.strip():
                valid_files.append(file)
            else:
                print(f"DEBUG: Skipping empty/invalid file at index {i}")
        
        print(f"DEBUG: Valid files count: {len(valid_files)}")
        
        if len(valid_files) < 2:
            print(f"DEBUG: Not enough valid files: {len(valid_files)}")
            return jsonify({"status": "error", "message": f"At least 2 valid PDF files are required for merging. Found {len(valid_files)} valid files."}), 400
        
        files = valid_files
        
        # Create merged document
        merged_doc = fitz.open()
        
        for file in files:
            print(f"DEBUG: Processing file: {file.filename}")
            if file and file.filename and file.filename.endswith('.pdf'):
                # Save temporary file
                temp_path = os.path.join(UPLOAD_FOLDER, f"temp_{file.filename}")
                file.save(temp_path)
                print(f"DEBUG: Saved temp file: {temp_path}")
                
                # Open and add pages to merged document
                temp_doc = fitz.open(temp_path)
                merged_doc.insert_pdf(temp_doc)
                temp_doc.close()
                print(f"DEBUG: Added pages from {file.filename}")
                
                # Remove temporary file
                os.remove(temp_path)
            else:
                print(f"DEBUG: Skipping invalid file: {file.filename if file else 'None'}")
        
        # Generate merged filename
        merged_filename = f"merged_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        merged_path = os.path.join(HTML_FOLDER, merged_filename)
        
        # Get page count before closing
        page_count = len(merged_doc)
        
        # Save merged document
        merged_doc.save(merged_path)
        merged_doc.close()
        
        return jsonify({
            "status": "success",
            "message": f"Successfully merged {len(files)} PDF files",
            "merged_filename": merged_filename,
            "download_url": f"/download_merged/{merged_filename}",
            "file_count": len(files),
            "page_count": page_count
        })
    
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_merged/<merged_filename>")
def download_merged(merged_filename):
    try:
        merged_path = os.path.join(HTML_FOLDER, merged_filename)
        if not os.path.exists(merged_path):
            return "Merged PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(merged_path, as_attachment=True, download_name=merged_filename)
        else:
            return send_file(merged_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading merged PDF: {str(e)}", 500




@app.route('/download_split/<split_folder>/<split_filename>')
def download_split(split_folder, split_filename):
    try:
        split_path = os.path.join(HTML_FOLDER, split_folder, split_filename)
        if not os.path.exists(split_path):
            return "Split PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(split_path, as_attachment=True, download_name=split_filename)
        else:
            return send_file(split_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading split PDF: {str(e)}", 500


@app.route('/add_signature', methods=['POST'])
def add_signature():
    try:
        print(f"DEBUG: Request files: {list(request.files.keys())}")
        print(f"DEBUG: Request form: {list(request.form.keys())}")
        
        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Get signature data and position
        signature_data = request.form.get('signature_data', '')
        page_number = int(request.form.get('page_number', 1))
        x_position = float(request.form.get('x_position', 100))
        y_position = float(request.form.get('y_position', 100))
        width = float(request.form.get('width', 200))
        height = float(request.form.get('height', 100))
        
        print(f"DEBUG: Signature data length: {len(signature_data) if signature_data else 0}")
        print(f"DEBUG: Page number: {page_number}, Position: ({x_position}, {y_position}), Size: ({width}, {height})")
        
        if not signature_data:
            return jsonify({"status": "error", "message": "No signature data provided"}), 400
        
        # Save uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)
        
        # Open PDF document
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        if page_number < 1 or page_number > total_pages:
            doc.close()
            os.remove(pdf_path)
            return jsonify({"status": "error", "message": f"Invalid page number. PDF has {total_pages} pages"}), 400
        
        # Get the specific page
        page = doc[page_number - 1]
        page_rect = page.rect
        
        # Convert signature data from base64 to image
        import base64
        import io
        from PIL import Image
        
        # Remove data URL prefix if present
        if signature_data.startswith('data:image'):
            signature_data = signature_data.split(',')[1]
        
        # Decode base64 image
        signature_bytes = base64.b64decode(signature_data)
        signature_image = Image.open(io.BytesIO(signature_bytes))
        
        # Convert PIL image to bytes
        img_byte_arr = io.BytesIO()
        signature_image.save(img_byte_arr, format='PNG')
        img_byte_arr = img_byte_arr.getvalue()
        
        # Create a temporary image file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_signature_{timestamp}.png")
        with open(temp_img_path, 'wb') as f:
            f.write(img_byte_arr)
        
        # Create signature rectangle
        signature_rect = fitz.Rect(x_position, y_position, x_position + width, y_position + height)
        
        # Insert signature image into PDF
        page.insert_image(signature_rect, filename=temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        signed_filename = f"{base_name}_signed.pdf"
        signed_path = os.path.join(HTML_FOLDER, signed_filename)
        
        # Save the signed PDF
        doc.save(signed_path)
        doc.close()
        
        # Clean up temporary files
        os.remove(pdf_path)
        os.remove(temp_img_path)
        
        return jsonify({
            "status": "success",
            "message": f"Signature added successfully to page {page_number}",
            "signed_filename": signed_filename,
            "download_url": f"/download_signed/{signed_filename}",
            "page_number": page_number,
            "total_pages": total_pages
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error adding signature: {str(e)}"}), 500


@app.route('/add_watermark', methods=['POST'])
def add_watermark():
    try:
        print(f"DEBUG: Watermark request files: {list(request.files.keys())}")
        print(f"DEBUG: Watermark request form: {list(request.form.keys())}")

        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400

        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400

        # Get watermark data and settings
        watermark_type = request.form.get('watermark_type', 'text')  # 'text' or 'image'
        watermark_text = request.form.get('watermark_text', '')
        watermark_image_data = request.form.get('watermark_image_data', '')
        page_number = int(request.form.get('page_number', 1))
        x_position = float(request.form.get('x_position', 100))
        y_position = float(request.form.get('y_position', 100))
        width = float(request.form.get('width', 200))
        height = float(request.form.get('height', 100))
        opacity = float(request.form.get('opacity', 0.5))
        rotation = float(request.form.get('rotation', 0))
        apply_to_all = request.form.get('apply_to_all', 'false').lower() == 'true'

        print(f"DEBUG: Watermark type: {watermark_type}")
        print(f"DEBUG: Page number: {page_number}, Position: ({x_position}, {y_position}), Size: ({width}, {height})")
        print(f"DEBUG: Opacity: {opacity}, Rotation: {rotation}, Apply to all: {apply_to_all}")

        if watermark_type == 'text' and not watermark_text:
            return jsonify({"status": "error", "message": "No watermark text provided"}), 400
        if watermark_type == 'image' and not watermark_image_data:
            return jsonify({"status": "error", "message": "No watermark image provided"}), 400

        # Save the uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)

        # Open the PDF
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        # Determine which pages to watermark
        if apply_to_all:
            pages_to_watermark = range(total_pages)
        else:
            if page_number < 1 or page_number > total_pages:
                doc.close()
                os.remove(pdf_path)
                return jsonify({"status": "error", "message": f"Invalid page number. PDF has {total_pages} pages"}), 400
            pages_to_watermark = [page_number - 1]
        
        # Process each page
        for page_idx in pages_to_watermark:
            page = doc[page_idx]
            page_rect = page.rect
            
            if watermark_type == 'text':
                # Add text watermark
                # Calculate font size based on height
                font_size = int(height * 0.8)  # Adjust multiplier as needed
                
                # Create text insertion point
                point = fitz.Point(x_position, y_position + height)
                
                # Insert text with rotation
                page.insert_text(
                    point,
                    watermark_text,
                    fontsize=font_size,
                    color=(0.5, 0.5, 0.5),  # Gray color for watermark
                    rotate=rotation
                )
                
            elif watermark_type == 'image':
                # Add image watermark
                if watermark_image_data.startswith('data:image'):
                    watermark_image_data = watermark_image_data.split(',')[1]
                
                watermark_bytes = base64.b64decode(watermark_image_data)
                
                # Process image with PIL for better control
                from PIL import Image
                import io
                
                watermark_image = Image.open(io.BytesIO(watermark_bytes))
                
                # Apply opacity if needed
                if opacity < 1.0:
                    # Create a new image with alpha channel
                    watermark_image = watermark_image.convert("RGBA")
                    # Apply opacity
                    alpha = watermark_image.split()[-1]
                    alpha = alpha.point(lambda p: int(p * opacity))
                    watermark_image.putalpha(alpha)
                
                # Convert back to bytes
                img_byte_arr = io.BytesIO()
                watermark_image.save(img_byte_arr, format='PNG')
                img_byte_arr = img_byte_arr.getvalue()
                
                # Create a temporary image file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                temp_img_path = os.path.join(UPLOAD_FOLDER, f'temp_watermark_{page_idx}_{timestamp}.png')
                with open(temp_img_path, 'wb') as f:
                    f.write(img_byte_arr)
                
                # Create image rectangle
                img_rect = fitz.Rect(x_position, y_position, x_position + width, y_position + height)
                
                # Insert the watermark image
                page.insert_image(img_rect, filename=temp_img_path, rotate=rotation)
                
                # Clean up temporary file
                if os.path.exists(temp_img_path):
                    os.remove(temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        watermarked_filename = f"{base_name}_watermarked.pdf"
        watermarked_path = os.path.join(HTML_FOLDER, watermarked_filename)
        
        # Save the modified PDF
        doc.save(watermarked_path)
        doc.close()
        
        # Clean up uploaded PDF
        os.remove(pdf_path)
        
        pages_watermarked = len(pages_to_watermark)
        return jsonify({
            "status": "success",
            "message": f"Watermark added successfully to {pages_watermarked} page(s)",
            "watermarked_filename": watermarked_filename,
            "download_url": f"/download_watermarked/{watermarked_filename}",
            "pages_watermarked": pages_watermarked
        })
        
    except Exception as e:
        print(f"ERROR in add_watermark: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download_watermarked/<watermarked_filename>')
def download_watermarked(watermarked_filename):
    try:
        watermarked_path = os.path.join(HTML_FOLDER, watermarked_filename)
        if not os.path.exists(watermarked_path):
            return "Watermarked PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(watermarked_path, as_attachment=True, download_name=watermarked_filename)
        else:
            return send_file(watermarked_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading watermarked PDF: {str(e)}", 500


@app.route('/download_signed/<signed_filename>')
def download_signed(signed_filename):
    try:
        signed_path = os.path.join(HTML_FOLDER, signed_filename)
        if not os.path.exists(signed_path):
            return "Signed PDF file not found", 404
        
        # Check if it's a download request (has download parameter)
        download = request.args.get('download', 'false').lower() == 'true'
        
        if download:
            return send_file(signed_path, as_attachment=True, download_name=signed_filename)
        else:
            return send_file(signed_path, as_attachment=False)
    
    except Exception as e:
        return f"Error downloading signed PDF: {str(e)}", 500


@app.route("/convert_pdf_to_word", methods=["POST"])
def convert_pdf_to_word():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Convert PDF to HTML first
        doc = fitz.open(filepath)
        html_content = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            html_content += page.get_text("html")
        doc.close()
        
        # Save HTML
        html_filename = f"{file.filename.replace('.pdf', '')}_converted.html"
        html_filepath = os.path.join(HTML_FOLDER, html_filename)
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # For now, return HTML (can be enhanced to convert to DOCX later)
        return jsonify({
            "status": "success",
            "message": "PDF converted to HTML successfully",
            "converted_filename": html_filename,
            "original_format": "PDF",
            "converted_format": "HTML",
            "download_url": f"/download_converted/{html_filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_pdf_to_html", methods=["POST"])
def convert_pdf_to_html():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Convert PDF to HTML
        doc = fitz.open(filepath)
        html_content = ""
        for page_num in range(len(doc)):
            page = doc[page_num]
            html_content += page.get_text("html")
        doc.close()
        
        # Wrap in proper HTML document structure
        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PDF Document</title>
    <style>
        body {{
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
            font-family: Arial, sans-serif;
        }}
        .pdf-container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            border-radius: 4px;
            overflow: hidden;
        }}
        .pdf-page {{
            position: relative;
            background: white;
            transform-origin: top left;
        }}
        .text-span {{
            position: absolute;
            white-space: nowrap;
        }}
        .editable-text {{
            cursor: text;
            border: 1px solid transparent;
            padding: 2px;
            margin: -2px;
        }}
        .editable-text:hover {{
            border: 1px dashed #007bff;
            background: rgba(0, 123, 255, 0.1);
        }}
        .editable-image {{
            position: absolute;
            cursor: pointer;
        }}
        .editable-image:hover {{
            outline: 2px dashed #007bff;
        }}
    </style>
</head>
<body>
    <div class="pdf-container">
        {html_content}
    </div>
</body>
</html>"""
        
        # Save HTML
        html_filename = f"{file.filename.replace('.pdf', '')}_converted.html"
        html_filepath = os.path.join(HTML_FOLDER, html_filename)
        with open(html_filepath, 'w', encoding='utf-8') as f:
            f.write(full_html)
        
        return jsonify({
            "status": "success",
            "message": "PDF converted to HTML successfully",
            "converted_filename": html_filename,
            "original_format": "PDF",
            "converted_format": "HTML",
            "download_url": f"/download_converted/{html_filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_word_to_pdf", methods=["POST"])
def convert_word_to_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # For Word to PDF, we'll return the original file for now
        # This can be enhanced with proper Word to PDF conversion
        return jsonify({
            "status": "success",
            "message": "Word document processed successfully",
            "converted_filename": file.filename,
            "original_format": "Word",
            "converted_format": "PDF",
            "download_url": f"/download_converted/{file.filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_html_to_pdf", methods=["POST"])
def convert_html_to_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # For HTML to PDF, we'll return the original file for now
        # This can be enhanced with proper HTML to PDF conversion
        return jsonify({
            "status": "success",
            "message": "HTML file processed successfully",
            "converted_filename": file.filename,
            "original_format": "HTML",
            "converted_format": "PDF",
            "download_url": f"/download_converted/{file.filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_image_to_pdf", methods=["POST"])
def convert_image_to_pdf():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # For image to PDF, we'll return the original file for now
        # This can be enhanced with proper image to PDF conversion
        return jsonify({
            "status": "success",
            "message": "Image file processed successfully",
            "converted_filename": file.filename,
            "original_format": "Image",
            "converted_format": "PDF",
            "download_url": f"/download_converted/{file.filename}"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/convert_pdf_to_images", methods=["POST"])
def convert_pdf_to_images():
    if "pdf" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files["pdf"]
    if file.filename == "":
        return jsonify({"error": "No selected file"}), 400

    try:
        # Save file
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(filepath)
        
        # Convert PDF to images
        doc = fitz.open(filepath)
        images = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_base64 = base64.b64encode(img_data).decode()
            images.append({
                "page": page_num + 1,
                "data": img_base64
            })
        
        doc.close()
        
        return jsonify({
            "status": "success",
            "message": f"PDF converted to {len(images)} images successfully",
            "converted_filename": f"{file.filename.replace('.pdf', '')}_images.zip",
            "original_format": "PDF",
            "converted_format": "Images",
            "total_images": len(images),
            "image_files": images,
            "download_url": f"/download_images/{file.filename.replace('.pdf', '')}_images.zip"
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/download_converted/<filename>")
def download_converted(filename):
    filepath = os.path.join(HTML_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return "File not found", 404

@app.route("/download_images/<filename>")
def download_images(filename):
    # This would return a zip file of all images
    # For now, return a placeholder
    return "Images download not implemented yet", 501

@app.route("/compress_pdf", methods=["POST"])
def compress_pdf():
    try:
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        compression_level = request.form.get('compression_level', 'medium')
        
        # Save the uploaded file
        filename = file.filename
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        # Open the PDF
        doc = fitz.open(filepath)
        
        # Set compression level
        if compression_level == "low":
            compression_quality = 0.8
        elif compression_level == "medium":
            compression_quality = 0.6
        else:  # high
            compression_quality = 0.4
        
        # Create compressed PDF
        compressed_filename = f"compressed_{filename}"
        compressed_path = os.path.join(EDITED_FOLDER, compressed_filename)
        
        # Save with compression
        doc.save(compressed_path, garbage=4, deflate=True, clean=True)
        doc.close()
        
        # Get file sizes
        original_size = os.path.getsize(filepath)
        compressed_size = os.path.getsize(compressed_path)
        compression_ratio = (1 - compressed_size / original_size) * 100
        
        return jsonify({
            "status": "success",
            "filename": compressed_filename,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "compression_ratio": round(compression_ratio, 2),
            "download_url": f"/download_compressed/{compressed_filename}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_compressed/<filename>")
def download_compressed(filename):
    try:
        compressed_path = os.path.join(EDITED_FOLDER, filename)
        if os.path.exists(compressed_path):
            return send_file(compressed_path, as_attachment=True, download_name=filename)
        else:
            return "Compressed file not found", 404
    except Exception as e:
        return f"Error downloading compressed file: {str(e)}", 500

@app.route("/save_edit_fill_sign/<filename>", methods=["POST"])
def save_edit_fill_sign(filename):
    try:
        print(f"DEBUG: Save edit fill sign endpoint called with filename: {filename}")
        
        if 'pdf' not in request.files:
            return jsonify({"status": "error", "message": "No PDF file provided"}), 400
        
        pdf_file = request.files['pdf']
        if pdf_file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        elements_data = request.form.get('elements', '{}')
        elements = json.loads(elements_data)
        
        print(f"DEBUG: Elements data: {elements}")
        
        text_elements = elements.get('textElements', [])
        signature_elements = elements.get('signatureElements', [])
        image_elements = elements.get('imageElements', [])
        total_pages = elements.get('totalPages', 1)
        
        print(f"DEBUG: Text elements: {len(text_elements)}, Signature elements: {len(signature_elements)}, Image elements: {len(image_elements)}")
        
        if not text_elements and not signature_elements and not image_elements:
            return jsonify({"status": "error", "message": "No elements to save"}), 400
        
        # Save the uploaded PDF
        original_filename = pdf_file.filename
        safe_filename = "".join(c for c in original_filename if c.isalnum() or c in '._-')
        if not safe_filename.endswith('.pdf'):
            safe_filename += '.pdf'
        pdf_path = os.path.join(UPLOAD_FOLDER, safe_filename)
        pdf_file.save(pdf_path)
        
        # Open the PDF
        doc = fitz.open(pdf_path)
        
        # Process text elements
        for text_element in text_elements:
            page_num = text_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                text = text_element.get('text', '')
                x = text_element.get('x', 0)
                y = text_element.get('y', 0)
                font_size = text_element.get('fontSize', 12)
                color = text_element.get('color', '#000000')
                
                # Convert color to RGB
                if color.startswith('#'):
                    color = color[1:]
                    r = int(color[0:2], 16) / 255.0
                    g = int(color[2:4], 16) / 255.0
                    b = int(color[4:6], 16) / 255.0
                    color_rgb = (r, g, b)
                else:
                    color_rgb = (0, 0, 0)
                
                # Insert text at the specified position (coordinates are already in PDF space)
                page.insert_text((x, y), text, fontsize=font_size, color=color_rgb)
        
        # Process signature elements
        for sig_element in signature_elements:
            page_num = sig_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                signature_data = sig_element.get('data', '')
                x = sig_element.get('x', 0)
                y = sig_element.get('y', 0)
                width = sig_element.get('width', 200)
                height = sig_element.get('height', 100)
                
                if signature_data:
                    # Remove data URL prefix if present
                    if signature_data.startswith('data:image'):
                        signature_data = signature_data.split(',')[1]
                    
                    # Decode base64 image
                    signature_bytes = base64.b64decode(signature_data)
                    
                    # Create signature rectangle
                    signature_rect = fitz.Rect(x, y, x + width, y + height)
                    
                    # Create a temporary image file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_signature_{timestamp}.png")
                    with open(temp_img_path, 'wb') as f:
                        f.write(signature_bytes)
                    
                    # Insert signature image
                    page.insert_image(signature_rect, filename=temp_img_path)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
        
        # Process image elements
        for img_element in image_elements:
            page_num = img_element.get('page', 1) - 1
            if 0 <= page_num < len(doc):
                page = doc[page_num]
                image_data = img_element.get('data', '')
                x = img_element.get('x', 0)
                y = img_element.get('y', 0)
                width = img_element.get('width', 200)
                height = img_element.get('height', 150)
                
                if image_data:
                    # Remove data URL prefix if present
                    if image_data.startswith('data:image'):
                        image_data = image_data.split(',')[1]
                    
                    # Decode base64 image
                    image_bytes = base64.b64decode(image_data)
                    
                    # Create image rectangle
                    image_rect = fitz.Rect(x, y, x + width, y + height)
                    
                    # Create a temporary image file
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    temp_img_path = os.path.join(UPLOAD_FOLDER, f"temp_image_{timestamp}.png")
                    with open(temp_img_path, 'wb') as f:
                        f.write(image_bytes)
                    
                    # Insert image
                    page.insert_image(image_rect, filename=temp_img_path)
                    
                    # Clean up temporary file
                    if os.path.exists(temp_img_path):
                        os.remove(temp_img_path)
        
        # Generate output filename
        base_name = os.path.splitext(safe_filename)[0]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        edited_filename = f"{base_name}_filled_signed_{timestamp}.pdf"
        edited_path = os.path.join(HTML_FOLDER, edited_filename)
        
        # Save the modified PDF
        doc.save(edited_path)
        doc.close()
        
        # Clean up uploaded PDF
        os.remove(pdf_path)
        
        return jsonify({
            "status": "success",
            "message": f"PDF updated successfully with {len(text_elements)} text elements, {len(signature_elements)} signatures, and {len(image_elements)} images",
            "filename": edited_filename,
            "download_url": f"/download_edited/{edited_filename}",
            "text_elements": len(text_elements),
            "signature_elements": len(signature_elements),
            "image_elements": len(image_elements)
        })
        
    except Exception as e:
        print(f"ERROR in save_edit_fill_sign: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_edited/<filename>")
def download_edited(filename):
    try:
        edited_path = os.path.join(HTML_FOLDER, filename)
        if not os.path.exists(edited_path):
            return "Edited PDF file not found", 404
        
        return send_file(edited_path, as_attachment=True, download_name=filename)
    
    except Exception as e:
        return f"Error downloading edited PDF: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)
