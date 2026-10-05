from flask import Flask, render_template_string, jsonify, request, send_file
import subprocess
import os
import threading
from datetime import datetime, timedelta
from dotenv import set_key, dotenv_values
import json

app = Flask(__name__)

from functools import wraps
from flask import request, Response

def check_auth(username, password):
    # Das Passwort kann später auch aus der .env gelesen werden
    expected_pass = dotenv_values(ENV_FILE).get("DASHBOARD_PASS", "hslu2026")
    return username == 'admin' and password == expected_pass

def authenticate():
    return Response('Login erforderlich.', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service_account.json')

# Modern HTML-Template with Tailwind CSS and Tabs
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSLU AI Agent</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🤖</text></svg>">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <script>
        tailwind.config = { theme: { extend: { colors: { brand: '#0078d4', } } } }
        
        function switchTab(tabId) {
            document.getElementById('dashboard-tab').classList.add('hidden');
            document.getElementById('settings-tab').classList.add('hidden');
            document.getElementById(tabId).classList.remove('hidden');
            
            document.getElementById('nav-dashboard').classList.remove('border-brand', 'text-brand');
            document.getElementById('nav-settings').classList.remove('border-brand', 'text-brand');
            document.getElementById('nav-dashboard').classList.add('border-transparent', 'text-gray-500');
            document.getElementById('nav-settings').classList.add('border-transparent', 'text-gray-500');
            
            if(tabId === 'dashboard-tab') {
                document.getElementById('nav-dashboard').classList.remove('border-transparent', 'text-gray-500');
                document.getElementById('nav-dashboard').classList.add('border-brand', 'text-brand');
            } else {
                document.getElementById('nav-settings').classList.remove('border-transparent', 'text-gray-500');
                document.getElementById('nav-settings').classList.add('border-brand', 'text-brand');
                loadSettings();
            }
        }
        
        function updateDashboard() {
            if (!document.getElementById('dashboard-tab').classList.contains('hidden')) {
                fetch('/log')
                    .then(r => r.text())
                    .then(text => {
                        const term = document.getElementById('terminal');
                        const isScrolledToBottom = term.scrollHeight - term.clientHeight <= term.scrollTop + 50;
                        term.textContent = text;
                        if (isScrolledToBottom) { term.scrollTop = term.scrollHeight; }
                    });
                
                fetch('/status')
                    .then(r => r.json())
                    .then(data => {
                        const statusBadge = document.getElementById('status-badge');
                        const statusText = document.getElementById('status-text');
                        const statusIcon = document.getElementById('status-icon');
                        const btn = document.getElementById('run-btn');
                        const testBtns = document.querySelectorAll('.test-btn');
                        document.getElementById('next-run').textContent = data.next_run;
                        
                        if (data.is_running) {
                            statusBadge.className = "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800";
                            statusText.textContent = "Agent arbeitet gerade...";
                            statusIcon.className = "fas fa-cog fa-spin mr-2";
                            btn.disabled = true;
                            btn.className = "w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-gray-400 cursor-not-allowed";
                            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Prozess läuft...';
                            testBtns.forEach(b => { b.disabled = true; b.classList.add('opacity-50', 'cursor-not-allowed'); });
                        } else {
                            statusBadge.className = "inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800";
                            statusText.textContent = "Bereit (Wartet auf Zeitplan)";
                            statusIcon.className = "fas fa-check-circle mr-2";
                            btn.disabled = false;
                            btn.className = "w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-brand hover:bg-blue-700 transition-colors";
                            btn.innerHTML = '<i class="fas fa-rocket mr-2"></i> Agent jetzt manuell starten';
                            testBtns.forEach(b => { b.disabled = false; b.classList.remove('opacity-50', 'cursor-not-allowed'); });
                        }
                    });
            }
        }
        
        function loadSettings() {
            fetch('/api/settings')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('HSLU_USERNAME').value = data.HSLU_USERNAME || '';
                    document.getElementById('HSLU_PASSWORD').value = data.HSLU_PASSWORD || '';
                    document.getElementById('HSLU_TOTP_SECRET').value = data.HSLU_TOTP_SECRET || '';
                    document.getElementById('GEMINI_API_KEY').value = data.GEMINI_API_KEY || '';
                    document.getElementById('GOOGLE_DRIVE_FOLDER_ID').value = data.GOOGLE_DRIVE_FOLDER_ID || '';
                    document.getElementById('GOOGLE_SERVICE_JSON').value = data.GOOGLE_SERVICE_JSON || '';
                    document.getElementById('NOTEBOOKLM_COOKIES').value = data.NOTEBOOKLM_COOKIES || '';
                });
        }
        
        function saveSettings(e) {
            e.preventDefault();
            const btn = document.getElementById('save-btn');
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Speichere...';
            
            const payload = {
                HSLU_USERNAME: document.getElementById('HSLU_USERNAME').value,
                HSLU_PASSWORD: document.getElementById('HSLU_PASSWORD').value,
                HSLU_TOTP_SECRET: document.getElementById('HSLU_TOTP_SECRET').value,
                GEMINI_API_KEY: document.getElementById('GEMINI_API_KEY').value,
                GOOGLE_DRIVE_FOLDER_ID: document.getElementById('GOOGLE_DRIVE_FOLDER_ID').value,
                GOOGLE_SERVICE_JSON: document.getElementById('GOOGLE_SERVICE_JSON').value,
                    NOTEBOOKLM_COOKIES: document.getElementById('NOTEBOOKLM_COOKIES').value
            };
            
            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(r => r.json())
            .then(data => {
                if (data.error) {
                    alert('Fehler beim Speichern der JSON-Datei: ' + data.error);
                } else {
                    alert('Einstellungen erfolgreich gespeichert!');
                }
                btn.innerHTML = '<i class="fas fa-save mr-2"></i> Einstellungen Speichern';
            });
        }
        
        function runAgent() { fetch('/run', {method: 'POST'}).then(r => r.json()).then(d => updateDashboard()); }
        function runTest(testType) { fetch('/test/' + testType, {method: 'POST'}).then(r => r.json()).then(d => updateDashboard()); }
        
        setInterval(updateDashboard, 2000);
        window.onload = updateDashboard;
    </script>
