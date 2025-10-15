from flask import Flask, render_template, request, send_file, redirect, url_for, jsonify, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
import os
import fitz
import base64
from io import BytesIO
import json
from datetime import datetime, timedelta
import glob
import uuid
import time
import subprocess
import shutil
import threading

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

@app.route("/health")
def health():
    upload_folder_exists = os.path.exists(UPLOAD_FOLDER)
    upload_folder_contents = os.listdir(UPLOAD_FOLDER) if upload_folder_exists else []
    return jsonify({
        "status": "ok", 
        "message": "Backend is running",
        "upload_folder": UPLOAD_FOLDER,
        "upload_folder_exists": upload_folder_exists,
        "upload_folder_contents": upload_folder_contents
    })
UPLOAD_FOLDER = "uploads"
EDITED_FOLDER = "edited"
HTML_FOLDER = "saved_html"
VIDEO_FOLDER = "converted_videos"
AUDIO_FOLDER = "converted_audio"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EDITED_FOLDER, exist_ok=True)
os.makedirs(HTML_FOLDER, exist_ok=True)
os.makedirs(VIDEO_FOLDER, exist_ok=True)
os.makedirs(AUDIO_FOLDER, exist_ok=True)

# Global progress tracking
conversion_progress = {}

# File cleanup system
def cleanup_old_files():
    """Clean up files older than 1 hour from all output directories"""
    try:
        current_time = time.time()
        cleanup_directories = [UPLOAD_FOLDER, EDITED_FOLDER, HTML_FOLDER, VIDEO_FOLDER, AUDIO_FOLDER]
        
        for directory in cleanup_directories:
            if os.path.exists(directory):
                for filename in os.listdir(directory):
                    file_path = os.path.join(directory, filename)
                    if os.path.isfile(file_path):
                        file_age = current_time - os.path.getmtime(file_path)
                        # Delete files older than 1 hour
                        if file_age > 3600:  # 1 hour in seconds
                            try:
                                os.remove(file_path)
                                print(f"Cleaned up old file: {file_path}")
                            except Exception as e:
                                print(f"Error deleting file {file_path}: {e}")
    except Exception as e:
        print(f"Error in cleanup_old_files: {e}")

