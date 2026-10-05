import os
import re
import json
import subprocess
import asyncio
from notebooklm import NotebookLMClient
from google_integration import GoogleWorkspace

STATE_FILE = "notebooklm_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f: return json.load(f)
    return {}

def save_state(state):
    with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=4)

def get_config():
    if os.path.exists('.env'):
        with open('.env', 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith('GOOGLE_DRIVE_FOLDER_ID='):
                    return line.strip().split('=', 1)[1].strip('\'"')
    return None

def get_all_files_in_folder_recursive(gw, folder_id):
    files = []
    # Hole Dateien im aktuellen Ordner
    q = f"'{folder_id}' in parents and trashed=false"
    results = gw.drive_service.files().list(q=q, fields="files(id, name, mimeType, modifiedTime)").execute().get('files', [])
    
    for f in results:
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            files.extend(get_all_files_in_folder_recursive(gw, f['id']))
        else:
            files.append(f)
    return files

async def sync_course(client, gw, state, course_name, drive_course_folder_id):
    if course_name not in state: state[course_name] = {}
        
    notebook_title = f"HSLU - {course_name}"
    notebooks = await client.notebooks.list()
    notebook = next((n for n in notebooks if n.title == notebook_title), None)
    
    if not notebook:
        print(f"  -> Erstelle neues NotebookLM: '{notebook_title}'...")
        notebook = await client.notebooks.create(notebook_title)
    
    existing_sources = await client.sources.list(notebook.id)
    source_map = {s.title: s for s in existing_sources}
    
    q_unterlagen = f"'{drive_course_folder_id}' in parents and name = 'Unterlagen' and mimeType = 'application/vnd.google-apps.folder' and trashed=false"
    unterlagen_folders = gw.drive_service.files().list(q=q_unterlagen, fields="files(id, name)").execute().get('files', [])
    
    if not unterlagen_folders: return
    
    all_files = get_all_files_in_folder_recursive(gw, unterlagen_folders[0]['id'])
    
    doc_files = [f for f in all_files if f['mimeType'] == 'application/vnd.google-apps.document' or f['mimeType'] == 'text/markdown' or '.md' in f['name'] or '.txt' in f['name']]
    
    if not doc_files:
        print(f"  -> Keine Dokumente gefunden.")
        return
        
    print(f"  -> {len(doc_files)} Dokumente gefunden.")
    
    for f in doc_files:
        fname = f['name']
        fid = f['id']
        fmime = f['mimeType']
        mod_time = f.get('modifiedTime', '')
        
        last_mod = state[course_name].get(fname)
        
        if fname in source_map and last_mod == mod_time:
            print(f"    - [OK] '{fname}' ist aktuell.")
            continue
            
        if fname in source_map and last_mod != mod_time:
            print(f"    - [UPDATE] '{fname}' hat eine neue Version. Ersetze...")
            await client.sources.delete(notebook.id, source_map[fname].id)
        else:
            print(f"    - [NEU] Lade '{fname}' hoch...")
            
        try:
            if fmime == 'application/vnd.google-apps.document':
                request = gw.drive_service.files().export_media(fileId=fid, mimeType='text/plain')
                content = request.execute()
                await client.sources.add_text(notebook.id, content.decode('utf-8', errors='ignore'), title=fname)
            else:
                request = gw.drive_service.files().get_media(fileId=fid)
                content = request.execute()
                await client.sources.add_text(notebook.id, content.decode('utf-8', errors='ignore'), title=fname)
            
            state[course_name][fname] = mod_time
            save_state(state)
        except Exception as e:
            print(f"      Fehler: {e}")

async def login_if_needed():
    try:
        async with NotebookLMClient.from_storage() as client:
            await client.notebooks.list()
            return True
    except:
        return False

async def main():
    if not await login_if_needed(): return
    root_id = get_config()
    if not root_id: return
    
    gw = GoogleWorkspace()
    state = load_state()
    query = f"'{root_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"
    courses = gw.drive_service.files().list(q=query, fields="files(id, name)").execute().get('files', [])
    
    async with NotebookLMClient.from_storage() as client:
        for course in courses:
            print(f"Pruefe Fach: {course['name']}")
            await sync_course(client, gw, state, course['name'], course['id'])

if __name__ == "__main__":
    asyncio.run(main())
