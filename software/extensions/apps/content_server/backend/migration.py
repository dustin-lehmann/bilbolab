"""
Migration script: converts experiments.json + flat dirs -> content/ tree.

Run as: python -m backend.migration
"""

import json
import os
import shutil
from pathlib import Path

# Try to import bcrypt, fall back to a basic hash if not available
try:
    from .auth import hash_password
except ImportError:
    import bcrypt
    def hash_password(plain):
        return bcrypt.hashpw(plain.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def migrate(base_dir=None):
    if base_dir is None:
        base_dir = Path(__file__).parent.parent

    base_dir = Path(base_dir)
    content_dir = base_dir / 'content'

    experiments_file = base_dir / 'experiments.json'
    settings_file = base_dir / 'settings.json'

    if not experiments_file.exists():
        print(f"No experiments.json found at {experiments_file}")
        return

    print(f"Migrating from {base_dir} to {content_dir}")

    # Load source data
    with open(experiments_file) as f:
        experiments_data = json.load(f)

    settings = {}
    if settings_file.exists():
        with open(settings_file) as f:
            settings = json.load(f)

    # Create content directory
    content_dir.mkdir(exist_ok=True)
    (content_dir / 'folders').mkdir(exist_ok=True)
    (content_dir / 'thumbnails').mkdir(exist_ok=True)

    # Copy thumbnails
    old_thumbs = base_dir / 'thumbnails'
    if old_thumbs.exists():
        for f in old_thumbs.iterdir():
            if f.is_file() and not f.name.startswith('.'):
                shutil.copy2(f, content_dir / 'thumbnails' / f.name)
        print(f"  Copied {len(list(old_thumbs.iterdir()))} thumbnails")

    # Copy logo
    logo = settings.get('logo')
    if logo:
        # Check in public dir first, then base dir
        for search_dir in [base_dir / 'frontend' / 'public', base_dir]:
            logo_src = search_dir / logo
            if logo_src.exists():
                shutil.copy2(logo_src, content_dir / logo)
                print(f"  Copied logo: {logo}")
                break

    # Write settings with default admin password
    content_settings = dict(settings)
    content_settings['adminPasswordHash'] = hash_password('admin')
    _write_json(content_dir / '_settings.json', content_settings)
    print("  Default admin password set to 'admin'")

    # Source media directories
    media_dirs = {
        'videos': base_dir / 'videos',
        'figures': base_dir / 'figures',
        'pdfs': base_dir / 'pdfs',
        'code': base_dir / 'code',
    }

    # Process folders recursively
    folder_order = []
    for folder_data in experiments_data.get('folders', []):
        _migrate_folder(folder_data, content_dir / 'folders', media_dirs)
        folder_order.append(folder_data['id'])

    # Write root structure
    _write_json(content_dir / '_structure.json', {'folderOrder': folder_order})

    total_folders, total_items = _count_tree(content_dir / 'folders')
    print(f"\nMigration complete: {total_folders} folders, {total_items} items")
    print(f"Content directory: {content_dir}")


def _migrate_folder(folder_data, parent_dir, media_dirs):
    """Recursively migrate a folder and its contents."""
    folder_id = folder_data['id']
    folder_path = parent_dir / folder_id
    folder_path.mkdir(parents=True, exist_ok=True)
    (folder_path / 'items').mkdir(exist_ok=True)
    (folder_path / 'subfolders').mkdir(exist_ok=True)

    # Build item order
    item_order = []
    for exp in folder_data.get('experiments', []):
        item_order.append(exp['id'])
        _migrate_item(exp, folder_path / 'items', media_dirs)

    # Build subfolder order
    subfolder_order = []
    for subfolder in folder_data.get('folders', []):
        subfolder_order.append(subfolder['id'])
        _migrate_folder(subfolder, folder_path / 'subfolders', media_dirs)

    # Write folder metadata
    folder_meta = {
        'id': folder_id,
        'name': folder_data.get('name', ''),
        'description': folder_data.get('description', ''),
        'draft': False,
        'thumbnail': folder_data.get('image'),
        'itemOrder': item_order,
        'subfolderOrder': subfolder_order,
    }
    _write_json(folder_path / '_folder.json', folder_meta)


def _migrate_item(item_data, items_dir, media_dirs):
    """Migrate a single item (experiment)."""
    item_id = item_data['id']
    item_path = items_dir / item_id
    item_path.mkdir(parents=True, exist_ok=True)
    files_dir = item_path / 'files'
    files_dir.mkdir(exist_ok=True)

    item_type = item_data.get('type', 'synchronized')

    # Copy media files
    if item_type in ('synchronized', 'collection'):
        for video in item_data.get('videos', []):
            _copy_media(video.get('file'), media_dirs.get('videos'), files_dir)
    elif item_type == 'figures':
        for fig in item_data.get('figures', []):
            _copy_media(fig.get('file'), media_dirs.get('figures'), files_dir)
    elif item_type == 'pdf':
        _copy_media(item_data.get('file'), media_dirs.get('pdfs'), files_dir)
    elif item_type == 'code':
        _copy_media(item_data.get('file'), media_dirs.get('code'), files_dir)

    # Write item metadata (keep all original fields)
    item_meta = {
        'id': item_id,
        'title': item_data.get('title', ''),
        'description': item_data.get('description', ''),
        'type': item_type,
        'date': item_data.get('date', ''),
        'draft': False,
        'thumbnail': item_data.get('image'),
    }

    # Type-specific fields
    if item_type in ('synchronized', 'collection'):
        item_meta['videos'] = item_data.get('videos', [])
        if item_type == 'synchronized':
            item_meta['markers'] = item_data.get('markers', [])
    elif item_type == 'figures':
        item_meta['figures'] = item_data.get('figures', [])
    elif item_type == 'pdf':
        item_meta['file'] = item_data.get('file', '')
    elif item_type == 'code':
        item_meta['file'] = item_data.get('file', '')
        item_meta['language'] = item_data.get('language', 'plaintext')
    elif item_type == 'interactive':
        item_meta['model'] = item_data.get('model', '')

    _write_json(item_path / '_item.json', item_meta)


def _copy_media(filename, src_dir, dest_dir):
    """Copy a media file if it exists."""
    if not filename or not src_dir:
        return
    src = Path(src_dir) / filename
    if src.exists():
        dest = Path(dest_dir) / filename
        if not dest.exists():
            shutil.copy2(src, dest)


def _write_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _count_tree(folders_dir):
    """Count folders and items in the tree."""
    folders = 0
    items = 0
    if not folders_dir.exists():
        return 0, 0
    for folder_json in folders_dir.rglob('_folder.json'):
        folders += 1
    for item_json in folders_dir.rglob('_item.json'):
        items += 1
    return folders, items


if __name__ == '__main__':
    migrate()