def cleanup_specific_file(file_path):
    """Clean up a specific file after download completion"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up file after download: {file_path}")
            return True
    except Exception as e:
        print(f"Error deleting file {file_path}: {e}")
    return False

def cleanup_session_files(session_id):
    """Clean up all files for a specific session"""
    try:
        cleanup_directories = [UPLOAD_FOLDER, EDITED_FOLDER, HTML_FOLDER, VIDEO_FOLDER, AUDIO_FOLDER]
        
        for directory in cleanup_directories:
            if os.path.exists(directory):
                pattern = os.path.join(directory, f"*{session_id}*")
                files_to_delete = glob.glob(pattern)
                for file_path in files_to_delete:
                    try:
                        os.remove(file_path)
                        print(f"Cleaned up session file: {file_path}")
                    except Exception as e:
                        print(f"Error deleting session file {file_path}: {e}")
    except Exception as e:
        print(f"Error in cleanup_session_files: {e}")

# Start background cleanup thread
def background_cleanup():
    """Background thread that runs cleanup every 30 minutes"""
    while True:
        time.sleep(1800)  # 30 minutes
        cleanup_old_files()

# Start the background cleanup thread
cleanup_thread = threading.Thread(target=background_cleanup, daemon=True)
cleanup_thread.start()

# Add cleanup endpoints
@app.route('/cleanup-file', methods=['POST'])
def cleanup_file_endpoint():
    """Clean up a specific file after download completion"""
    try:
        data = request.get_json()
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'success': False, 'error': 'No file path provided'}), 400
        
        success = cleanup_specific_file(file_path)
        
        if success:
            return jsonify({'success': True, 'message': 'File cleaned up successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to clean up file'}), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cleanup-session', methods=['POST'])
def cleanup_session_endpoint():
    """Clean up all files for a specific session"""
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        
        if not session_id:
            return jsonify({'success': False, 'error': 'No session ID provided'}), 400
        
        cleanup_session_files(session_id)
        return jsonify({'success': True, 'message': 'Session files cleaned up successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/cleanup-all', methods=['POST'])
def cleanup_all_endpoint():
    """Manually trigger cleanup of all old files"""
    try:
        cleanup_old_files()
        return jsonify({'success': True, 'message': 'All old files cleaned up successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        print(f"DEBUG: Upload endpoint called")
        print(f"DEBUG: Upload folder: {UPLOAD_FOLDER}")
        print(f"DEBUG: Upload folder exists: {os.path.exists(UPLOAD_FOLDER)}")
        print(f"DEBUG: Upload folder contents before: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
        
        if "pdf" not in request.files:
            print("ERROR: No pdf file in request")
            return "No file uploaded", 400
        file = request.files["pdf"]
        if file.filename == "":
            print("ERROR: No filename provided")
            return "No selected file", 400

        print(f"DEBUG: Uploading file: {file.filename}")
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        print(f"DEBUG: Saving to: {filepath}")
        
        try:
            file.save(filepath)
            print(f"DEBUG: File saved successfully")
            print(f"DEBUG: File exists after save: {os.path.exists(filepath)}")
            print(f"DEBUG: Upload folder contents after: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
        except Exception as e:
            print(f"ERROR: Failed to save file: {str(e)}")
            return f"Failed to save file: {str(e)}", 500
            
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
    print(f"DEBUG: pdf_info called with filename: {filename}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: Looking for file at: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    print(f"DEBUG: Upload folder contents: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
    try:
        doc = fitz.open(filepath)
        page_count = len(doc)
        doc.close()
        print(f"DEBUG: Successfully got page count: {page_count}")
        return jsonify({
            "filename": filename,
            "page_count": page_count
        })
    except Exception as e:
        print(f"ERROR: Exception in get_pdf_info: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/pdf_thumbnail/<filename>/<int:page_num>")
def get_pdf_thumbnail(filename, page_num):
    """Get thumbnail image for a specific page"""
    print(f"DEBUG: thumbnail called with filename: {filename}, page: {page_num}")
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"DEBUG: File path: {filepath}")
    print(f"DEBUG: File exists: {os.path.exists(filepath)}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
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
    print(f"DEBUG: Upload folder contents: {os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else 'Folder does not exist'}")
    
    if not os.path.exists(filepath):
        print(f"ERROR: File not found: {filepath}")
        return jsonify({"error": f"File not found: {filename}"}), 404
    
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

@app.route("/convert-video", methods=["POST"])
def convert_video():
    try:
        print(f"DEBUG: Video conversion endpoint called")
        print(f"DEBUG: Request files: {list(request.files.keys())}")
        print(f"DEBUG: Request form: {list(request.form.keys())}")
        
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No video file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Get conversion parameters
        output_format = request.form.get('outputFormat', 'mp4')
        quality = int(request.form.get('quality', 80))
        compression = request.form.get('compression', 'medium')
        
        print(f"DEBUG: Converting to {output_format}, quality: {quality}%, compression: {compression}")
        
        # Save the uploaded file with unique filename to prevent conflicts
        import uuid
        original_filename = file.filename
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{unique_id}_{original_filename}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        print(f"DEBUG: Video file saved: {filepath}")
        
        # Generate output filename
        base_name = os.path.splitext(filename)[0]
        converted_filename = f"{base_name}_converted.{output_format}"
        converted_path = os.path.join(VIDEO_FOLDER, converted_filename)
        
        # Get original file size
        original_size = os.path.getsize(filepath)
        print(f"DEBUG: Original file size: {original_size} bytes ({original_size / 1024 / 1024:.2f} MB)")
        
        # REAL video compression using FFmpeg
        import subprocess
        import shutil
        
        # Map quality to CRF (Constant Rate Factor) for H.264
        quality_map = {
            95: 18,  # Ultra High
            85: 23,  # High
            75: 28,  # Medium
            60: 32,  # Low
            40: 36   # Very Low
        }
        
        # Map compression to preset
        preset_map = {
            'none': 'ultrafast',
            'light': 'fast',
            'medium': 'medium',
            'heavy': 'slow',
            'web': 'veryslow'
        }
        
        crf = quality_map.get(quality, 28)
        preset = preset_map.get(compression, 'medium')
        
        print(f"DEBUG: Starting FFmpeg compression with CRF={crf}, preset={preset}")
        
        # Initialize progress tracking using unique filename
        conversion_progress[filename] = {
            "status": "processing",
            "progress": 5,
            "message": "Starting video compression..."
        }
        print(f"DEBUG: Initialized progress tracking for {filename}")
        
        # No background progress thread - only use real-time FFmpeg progress
        
        # FFmpeg command for faster video compression with aggressive speed optimizations
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', filepath,
            '-c:v', 'libx264',
            '-crf', str(crf),
            '-preset', 'ultrafast',  # Fastest preset for Railway
            '-c:a', 'aac',
            '-b:a', '96k',  # Lower bitrate for faster processing
            '-movflags', '+faststart',
            '-threads', '2',  # Limit threads to prevent resource exhaustion
            '-x264opts', 'no-cabac:ref=1:subme=1:me=dia:analyse=none:trellis=0:no-weightb:aq-mode=0:8x8dct=0:weightp=0',
            '-tune', 'fastdecode',  # Optimize for fast decoding
            '-y',  # Overwrite output file
            converted_path
        ]
        
        try:
            print(f"DEBUG: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
            
            # Run FFmpeg with real-time output for progress tracking
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                universal_newlines=True,
                bufsize=1
            )
            
            # Real-time progress tracking from FFmpeg output
            start_time = time.time()
            last_update = start_time
            total_duration = None
            current_time_pos = 0
            
            # First, get video duration
            try:
                duration_cmd = [
                    'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1', filepath
                ]
                duration_result = subprocess.run(duration_cmd, capture_output=True, text=True, timeout=10)
                if duration_result.returncode == 0:
                    total_duration = float(duration_result.stdout.strip())
                    print(f"DEBUG: Video duration: {total_duration:.2f} seconds")
            except:
                print("DEBUG: Could not get video duration, using fallback progress")
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    line = output.strip()
                    current_time = time.time()
                    elapsed_time = current_time - start_time
                    
                    # Parse FFmpeg output for real progress
                    if 'time=' in line:
                        try:
                            time_part = [part for part in line.split() if part.startswith('time=')][0]
                            time_str = time_part.split('=')[1]
                            # Parse time format (HH:MM:SS.mmm)
                            time_parts = time_str.split(':')
                            if len(time_parts) == 3:
                                hours, minutes, seconds = time_parts
                                current_time_pos = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
                                
                                # Calculate real progress percentage
                                if total_duration and total_duration > 0:
                                    progress = min(95, int((current_time_pos / total_duration) * 100))
                                    conversion_progress[filename]["message"] = f"Processing video... {time_str} ({progress}%)"
                                    conversion_progress[filename]["progress"] = progress
                                    print(f"DEBUG: Real progress: {progress}% - {time_str} / {total_duration:.2f}s")
                                else:
                                    # Fallback to time-based if no duration
                                    progress = min(95, 5 + int(elapsed_time * 3.2))
                                    conversion_progress[filename]["message"] = f"Processing video... {time_str} ({elapsed_time:.0f}s)"
                                    conversion_progress[filename]["progress"] = progress
                                    print(f"DEBUG: Fallback progress: {progress}% - {elapsed_time:.0f}s")
                        except Exception as e:
                            print(f"DEBUG: Error parsing time: {e}")
                    
                    elif 'frame=' in line:
                        try:
                            frame_part = [part for part in line.split() if part.startswith('frame=')][0]
                            frame_num = int(frame_part.split('=')[1])
                            conversion_progress[filename]["message"] = f"Processing frame {frame_num}... ({elapsed_time:.0f}s)"
                        except:
                            pass
                    
                    # Update every 2 seconds as fallback
                    elif current_time - last_update >= 2.0:
                        if not total_duration:
                            progress = min(95, 5 + int(elapsed_time * 3.2))
                            conversion_progress[filename]["message"] = f"Processing video... {elapsed_time:.0f}s elapsed"
                            conversion_progress[filename]["progress"] = progress
                            print(f"DEBUG: Fallback progress update: {progress}% - {elapsed_time:.0f}s elapsed")
                        last_update = current_time
            
            # Set progress to 99% before waiting for completion
            conversion_progress[filename]["progress"] = 99
            conversion_progress[filename]["message"] = "Finalizing conversion..."
            print(f"DEBUG: Progress set to 99% - finalizing conversion")
            
            # Wait for process to complete with timeout
            try:
                return_code = process.wait(timeout=120)  # 2 minute timeout for Railway
            except subprocess.TimeoutExpired:
                print(f"DEBUG: FFmpeg process timed out after 2 minutes")
                process.kill()
                return_code = -1
            
            if return_code == 0:
                print(f"DEBUG: FFmpeg compression completed successfully")
                # Stop progress thread and set final progress
                conversion_progress[filename] = {
                    "status": "completed",
                    "progress": 100,
                    "message": "Video compression completed successfully!"
                }
                print(f"DEBUG: Progress set to 100% - conversion completed")
            else:
                print(f"DEBUG: FFmpeg failed with return code: {return_code}")
                # Fallback to copying if FFmpeg fails
                shutil.copy2(filepath, converted_path)
                print(f"DEBUG: Fallback: copied original file")
                conversion_progress[filename] = {
                    "status": "completed",
                    "progress": 100,
                    "message": "Video processing completed (fallback mode)"
                }
                print(f"DEBUG: Progress set to 100% - fallback completed")
                
        except subprocess.TimeoutExpired:
            print(f"DEBUG: FFmpeg timeout after 2 minutes, falling back to copy")
            shutil.copy2(filepath, converted_path)
        except FileNotFoundError:
            print(f"DEBUG: FFmpeg not found in PATH, falling back to copy")
            print(f"DEBUG: Please install FFmpeg: https://ffmpeg.org/download.html")
            shutil.copy2(filepath, converted_path)
        except Exception as e:
            print(f"DEBUG: FFmpeg error: {e}, falling back to copy")
            shutil.copy2(filepath, converted_path)
        
        print(f"DEBUG: Video saved to: {converted_path}")
        
        # Get converted file size
        converted_size = os.path.getsize(converted_path)
        print(f"DEBUG: Converted file size: {converted_size} bytes ({converted_size / 1024 / 1024:.2f} MB)")
        if converted_size != original_size:
            reduction = ((original_size - converted_size) / original_size * 100)
            print(f"DEBUG: Size reduction: {reduction:.1f}%")
        else:
            print(f"DEBUG: No size reduction (FFmpeg may not be available)")
        
        # Clean up original file (with error handling)
        try:
            os.remove(filepath)
            print(f"DEBUG: Original file cleaned up: {filepath}")
        except Exception as e:
            print(f"DEBUG: Could not remove original file (may be in use): {e}")
            # Don't fail the conversion if we can't delete the original file
        
        return jsonify({
            "status": "success",
            "message": f"Video converted to {output_format.upper()} successfully",
            "converted_filename": converted_filename,
            "unique_filename": filename,  # Add the unique filename for progress tracking
            "original_format": filename.split('.')[-1].upper(),
            "converted_format": output_format.upper(),
            "quality": quality,
            "compression": compression,
            "original_size": original_size,
            "converted_size": converted_size,
            "download_url": f"/download_converted_video/{converted_filename}"
        })
        
    except Exception as e:
        print(f"ERROR in convert_video: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/download_converted_video/<path:filename>")
def download_converted_video(filename):
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        # Use absolute path to avoid any path resolution issues
        file_path = os.path.abspath(os.path.join(VIDEO_FOLDER, decoded_filename))
        print(f"DEBUG: Looking for file: {file_path}")
        print(f"DEBUG: File exists: {os.path.exists(file_path)}")
        
        if not os.path.exists(file_path):
            print(f"DEBUG: File not found: {file_path}")
            # List files in the directory to debug
            try:
                video_dir = os.path.abspath(VIDEO_FOLDER)
                files_in_dir = os.listdir(video_dir)
                print(f"DEBUG: Files in {video_dir}: {files_in_dir}")
                print(f"DEBUG: Looking for: {decoded_filename}")
            except Exception as e:
                print(f"DEBUG: Error listing directory: {e}")
            return "Converted video file not found", 404
        
        print(f"DEBUG: File found, sending: {file_path}")
        return send_file(file_path, as_attachment=True, download_name=decoded_filename)
    
    except Exception as e:
        print(f"ERROR in download_converted_video: {str(e)}")
        return f"Error downloading converted video: {str(e)}", 500

@app.route("/conversion_progress/<filename>")
def get_conversion_progress(filename):
    """Get the progress of a video conversion"""
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        # Try to find progress by exact match first
        progress = conversion_progress.get(decoded_filename)
        
        # If not found, try to find by partial match (for unique filenames)
        if not progress:
            for key, value in conversion_progress.items():
                if decoded_filename in key or key in decoded_filename:
                    progress = value
                    print(f"DEBUG: Found progress by partial match: {key} -> {decoded_filename}")
                    break
        
        if not progress:
            progress = {
                "status": "not_found",
                "progress": 0,
                "message": "Conversion not found"
            }
        
        print(f"DEBUG: Progress request for {decoded_filename}: {progress}")
        return jsonify(progress)
    except Exception as e:
        print(f"DEBUG: Progress error: {e}")
        return jsonify({"error": str(e)}), 500

# Audio Conversion Functions
def allowed_audio_file(filename):
    """Check if file extension is allowed for audio"""
    ALLOWED_AUDIO_EXTENSIONS = {'mp3', 'wav', 'flac', 'aac', 'ogg', 'm4a', 'wma', 'aiff', 'au', 'opus'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_AUDIO_EXTENSIONS

def convert_audio_file(input_path, output_path, output_format, bitrate=192, sample_rate=44100, channels="stereo", quality=80):
    """Convert audio using FFmpeg"""
    try:
        print(f"DEBUG: Starting audio conversion from {input_path} to {output_path}")
        print(f"DEBUG: Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Build FFmpeg command based on output format
        cmd = ['ffmpeg', '-i', input_path]
        
        # Audio codec selection
        if output_format == 'mp3':
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'aac':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'flac':
            cmd.extend(['-acodec', 'flac'])
        elif output_format == 'ogg':
            cmd.extend(['-acodec', 'libvorbis'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'opus':
            cmd.extend(['-acodec', 'libopus'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wav':
            cmd.extend(['-acodec', 'pcm_s16le'])
        elif output_format == 'aiff':
            cmd.extend(['-acodec', 'pcm_s16be'])
        elif output_format == 'm4a':
            cmd.extend(['-acodec', 'aac'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        elif output_format == 'wma':
            cmd.extend(['-acodec', 'wmav2'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        else:
            # Default to libmp3lame for unknown formats
            cmd.extend(['-acodec', 'libmp3lame'])
            if bitrate > 0:
                cmd.extend(['-ab', f'{bitrate}k'])
        
        # Sample rate
        cmd.extend(['-ar', str(sample_rate)])
        
        # Channel configuration
        if channels == 'mono':
            cmd.extend(['-ac', '1'])
        elif channels == 'stereo':
            cmd.extend(['-ac', '2'])
        elif channels == 'surround':
            cmd.extend(['-ac', '6'])  # 5.1 surround
        # For 'original', don't specify channels
        
        # Quality settings for lossy formats
        if output_format in ['mp3', 'aac', 'ogg', 'opus', 'm4a', 'wma']:
            if quality < 50:
                cmd.extend(['-q:a', '9'])  # Low quality
            elif quality < 70:
                cmd.extend(['-q:a', '6'])  # Medium quality
            elif quality < 90:
                cmd.extend(['-q:a', '3'])  # High quality
            else:
                cmd.extend(['-q:a', '0'])  # Maximum quality
        
        # Overwrite output file
        cmd.extend(['-y', output_path])
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(cmd)}")
        
        # Run FFmpeg command
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print(f"DEBUG: FFmpeg return code: {result.returncode}")
        print(f"DEBUG: FFmpeg stdout: {result.stdout}")
        print(f"DEBUG: FFmpeg stderr: {result.stderr}")
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg error: {result.stderr}")
        
        # Check if output file was created and has content
        if not os.path.exists(output_path):
            raise Exception("Output file was not created")
        
        output_size = os.path.getsize(output_path)
        print(f"DEBUG: Output file size: {output_size} bytes")
        
        if output_size == 0:
            raise Exception("Output file is empty")
        
        return True
        
    except Exception as e:
        print(f"Audio conversion error: {str(e)}")
        return False

@app.route('/convert-image', methods=['POST'])
def convert_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Get conversion settings
    output_format = request.form.get('outputFormat', 'jpg')
    quality = int(request.form.get('quality', 85))
    resize = request.form.get('resize', 'false').lower() == 'true'
    width = int(request.form.get('width', 1920))
    height = int(request.form.get('height', 1080))
    maintain_aspect_ratio = request.form.get('maintainAspectRatio', 'true').lower() == 'true'
    compression = request.form.get('compression', 'medium')
    
    try:
        # Create uploads directory if it doesn't exist
        uploads_dir = 'converted_images'
        uploads_dir = os.path.abspath(uploads_dir)  # Get absolute path
        os.makedirs(uploads_dir, exist_ok=True)
        print(f"DEBUG: Created/verified directory: {uploads_dir}")
        
        # Generate unique filename
        unique_id = str(uuid.uuid4())[:8]
        original_filename = secure_filename(file.filename)
        name, ext = os.path.splitext(original_filename)
        filename = f"{unique_id}_{name}_converted.{output_format}"
        filepath = os.path.join(uploads_dir, filename)
        
        print(f"DEBUG: Target filepath: {filepath}")
        print(f"DEBUG: Directory exists: {os.path.exists(uploads_dir)}")
        
        # Save uploaded file
        temp_path = os.path.join(uploads_dir, f"temp_{unique_id}_{original_filename}")
        print(f"DEBUG: Temp filepath: {temp_path}")
        file.save(temp_path)
        
        # Get original file size
        original_size = os.path.getsize(temp_path)
        
        # Build FFmpeg command for image conversion
        ffmpeg_cmd = ['ffmpeg', '-i', temp_path]
        
        # Add resize parameters if requested
        if resize:
            if maintain_aspect_ratio:
                ffmpeg_cmd.extend(['-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease'])
            else:
                ffmpeg_cmd.extend(['-vf', f'scale={width}:{height}'])
        
        # Add format-specific parameters
        if output_format in ['jpg', 'jpeg']:
            ffmpeg_cmd.extend(['-q:v', str(100 - quality)])  # FFmpeg uses inverse quality
        elif output_format == 'png':
            ffmpeg_cmd.extend(['-compression_level', str(9 - (quality // 10))])
        elif output_format == 'webp':
            ffmpeg_cmd.extend(['-quality', str(quality)])
        elif output_format == 'bmp':
            ffmpeg_cmd.extend(['-pix_fmt', 'bgr24'])
        elif output_format == 'tiff':
            ffmpeg_cmd.extend(['-compression', 'lzw'])
        elif output_format == 'gif':
            ffmpeg_cmd.extend(['-pix_fmt', 'pal8'])
        
        ffmpeg_cmd.extend(['-update', '1', '-y', filepath])  # Overwrite output file, single image
        
        print(f"DEBUG: Running FFmpeg command: {' '.join(ffmpeg_cmd)}")
        
        try:
            # Run FFmpeg
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
            print(f"DEBUG: FFmpeg return code: {result.returncode}")
            print(f"DEBUG: FFmpeg stdout: {result.stdout}")
            print(f"DEBUG: FFmpeg stderr: {result.stderr}")
            
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            if result.returncode == 0:
                # Check if output file was created
                if os.path.exists(filepath):
                    # Get converted file size
                    converted_size = os.path.getsize(filepath)
                    compression_ratio = ((original_size - converted_size) / original_size) * 100
                    
                    # Create download URL
                    download_url = f"http://localhost:5000/download/{filename}"
                    
                    return jsonify({
                        'success': True,
                        'downloadUrl': download_url,
                        'originalSize': original_size,
                        'convertedSize': converted_size,
                        'compressionRatio': compression_ratio,
                        'message': 'Image converted successfully'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'error': 'FFmpeg completed but no output file was created'
                    }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': f'FFmpeg error: {result.stderr}'
                }), 500
        except subprocess.TimeoutExpired:
            return jsonify({
                'success': False,
                'error': 'FFmpeg process timed out'
            }), 500
        except Exception as e:
            print(f"DEBUG: Exception in FFmpeg execution: {str(e)}")
            return jsonify({
                'success': False,
                'error': f'FFmpeg execution error: {str(e)}'
            }), 500
            
    except subprocess.TimeoutExpired:
        return jsonify({
            'success': False,
            'error': 'Conversion timed out'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Conversion failed: {str(e)}'
        }), 500

@app.route('/generate-qr', methods=['POST'])
def generate_qr():
    """Generate QR code from provided data"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        qr_type = data.get('type', 'text')
        qr_data = data.get('data', {})
        
        # Import qrcode here to avoid import errors if not installed
        try:
            import qrcode
            from io import BytesIO
            import base64
        except ImportError as e:
            print(f"DEBUG: Import error: {e}")
            return jsonify({
                'success': False,
                'error': f'QR code library not installed: {str(e)}'
            }), 500
        
        # Generate QR code content based on type
        qr_content = ""
        
        if qr_type == 'url':
            qr_content = qr_data.get('url', '')
        elif qr_type == 'text':
            qr_content = qr_data.get('text', '')
        elif qr_type == 'wifi':
            ssid = qr_data.get('ssid', '')
            password = qr_data.get('password', '')
            encryption = qr_data.get('encryption', 'WPA')
            hidden = qr_data.get('hidden', False)
            qr_content = f"WIFI:T:{encryption};S:{ssid};P:{password};H:{str(hidden).lower()};;"
        elif qr_type == 'email':
            email = qr_data.get('email', '')
            subject = qr_data.get('subject', '')
            body = qr_data.get('body', '')
            qr_content = f"mailto:{email}?subject={subject}&body={body}"
        elif qr_type == 'sms':
            phone = qr_data.get('phoneNumber', '')
            message = qr_data.get('message', '')
            qr_content = f"sms:{phone}:{message}"
        elif qr_type == 'phone':
            phone = qr_data.get('phone', '')
            qr_content = f"tel:{phone}"
        elif qr_type == 'vcard':
            name = qr_data.get('name', '')
            organization = qr_data.get('organization', '')
            title = qr_data.get('vcardTitle', '')
            phone = qr_data.get('vcardPhone', '')
            email = qr_data.get('email', '')
            website = qr_data.get('website', '')
            address = qr_data.get('address', '')
            
            vcard = f"BEGIN:VCARD\nVERSION:3.0\n"
            if name: vcard += f"FN:{name}\n"
            if organization: vcard += f"ORG:{organization}\n"
            if title: vcard += f"TITLE:{title}\n"
            if phone: vcard += f"TEL:{phone}\n"
            if email: vcard += f"EMAIL:{email}\n"
            if website: vcard += f"URL:{website}\n"
            if address: vcard += f"ADR:{address}\n"
            vcard += "END:VCARD"
            qr_content = vcard
        elif qr_type == 'location':
            latitude = qr_data.get('latitude', 0)
            longitude = qr_data.get('longitude', 0)
            qr_content = f"geo:{latitude},{longitude}"
        elif qr_type == 'calendar':
            title = qr_data.get('calendarTitle', '')
            description = qr_data.get('description', '')
            start_date = qr_data.get('startDate', '')
            end_date = qr_data.get('endDate', '')
            location = qr_data.get('location', '')
            
            # Create a simple calendar event format
            qr_content = f"BEGIN:VEVENT\nSUMMARY:{title}\nDESCRIPTION:{description}\nDTSTART:{start_date}\nDTEND:{end_date}\nLOCATION:{location}\nEND:VEVENT"
        else:
            qr_content = str(qr_data.get('text', ''))
        
        if not qr_content:
            return jsonify({
                'success': False,
                'error': 'No content to generate QR code for'
            }), 400
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_content)
        qr.make(fit=True)
        
        # Create image
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': f"data:image/png;base64,{img_str}",
            'content': qr_content,
            'type': qr_type
        })
        
    except Exception as e:
        print(f"ERROR: QR generation failed: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'QR generation failed: {str(e)}'
        }), 500

