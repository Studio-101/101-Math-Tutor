import io
import json
import logging
import os
import socket
import threading
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Dict, Any, Tuple
import urllib.parse
import qrcode
from PIL import Image

logger = logging.getLogger(__name__)

# Global in-memory storage for pending uploads by session_id
# Structure: { session_id: [ {"image_bytes": bytes, "note": str, "timestamp": float} ] }
_SESSIONS_LOCK = threading.Lock()
_SESSIONS: Dict[str, list] = {}
_SERVER_INSTANCE: Optional[HTTPServer] = None
_SERVER_THREAD: Optional[threading.Thread] = None
_SERVER_PORT: int = 8502
_SERVER_IP: str = "127.0.0.1"


def get_local_lan_ip() -> str:
    """
    Detects the primary LAN IP address of this machine that can reach external devices (like a phone on the same Wi-Fi).
    Falls back to 127.0.0.1 if offline.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Does not actually send data over network
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"


HTML_MOBILE_PAGE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>GSAT 數學家教 - 手機拍照上傳</title>
  <style>
    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    body {
      background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%);
      color: #f8fafc;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 1.25rem;
    }
    .header {
      text-align: center;
      margin-top: 0.8rem;
      margin-bottom: 1.5rem;
    }
    .header h1 {
      font-size: 1.4rem;
      font-weight: 700;
      color: #e0e7ff;
      margin-bottom: 0.3rem;
    }
    .header p {
      font-size: 0.88rem;
      color: #94a3b8;
    }
    .card {
      background: rgba(30, 41, 59, 0.7);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 1.25rem;
      width: 100%;
      max-width: 440px;
      padding: 1.5rem;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    }
    .upload-zone {
      border: 2px dashed #6366f1;
      border-radius: 1rem;
      padding: 1.8rem 1rem;
      text-align: center;
      background: rgba(99, 102, 241, 0.05);
      cursor: pointer;
      transition: all 0.2s ease;
      margin-bottom: 1.2rem;
    }
    .upload-zone:active {
      transform: scale(0.98);
      background: rgba(99, 102, 241, 0.15);
    }
    .camera-icon {
      font-size: 3rem;
      margin-bottom: 0.5rem;
      display: block;
    }
    .upload-title {
      font-size: 1.15rem;
      font-weight: 600;
      color: #c7d2fe;
      margin-bottom: 0.3rem;
    }
    .upload-subtitle {
      font-size: 0.85rem;
      color: #94a3b8;
    }
    #previewContainer {
      display: none;
      margin-bottom: 1.2rem;
      text-align: center;
    }
    #imagePreview {
      max-width: 100%;
      max-height: 320px;
      border-radius: 0.75rem;
      border: 1px solid rgba(255, 255, 255, 0.2);
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      display: block;
      margin: 0 auto 0.6rem auto;
    }
    .retake-btn {
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: #c7d2fe;
      padding: 0.35rem 0.8rem;
      border-radius: 0.5rem;
      font-size: 0.82rem;
      cursor: pointer;
      display: inline-block;
    }
    .retake-btn:active {
      background: rgba(99, 102, 241, 0.3);
    }
    .input-group {
      margin-bottom: 1.2rem;
    }
    .input-group label {
      display: block;
      font-size: 0.85rem;
      color: #cbd5e1;
      margin-bottom: 0.4rem;
      font-weight: 500;
    }
    .input-group input {
      width: 100%;
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 0.6rem;
      color: #fff;
      padding: 0.75rem 0.9rem;
      font-size: 0.95rem;
      outline: none;
    }
    .input-group input:focus {
      border-color: #6366f1;
    }
    .btn-submit {
      width: 100%;
      background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
      color: #fff;
      border: none;
      border-radius: 0.75rem;
      padding: 0.9rem;
      font-size: 1.05rem;
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 4px 14px rgba(99, 102, 241, 0.4);
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
    }
    .btn-submit:disabled {
      background: #475569;
      color: #94a3b8;
      cursor: not-allowed;
      box-shadow: none;
    }
    .status-card {
      text-align: center;
      padding: 2rem 1.25rem;
      background: rgba(34, 197, 94, 0.15);
      border: 1px solid rgba(34, 197, 94, 0.35);
      border-radius: 1rem;
      display: none;
      margin-bottom: 0.5rem;
      cursor: pointer;
    }
    .status-card .icon {
      font-size: 3.2rem;
      margin-bottom: 0.6rem;
      display: block;
    }
    .status-card h2 {
      font-size: 1.3rem;
      color: #86efac;
      margin-bottom: 0.5rem;
    }
    .status-card p {
      font-size: 0.92rem;
      color: #cbd5e1;
      margin-bottom: 0;
      line-height: 1.5;
    }
    .tips {
      margin-top: 1.5rem;
      font-size: 0.8rem;
      color: #64748b;
      line-height: 1.5;
      text-align: center;
    }
  </style>
</head>
<body>

  <div class="header">
    <h1>📐 數學手寫草稿拍傳助手</h1>
    <p>即拍即傳 • 電腦端直接框選裁剪</p>
  </div>

  <div class="card">
    <input type="file" id="cameraInput" accept="image/*" capture="environment" style="display: none;">

    <!-- State 1: Ready to take photo -->
    <div class="upload-zone" id="uploadZone" onclick="document.getElementById('cameraInput').click()">
      <span class="camera-icon">📸</span>
      <div class="upload-title">點擊啟動相機拍照</div>
      <div class="upload-subtitle">對準你的手寫算式或草稿</div>
    </div>

    <!-- State 2: Preview photo -->
    <div id="previewContainer">
      <img id="imagePreview" alt="預覽照片">
      <button type="button" class="retake-btn" onclick="document.getElementById('cameraInput').click()">🔄 重新拍攝</button>
      <div style="margin-top: 1rem;">
        <button id="submitBtn" class="btn-submit" onclick="uploadPhoto()">
          <span>🚀 傳送到電腦家教</span>
        </button>
      </div>
    </div>

    <!-- State 3: Upload Success Card (No redundant buttons, focus shifts to PC) -->
    <div id="statusCard" class="status-card" onclick="resetToInitialState()" title="若稍後需再次拍照，點擊此處即可重設">
      <span class="icon">🎉</span>
      <h2>照片已成功傳送！</h2>
      <p>請將視線移回電腦大螢幕，進行框選裁剪並由家教開始診斷。</p>
    </div>

    <div id="statusError" class="status-msg status-error"></div>
  </div>

  <div class="tips">
    💡 提示：拍完直接送出即可，電腦大螢幕會提供裁剪工具，方便精確框選！
  </div>

  <script>
    const cameraInput = document.getElementById('cameraInput');
    const uploadZone = document.getElementById('uploadZone');
    const previewContainer = document.getElementById('previewContainer');
    const imagePreview = document.getElementById('imagePreview');
    const submitBtn = document.getElementById('submitBtn');
    const statusCard = document.getElementById('statusCard');
    const statusError = document.getElementById('statusError');

    let currentFile = null;

    // Extract session ID from URL query params
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session') || 'default';

    cameraInput.addEventListener('change', function(e) {
      if (this.files && this.files[0]) {
        currentFile = this.files[0];
        const reader = new FileReader();
        reader.onload = function(evt) {
          imagePreview.src = evt.target.result;
          uploadZone.style.display = 'none';
          statusCard.style.display = 'none';
          statusError.style.display = 'none';
          previewContainer.style.display = 'block';
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<span>🚀 傳送到電腦家教</span>';
        }
        reader.readAsDataURL(currentFile);
      }
    });

    async function uploadPhoto() {
      if (!currentFile) return;

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span>⏳ 傳送中，請稍候...</span>';
      statusError.style.display = 'none';

      const formData = new FormData();
      formData.append('session_id', sessionId);
      formData.append('image', currentFile);
      formData.append('note', '');

      try {
        const response = await fetch('/api/upload', {
          method: 'POST',
          body: formData
        });
        const result = await response.json();
        if (result.status === 'ok') {
          // Switch to State 3: Success Card
          previewContainer.style.display = 'none';
          statusCard.style.display = 'block';
        } else {
          throw new Error(result.message || '傳送失敗');
        }
      } catch (err) {
        statusError.innerText = '❌ 傳送失敗：' + err.message + '，請確認手機與電腦是否連上相同 Wi-Fi。';
        statusError.style.display = 'block';
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span>重試傳送</span>';
      }
    }

    function resetToInitialState() {
      currentFile = null;
      cameraInput.value = '';
      uploadZone.style.display = 'block';
      previewContainer.style.display = 'none';
      statusCard.style.display = 'none';
      statusError.style.display = 'none';
    }
  </script>



</body>
</html>
"""


class SyncServerHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress noisy standard HTTP access logs
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/upload" or path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_MOBILE_PAGE.encode("utf-8"))
            return

        elif path == "/api/poll":
            session_id = query.get("session", ["default"])[0]
            with _SESSIONS_LOCK:
                items = _SESSIONS.get(session_id, [])
                count = len(items)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"count": count}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()
        self.wfile.write(b"Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/upload":
            content_type = self.headers.get("Content-Type", "")
            content_length = int(self.headers.get("Content-Length", 0))

            if not content_type.startswith("multipart/form-data"):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"status":"error","message":"Expected multipart/form-data"}')
                return

            body = self.rfile.read(content_length)
            
            # Simple multipart/form-data parser for image and text fields
            boundary = content_type.split("boundary=")[-1].strip().encode()
            parts = body.split(b"--" + boundary)

            session_id = "default"
            note = ""
            image_bytes = None

            for part in parts:
                if not part or part == b"--\r\n" or part == b"--":
                    continue
                header_data_split = part.split(b"\r\n\r\n", 1)
                if len(header_data_split) != 2:
                    continue
                raw_headers, raw_data = header_data_split
                headers_text = raw_headers.decode("latin1", errors="ignore")
                data = raw_data.rstrip(b"\r\n")

                if 'name="session_id"' in headers_text:
                    session_id = data.decode("utf-8", errors="ignore").strip()
                elif 'name="note"' in headers_text:
                    note = data.decode("utf-8", errors="ignore").strip()
                elif 'name="image"' in headers_text:
                    image_bytes = data

            if image_bytes:
                with _SESSIONS_LOCK:
                    if session_id not in _SESSIONS:
                        _SESSIONS[session_id] = []
                    _SESSIONS[session_id].append({
                        "image_bytes": image_bytes,
                        "note": note,
                    })

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok","message":"Upload successful"}')
                return
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"status":"error","message":"No image received"}')
                return

        self.send_response(404)
        self.end_headers()


