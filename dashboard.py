from flask import Flask, render_template_string, jsonify, request, send_file, Response
import subprocess
import os
import threading
from datetime import datetime, timedelta
from dotenv import set_key, dotenv_values
import json
import hmac
from functools import wraps

app = Flask(__name__)

ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'service_account.json')
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'agent_run.log')
process = None

def check_auth(username, password):
    # Kein Standardpasswort: ohne DASHBOARD_PASS ist der Zugang gesperrt.
    expected_pass = dotenv_values(ENV_FILE).get("DASHBOARD_PASS")
    if not expected_pass:
        return False
    return (hmac.compare_digest(username or "", "admin")
            & hmac.compare_digest(password or "", expected_pass))

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

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de" class="h-full bg-gray-50">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSLU KI-Studienassistent</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🤖</text></svg>">
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        brand: '#0078d4',
                        brandHover: '#005a9e'
                    }
                }
            }
        }
        
        
        function switchTab(tabId) {
            document.getElementById('dashboard-tab').classList.add('hidden');
            document.getElementById('settings-tab').classList.add('hidden');
            document.getElementById('live-tab').classList.add('hidden');
            document.getElementById(tabId).classList.remove('hidden');
            
            ['dashboard', 'live', 'settings'].forEach(id => {
                document.getElementById('nav-' + id).classList.remove('border-brand', 'text-brand');
                document.getElementById('nav-' + id).classList.add('border-transparent', 'text-gray-500');
            });
            
            let activeNav = tabId.replace('-tab', '');
            document.getElementById('nav-' + activeNav).classList.remove('border-transparent', 'text-gray-500');
            document.getElementById('nav-' + activeNav).classList.add('border-brand', 'text-brand');
            
            if (tabId === 'settings-tab') loadSettings();
            if (tabId === 'live-tab') loadLiveMeetings();
        }

        
        
        function loadLiveMeetings() {
            fetch('/api/live_meetings')
                .then(r => r.json())
                .then(data => {
                    const c = document.getElementById('live-meetings-container');
                    if (data.length === 0) {
                        c.innerHTML = '<p class="text-sm text-gray-500">Keine Fächer gefunden. Klicken Sie auf "Fächer erkennen".</p>';
                        return;
                    }
                    let html = '';
                    data.forEach((m, idx) => {
                        html += `
                        <div class="bg-gray-50 p-4 rounded border flex flex-col md:flex-row md:items-center gap-4">
                            <div class="md:w-1/4 font-medium text-gray-800" title="${m.title}">${m.title.length > 30 ? m.title.substring(0,27)+'...' : m.title}</div>
                            <input type="hidden" class="m-title" value="${m.title}">
                            <div class="md:w-1/6">
                                <label class="text-xs text-gray-500 block mb-1">Meeting ID/Link</label>
                                <input type="text" class="m-id w-full p-2 border rounded text-sm" value="${m.meeting_id || ''}">
                            </div>
                            <div class="md:w-1/6">
                                <label class="text-xs text-gray-500 block mb-1">Passcode</label>
                                <input type="text" class="m-pass w-full p-2 border rounded text-sm" value="${m.passcode || ''}">
                            </div>
                            <div class="md:w-1/6">
                                <label class="text-xs text-gray-500 block mb-1">Wochentag</label>
                                <select class="m-day w-full p-2 border rounded text-sm">
                                    <option value="1" ${m.day == '1' ? 'selected' : ''}>Montag</option>
                                    <option value="2" ${m.day == '2' ? 'selected' : ''}>Dienstag</option>
                                    <option value="3" ${m.day == '3' ? 'selected' : ''}>Mittwoch</option>
                                    <option value="4" ${m.day == '4' ? 'selected' : ''}>Donnerstag</option>
                                    <option value="5" ${m.day == '5' ? 'selected' : ''}>Freitag</option>
                                    <option value="6" ${m.day == '6' ? 'selected' : ''}>Samstag</option>
                                    <option value="0" ${m.day == '0' ? 'selected' : ''}>Sonntag</option>
                                </select>
                            </div>
                            <div class="md:w-1/6">
                                <label class="text-xs text-gray-500 block mb-1">Von - Bis</label>
                                <div class="flex items-center space-x-1">
                                    <input type="time" class="m-time-start w-full p-2 border rounded text-sm" value="${m.time_start || ''}">
                                    <span class="text-gray-500">-</span>
                                    <input type="time" class="m-time-end w-full p-2 border rounded text-sm" value="${m.time_end || ''}">
                                </div>
                            </div>
                            <div class="md:w-1/6 flex items-center justify-end md:mt-5">
                                <label class="flex items-center space-x-2 cursor-pointer">
                                    <input type="checkbox" class="m-record w-5 h-5 text-brand rounded border-gray-300" ${m.record ? 'checked' : ''}>
                                    <span class="text-sm font-medium">Abhören</span>
                                </label>
                            </div>
                        </div>`;
                    });
                    c.innerHTML = html;
                });
        }
        
        function saveLiveMeetings() {
            const rows = document.querySelectorAll('#live-meetings-container > div');
            let data = [];
            rows.forEach(r => {
                data.push({
                    title: r.querySelector('.m-title').value,
                    meeting_id: r.querySelector('.m-id').value,
                    passcode: r.querySelector('.m-pass').value,
                    day: r.querySelector('.m-day').value,
                    time_start: r.querySelector('.m-time-start').value,
                    time_end: r.querySelector('.m-time-end').value,
                    record: r.querySelector('.m-record').checked
                });
            });
            fetch('/api/live_meetings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(r => r.json()).then(res => {
                alert('Gespeichert!');
            });
        }
        
        function detectSubjects() {
            if (confirm("Achtung: Dies überschreibt alle bisherigen Meeting-Einträge. Fortfahren?")) {
                const btn = event.currentTarget;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Analysiere ILIAS...';
                btn.disabled = true;
                
                fetch('/api/detect_subjects', {method: 'POST'})
                    .then(r => r.json())
                    .then(res => {
                        alert(res.message);
                        loadLiveMeetings();
                        btn.innerHTML = '<i class="fas fa-magic mr-2"></i> Fächer erkennen';
                        btn.disabled = false;
                    })
                    .catch(e => {
                        alert("Fehler!");
                        btn.innerHTML = '<i class="fas fa-magic mr-2"></i> Fächer erkennen';
                        btn.disabled = false;
                    });
            }
        }
        
        function toggleVisibility
