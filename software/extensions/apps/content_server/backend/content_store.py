"""
Content store - file-based content management abstraction.

Layout:
  content/
    _settings.json          # App settings + adminPasswordHash
    _structure.json         # Root folder ordering
    _secret.key             # JWT signing key
    thumbnails/             # Shared thumbnail images
    logo.png                # Logo file
    folders/
      <folder_id>/
        _folder.json        # {id, name, description, draft, thumbnail, itemOrder}
        items/
          <item_id>/
            _item.json      # Item metadata
            files/           # Media files
        subfolders/
          <subfolder_id>/   # Recursive structure
"""

import json
import os
import shutil
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path


class ContentStore:
    def __init__(self, content_dir):
        self.content_dir = Path(content_dir)
        self.content_dir.mkdir(parents=True, exist_ok=True)
        (self.content_dir / 'folders').mkdir(exist_ok=True)
        (self.content_dir / 'thumbnails').mkdir(exist_ok=True)

        # In-memory cache
        self._cache = {}
        self._mtimes = {}

    # --- Atomic JSON I/O ---

    def _read_json(self, path):
        path = Path(path)
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        cache_key = str(path)
        if cache_key in self._cache and self._mtimes.get(cache_key) == mtime:
            return self._cache[cache_key]
        with open(path, 'r') as f:
            data = json.load(f)
        self._cache[cache_key] = data
        self._mtimes[cache_key] = mtime
        return data

    def _write_json(self, path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        # Invalidate cache
        cache_key = str(path)
        self._cache.pop(cache_key, None)
        self._mtimes.pop(cache_key, None)

    # --- Settings ---

    def get_settings(self):
        data = self._read_json(self.content_dir / '_settings.json')
        return data or {'title': 'Additional Material', 'folderStyle': 'accordion'}

    def get_public_settings(self):
        settings = self.get_settings()
        result = {k: v for k, v in settings.items() if k != 'adminPasswordHash'}
        return result

    def update_settings(self, data):
        current = self.get_settings()
        current.update(data)
        self._write_json(self.content_dir / '_settings.json', current)
        return current

    def get_admin_password_hash(self):
        settings = self.get_settings()
        return settings.get('adminPasswordHash')

    def set_admin_password_hash(self, hashed):
        settings = self.get_settings()
        settings['adminPasswordHash'] = hashed
        self._write_json(self.content_dir / '_settings.json', settings)

    # --- Structure (root folder ordering) ---

    def _get_structure(self):
        data = self._read_json(self.content_dir / '_structure.json')
        return data or {'folderOrder': []}

    def _save_structure(self, data):
        self._write_json(self.content_dir / '_structure.json', data)

    # --- Folder operations ---

    def _folder_path(self, folder_id, parent_path=None):
        """Find folder path by ID, searching recursively."""
        if parent_path:
            return parent_path / 'subfolders' / folder_id
        # Search for folder in tree
        return self._find_folder_path(folder_id)

    def _find_folder_path(self, folder_id):
        """Search for a folder by ID in the content tree."""
        root = self.content_dir / 'folders' / folder_id
        if root.exists():
            return root
        # Search in subfolders recursively
        for path in self.content_dir.rglob(f'subfolders/{folder_id}'):
            if path.is_dir() and (path / '_folder.json').exists():
                return path
        return None

    def _find_item_path(self, item_id):
        """Search for an item by ID in the content tree."""
        for path in self.content_dir.rglob(f'items/{item_id}'):
            if path.is_dir() and (path / '_item.json').exists():
                return path
        return None

    def _read_folder(self, folder_path, include_drafts=False):
        """Read folder metadata and its contents recursively."""
        folder_json = folder_path / '_folder.json'
        if not folder_json.exists():
            return None
        folder = self._read_json(folder_json)
        if not folder:
            return None
        if not include_drafts and folder.get('draft', False):
            return None

        # Read subfolders
        subfolders_dir = folder_path / 'subfolders'
        subfolders = []
        if subfolders_dir.exists():
            subfolder_order = folder.get('subfolderOrder', [])
            subfolder_ids = set()
            for sub_dir in subfolders_dir.iterdir():
                if sub_dir.is_dir() and (sub_dir / '_folder.json').exists():
                    subfolder_ids.add(sub_dir.name)

            # Ordered first, then any unordered ones
            ordered = [sid for sid in subfolder_order if sid in subfolder_ids]
            unordered = [sid for sid in subfolder_ids if sid not in set(subfolder_order)]
            for sid in ordered + sorted(unordered):
                sub = self._read_folder(subfolders_dir / sid, include_drafts)
                if sub:
                    subfolders.append(sub)

        # Read items (experiments)
        items_dir = folder_path / 'items'
        experiments = []
        if items_dir.exists():
            item_order = folder.get('itemOrder', [])
            item_ids = set()
            for item_dir in items_dir.iterdir():
                if item_dir.is_dir() and (item_dir / '_item.json').exists():
                    item_ids.add(item_dir.name)

            ordered = [iid for iid in item_order if iid in item_ids]
            unordered = [iid for iid in item_ids if iid not in set(item_order)]
            for iid in ordered + sorted(unordered):
                item = self._read_item(items_dir / iid, include_drafts)
                if item:
                    experiments.append(item)

        result = {k: v for k, v in folder.items()
                  if k not in ('itemOrder', 'subfolderOrder')}
        result['folders'] = subfolders
        result['experiments'] = experiments
        return result

    def _read_item(self, item_path, include_drafts=False):
        """Read item metadata."""
        item_json = item_path / '_item.json'
        if not item_json.exists():
            return None
        item = self._read_json(item_json)
        if not item:
            return None
        if not include_drafts and item.get('draft', False):
            return None
        return item

    def get_all_content(self, include_drafts=False):
        """Walk the entire content tree and return nested structure."""
        structure = self._get_structure()
        folder_order = structure.get('folderOrder', [])
        folders_dir = self.content_dir / 'folders'

        existing_ids = set()
        if folders_dir.exists():
            for d in folders_dir.iterdir():
                if d.is_dir() and (d / '_folder.json').exists():
                    existing_ids.add(d.name)

        ordered = [fid for fid in folder_order if fid in existing_ids]
        unordered = [fid for fid in existing_ids if fid not in set(folder_order)]

        folders = []
        for fid in ordered + sorted(unordered):
            folder = self._read_folder(folders_dir / fid, include_drafts)
            if folder:
                folders.append(folder)

        return {'folders': folders, 'experiments': []}

    def get_folder(self, folder_id, include_drafts=False):
        """Get a single folder with breadcrumb."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return None
        folder = self._read_folder(folder_path, include_drafts)
        if not folder:
            return None
        folder['breadcrumb'] = self._get_breadcrumb(folder_path)
        return folder

    def _get_breadcrumb(self, folder_path):
        """Build breadcrumb from folder path."""
        crumbs = []
        current = folder_path
        while True:
            parent = current.parent
            if parent.name != 'subfolders':
                break
            grandparent = parent.parent
            if not (grandparent / '_folder.json').exists():
                break
            parent_data = self._read_json(grandparent / '_folder.json')
            if parent_data:
                crumbs.insert(0, {'id': parent_data['id'], 'name': parent_data['name']})
            current = grandparent
        return crumbs

    def get_item(self, item_id, include_drafts=False):
        """Get a single item with breadcrumb."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return None, []
        item = self._read_item(item_path, include_drafts)
        if not item:
            return None, []

        # Build breadcrumb from the items/ parent folder
        folder_path = item_path.parent.parent  # items/<id> -> items -> folder
        breadcrumb = []
        if (folder_path / '_folder.json').exists():
            folder_data = self._read_json(folder_path / '_folder.json')
            breadcrumb = self._get_breadcrumb(folder_path)
            if folder_data:
                breadcrumb.append({'id': folder_data['id'], 'name': folder_data['name']})

        return item, breadcrumb

    def search(self, query, include_drafts=False):
        """Search items and folders by title/name."""
        query = query.lower().strip()
        if not query:
            return []

        results = []
        content = self.get_all_content(include_drafts)

        def search_folders(folders, path=None):
            if path is None:
                path = []
            for folder in folders:
                folder_path = path + [{'id': folder['id'], 'name': folder['name']}]

                if query in folder.get('name', '').lower():
                    results.append({
                        'id': folder['id'],
                        'title': folder['name'],
                        'description': folder.get('description', ''),
                        'type': 'folder',
                        'experimentCount': self._count_experiments(folder),
                        'folderPath': path,
                        'draft': folder.get('draft', False)
                    })

                for exp in folder.get('experiments', []):
                    if query in exp.get('title', '').lower():
                        exp_type = exp.get('type', 'synchronized')
                        item_count = (len(exp.get('figures', []))
                                      if exp_type == 'figures'
                                      else len(exp.get('videos', [])))
                        result = {
                            'id': exp['id'],
                            'title': exp['title'],
                            'description': exp.get('description', ''),
                            'type': 'experiment',
                            'experimentType': exp_type,
                            'videoCount': item_count,
                            'folderPath': folder_path,
                            'draft': exp.get('draft', False)
                        }
                        if exp_type == 'code':
                            result['language'] = exp.get('language', 'plaintext')
                        results.append(result)

                if folder.get('folders'):
                    search_folders(folder['folders'], folder_path)

        search_folders(content.get('folders', []))
        return results

    def _count_experiments(self, folder):
        count = len(folder.get('experiments', []))
        for sub in folder.get('folders', []):
            count += self._count_experiments(sub)
        return count

    # --- File serving ---

    def get_file_path(self, item_id, filename):
        """Resolve an item's file path."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return None
        file_path = item_path / 'files' / filename
        if file_path.exists():
            return file_path
        return None

    def find_legacy_file(self, filename, media_type=None):
        """Search content/ for a file by name (backwards compat for /videos/, /figures/, etc.)."""
        # Search in all item files/ directories
        for path in self.content_dir.rglob(f'files/{filename}'):
            if path.is_file():
                return path
        # Also check thumbnails
        thumb = self.content_dir / 'thumbnails' / filename
        if thumb.exists():
            return thumb
        return None

    def get_thumbnail_path(self, filename):
        """Get path to a thumbnail file."""
        path = self.content_dir / 'thumbnails' / filename
        if path.exists():
            return path
        return None

    def get_logo_path(self):
        """Find the logo file."""
        settings = self.get_settings()
        logo = settings.get('logo')
        if logo:
            # Check in content dir
            logo_path = self.content_dir / logo
            if logo_path.exists():
                return logo_path
        return None

    # --- Admin write operations ---

    def create_folder(self, parent_id, data):
        """Create a new folder."""
        folder_id = data.get('id') or str(uuid.uuid4())[:8]
        folder_data = {
            'id': folder_id,
            'name': data.get('name', 'New Folder'),
            'description': data.get('description', ''),
            'draft': data.get('draft', False),
            'thumbnail': data.get('thumbnail'),
            'itemOrder': [],
            'subfolderOrder': []
        }

        if parent_id:
            parent_path = self._find_folder_path(parent_id)
            if not parent_path:
                return None
            folder_path = parent_path / 'subfolders' / folder_id
            # Add to parent's subfolderOrder
            parent_data = self._read_json(parent_path / '_folder.json')
            if parent_data:
                order = parent_data.get('subfolderOrder', [])
                order.append(folder_id)
                parent_data['subfolderOrder'] = order
                self._write_json(parent_path / '_folder.json', parent_data)
        else:
            folder_path = self.content_dir / 'folders' / folder_id
            # Add to root structure
            structure = self._get_structure()
            structure.setdefault('folderOrder', []).append(folder_id)
            self._save_structure(structure)

        folder_path.mkdir(parents=True, exist_ok=True)
        (folder_path / 'items').mkdir(exist_ok=True)
        (folder_path / 'subfolders').mkdir(exist_ok=True)
        self._write_json(folder_path / '_folder.json', folder_data)
        return folder_data

    def update_folder(self, folder_id, data):
        """Update folder metadata."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return None
        current = self._read_json(folder_path / '_folder.json')
        if not current:
            return None
        # Only update allowed fields
        for key in ('name', 'description', 'draft', 'thumbnail'):
            if key in data:
                current[key] = data[key]
        self._write_json(folder_path / '_folder.json', current)
        return current

    def delete_folder(self, folder_id):
        """Delete a folder and all its contents."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return False

        # Remove from parent's order
        parent = folder_path.parent
        if parent.name == 'subfolders':
            grandparent = parent.parent
            gp_data = self._read_json(grandparent / '_folder.json')
            if gp_data:
                order = gp_data.get('subfolderOrder', [])
                if folder_id in order:
                    order.remove(folder_id)
                gp_data['subfolderOrder'] = order
                self._write_json(grandparent / '_folder.json', gp_data)
        else:
            # Root folder
            structure = self._get_structure()
            if folder_id in structure['folderOrder']:
                structure['folderOrder'].remove(folder_id)
            self._save_structure(structure)

        shutil.rmtree(folder_path)
        return True

    def reorder_folders(self, parent_id, ordered_ids):
        """Reorder folders within a parent."""
        if parent_id:
            parent_path = self._find_folder_path(parent_id)
            if not parent_path:
                return False
            parent_data = self._read_json(parent_path / '_folder.json')
            if not parent_data:
                return False
            parent_data['subfolderOrder'] = ordered_ids
            self._write_json(parent_path / '_folder.json', parent_data)
        else:
            structure = self._get_structure()
            structure['folderOrder'] = ordered_ids
            self._save_structure(structure)
        return True

    def move_folder(self, folder_id, new_parent_id, position=None):
        """Move a folder to a different parent."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return False

        # Remove from current parent
        old_parent = folder_path.parent
        if old_parent.name == 'subfolders':
            gp = old_parent.parent
            gp_data = self._read_json(gp / '_folder.json')
            if gp_data:
                order = gp_data.get('subfolderOrder', [])
                if folder_id in order:
                    order.remove(folder_id)
                gp_data['subfolderOrder'] = order
                self._write_json(gp / '_folder.json', gp_data)
        else:
            structure = self._get_structure()
            if folder_id in structure['folderOrder']:
                structure['folderOrder'].remove(folder_id)
            self._save_structure(structure)

        # Move to new parent
        if new_parent_id:
            new_parent_path = self._find_folder_path(new_parent_id)
            if not new_parent_path:
                return False
            new_dest = new_parent_path / 'subfolders' / folder_id
            new_dest.parent.mkdir(exist_ok=True)
            shutil.move(str(folder_path), str(new_dest))

            parent_data = self._read_json(new_parent_path / '_folder.json')
            if parent_data:
                order = parent_data.get('subfolderOrder', [])
                if position is not None and 0 <= position <= len(order):
                    order.insert(position, folder_id)
                else:
                    order.append(folder_id)
                parent_data['subfolderOrder'] = order
                self._write_json(new_parent_path / '_folder.json', parent_data)
        else:
            new_dest = self.content_dir / 'folders' / folder_id
            shutil.move(str(folder_path), str(new_dest))

            structure = self._get_structure()
            order = structure['folderOrder']
            if position is not None and 0 <= position <= len(order):
                order.insert(position, folder_id)
            else:
                order.append(folder_id)
            self._save_structure(structure)

        return True

    # --- Item operations ---

    def create_item(self, folder_id, data):
        """Create a new item in a folder."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return None

        item_id = data.get('id') or str(uuid.uuid4())[:8]
        item_data = {
            'id': item_id,
            'title': data.get('title', 'New Item'),
            'description': data.get('description', ''),
            'type': data.get('type', 'synchronized'),
            'date': data.get('date', ''),
            'draft': data.get('draft', False),
            'thumbnail': data.get('thumbnail'),
        }

        # Type-specific fields
        item_type = item_data['type']
        if item_type == 'video':
            item_data['file'] = data.get('file', '')
            item_data['markers'] = data.get('markers', [])
        elif item_type in ('synchronized', 'collection'):
            item_data['videos'] = data.get('videos', [])
            if item_type == 'synchronized':
                item_data['markers'] = data.get('markers', [])
        elif item_type == 'figures':
            item_data['figures'] = data.get('figures', [])
        elif item_type == 'pdf':
            item_data['file'] = data.get('file', '')
        elif item_type == 'code':
            item_data['file'] = data.get('file', '')
            item_data['language'] = data.get('language', 'plaintext')
        elif item_type == 'interactive':
            item_data['model'] = data.get('model', '')

        item_path = folder_path / 'items' / item_id
        item_path.mkdir(parents=True, exist_ok=True)
        (item_path / 'files').mkdir(exist_ok=True)
        self._write_json(item_path / '_item.json', item_data)

        # Add to folder's itemOrder
        folder_data = self._read_json(folder_path / '_folder.json')
        if folder_data:
            order = folder_data.get('itemOrder', [])
            order.append(item_id)
            folder_data['itemOrder'] = order
            self._write_json(folder_path / '_folder.json', folder_data)

        return item_data

    def update_item(self, item_id, data):
        """Update item metadata."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return None
        current = self._read_json(item_path / '_item.json')
        if not current:
            return None

        # Update fields
        for key in ('title', 'description', 'type', 'date', 'draft', 'thumbnail',
                     'videos', 'markers', 'figures', 'file', 'language', 'model',
                     'chapter', 'section', 'subsection', 'page', 'additionalInfo',
                     'overlays', 'overlayStyle'):
            if key in data:
                current[key] = data[key]

        self._write_json(item_path / '_item.json', current)
        return current

    def delete_item(self, item_id):
        """Delete an item and its files."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return False

        # Remove from parent folder's itemOrder
        folder_path = item_path.parent.parent  # items/<id> -> items -> folder
        folder_data = self._read_json(folder_path / '_folder.json')
        if folder_data:
            order = folder_data.get('itemOrder', [])
            if item_id in order:
                order.remove(item_id)
            folder_data['itemOrder'] = order
            self._write_json(folder_path / '_folder.json', folder_data)

        shutil.rmtree(item_path)
        return True

    def reorder_items(self, folder_id, ordered_ids):
        """Reorder items within a folder."""
        folder_path = self._find_folder_path(folder_id)
        if not folder_path:
            return False
        folder_data = self._read_json(folder_path / '_folder.json')
        if not folder_data:
            return False
        folder_data['itemOrder'] = ordered_ids
        self._write_json(folder_path / '_folder.json', folder_data)
        return True

    def move_item(self, item_id, target_folder_id, position=None):
        """Move an item to a different folder."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return False

        # Remove from current folder's order
        old_folder_path = item_path.parent.parent
        old_folder_data = self._read_json(old_folder_path / '_folder.json')
        if old_folder_data:
            order = old_folder_data.get('itemOrder', [])
            if item_id in order:
                order.remove(item_id)
            old_folder_data['itemOrder'] = order
            self._write_json(old_folder_path / '_folder.json', old_folder_data)

        # Move to target folder
        target_path = self._find_folder_path(target_folder_id)
        if not target_path:
            return False

        new_item_path = target_path / 'items' / item_id
        new_item_path.parent.mkdir(exist_ok=True)
        shutil.move(str(item_path), str(new_item_path))

        # Add to target folder's order
        target_data = self._read_json(target_path / '_folder.json')
        if target_data:
            order = target_data.get('itemOrder', [])
            if position is not None and 0 <= position <= len(order):
                order.insert(position, item_id)
            else:
                order.append(item_id)
            target_data['itemOrder'] = order
            self._write_json(target_path / '_folder.json', target_data)

        return True

    # --- File management ---

    def upload_file(self, item_id, file_stream, filename):
        """Upload a file to an item."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return None
        files_dir = item_path / 'files'
        files_dir.mkdir(exist_ok=True)
        dest = files_dir / filename
        file_stream.save(dest)
        return str(dest)

    def delete_file(self, item_id, filename):
        """Delete a file from an item."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return False
        file_path = item_path / 'files' / filename
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def get_item_files(self, item_id):
        """List files in an item's files/ directory."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return []
        files_dir = item_path / 'files'
        if not files_dir.exists():
            return []
        return [f.name for f in files_dir.iterdir() if f.is_file()]

    def set_thumbnail(self, entity_id, file_stream, filename):
        """Upload a custom thumbnail for any entity."""
        thumb_dir = self.content_dir / 'thumbnails'
        thumb_dir.mkdir(exist_ok=True)
        ext = Path(filename).suffix or '.jpg'
        safe_name = f'{entity_id}_thumb{ext}'
        dest = thumb_dir / safe_name
        file_stream.save(dest)
        return safe_name

    def generate_thumbnail(self, item_id, video_filename=None):
        """Auto-generate thumbnail from video using ffmpeg."""
        item_path = self._find_item_path(item_id)
        if not item_path:
            return None

        # Find video file
        files_dir = item_path / 'files'
        if video_filename:
            video_path = files_dir / video_filename
        else:
            # Find first video
            video_path = None
            for ext in ('.mp4', '.webm', '.mov', '.avi'):
                for f in files_dir.iterdir():
                    if f.suffix.lower() == ext:
                        video_path = f
                        break
                if video_path:
                    break

        if not video_path or not video_path.exists():
            return None

        thumb_name = f'{item_id}_thumb.jpg'
        thumb_path = self.content_dir / 'thumbnails' / thumb_name

        try:
            subprocess.run(
                ['ffmpeg', '-y', '-i', str(video_path),
                 '-ss', '00:00:01', '-vframes', '1',
                 '-vf', 'scale=640:-1',
                 str(thumb_path)],
                capture_output=True, timeout=30
            )
            if thumb_path.exists():
                return thumb_name
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return None

    def upload_logo(self, file_stream, filename):
        """Upload a logo file."""
        dest = self.content_dir / filename
        file_stream.save(dest)
        settings = self.get_settings()
        settings['logo'] = filename
        self._write_json(self.content_dir / '_settings.json', settings)
        return filename

    def upload_thesis(self, file_stream, filename):
        """Upload the thesis PDF document."""
        dest = self.content_dir / filename
        file_stream.save(dest)
        settings = self.get_settings()
        settings['thesisDocument'] = filename
        self._write_json(self.content_dir / '_settings.json', settings)
        return filename

    def get_thesis_path(self):
        """Find the thesis document file."""
        settings = self.get_settings()
        thesis = settings.get('thesisDocument')
        if thesis:
            thesis_path = self.content_dir / thesis
            if thesis_path.exists():
                return thesis_path
        return None

    # --- Export ---

    def export_zip(self):
        """Export entire content directory as ZIP."""
        tmp_fd, tmp_path = tempfile.mkstemp(suffix='.zip')
        os.close(tmp_fd)
        with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in self.content_dir.rglob('*'):
                if file_path.is_file():
                    arcname = file_path.relative_to(self.content_dir)
                    zf.write(file_path, arcname)
        return tmp_path

    def import_zip(self, zip_path):
        """Replace entire content directory from a ZIP archive.

        The ZIP must contain the same layout as content/:
        _settings.json, _structure.json, folders/, thumbnails/, etc.

        Preserves the current admin password and secret key unless
        the ZIP explicitly contains them.
        """
        zip_path = Path(zip_path)
        if not zipfile.is_zipfile(zip_path):
            raise ValueError('Not a valid ZIP file')

        # Validate: ZIP must have _structure.json
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            if '_structure.json' not in names:
                raise ValueError('ZIP missing _structure.json — not a valid content export')

        # Save current auth state so we don't lock ourselves out
        current_password_hash = self.get_admin_password_hash()
        secret_key_path = self.content_dir / '_secret.key'
        current_secret_key = secret_key_path.read_text() if secret_key_path.exists() else None

        # Remove old content (except _secret.key which we restore)
        backup_dir = self.content_dir.parent / '_content_backup'
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        shutil.move(str(self.content_dir), str(backup_dir))

        try:
            # Extract new content
            self.content_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(self.content_dir)

            # Restore secret key (so existing tokens keep working)
            if current_secret_key:
                (self.content_dir / '_secret.key').write_text(current_secret_key)

            # Restore admin password if ZIP didn't include one
            settings = self.get_settings()
            if not settings.get('adminPasswordHash') and current_password_hash:
                settings['adminPasswordHash'] = current_password_hash
                self._write_json(self.content_dir / '_settings.json', settings)

            # Ensure required dirs exist
            (self.content_dir / 'folders').mkdir(exist_ok=True)
            (self.content_dir / 'thumbnails').mkdir(exist_ok=True)

            # Flush cache
            self._cache.clear()
            self._mtimes.clear()

            # Clean up backup
            shutil.rmtree(backup_dir)

        except Exception:
            # Restore from backup on failure
            if self.content_dir.exists():
                shutil.rmtree(self.content_dir)
            shutil.move(str(backup_dir), str(self.content_dir))
            self._cache.clear()
            self._mtimes.clear()
            raise

    def clear_all_content(self):
        """Remove all folders and items, keeping settings, auth, and logo."""
        # Remove all folders
        folders_dir = self.content_dir / 'folders'
        if folders_dir.exists():
            shutil.rmtree(folders_dir)
        folders_dir.mkdir(exist_ok=True)

        # Remove thumbnails
        thumbs_dir = self.content_dir / 'thumbnails'
        if thumbs_dir.exists():
            shutil.rmtree(thumbs_dir)
        thumbs_dir.mkdir(exist_ok=True)

        # Reset structure to empty
        self._write_json(self.content_dir / '_structure.json', {'folderOrder': []})

        self._cache.clear()
        self._mtimes.clear()
