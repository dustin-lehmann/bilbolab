"""
Public API routes - same response format as the original server.py.
"""

import os
from flask import Blueprint, jsonify, request, send_from_directory, send_file, redirect

public_bp = Blueprint('public', __name__)

# ContentStore and VisitorLog instances set by app factory
store = None
visitor_log = None


def init_public_routes(content_store, vlog=None):
    global store, visitor_log
    store = content_store
    visitor_log = vlog


@public_bp.route('/api/settings')
def get_settings():
    return jsonify(store.get_public_settings())


@public_bp.route('/api/experiments')
def get_experiments():
    return jsonify(store.get_all_content(include_drafts=False))


@public_bp.route('/api/experiments/<experiment_id>')
def get_experiment(experiment_id):
    item, folder_path = store.get_item(experiment_id, include_drafts=False)
    if item:
        result = dict(item)
        if folder_path:
            result['folderPath'] = folder_path
        return jsonify(result)
    return jsonify({'error': 'Experiment not found'}), 404


@public_bp.route('/api/folders/<folder_id>')
def get_folder(folder_id):
    folder = store.get_folder(folder_id, include_drafts=False)
    if folder:
        return jsonify(folder)
    return jsonify({'error': 'Folder not found'}), 404


@public_bp.route('/api/search')
def search():
    query = request.args.get('q', '')
    results = store.search(query, include_drafts=False)
    return jsonify({'results': results})


@public_bp.route('/api/videos')
def list_videos():
    """List all video files across all items."""
    videos = []
    for path in store.content_dir.rglob('files/*.mp4'):
        videos.append(path.name)
    for path in store.content_dir.rglob('files/*.webm'):
        videos.append(path.name)
    return jsonify({'videos': videos})


# --- File serving ---

@public_bp.route('/content/files/<item_id>/<path:filename>')
def serve_item_file(item_id, filename):
    """Serve files from a specific item."""
    file_path = store.get_file_path(item_id, filename)
    if file_path:
        response = send_file(file_path)
        if filename.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
            response.headers['Cache-Control'] = 'public, max-age=31536000'
            response.headers['Accept-Ranges'] = 'bytes'
        return response
    return jsonify({'error': 'File not found'}), 404


@public_bp.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    thumb_path = store.get_thumbnail_path(filename)
    if thumb_path:
        return send_file(thumb_path)
    return jsonify({'error': 'Thumbnail not found'}), 404


# --- Legacy routes (backwards compatibility) ---

def _serve_legacy(filename, media_type=None):
    path = store.find_legacy_file(filename, media_type)
    if path:
        response = send_file(path)
        if media_type == 'videos':
            response.headers['Cache-Control'] = 'public, max-age=31536000'
            response.headers['Accept-Ranges'] = 'bytes'
        elif media_type == 'code':
            response.headers['Content-Type'] = 'text/plain'
        return response
    return jsonify({'error': 'File not found'}), 404


@public_bp.route('/videos/<path:filename>')
def serve_video(filename):
    return _serve_legacy(filename, 'videos')


@public_bp.route('/pdfs/<path:filename>')
def serve_pdf(filename):
    return _serve_legacy(filename, 'pdfs')


@public_bp.route('/figures/<path:filename>')
def serve_figure(filename):
    return _serve_legacy(filename, 'figures')


@public_bp.route('/code/<path:filename>')
def serve_code(filename):
    return _serve_legacy(filename, 'code')


# --- Visitor tracking ---

@public_bp.route('/api/track', methods=['POST'])
def track_view():
    if not visitor_log:
        return jsonify({'ok': True})
    data = request.get_json(silent=True) or {}
    ip = (request.headers.get('CF-Connecting-IP')
          or request.headers.get('X-Forwarded-For')
          or request.remote_addr)
    if ip and ',' in ip:
        ip = ip.split(',')[0].strip()
    vid = data.get('vid', ip)  # browser-generated visitor ID, fallback to IP
    path = data.get('path', '')
    if not path or path.startswith('/admin'):
        return jsonify({'ok': True})
    action = data.get('action', 'view')
    if action == 'leave':
        visitor_log.update_duration(vid, path, data.get('duration', 0))
    else:
        visitor_log.record_view(vid, ip, path, data.get('title'), request.user_agent.string)
    return jsonify({'ok': True})


# --- Thesis document ---

@public_bp.route('/thesis/<path:filename>')
def serve_thesis(filename):
    """Serve the thesis PDF document."""
    thesis_path = store.get_thesis_path()
    if thesis_path and thesis_path.name == filename:
        return send_file(thesis_path)
    return jsonify({'error': 'Not found'}), 404


# Serve logo from content dir — MUST be last (catch-all)
@public_bp.route('/<path:filename>')
def serve_root_file(filename):
    """Serve files from content root (logo, etc.) - only specific extensions."""
    if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.svg', '.ico', '.webp')):
        return jsonify({'error': 'Not found'}), 404
    file_path = store.content_dir / filename
    if file_path.exists():
        return send_file(file_path)
    return jsonify({'error': 'Not found'}), 404