(inputId, btn) {
            const input = document.getElementById(inputId);
            const icon = btn.querySelector('i');
            if (input.type === 'password') {
                input.type = 'text';
                icon.className = 'fas fa-eye-slash text-gray-700';
            } else {
                input.type = 'password';
                icon.className = 'fas fa-eye text-gray-400';
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
                            btn.className = "w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-brand hover:bg-brandHover transition-colors";
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
                    document.getElementById('HSLU_MS_EMAIL').value = data.HSLU_MS_EMAIL || '';
                    document.getElementById('HSLU_MS_PASSWORD').value = data.HSLU_MS_PASSWORD || '';
                    document.getElementById('HSLU_MS_TOTP_SECRET').value = data.HSLU_MS_TOTP_SECRET || '';
                    document.getElementById('DASHBOARD_PASS').value = data.DASHBOARD_PASS || '';
                    document.getElementById('GEMINI_API_KEY').value = data.GEMINI_API_KEY || '';
                    document.getElementById('GOOGLE_DRIVE_FOLDER_ID').value = data.GOOGLE_DRIVE_FOLDER_ID || '';
                    document.getElementById('GOOGLE_SERVICE_JSON').value = data.GOOGLE_SERVICE_JSON || '';
                    document.getElementById('NOTEBOOKLM_COOKIES').value = data.NOTEBOOKLM_COOKIES || '';
                    
                    // Update quick cards
                    const iliasBadge = document.getElementById('card-ilias-status');
                    if (iliasBadge) {
                        iliasBadge.innerHTML = data.HSLU_PASSWORD ? '<span class="text-green-600 font-semibold"><i class="fas fa-check-circle mr-1"></i>Aktiv</span>' : '<span class="text-amber-500 font-semibold"><i class="fas fa-exclamation-triangle mr-1"></i>Fehlt</span>';
                    }
                    const msBadge = document.getElementById('card-ms-status');
                    if (msBadge) {
                        msBadge.innerHTML = data.HSLU_MS_PASSWORD ? '<span class="text-green-600 font-semibold"><i class="fas fa-check-circle mr-1"></i>Aktiv</span>' : '<span class="text-amber-500 font-semibold"><i class="fas fa-exclamation-triangle mr-1"></i>Fehlt</span>';
                    }
                    const driveBadge = document.getElementById('card-drive-status');
                    if (driveBadge) {
                        driveBadge.innerHTML = data.GOOGLE_DRIVE_FOLDER_ID ? '<span class="text-green-600 font-semibold"><i class="fas fa-check-circle mr-1"></i>Aktiv</span>' : '<span class="text-amber-500 font-semibold"><i class="fas fa-exclamation-triangle mr-1"></i>Fehlt</span>';
                    }
                });
        }
        
        function saveSettings(e) {
            e.preventDefault();
            const btn = document.getElementById('save-btn');
            const alertBox = document.getElementById('save-alert');
            btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i> Speichere Daten...';
            btn.disabled = true;
            
            const payload = {
                HSLU_USERNAME: document.getElementById('HSLU_USERNAME').value.trim(),
                HSLU_PASSWORD: document.getElementById('HSLU_PASSWORD').value.trim(),
                HSLU_TOTP_SECRET: document.getElementById('HSLU_TOTP_SECRET').value.trim(),
                HSLU_MS_EMAIL: document.getElementById('HSLU_MS_EMAIL').value.trim(),
                HSLU_MS_PASSWORD: document.getElementById('HSLU_MS_PASSWORD').value.trim(),
                HSLU_MS_TOTP_SECRET: document.getElementById('HSLU_MS_TOTP_SECRET').value.trim(),
                DASHBOARD_PASS: document.getElementById('DASHBOARD_PASS').value.trim(),
                GEMINI_API_KEY: document.getElementById('GEMINI_API_KEY').value.trim(),
                GOOGLE_DRIVE_FOLDER_ID: document.getElementById('GOOGLE_DRIVE_FOLDER_ID').value.trim(),
                GOOGLE_SERVICE_JSON: document.getElementById('GOOGLE_SERVICE_JSON').value.trim(),
                NOTEBOOKLM_COOKIES: document.getElementById('NOTEBOOKLM_COOKIES').value.trim()
            };
            
            fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(r => r.json())
            .then(data => {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-save mr-2"></i> Einstellungen & Logins Speichern';
                alertBox.classList.remove('hidden');
                if (data.error) {
                    alertBox.className = "p-4 mb-4 rounded-md bg-red-100 text-red-800 border border-red-300";
                    alertBox.innerHTML = '<i class="fas fa-times-circle mr-2"></i> Fehler: ' + data.error;
                } else {
                    alertBox.className = "p-4 mb-4 rounded-md bg-green-100 text-green-800 border border-green-300";
                    alertBox.innerHTML = '<i class="fas fa-check-circle mr-2"></i> <b>Erfolgreich gespeichert!</b> Alle Zugangsdaten wurden aktualisiert und sind sofort aktiv.';
                    loadSettings();
                    setTimeout(() => { alertBox.classList.add('hidden'); }, 6000);
                }
            })
            .catch(err => {
                btn.disabled = false;
                btn.innerHTML = '<i class="fas fa-save mr-2"></i> Einstellungen & Logins Speichern';
                alertBox.classList.remove('hidden');
                alertBox.className = "p-4 mb-4 rounded-md bg-red-100 text-red-800 border border-red-300";
                alertBox.innerHTML = '<i class="fas fa-times-circle mr-2"></i> Verbindungsfehler: ' + err;
            });
        }
        
        function runAgent() { fetch('/run', {method: 'POST'}).then(r => r.json()).then(d => updateDashboard()); }
        function runTest(testType) { fetch('/test/' + testType, {method: 'POST'}).then(r => r.json()).then(d => updateDashboard()); }
        
        setInterval(updateDashboard, 2000);
        window.addEventListener('DOMContentLoaded', () => {
            updateDashboard();
            loadSettings();
        });
    </script>
