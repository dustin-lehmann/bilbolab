"""
Admin API routes - all require JWT authentication.
"""

import os
from flask import Blueprint, jsonify, request, send_file

from .auth import require_admin, hash_password, verify_password, create_token

admin_bp = Blueprint('admin', __name__, url_prefix='/api/admin')

# ContentStore and VisitorLog instances set by app factory
store = None
visitor_log = None


def init_admin_routes(content_store, vlog=None):
    global store, visitor_log
    store = content_store
    visitor_log = vlog


# --- Auth endpoints ---

@admin_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({'error': 'Password required'}), 400

    stored_hash = store.get_admin_password_hash()
    if not stored_hash:
        return jsonify({'error': 'Admin not configured'}), 500

    if not verify_password(data['password'], stored_hash):
        return jsonify({'error': 'Invalid password'}), 401

    token = create_token()
    return jsonify({'token': token})


@admin_bp.route('/verify')
@require_admin
def verify():
    return jsonify({'valid': True})


@admin_bp.route('/set-password', methods=['POST'])
@require_admin
def set_password():
    data = request.get_json()
    if not data or 'password' not in data:
        return jsonify({'error': 'Password required'}), 400
    if len(data['password']) < 4:
        return jsonify({'error': 'Password too short'}), 400

    hashed = hash_password(data['password'])
    store.set_admin_password_hash(hashed)
    return jsonify({'success': True})


# --- Content tree ---

@admin_bp.route('/content')
@require_admin
def get_content():
    return jsonify(store.get_all_content(include_drafts=True))


# --- Settings ---

@admin_bp.route('/settings', methods=['GET'])
@require_admin
def get_settings():
    return jsonify(store.get_public_settings())


@admin_bp.route('/settings', methods=['PUT'])
@require_admin
def update_settings():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    # Don't allow setting password hash via settings endpoint
    data.pop('adminPasswordHash', None)
    result = store.update_settings(data)
    return jsonify(result)


# --- Folders ---

@admin_bp.route('/folders', methods=['POST'])
@require_admin
def create_folder():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    parent_id = data.pop('parentId', None)
    folder = store.create_folder(parent_id, data)
    if folder:
        return jsonify(folder), 201
    return jsonify({'error': 'Parent folder not found'}), 404


