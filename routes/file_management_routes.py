from flask import Blueprint, jsonify, request, render_template_string
from utils.file_manager import cleanup_old_files, create_file_summary, get_file_count_by_date
import logging

file_management_bp = Blueprint('file_management', __name__)

@file_management_bp.route('/file-summary')
def file_summary():
    """파일 현황 요약을 보여줍니다."""
    try:
        summary = create_file_summary()
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>파일 현황 요약</title>
            <meta charset="utf-8">
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
                .summary { white-space: pre-line; font-family: monospace; line-height: 1.6; }
                .actions { margin-top: 20px; text-align: center; }
                .btn { padding: 10px 20px; margin: 5px; border: none; border-radius: 5px; cursor: pointer; text-decoration: none; display: inline-block; }
                .btn-primary { background-color: #007bff; color: white; }
                .btn-danger { background-color: #dc3545; color: white; }
                .btn:hover { opacity: 0.8; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📁 파일 현황 요약</h1>
                <div class="summary">{{ summary }}</div>
                <div class="actions">
                    <a href="/cleanup-files" class="btn btn-danger" onclick="return confirm('30일 이전 파일들을 삭제하시겠습니까?')">🧹 오래된 파일 정리</a>
                    <a href="/file-summary" class="btn btn-primary">🔄 새로고침</a>
                    <a href="/" class="btn btn-primary">🏠 홈으로</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return render_template_string(html_template, summary=summary)
        
    except Exception as e:
        logging.error(f"Error creating file summary: {e}")
        return jsonify({"error": str(e)}), 500

@file_management_bp.route('/cleanup-files', methods=['POST', 'GET'])
def cleanup_files():
    """오래된 파일들을 정리합니다."""
    try:
        cleanup_old_files()
        return jsonify({"message": "파일 정리가 완료되었습니다.", "success": True}), 200
    except Exception as e:
        logging.error(f"Error during file cleanup: {e}")
        return jsonify({"error": str(e)}), 500

@file_management_bp.route('/api/file-stats')
def file_stats():
    """파일 통계를 JSON으로 반환합니다."""
    try:
        stats = get_file_count_by_date()
        return jsonify(stats), 200
    except Exception as e:
        logging.error(f"Error getting file stats: {e}")
        return jsonify({"error": str(e)}), 500 