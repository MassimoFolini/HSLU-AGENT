import os
import json
from registry import registry

old_sync = os.path.join("downloads", "sync_state.json")

if os.path.exists(old_sync):
    with open(old_sync, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
            for course_id, items in data.items():
                print(f"Migrating course {course_id}...")
                for item_str in items:
                    parts = item_str.rsplit('_', 1)
                    title = parts[0]
                    url = parts[1] if len(parts) > 1 else ""
                    
                    item_id = registry.generate_id(url, title)
                    registry.register_item(course_id, item_id, "pdf", title, url)
                    registry.mark_processed(course_id, item_id)
            print("Migration successful! Old sync_state.json items are now marked as processed in ilias_registry.json.")
        except Exception as e:
            print(f"Error migrating: {e}")
else:
    print("No old sync_state.json found.")
