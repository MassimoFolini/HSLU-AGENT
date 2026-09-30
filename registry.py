import json
import os
import time
from datetime import datetime
import hashlib

REGISTRY_FILE = os.path.join(os.path.dirname(__file__), "ilias_registry.json")

class IliasRegistry:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if os.path.exists(REGISTRY_FILE):
            try:
                with open(REGISTRY_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return {"metadata": {"last_scan": None}, "courses": {}}

    def _save(self):
        with open(REGISTRY_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def generate_id(self, url, title):
        unique_string = f"{url}_{title}"
        return hashlib.md5(unique_string.encode('utf-8')).hexdigest()

    def needs_processing(self, course_id, item_id):
        if course_id not in self.data["courses"]:
            return True
        items = self.data["courses"][course_id].get("items", {})
        if item_id not in items:
            return True
        return items[item_id].get("status") != "processed"

    def register_item(self, course_id, item_id, item_type, title, url):
        if course_id not in self.data["courses"]:
            self.data["courses"][course_id] = {"items": {}}
        
        items = self.data["courses"][course_id]["items"]
        if item_id not in items:
            items[item_id] = {
                "type": item_type,
                "title": title,
                "url": url,
                "first_seen": datetime.now().isoformat(),
                "last_processed": None,
                "status": "pending"
            }
            self._save()
            return True
        return False

    def mark_processed(self, course_id, item_id):
        if course_id in self.data["courses"]:
            items = self.data["courses"][course_id].get("items", {})
            if item_id in items:
                items[item_id]["status"] = "processed"
                items[item_id]["last_processed"] = datetime.now().isoformat()
                self._save()

    def update_scan_time(self):
        self.data["metadata"]["last_scan"] = datetime.now().isoformat()
        self._save()

    def get_pending_items(self):
        pending = []
        for course_id, course_data in self.data["courses"].items():
            for item_id, item_data in course_data.get("items", {}).items():
                if item_data.get("status") == "pending":
                    pending.append({
                        "course_id": course_id,
                        "item_id": item_id,
                        **item_data
                    })
        return pending

registry = IliasRegistry()