@app.route('/download/<filename>')
def download_file(filename):
    """Download converted files"""
    try:
        # Check in converted_images directory first
        converted_images_path = os.path.abspath(os.path.join('converted_images', filename))
        print(f"DEBUG: Looking for file at: {converted_images_path}")
        print(f"DEBUG: File exists: {os.path.exists(converted_images_path)}")
        
        if os.path.exists(converted_images_path):
            return send_file(converted_images_path, as_attachment=True)
        
        # Check in other directories if needed
        converted_videos_path = os.path.abspath(os.path.join('converted_videos', filename))
        if os.path.exists(converted_videos_path):
            return send_file(converted_videos_path, as_attachment=True)
            
        return jsonify({'error': f'File not found: {filename}'}), 404
    except Exception as e:
        print(f"DEBUG: Download error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/convert-audio', methods=['POST'])
def convert_audio():
    """Convert audio to different format"""
    try:
        # Check if file is provided
        if 'file' not in request.files:
            return jsonify({"status": "error", "message": "No file provided"}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({"status": "error", "message": "No file selected"}), 400
        
        # Check file type
        if not allowed_audio_file(file.filename):
            return jsonify({"status": "error", "message": "Invalid file type"}), 400
        
        # Get parameters
        output_format = request.form.get('outputFormat', 'mp3')
        bitrate = int(request.form.get('bitrate', 192))
        sample_rate = int(request.form.get('sampleRate', 44100))
        channels = request.form.get('channels', 'stereo')
        quality = int(request.form.get('quality', 80))
        
        print(f"DEBUG: Received request - Format: {output_format}, Bitrate: {bitrate}, Sample Rate: {sample_rate}, Channels: {channels}, Quality: {quality}")
        
        # Generate unique filenames
        unique_id = str(uuid.uuid4())[:8]
        original_filename = file.filename
        base_name = os.path.splitext(original_filename)[0]
        
        # Input file path
        input_filename = f"{unique_id}_{original_filename}"
        input_path = os.path.join(AUDIO_FOLDER, input_filename)
        
        # Output file path
        output_filename = f"{unique_id}_{base_name}_converted.{output_format}"
        output_path = os.path.join(AUDIO_FOLDER, output_filename)
        
        print(f"DEBUG: Input path: {input_path}")
        print(f"DEBUG: Output path: {output_path}")
        
        # Save uploaded file
        file.save(input_path)
        print(f"DEBUG: File saved successfully")
        
        # Get original file size
        original_size = os.path.getsize(input_path)
        print(f"DEBUG: Original file size: {original_size} bytes")
        
        # Convert audio
        print(f"DEBUG: Starting conversion...")
        success = convert_audio_file(input_path, output_path, output_format, bitrate, sample_rate, channels, quality)
        print(f"DEBUG: Conversion result: {success}")
        
        if not success:
            # Clean up input file
            if os.path.exists(input_path):
                os.remove(input_path)
            return jsonify({"status": "error", "message": "Conversion failed"}), 500
        
        # Get converted file size
        converted_size = os.path.getsize(output_path)
        
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)
        
        # Return success response
        return jsonify({
            "status": "success",
            "message": f"Audio conversion completed successfully",
            "original_filename": original_filename,
            "converted_filename": output_filename,
            "original_size": original_size,
            "converted_size": converted_size,
            "download_url": f"/download_converted_audio/{output_filename}",
            "output_format": output_format,
            "bitrate": bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
            "quality": quality
        })
        
    except Exception as e:
        print(f"Error in convert_audio: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/download_converted_audio/<filename>')
def download_converted_audio(filename):
    """Download converted audio file"""
    try:
        # Decode URL-encoded filename
        from urllib.parse import unquote
        decoded_filename = unquote(filename)
        
        file_path = os.path.abspath(os.path.join(AUDIO_FOLDER, decoded_filename))
        print(f"DEBUG: Looking for audio file: {file_path}")
        
        if not os.path.exists(file_path):
            print(f"DEBUG: Audio file not found: {file_path}")
            return "Converted audio file not found", 404
        
        print(f"DEBUG: Audio file found, sending: {file_path}")
        return send_file(file_path, as_attachment=True, download_name=decoded_filename)
        
    except Exception as e:
        print(f"ERROR in download_converted_audio: {str(e)}")
        return f"Error downloading converted audio: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