</head>
<body class="h-full">
    <div class="min-h-full">
        <!-- Navbar -->
        <nav class="bg-gray-800">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex items-center justify-between h-16">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 text-white font-bold text-xl flex items-center">
                            <i class="fas fa-robot text-brand mr-3 text-2xl"></i>
                            HSLU KI-Studienassistent
                        </div>
                    </div>
                </div>
            </div>
        </nav>
        
        <!-- Tabs -->
        <div class="bg-white border-b border-gray-200">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <nav class="-mb-px flex space-x-8" aria-label="Tabs">
                    <button id="nav-dashboard" onclick="switchTab('dashboard-tab')" class="border-brand text-brand whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm">
                        <i class="fas fa-tachometer-alt mr-2"></i> Dashboard
                    </button>
                    <button id="nav-settings" onclick="switchTab('settings-tab')" class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm">
                        <i class="fas fa-cog mr-2"></i> Konfiguration
                    </button>
                </nav>
            </div>
        </div>

        <main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
            <!-- DASHBOARD TAB -->
            <div id="dashboard-tab" class="px-4 sm:px-0">
                <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
                    <div class="lg:col-span-1 space-y-6">
                        <div class="bg-white overflow-hidden shadow rounded-lg">
                            <div class="p-5">
                                <div class="flex items-center">
                                    <div class="flex-shrink-0"><i class="fas fa-server text-gray-400 text-3xl"></i></div>
                                    <div class="ml-5 w-0 flex-1">
                                        <dl>
                                            <dt class="text-sm font-medium text-gray-500 truncate">Systemstatus</dt>
                                            <dd class="mt-2">
                                                <span id="status-badge" class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-800">
                                                    <i id="status-icon" class="fas fa-circle-notch mr-2"></i>
                                                    <span id="status-text">Lade Status...</span>
                                                </span>
                                            </dd>
                                        </dl>
                                    </div>
                                </div>
                            </div>
                            <div class="bg-gray-50 px-5 py-3">
                                <div class="text-sm text-gray-500">
                                    <i class="far fa-calendar-alt mr-2"></i>Nächster Start: <br>
                                    <strong id="next-run" class="text-gray-900 ml-6">Lädt...</strong>
                                </div>
                            </div>
                        </div>

                        <div class="bg-white overflow-hidden shadow rounded-lg p-5 border-t-4 border-brand">
                            <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4">Hauptsteuerung</h3>
                            <button id="run-btn" onclick="runAgent()" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-brand hover:bg-blue-700">
                                <i class="fas fa-rocket mr-2"></i> Agent jetzt manuell starten
                            </button>
                        </div>
                        
                        <div class="bg-white overflow-hidden shadow rounded-lg p-5">
                            <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4">Verbindungen Testen</h3>
                            <div class="space-y-3">
                                <button onclick="runTest('google')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fab fa-google text-red-500 mr-2"></i> Google Drive & Docs</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                                <button onclick="runTest('gemini')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fas fa-brain text-purple-500 mr-2"></i> Gemini KI API</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                                <button onclick="runTest('ilias')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fas fa-university text-blue-500 mr-2"></i> HSLU ILIAS Login</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="lg:col-span-2">
                        <div class="bg-gray-900 rounded-lg shadow flex flex-col h-[400px] border border-gray-700 mb-6">
                            <div class="bg-gray-800 px-4 py-2 border-b border-gray-700 rounded-t-lg flex items-center">
                                <i class="fas fa-eye text-gray-400 mr-2"></i>
                                <div class="text-xs text-gray-400 font-mono">Live Browser View (Auto-Refresh)</div>
                            </div>
                            <div class="p-2 flex-1 flex items-center justify-center overflow-hidden bg-black">
                                <img id="live-view" src="/api/current_view" alt="Waiting for screenshot..." class="max-h-full max-w-full object-contain" onerror="this.style.display='none'" onload="this.style.display='block'">
                            </div>
                        </div>
                        <div class="bg-gray-900 rounded-lg shadow flex flex-col h-[400px] border border-gray-700">
                            <div class="bg-gray-800 px-4 py-2 border-b border-gray-700 rounded-t-lg flex items-center">
                                <div class="flex space-x-2">
                                    <div class="w-3 h-3 rounded-full bg-red-500"></div>
                                    <div class="w-3 h-3 rounded-full bg-yellow-500"></div>
                                    <div class="w-3 h-3 rounded-full bg-green-500"></div>
                                </div>
                                <div class="ml-4 text-xs text-gray-400 font-mono">agent.log — Live Terminal</div>
                            </div>
                            <div id="terminal" class="p-4 flex-1 overflow-y-auto text-green-400 font-mono text-sm whitespace-pre-wrap">Lade Logs...</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- SETTINGS TAB -->
            <div id="settings-tab" class="hidden px-4 sm:px-0 max-w-4xl mx-auto">
                <div class="bg-white shadow overflow-hidden sm:rounded-lg mb-6">
                    <div class="px-4 py-5 sm:px-6 border-b border-gray-200">
                        <h3 class="text-lg leading-6 font-medium text-gray-900"><i class="fas fa-cogs text-gray-400 mr-2"></i> Agent Konfiguration</h3>
                        <p class="mt-1 max-w-2xl text-sm text-gray-500">Diese Einstellungen werden sicher in der .env und service_account.json Datei auf dem Server gespeichert.</p>
                    </div>
                    <form onsubmit="saveSettings(event)" class="px-4 py-5 sm:p-6 space-y-6">
                        
                        <div>
                            <h4 class="text-md font-medium text-gray-900 mb-4 border-b pb-2"><i class="fas fa-university text-blue-500 mr-2"></i> HSLU & SWITCH edu-ID</h4>
                            <div class="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-2">
                                <div class="sm:col-span-2">
                                    <label class="block text-sm font-medium text-gray-700">HSLU E-Mail Adresse</label>
                                    <input type="text" id="HSLU_USERNAME" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border">
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">Passwort</label>
                                    <input type="password" id="HSLU_PASSWORD" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border">
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">TOTP Secret (2FA)</label>
                                    <input type="password" id="HSLU_TOTP_SECRET" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border">
                                </div>
                            </div>
                        </div>

                        <div class="pt-4">
                            <h4 class="text-md font-medium text-gray-900 mb-4 border-b pb-2"><i class="fas fa-brain text-purple-500 mr-2"></i> Künstliche Intelligenz</h4>
                            <div>
                                <label class="block text-sm font-medium text-gray-700">Gemini API Key</label>
                                <input type="password" id="GEMINI_API_KEY" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border">
                            </div>
                        </div>

                        <div class="pt-4">
                            <h4 class="text-md font-medium text-gray-900 mb-4 border-b pb-2"><i class="fab fa-google text-red-500 mr-2"></i> Google Drive & Docs API</h4>
                            <div class="space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">Google Drive Ziel-Ordner ID (Root-Ordner)</label>
                                    <p class="text-xs text-gray-500 mb-1">Zu finden in der URL deines Drive-Ordners: drive.google.com/drive/folders/<b>DEINE_ID_HIER</b></p>
                                    <input type="text" id="GOOGLE_DRIVE_FOLDER_ID" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border">
                                </div>
                                
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">Google Service Account JSON (Für Drive & Docs API)</label>
                                    <p class="text-xs text-gray-500 mb-1">Füge hier den kompletten Inhalt der service_account.json (oder credentials.json) ein.</p>
                                    <textarea id="GOOGLE_SERVICE_JSON" rows="6" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border font-mono text-xs" placeholder='{ "type": "service_account", "project_id": "..." }'></textarea>
                                </div>
                            </div>
                            </div>
                            
                            <h4 class="text-md font-medium text-gray-900 mb-4 border-b pb-2 mt-8"><i class="fas fa-podcast text-indigo-500 mr-2"></i> NotebookLM (Audio Podcasts)</h4>
                            <div class="space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">NotebookLM Cookie JSON</label>
                                    <p class="text-xs text-gray-500 mb-1">Füge hier die exportierten JSON-Cookies von notebooklm.google.com ein (via EditThisCookie o.ä.).</p>
                                    <textarea id="NOTEBOOKLM_COOKIES" rows="6" class="mt-1 focus:ring-brand focus:border-brand block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border font-mono text-xs" placeholder='[{"domain": ".google.com", "name": "SID", ...}]'></textarea>
                                </div>
                            </div>

                        <div class="pt-6">
                            <button type="submit" id="save-btn" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700">
                                <i class="fas fa-save mr-2"></i> Einstellungen Speichern
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            
        </main>
    </div>