def start_sync_server(port: int = 8502) -> Tuple[str, int]:
    """
    Starts the mobile sync HTTP server in a daemon thread if not already running.
    Returns (lan_ip, port).
    """
    global _SERVER_INSTANCE, _SERVER_THREAD, _SERVER_PORT, _SERVER_IP

    _SERVER_IP = get_local_lan_ip()
    _SERVER_PORT = port

    if _SERVER_INSTANCE is not None:
        return _SERVER_IP, _SERVER_PORT

    try:
        server = HTTPServer(("0.0.0.0", _SERVER_PORT), SyncServerHandler)
        _SERVER_INSTANCE = server
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        _SERVER_THREAD = thread
        thread.start()
        logger.info(f"Sync server running on http://{_SERVER_IP}:{_SERVER_PORT}")
    except Exception as e:
        logger.warning(f"Could not bind port {_SERVER_PORT}: {e}. Trying auto-port.")
        try:
            server = HTTPServer(("0.0.0.0", 0), SyncServerHandler)
            _SERVER_PORT = server.server_port
            _SERVER_INSTANCE = server
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            _SERVER_THREAD = thread
            thread.start()
        except Exception as err:
            logger.error(f"Failed to start sync server: {err}")

    return _SERVER_IP, _SERVER_PORT


def get_sync_url(session_id: str) -> str:
    """Returns the full URL for mobile access."""
    ip, port = start_sync_server(_SERVER_PORT)
    return f"http://{ip}:{port}/upload?session={session_id}"


def generate_qr_code_image(url: str) -> bytes:
    """Generates a high-quality QR code image as PNG bytes."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1E1B4B", back_color="#FFFFFF")
    
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def pop_latest_upload(session_id: str) -> Optional[dict]:
    """
    Pops the next uploaded item for this session if available.
    Returns dict with keys: 'image_bytes', 'note' or None.
    """
    with _SESSIONS_LOCK:
        if session_id in _SESSIONS and len(_SESSIONS[session_id]) > 0:
            return _SESSIONS[session_id].pop(0)
    return None


def has_pending_upload(session_id: str) -> bool:
    """Checks if there are any uploads waiting for this session."""
    with _SESSIONS_LOCK:
        return session_id in _SESSIONS and len(_SESSIONS[session_id]) > 0