@admin_bp.route('/folders/<folder_id>', methods=['PUT'])
@require_admin
def update_folder(folder_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    folder = store.update_folder(folder_id, data)
    if folder:
        return jsonify(folder)
    return jsonify({'error': 'Folder not found'}), 404


@admin_bp.route('/folders/<folder_id>', methods=['DELETE'])
@require_admin
def delete_folder(folder_id):
    if store.delete_folder(folder_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Folder not found'}), 404


@admin_bp.route('/folders/reorder', methods=['PUT'])
@require_admin
def reorder_folders():
    data = request.get_json()
    if not data or 'orderedIds' not in data:
        return jsonify({'error': 'orderedIds required'}), 400
    parent_id = data.get('parentId')
    if store.reorder_folders(parent_id, data['orderedIds']):
        return jsonify({'success': True})
    return jsonify({'error': 'Parent not found'}), 404


@admin_bp.route('/folders/<folder_id>/move', methods=['PUT'])
@require_admin
def move_folder(folder_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    new_parent_id = data.get('newParentId')
    position = data.get('position')
    if store.move_folder(folder_id, new_parent_id, position):
        return jsonify({'success': True})
    return jsonify({'error': 'Move failed'}), 400


# --- Items ---

@admin_bp.route('/items', methods=['POST'])
@require_admin
def create_item():
    data = request.get_json()
    if not data or 'folderId' not in data:
        return jsonify({'error': 'folderId required'}), 400
    folder_id = data.pop('folderId')
    item = store.create_item(folder_id, data)
    if item:
        return jsonify(item), 201
    return jsonify({'error': 'Folder not found'}), 404


@admin_bp.route('/items/<item_id>', methods=['GET'])
@require_admin
def get_item(item_id):
    item, breadcrumb = store.get_item(item_id, include_drafts=True)
    if item:
        result = dict(item)
        result['folderPath'] = breadcrumb
        result['files'] = store.get_item_files(item_id)
        return jsonify(result)
    return jsonify({'error': 'Item not found'}), 404


@admin_bp.route('/items/<item_id>', methods=['PUT'])
@require_admin
def update_item(item_id):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400
    item = store.update_item(item_id, data)
    if item:
        return jsonify(item)
    return jsonify({'error': 'Item not found'}), 404


@admin_bp.route('/items/<item_id>', methods=['DELETE'])
@require_admin
def delete_item(item_id):
    if store.delete_item(item_id):
        return jsonify({'success': True})
    return jsonify({'error': 'Item not found'}), 404


@admin_bp.route('/items/reorder', methods=['PUT'])
@require_admin
def reorder_items():
    data = request.get_json()
    if not data or 'orderedIds' not in data or 'folderId' not in data:
        return jsonify({'error': 'folderId and orderedIds required'}), 400
    if store.reorder_items(data['folderId'], data['orderedIds']):
        return jsonify({'success': True})
    return jsonify({'error': 'Folder not found'}), 404


@admin_bp.route('/items/<item_id>/move', methods=['PUT'])
@require_admin
def move_item(item_id):
    data = request.get_json()
    if not data or 'targetFolderId' not in data:
        return jsonify({'error': 'targetFolderId required'}), 400
    position = data.get('position')
    if store.move_item(item_id, data['targetFolderId'], position):
        return jsonify({'success': True})
    return jsonify({'error': 'Move failed'}), 400


# --- File uploads ---

@admin_bp.route('/items/<item_id>/files', methods=['POST'])
@require_admin
def upload_files(item_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    uploaded = []
    for f in request.files.getlist('file'):
        if f.filename:
            path = store.upload_file(item_id, f, f.filename)
            if path:
                uploaded.append(f.filename)
    if uploaded:
        return jsonify({'files': uploaded}), 201
    return jsonify({'error': 'Upload failed'}), 400


@admin_bp.route('/items/<item_id>/files/<filename>', methods=['DELETE'])
@require_admin
def delete_file(item_id, filename):
    if store.delete_file(item_id, filename):
        return jsonify({'success': True})
    return jsonify({'error': 'File not found'}), 404


# --- Thumbnails ---

@admin_bp.route('/thumbnails/<entity_id>', methods=['POST'])
@require_admin
def upload_thumbnail(entity_id):
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if f.filename:
        name = store.set_thumbnail(entity_id, f, f.filename)
        if name:
            store.update_item(entity_id, {'thumbnail': name})
            return jsonify({'thumbnail': name}), 201
    return jsonify({'error': 'Upload failed'}), 400


@admin_bp.route('/thumbnails/<item_id>/generate', methods=['POST'])
@require_admin
def generate_thumbnail(item_id):
    data = request.get_json() or {}
    video_filename = data.get('videoFilename')
    name = store.generate_thumbnail(item_id, video_filename)
    if name:
        store.update_item(item_id, {'thumbnail': name})
        return jsonify({'thumbnail': name})
    return jsonify({'error': 'Thumbnail generation failed (ffmpeg required)'}), 400


# --- Logo ---

@admin_bp.route('/logo', methods=['POST'])
@require_admin
def upload_logo():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if f.filename:
        name = store.upload_logo(f, f.filename)
        if name:
            return jsonify({'logo': name})
    return jsonify({'error': 'Upload failed'}), 400


# --- Thesis document ---

@admin_bp.route('/thesis', methods=['POST'])
@require_admin
def upload_thesis():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if f.filename and f.filename.lower().endswith('.pdf'):
        name = store.upload_thesis(f, f.filename)
        if name:
            return jsonify({'thesisDocument': name})
    return jsonify({'error': 'Upload failed (PDF required)'}), 400


# --- Export / Import ---

@admin_bp.route('/export')
@require_admin
def export_content():
    zip_path = store.export_zip()
    return send_file(zip_path, as_attachment=True,
                     download_name='content_export.zip',
                     mimetype='application/zip')


@admin_bp.route('/import', methods=['POST'])
@require_admin
def import_content():
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    f = request.files['file']
    if not f.filename or not f.filename.endswith('.zip'):
        return jsonify({'error': 'Must be a ZIP file'}), 400
    import tempfile
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    try:
        f.save(tmp.name)
        tmp.close()
        store.import_zip(tmp.name)
        return jsonify({'success': True})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': f'Import failed: {str(e)}'}), 500
    finally:
        import os
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


@admin_bp.route('/clear', methods=['POST'])
@require_admin
def clear_content():
    store.clear_all_content()
    return jsonify({'success': True})


# --- Visitors ---

@admin_bp.route('/visitors')
@require_admin
def get_visitors():
    if not visitor_log:
        return jsonify({'visitors': []})
    days = request.args.get('days', 30, type=int)
    visitors = visitor_log.get_visitors_summary(days=days)
    return jsonify({'visitors': visitors})


@admin_bp.route('/visitors/clear', methods=['POST'])
@require_admin
def clear_visitors():
    if visitor_log:
        visitor_log.clear()
    return jsonify({'success': True})