</body>
</html>
"""

LOG_FILE = "agent_run.log"
process = None

def get_next_sunday():
    now = datetime.now()
    days_ahead = 6 - now.weekday()
    if days_ahead <= 0: days_ahead += 7
    next_sunday = now + timedelta(days=days_ahead)
    return next_sunday.replace(hour=18, minute=0, second=0).strftime("%A, %d.%m.%Y - 18:00 Uhr")

def run_script_task(cmd_list, title):
    global process
    with open(LOG_FILE, "a") as f:
        f.write("\\n\\n" + "="*70 + "\\n")
        f.write(f"{title} - {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\\n")
        f.write("="*70 + "\\n")
    process = subprocess.Popen(cmd_list, stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT)
    process.wait()

@app.route('/')
def index(): return render_template_string(HTML_TEMPLATE)

@app.route('/api/current_view')
def get_current_view():
    import os
    path = os.path.join("downloads", "current_view.png")
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return "", 404

@app.route('/log')
def get_log():
    if not os.path.exists(LOG_FILE): return "System bereit. Noch keine Log-Einträge vorhanden."
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f: return "".join(f.readlines()[-300:])

@app.route('/status')
def get_status():
    global process
    is_running = process is not None and process.poll() is None
    return jsonify({"is_running": is_running, "next_run": get_next_sunday()})

@app.route('/run', methods=['POST'])
def run_now():
    global process
    if process is not None and process.poll() is None: return jsonify({"message": "Läuft bereits!"})
    threading.Thread(target=run_script_task, args=(["bash", "-c", "/opt/KiAgentHSLU/venv/bin/python -u run_weeks.py"], "HAUPT-DURCHLAUF (NEW)")).start()
    return jsonify({"message": "Gestartet!"})

@app.route('/test/<test_type>', methods=['POST'])
def run_test(test_type):
    global process
    if process is not None and process.poll() is None: return jsonify({"message": "Ein anderer Prozess läuft bereits!"})
    cmd_map = {
        "google": (["python", "tests/test_google_drive.py"], "TEST: GOOGLE DRIVE API"),
        "gemini": (["python", "tests/test_setup.py"], "TEST: GEMINI KI API & SETUP"),
        "ilias": (["python", "tests/test_login.py"], "TEST: HSLU ILIAS LOGIN")
    }
    if test_type not in cmd_map: return jsonify({"message": "Unbekannter Test!"})
    cmd, title = cmd_map[test_type]
    threading.Thread(target=run_script_task, args=(cmd, title)).start()
    return jsonify({"message": f"{title} gestartet!"})

@app.route('/api/settings', methods=['GET'])
def get_settings():
    if not os.path.exists(ENV_FILE): open(ENV_FILE, 'a').close()
    config = dotenv_values(ENV_FILE)
    
    # Read service_account.json or credentials.json
    service_json_content = ""
    if os.path.exists(SERVICE_ACCOUNT_FILE):
        with open(SERVICE_ACCOUNT_FILE, "r", encoding="utf-8") as f:
            service_json_content = f.read()
    elif os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')):
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json'), "r", encoding="utf-8") as f:
            service_json_content = f.read()
            
    return jsonify({
        "HSLU_USERNAME": config.get("HSLU_USERNAME", ""),
        "HSLU_PASSWORD": config.get("HSLU_PASSWORD", ""),
        "HSLU_TOTP_SECRET": config.get("HSLU_TOTP_SECRET", ""),
        "GEMINI_API_KEY": config.get("GEMINI_API_KEY", ""),
        "GOOGLE_DRIVE_FOLDER_ID": config.get("GOOGLE_DRIVE_FOLDER_ID", "").strip("'").strip('"'),
        "GOOGLE_SERVICE_JSON": service_json_content,
        "NOTEBOOKLM_COOKIES": "" if not os.path.exists('notebooklm_cookies.json') else open('notebooklm_cookies.json').read()
    })

@app.route('/api/settings', methods=['POST'])
def save_settings():
    data = request.json
    if not os.path.exists(ENV_FILE): open(ENV_FILE, 'a').close()
    
    # Extract service account JSON
    service_json = data.pop("GOOGLE_SERVICE_JSON", "")
    nblm_cookies = data.pop("NOTEBOOKLM_COOKIES", "")
    if nblm_cookies and nblm_cookies.strip() != "":
        with open('notebooklm_cookies.json', 'w') as f:
            f.write(nblm_cookies)
        import subprocess
        try:
            subprocess.run(["/opt/KiAgentHSLU/venv/bin/python", "-m", "notebooklm", "auth", "import-cookies", "notebooklm_cookies.json"], check=False)
        except:
            pass

    if service_json and service_json.strip() != "":
        try:
            # Validate JSON format
            parsed_json = json.loads(service_json)
            # Save it to the appropriate file depending on type
            # Standard ist service_account.json
            target_file = SERVICE_ACCOUNT_FILE
            # Falls es ein standard OAuth Credentials File ist
            if "installed" in parsed_json or "web" in parsed_json:
                target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
                
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    for key, value in data.items():
        if key == "GOOGLE_DRIVE_FOLDER_ID" and value:
            value = f"'{value}'" if not value.startswith("'") else value
        set_key(ENV_FILE, key, str(value))
        
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)






