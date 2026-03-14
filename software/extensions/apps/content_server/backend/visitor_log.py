"""
Visitor tracking - append-only JSONL log with query methods.

Stores page views in content/_visitors.jsonl (one JSON object per line).
Each entry: {vid, ip, path, title, timestamp, duration, userAgent}

Visitors are identified by a persistent browser-generated ID (vid) stored
in localStorage, so they remain the same person even when their IP changes.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


class VisitorLog:
    def __init__(self, content_dir):
        self.log_path = Path(content_dir) / '_visitors.jsonl'

    def record_view(self, vid, ip, path, title=None, user_agent=None):
        """Append a page view entry."""
        entry = {
            'vid': vid,
            'ip': ip,
            'path': path,
            'title': title or '',
            'ts': datetime.utcnow().isoformat() + 'Z',
            'duration': 0,
            'ua': (user_agent or '')[:200],
        }
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def update_duration(self, vid, path, duration):
        """Append a duration-update marker for the most recent matching view."""
        entry = {
            '_update': True,
            'vid': vid,
            'path': path,
            'ts': datetime.utcnow().isoformat() + 'Z',
            'duration': min(int(duration), 7200),  # cap at 2 hours
        }
        with open(self.log_path, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def get_all_views(self, days=None):
        """Read all views, merging duration updates into original entries."""
        if not self.log_path.exists():
            return []

        views = []
        cutoff = None
        if days:
            cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat() + 'Z'

        with open(self.log_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if cutoff and entry.get('ts', '') < cutoff:
                    continue

                if entry.get('_update'):
                    # Find most recent view from same vid+path and update duration
                    vid = entry.get('vid') or entry.get('ip')
                    for v in reversed(views):
                        v_vid = v.get('vid') or v.get('ip')
                        if v_vid == vid and v['path'] == entry['path']:
                            v['duration'] = entry['duration']
                            break
                else:
                    views.append(entry)

        return views

    def get_visitors_summary(self, days=30):
        """Get visitor data grouped by visitor ID for the admin panel."""
        views = self.get_all_views(days=days)

        by_vid = {}
        for v in views:
            # Use vid as primary key, fall back to ip for old entries
            key = v.get('vid') or v.get('ip', 'unknown')
            if key not in by_vid:
                by_vid[key] = {
                    'vid': key,
                    'ips': set(),
                    'userAgent': v.get('ua', ''),
                    'firstSeen': v['ts'],
                    'lastSeen': v['ts'],
                    'views': [],
                    'totalViews': 0,
                    'totalDuration': 0,
                }
            visitor = by_vid[key]
            if v.get('ip'):
                visitor['ips'].add(v['ip'])
            visitor['lastSeen'] = v['ts']
            visitor['totalViews'] += 1
            visitor['totalDuration'] += v.get('duration', 0)
            if v.get('ua'):
                visitor['userAgent'] = v['ua']
            visitor['views'].append({
                'path': v['path'],
                'title': v.get('title', ''),
                'timestamp': v['ts'],
                'duration': v.get('duration', 0),
                'ip': v.get('ip', ''),
            })

        # Convert sets to lists for JSON serialization
        for visitor in by_vid.values():
            visitor['ips'] = sorted(visitor['ips'])

        # Sort by last seen (most recent first)
        return sorted(by_vid.values(), key=lambda x: x['lastSeen'], reverse=True)

    def clear(self):
        """Clear all visitor data."""
        if self.log_path.exists():
            self.log_path.unlink()