</head>
<body class="h-full">
    <div class="min-h-full">
        <!-- Navbar -->
        <nav class="bg-gray-900 border-b border-gray-800">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div class="flex items-center justify-between h-16">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 text-white font-bold text-xl flex items-center">
                            <i class="fas fa-graduation-cap text-blue-400 mr-3 text-2xl"></i>
                            HSLU KI-Studienassistent
                        </div>
                    </div>
                    <div class="text-xs text-gray-400 font-mono hidden sm:block">
                        <i class="fas fa-shield-alt text-green-400 mr-1"></i> HSLU & Cloud Sync Node
                    </div>
                </div>
            </div>
        </nav>
        
        <!-- Tabs -->
        <div class="bg-white border-b border-gray-200 shadow-sm sticky top-0 z-10">
            <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <nav class="-mb-px flex space-x-8" aria-label="Tabs">
                    <button id="nav-dashboard" onclick="switchTab('dashboard-tab')" class="border-brand text-brand whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center">
                        <i class="fas fa-tachometer-alt mr-2"></i> Dashboard & Status
                    </button>
                    <button id="nav-live" onclick="switchTab('live-tab')" class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center">
                        <i class="fas fa-video mr-2"></i> Live-Meetings
                    </button>
                    <button id="nav-settings" onclick="switchTab('settings-tab')" class="border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex items-center">
                        <i class="fas fa-key mr-2 text-amber-500"></i> Logins & Zugangsdaten
                    </button>
                </nav>
            </div>
        </div>

        <main class="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
            <!-- DASHBOARD TAB -->
            <div id="dashboard-tab" class="px-4 sm:px-0">
                <div class="grid grid-cols-1 gap-6 lg:grid-cols-3">
                    <div class="lg:col-span-1 space-y-6">
                        
                        <!-- Systemstatus Card -->
                        <div class="bg-white overflow-hidden shadow rounded-lg border border-gray-100">
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
                            <div class="bg-gray-50 px-5 py-3 border-t border-gray-100">
                                <div class="text-sm text-gray-500">
                                    <i class="far fa-calendar-alt mr-2 text-brand"></i>Nächster Auto-Lauf: <br>
                                    <strong id="next-run" class="text-gray-900 ml-6">Lädt...</strong>
                                </div>
                            </div>
                        </div>

                        <!-- Steuerung Card -->
                        <div class="bg-white overflow-hidden shadow rounded-lg p-5 border-t-4 border-brand">
                            <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4 flex items-center">
                                <i class="fas fa-play text-brand mr-2"></i> Hauptsteuerung
                            </h3>
                            <button id="run-btn" onclick="runAgent()" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-brand hover:bg-brandHover">
                                <i class="fas fa-rocket mr-2"></i> Agent jetzt manuell starten
                            </button>
                        </div>
                        
                        <!-- Gespeicherte Zugänge Quick-Card -->
                        <div class="bg-white overflow-hidden shadow rounded-lg p-5 border border-gray-100">
                            <div class="flex items-center justify-between mb-3 border-b pb-2">
                                <h3 class="text-base font-medium text-gray-900 flex items-center">
                                    <i class="fas fa-shield-alt text-amber-500 mr-2"></i> Zugangsdaten-Status
                                </h3>
                                <button onclick="switchTab('settings-tab')" class="text-xs text-brand hover:underline font-medium">
                                    Pflegen <i class="fas fa-arrow-right ml-1"></i>
                                </button>
                            </div>
                            <div class="space-y-2 text-sm">
                                <div class="flex justify-between items-center py-1">
                                    <span class="text-gray-600"><i class="fas fa-university text-blue-500 mr-2"></i>ILIAS (Switch edu-ID)</span>
                                    <span id="card-ilias-status"><i class="fas fa-spinner fa-spin text-gray-400"></i></span>
                                </div>
                                <div class="flex justify-between items-center py-1">
                                    <span class="text-gray-600"><i class="fas fa-video text-blue-600 mr-2"></i>Microsoft 365 & Zoom</span>
                                    <span id="card-ms-status"><i class="fas fa-spinner fa-spin text-gray-400"></i></span>
                                </div>
                                <div class="flex justify-between items-center py-1">
                                    <span class="text-gray-600"><i class="fab fa-google text-red-500 mr-2"></i>Google Drive Cloud</span>
                                    <span id="card-drive-status"><i class="fas fa-spinner fa-spin text-gray-400"></i></span>
                                </div>
                            </div>
                            <button onclick="switchTab('settings-tab')" class="mt-4 w-full flex justify-center py-2 px-3 border border-gray-300 rounded-md shadow-sm text-xs font-medium text-gray-700 bg-gray-50 hover:bg-gray-100">
                                <i class="fas fa-key mr-2 text-amber-500"></i> Zugangsdaten öffnen & ändern
                            </button>
                        </div>

                        <!-- Tests Card -->
                        <div class="bg-white overflow-hidden shadow rounded-lg p-5 border border-gray-100">
                            <h3 class="text-lg leading-6 font-medium text-gray-900 mb-4 flex items-center">
                                <i class="fas fa-vial text-purple-500 mr-2"></i> Verbindungen Testen
                            </h3>
                            <div class="space-y-3">
                                <button onclick="runTest('ilias')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fas fa-university text-blue-500 mr-2"></i> 1. HSLU ILIAS Login</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                                <button onclick="runTest('zoom')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-blue-200 shadow-sm text-sm font-medium rounded-md text-blue-800 bg-blue-50 hover:bg-blue-100">
                                    <span class="flex items-center"><i class="fas fa-video text-blue-600 mr-2"></i> 2. Zoom & Microsoft Login</span>
                                    <i class="fas fa-play text-blue-500"></i>
                                </button>
                                <button onclick="runTest('google')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fab fa-google text-red-500 mr-2"></i> 3. Google Drive Sync</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                                <button onclick="runTest('gemini')" class="test-btn w-full flex items-center justify-between px-4 py-2 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50">
                                    <span class="flex items-center"><i class="fas fa-brain text-purple-500 mr-2"></i> 4. Gemini KI API</span>
                                    <i class="fas fa-play text-gray-400"></i>
                                </button>
                            </div>
                        </div>

                    </div>
                    
                    <!-- Right Column: Terminal & View -->
                    <div class="lg:col-span-2">
                        <div class="bg-gray-900 rounded-lg shadow flex flex-col h-[350px] border border-gray-700 mb-6">
                            <div class="bg-gray-800 px-4 py-2 border-b border-gray-700 rounded-t-lg flex items-center justify-between">
                                <div class="flex items-center">
                                    <i class="fas fa-eye text-blue-400 mr-2"></i>
                                    <div class="text-xs text-gray-300 font-mono">Live Browser Ansicht (Auto-Refresh)</div>
                                </div>
                                <span class="text-xs text-gray-500 font-mono">Aktueller Screen</span>
                            </div>
                            <div class="p-2 flex-1 flex items-center justify-center overflow-hidden bg-black">
                                <img id="live-view" src="/api/current_view" alt="Warte auf Screenshot..." class="max-h-full max-w-full object-contain" onerror="this.style.display='none'" onload="this.style.display='block'">
                            </div>
                        </div>
                        
                        <div class="bg-gray-900 rounded-lg shadow flex flex-col h-[450px] border border-gray-700">
                            <div class="bg-gray-800 px-4 py-2 border-b border-gray-700 rounded-t-lg flex items-center justify-between">
                                <div class="flex items-center space-x-2">
                                    <div class="w-3 h-3 rounded-full bg-red-500"></div>
                                    <div class="w-3 h-3 rounded-full bg-yellow-500"></div>
                                    <div class="w-3 h-3 rounded-full bg-green-500"></div>
                                    <div class="ml-4 text-xs text-gray-300 font-mono">agent_run.log — Live Terminal</div>
                                </div>
                                <span class="text-xs text-gray-500 font-mono">Realtime</span>
                            </div>
                            <div id="terminal" class="p-4 flex-1 overflow-y-auto text-green-400 font-mono text-xs whitespace-pre-wrap leading-relaxed">Lade Logs...</div>
                        </div>
                    </div>
                </div>
            </div>
            
            
            <!-- LIVE MEETINGS TAB -->
            <div id="live-tab" class="hidden px-4 sm:px-0">
                <div class="bg-white shadow overflow-hidden sm:rounded-lg mb-6">
                    <div class="px-4 py-5 border-b border-gray-200 sm:px-6 flex justify-between items-center">
                        <div>
                            <h3 class="text-lg leading-6 font-medium text-gray-900"><i class="fas fa-video text-brand mr-2"></i> Live-Meetings verwalten</h3>
                            <p class="mt-1 max-w-2xl text-sm text-gray-500">Tragen Sie hier die Zugangsdaten für Ihre Live-Zoom-Vorlesungen ein.</p>
                        </div>
                        <button onclick="detectSubjects()" class="inline-flex items-center px-4 py-2 border border-transparent shadow-sm text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700">
                            <i class="fas fa-magic mr-2"></i> Fächer erkennen
                        </button>
                    </div>
                    <div class="p-6">
                        <div id="live-meetings-container" class="space-y-4">
                            <!-- Rows inserted via JS -->
                        </div>
                        <div class="mt-6">
                            <button onclick="saveLiveMeetings()" class="w-full flex justify-center py-3 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-green-600 hover:bg-green-700">
                                <i class="fas fa-save mr-2 text-lg"></i> Meetings Speichern
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- SETTINGS TAB (LOGINS & ZUGANGSDATEN) -->
            <div id="settings-tab" class="hidden px-4 sm:px-0 max-w-4xl mx-auto">
                <div class="bg-white shadow overflow-hidden sm:rounded-lg mb-6 border border-gray-200">
                    <div class="px-6 py-5 border-b border-gray-200 bg-gray-50">
                        <h3 class="text-xl leading-6 font-bold text-gray-900 flex items-center">
                            <i class="fas fa-key text-amber-500 mr-3 text-2xl"></i> Logins & Zugangsdaten pflegen
                        </h3>
                        <p class="mt-1 text-sm text-gray-600">
                            Hier kannst du alle Passwörter, E-Mails und API-Schlüssel zentral anpassen. Alle Änderungen werden direkt auf dem Server gesichert und stehen für automatische Downloads sofort zur Verfügung.
                        </p>
                    </div>

                    <div id="save-alert" class="hidden mx-6 mt-4"></div>

                    <form onsubmit="saveSettings(event)" class="px-6 py-6 space-y-8">
                        
                        <!-- 1. HSLU ILIAS & SWITCH edu-ID -->
                        <div class="bg-white rounded-lg p-5 border border-blue-100 bg-blue-50/20">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fas fa-university text-blue-600 mr-2 text-lg"></i> 1. HSLU ILIAS & SWITCH edu-ID
                            </h4>
                            <p class="text-xs text-gray-500 mb-4">Wird für den Zugriff auf Skripte, Vorlesungsunterlagen und ILIAS-Dateien verwendet.</p>
                            
                            <div class="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-2">
                                <div class="sm:col-span-2">
                                    <label class="block text-sm font-medium text-gray-700">HSLU E-Mail / Benutzername</label>
                                    <input type="text" id="HSLU_USERNAME" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border focus:ring-brand focus:border-brand" placeholder="vorname.nachname@stud.hslu.ch">
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">SWITCH edu-ID Passwort</label>
                                    <div class="relative mt-1">
                                        <input type="password" id="HSLU_PASSWORD" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border focus:ring-brand focus:border-brand">
                                        <button type="button" onclick="toggleVisibility('HSLU_PASSWORD', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                            <i class="fas fa-eye text-gray-400"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">SWITCH edu-ID 2FA Key (TOTP Secret)</label>
                                    <div class="relative mt-1">
                                        <input type="password" id="HSLU_TOTP_SECRET" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border font-mono text-xs focus:ring-brand focus:border-brand" placeholder="32-stelliger Base32 Key">
                                        <button type="button" onclick="toggleVisibility('HSLU_TOTP_SECRET', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                            <i class="fas fa-eye text-gray-400"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 2. Microsoft 365 & Zoom -->
                        <div class="bg-white rounded-lg p-5 border border-indigo-100 bg-indigo-50/20">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fas fa-video text-blue-600 mr-2 text-lg"></i> 2. Microsoft 365 & Zoom Cloud Login
                            </h4>
                            <p class="text-xs text-gray-500 mb-4">Wird für geschützte Zoom-Cloud-Aufzeichnungen (hslu.zoom.us / NetID SSO) benötigt.</p>
                            
                            <div class="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-2">
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">Microsoft E-Mail (stud.hslu.ch)</label>
                                    <input type="text" id="HSLU_MS_EMAIL" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border focus:ring-brand focus:border-brand" placeholder="vorname.nachname@stud.hslu.ch">
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">Microsoft / Campus Passwort</label>
                                    <div class="relative mt-1">
                                        <input type="password" id="HSLU_MS_PASSWORD" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border focus:ring-brand focus:border-brand" placeholder="Passwort für Teams / Microsoft 365">
                                        <button type="button" onclick="toggleVisibility('HSLU_MS_PASSWORD', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                            <i class="fas fa-eye text-gray-400"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="sm:col-span-2">
                                    <label class="block text-sm font-medium text-gray-700">Microsoft Authenticator 2FA Key (Optional / TOTP Secret)</label>
                                    <div class="relative mt-1">
                                        <input type="password" id="HSLU_MS_TOTP_SECRET" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border font-mono text-xs focus:ring-brand focus:border-brand" placeholder="Falls Microsoft 2FA-Code verlangt (Base32 Key aus Authenticator)">
                                        <button type="button" onclick="toggleVisibility('HSLU_MS_TOTP_SECRET', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                            <i class="fas fa-eye text-gray-400"></i>
                                        </button>
                                    </div>
                                    <p class="text-xs text-gray-400 mt-1">Hinweis: Falls für Microsoft ein separater 2FA-App-Code verlangt wird, kann hier der TOTP-Schlüssel hinterlegt werden.</p>
                                </div>
                            </div>
                        </div>

                        <!-- 3. Dashboard Web-Passwort -->
                        <div class="bg-white rounded-lg p-5 border border-gray-200">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fas fa-lock text-gray-600 mr-2 text-lg"></i> 3. Dashboard Admin-Zugang
                            </h4>
                            <div class="grid grid-cols-1 gap-y-4 gap-x-4 sm:grid-cols-2">
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">Benutzername</label>
                                    <input type="text" value="admin" disabled class="mt-1 block w-full bg-gray-100 shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border cursor-not-allowed text-gray-500">
                                </div>
                                <div class="sm:col-span-1">
                                    <label class="block text-sm font-medium text-gray-700">Dashboard Passwort</label>
                                    <div class="relative mt-1">
                                        <input type="password" id="DASHBOARD_PASS" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border focus:ring-brand focus:border-brand">
                                        <button type="button" onclick="toggleVisibility('DASHBOARD_PASS', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                            <i class="fas fa-eye text-gray-400"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- 4. Google Drive & Docs API -->
                        <div class="bg-white rounded-lg p-5 border border-red-100 bg-red-50/20">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fab fa-google text-red-500 mr-2 text-lg"></i> 4. Google Drive Cloud-Ablage
                            </h4>
                            <div class="space-y-4">
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">Google Drive Ziel-Ordner ID (Root-Ordner)</label>
                                    <p class="text-xs text-gray-500 mb-1">Aus der URL deines Ziel-Ordners: drive.google.com/drive/folders/<b>DEINE_ID_HIER</b></p>
                                    <input type="text" id="GOOGLE_DRIVE_FOLDER_ID" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border font-mono text-xs focus:ring-brand focus:border-brand">
                                </div>
                                <div>
                                    <label class="block text-sm font-medium text-gray-700">Google Service Account JSON</label>
                                    <textarea id="GOOGLE_SERVICE_JSON" rows="5" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border font-mono text-xs focus:ring-brand focus:border-brand" placeholder='{ "type": "service_account", ... }'></textarea>
                                </div>
                            </div>
                        </div>

                        <!-- 5. KI & Gemini -->
                        <div class="bg-white rounded-lg p-5 border border-purple-100 bg-purple-50/20">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fas fa-brain text-purple-600 mr-2 text-lg"></i> 5. Google Gemini KI API
                            </h4>
                            <div>
                                <label class="block text-sm font-medium text-gray-700">Gemini API Key</label>
                                <div class="relative mt-1">
                                    <input type="password" id="GEMINI_API_KEY" class="block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 pr-10 border font-mono text-xs focus:ring-brand focus:border-brand">
                                    <button type="button" onclick="toggleVisibility('GEMINI_API_KEY', this)" class="absolute inset-y-0 right-0 px-3 flex items-center">
                                        <i class="fas fa-eye text-gray-400"></i>
                                    </button>
                                </div>
                            </div>
                        </div>

                        <!-- 6. NotebookLM -->
                        <div class="bg-white rounded-lg p-5 border border-gray-200">
                            <h4 class="text-base font-semibold text-gray-900 mb-3 flex items-center border-b pb-2">
                                <i class="fas fa-podcast text-indigo-500 mr-2 text-lg"></i> 6. NotebookLM (Audio Podcasts)
                            </h4>
                            <div>
                                <label class="block text-sm font-medium text-gray-700">NotebookLM Cookie JSON</label>
                                <textarea id="NOTEBOOKLM_COOKIES" rows="4" class="mt-1 block w-full shadow-sm sm:text-sm border-gray-300 rounded-md p-2 border font-mono text-xs focus:ring-brand focus:border-brand" placeholder='[{"domain": ".google.com", "name": "SID", ...}]'></textarea>
                            </div>
                        </div>

                        <!-- Submit Button -->
                        <div class="pt-4">
                            <button type="submit" id="save-btn" class="w-full flex justify-center py-4 px-4 border border-transparent rounded-lg shadow-md text-base font-bold text-white bg-green-600 hover:bg-green-700 transition-colors cursor-pointer">
                                <i class="fas fa-save mr-2 text-lg"></i> Einstellungen & Logins Speichern
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

def get_next_sunday():
    now = datetime.now()
    days_ahead = 6 - now.weekday()
    if days_ahead <= 0: days_ahead += 7
    next_sunday = now + timedelta(days=days_ahead)
    return next_sunday.replace(hour=18, minute=0, second=0).strftime("%A, %d.%m.%Y - 18:00 Uhr")

def run_script_task(cmd_list, title):
    global process
    with open(LOG_FILE, "a") as f:
        f.write("\n\n" + "="*70 + "\n")
        f.write(f"{title} - {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
        f.write("="*70 + "\n")
    process = subprocess.Popen(cmd_list, stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT)
    process.wait()

@app.route('/')
@requires_auth
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/current_view')
@requires_auth
def get_current_view():
    path = os.path.join("downloads", "current_view.png")
    if os.path.exists(path):
        return send_file(path, mimetype='image/png')
    return "", 404

@app.route('/log')
@requires_auth
def get_log():
    if not os.path.exists(LOG_FILE):
        return "System bereit. Noch keine Log-Einträge vorhanden."
    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
        return "".join(f.readlines()[-300:])

@app.route('/status')
@requires_auth
def get_status():
    global process
    is_running = process is not None and process.poll() is None
    return jsonify({"is_running": is_running, "next_run": get_next_sunday()})

@app.route('/run', methods=['POST'])
@requires_auth
def run_now():
    global process
    if process is not None and process.poll() is None:
        return jsonify({"message": "Läuft bereits!"})
    threading.Thread(
        target=run_script_task,
        args=(["bash", "-c", "/opt/KiAgentHSLU/venv/bin/python -u run_weeks.py"], "HAUPT-DURCHLAUF (AGENT)")
    ).start()
    return jsonify({"message": "Gestartet!"})

@app.route('/test/<test_type>', methods=['POST'])
@requires_auth
def run_test(test_type):
    global process
    if process is not None and process.poll() is None:
        return jsonify({"message": "Ein anderer Prozess läuft bereits!"})
    cmd_map = {
        "google": (["/opt/KiAgentHSLU/venv/bin/python", "-u", "tests/test_google_drive.py"], "TEST: GOOGLE DRIVE API"),
        "gemini": (["/opt/KiAgentHSLU/venv/bin/python", "-u", "tests/test_setup.py"], "TEST: GEMINI KI API & SETUP"),
        "ilias": (["/opt/KiAgentHSLU/venv/bin/python", "-u", "tests/test_login.py"], "TEST: HSLU ILIAS LOGIN"),
        "zoom": (["/opt/KiAgentHSLU/venv/bin/python", "-u", "tests/test_zoom_full.py"], "TEST: ZOOM & MICROSOFT 365 LOGIN")
    }
    if test_type not in cmd_map:
        return jsonify({"message": "Unbekannter Test!"})
    cmd, title = cmd_map[test_type]
    threading.Thread(target=run_script_task, args=(cmd, title)).start()
    return jsonify({"message": f"{title} gestartet!"})

@app.route('/api/settings', methods=['GET'])
@requires_auth
def get_settings():
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, 'a').close()
    config = dotenv_values(ENV_FILE)
    
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
        "HSLU_MS_EMAIL": config.get("HSLU_MS_EMAIL", config.get("HSLU_USERNAME", "")),
        "HSLU_MS_PASSWORD": config.get("HSLU_MS_PASSWORD", config.get("ZOOM_PASSWORD", "")),
        "HSLU_MS_TOTP_SECRET": config.get("HSLU_MS_TOTP_SECRET", ""),
        "DASHBOARD_PASS": config.get("DASHBOARD_PASS", ""),
        "GEMINI_API_KEY": config.get("GEMINI_API_KEY", ""),
        "GOOGLE_DRIVE_FOLDER_ID": config.get("GOOGLE_DRIVE_FOLDER_ID", "").strip("'").strip('"'),
        "GOOGLE_SERVICE_JSON": service_json_content,
        "NOTEBOOKLM_COOKIES": "" if not os.path.exists('notebooklm_cookies.json') else open('notebooklm_cookies.json').read()
    })

@app.route('/api/settings', methods=['POST'])
@requires_auth
def save_settings():
    data = request.json or {}
    if not os.path.exists(ENV_FILE):
        open(ENV_FILE, 'a').close()
    
    service_json = data.pop("GOOGLE_SERVICE_JSON", "")
    nblm_cookies = data.pop("NOTEBOOKLM_COOKIES", "")
    
    if nblm_cookies and nblm_cookies.strip() != "":
        with open('notebooklm_cookies.json', 'w', encoding='utf-8') as f:
            f.write(nblm_cookies)
        try:
            subprocess.run(["/opt/KiAgentHSLU/venv/bin/python", "-m", "notebooklm", "auth", "import-cookies", "notebooklm_cookies.json"], check=False)
        except Exception:
            pass

    if service_json and service_json.strip() != "":
        try:
            parsed_json = json.loads(service_json)
            target_file = SERVICE_ACCOUNT_FILE
            if "installed" in parsed_json or "web" in parsed_json:
                target_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'credentials.json')
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2)
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})
    
    # Mirror MS credentials to ZOOM
    if "HSLU_MS_PASSWORD" in data:
        data["ZOOM_PASSWORD"] = data["HSLU_MS_PASSWORD"]
    if "HSLU_MS_EMAIL" in data:
        data["ZOOM_EMAIL"] = data["HSLU_MS_EMAIL"]

    for key, value in data.items():
        val_str = str(value).strip().strip("'").strip('"') if value is not None else ""
        set_key(ENV_FILE, key, val_str)
        
    return jsonify({"success": True})


@app.route('/api/live_meetings', methods=['GET'])
@requires_auth
def get_live_meetings():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_meetings.json')
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return "[]"

@app.route('/api/live_meetings', methods=['POST'])
@requires_auth
def save_live_meetings():
    data = request.json or []
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'live_meetings.json')
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return jsonify({"success": True})

@app.route('/api/detect_subjects', methods=['POST'])
@requires_auth
def detect_subjects():
    cmd = ["/opt/KiAgentHSLU/venv/bin/python", "-u", "detect_live_courses.py"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        return jsonify({"message": "Fächer erfolgreich erkannt!"})
    else:
        return jsonify({"message": f"Fehler bei Erkennung: {res.stderr}"}), 500

if __name__ == '__main__':
    # Standard: nur lokal erreichbar. Auf dem Server DASHBOARD_HOST=0.0.0.0 in .env setzen
    # und einen HTTPS-Reverse-Proxy (z.B. Caddy/nginx) davorschalten.
    host = dotenv_values(ENV_FILE).get("DASHBOARD_HOST") or "127.0.0.1"
    app.run(host=host, port=5000)
