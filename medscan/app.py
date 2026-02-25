"""
MedScan — Medical Report OCR Web App
Storage  : Google Sheets via Apps Script Web App URL
OCR      : OCR.space cloud API
Supports : Images up to 5MB (auto-compressed before sending to OCR)
"""

import re, os, traceback, base64, requests, io
from datetime import datetime
from PIL import Image
from flask import Flask, request, jsonify, render_template
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────────────────────
OCR_API_KEY     = os.getenv("OCR_API_KEY", "")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "")
SHEET_ID        = os.getenv("SHEET_ID", "")

COLUMNS = [
    "Timestamp", "Patient Name", "Age", "Gender",
    "Height (cm)", "Weight (kg)", "BMI",
    "Systolic BP", "Diastolic BP", "BP Status",
    "Fasting Sugar (mg/dL)", "Post Prandial Sugar (mg/dL)", "Sugar Status",
]

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

# ── CORS ──────────────────────────────────────────────────────────────────────
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

# ── Image compression ─────────────────────────────────────────────────────────
def compress_image(img_bytes: bytes, max_kb: int = 900) -> bytes:
    """
    Auto-compress image to stay under max_kb (900KB).
    OCR.space free tier limit is 1MB — we target 900KB to be safe.
    Handles camera images up to 5MB.
    """
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")

    # If already small enough, return as-is
    if len(img_bytes) <= max_kb * 1024:
        return img_bytes

    # Try progressively lower quality until under limit
    for quality in [85, 75, 65, 55, 45, 35]:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        compressed = buf.getvalue()
        print(f"[COMPRESS] quality={quality} → {len(compressed)//1024}KB")
        if len(compressed) <= max_kb * 1024:
            return compressed

    # Last resort — resize to half dimensions
    w, h = img.size
    img  = img.resize((w // 2, h // 2), Image.LANCZOS)
    buf  = io.BytesIO()
    img.save(buf, format="JPEG", quality=50, optimize=True)
    print(f"[COMPRESS] resized to {w//2}x{h//2}")
    return buf.getvalue()

# ── OCR via ocr.space ─────────────────────────────────────────────────────────
def ocr_image_bytes(img_bytes: bytes, filename: str) -> str:
    original_kb = len(img_bytes) // 1024
    print(f"[OCR] {filename} — original size: {original_kb}KB")

    # Auto-compress if over 900KB
    if original_kb > 900:
        print(f"[COMPRESS] Compressing {original_kb}KB image...")
        img_bytes = compress_image(img_bytes)
        print(f"[COMPRESS] Final size: {len(img_bytes)//1024}KB")

    b64  = base64.b64encode(img_bytes).decode("utf-8")
    ext  = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    mime = {"png":"image/png","jpg":"image/jpeg","jpeg":"image/jpeg",
            "bmp":"image/bmp","tiff":"image/tiff","tif":"image/tiff"}.get(ext,"image/jpeg")
    payload = {
        "apikey":            OCR_API_KEY,
        "base64Image":       f"data:{mime};base64,{b64}",
        "language":          "eng",
        "isTable":           "true",
        "OCREngine":         "2",
        "scale":             "true",
        "detectOrientation": "true",
    }
    resp = requests.post("https://api.ocr.space/parse/image", data=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if data.get("IsErroredOnProcessing"):
        raise ValueError(data.get("ErrorMessage", ["OCR failed"])[0])
    return " ".join(r.get("ParsedText","") for r in (data.get("ParsedResults") or []))

# ── Apps Script helpers ───────────────────────────────────────────────────────
def sheet_append(rows: list):
    resp = requests.post(APPS_SCRIPT_URL,
                         json={"action": "append", "rows": rows}, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("status") != "ok":
        raise ValueError(result.get("message", "Apps Script error"))
    return result

def sheet_read():
    resp = requests.get(APPS_SCRIPT_URL, params={"action": "read"}, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if result.get("status") != "ok":
        raise ValueError(result.get("message", "Apps Script read error"))
    return result.get("data", [])

# ── Parsing helpers ───────────────────────────────────────────────────────────
def find(pattern, text, group=1):
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(group).strip() if m else None

def is_handwritten_table(text):
    has_label    = bool(re.search(r'Patient\s*Name\s*:', text, re.IGNORECASE))
    has_bp_slash = len(re.findall(r'\d{2,3}[/|\\]\d{2,3}', text)) >= 3
    return not has_label and has_bp_slash

def parse_handwritten_line(line):
    line = line.strip()
    if not line or len(line) < 5: return None
    bp = re.search(r'(\d{2,3})[/|\\](\d{2,3})', line)
    if not bp: return None
    systolic, diastolic = int(bp.group(1)), int(bp.group(2))
    if not (60 <= systolic <= 250 and 40 <= diastolic <= 150): return None
    after_bp = line[bp.end():]
    pr_match = re.search(r'\b(\d{2,3})\b', after_bp)
    pr = int(pr_match.group(1)) if pr_match else None
    name = re.sub(r'^[^A-Za-z]+', '', line[:bp.start()]).strip()
    name = re.sub(r'[^A-Za-z\s\.\-]+$', '', name).strip()
    if not name or len(name) < 2: return None
    notes = ''
    if pr_match:
        nm = re.search(r'[A-Za-z]{4,}', after_bp[pr_match.end():].strip())
        notes = nm.group(0) if nm else ''
    return {"Patient Name": name, "Systolic BP": str(systolic),
            "Diastolic BP": str(diastolic),
            "Pulse / PR (bpm)": str(pr) if pr else '', "Notes": notes}

def extract_handwritten(text):
    rows = []
    for line in text.split('\n'):
        row = parse_handwritten_line(line)
        if row:
            row["BP Status"]    = bp_status(row["Systolic BP"], row["Diastolic BP"])
            row["Sugar Status"] = ''
            row["Timestamp"]    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            for col in ["Age","Gender","Height (cm)","Weight (kg)","BMI",
                        "Fasting Sugar (mg/dL)","Post Prandial Sugar (mg/dL)"]:
                row[col] = ''
            rows.append(row)
    return rows

def extract(text):
    f = {}
    f["Patient Name"] = find(r'Patient\s*Name:\s*(.*?)(?=\s+Age\s*[|/]|\s+Ref\.|\n|$)', text)
    f["Age"]    = (find(r'Age\s*/\s*Gender[:\s]+(\d{1,3})', text) or
                   find(r'Age[^\d]{0,15}(\d{1,3})\s*Years?', text))
    f["Gender"] = (find(r'\d+\s*Years?\s*/\s*([A-Za-z]+)', text) or
                   find(r'Gender[:\s]+([A-Za-z]+)', text))
    f["Height (cm)"]  = find(r'Height[:\s]+(\d{2,3})\s*cm', text)
    f["Weight (kg)"]  = find(r'Weight[:\s]+(\d{2,3}(?:\.\d)?)\s*kg', text)
    f["BMI"]          = find(r'BMI[^\d]{0,20}(\d{1,2}\.\d+)', text)
    f["Systolic BP"]  = (find(r'Blood\s+Pressure\s+\(Systolic\)\s+(\d{2,3})', text) or
                         find(r'Systolic[^\d\n]{0,15}(\d{2,3})', text))
    f["Diastolic BP"] = (find(r'Blood\s+Pressure\s+\(Diastolic\)\s+(\d{2,3})', text) or
                         find(r'Diastolic[^\d\n]{0,15}(\d{2,3})', text))
    f["Fasting Sugar (mg/dL)"] = (
        find(r'Fasting\s+Blood\s+Glucose\s+(\d{2,3}(?:\.\d)?)', text) or
        find(r'Fasting\s+(?:Sugar|Glucose)[:\s]+(\d{2,3})', text))
    f["Post Prandial Sugar (mg/dL)"] = (
        find(r'Post\s+Prandial\s+Glucose\s+(\d{2,3}(?:\.\d)?)', text) or
        find(r'Post\s+Prandial[:\s]+(\d{2,3})', text))
    return f

def bp_status(s, d):
    try:
        s, d = int(s), int(d)
        if s >= 140 or d >= 90: return "High"
        if s >= 130 or d >= 80: return "Elevated"
        if s < 90  or d < 60:   return "Low"
        return "Normal"
    except: return ""

def sugar_status(f, p):
    parts = []
    try:
        fv = float(f)
        parts.append("Fasting: Diabetic" if fv >= 126 else
                     "Fasting: Pre-Diabetic" if fv >= 100 else "Fasting: Normal")
    except: pass
    try:
        pv = float(p)
        parts.append("PP: Diabetic" if pv >= 200 else
                     "PP: Pre-Diabetic" if pv >= 140 else "PP: Normal")
    except: pass
    return " | ".join(parts)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/scan", methods=["POST","OPTIONS"])
def scan():
    if request.method == "OPTIONS": return jsonify({}), 200
    if "images" not in request.files: return jsonify({"error":"No images in request"}), 400
    if not OCR_API_KEY: return jsonify({"error":"OCR_API_KEY not configured"}), 500

    results = []
    for file in request.files.getlist("images"):
        if not file.filename: continue
        try:
            img_bytes = file.read()
            if not img_bytes:
                results.append({"filename":file.filename,"success":False,"error":"Empty file"}); continue
            raw_text = ocr_image_bytes(img_bytes, file.filename)
            if is_handwritten_table(raw_text):
                rows = extract_handwritten(raw_text)
                if rows:
                    results.append({"filename":file.filename,"success":True,
                                    "mode":"handwritten","rows":rows,"count":len(rows)})
                else:
                    results.append({"filename":file.filename,"success":False,
                                    "error":"Could not parse handwritten table rows"})
            else:
                fields = extract(raw_text)
                fields["BP Status"]    = bp_status(fields.get("Systolic BP"), fields.get("Diastolic BP"))
                fields["Sugar Status"] = sugar_status(fields.get("Fasting Sugar (mg/dL)"),
                                                      fields.get("Post Prandial Sugar (mg/dL)"))
                fields["Timestamp"]    = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                results.append({"filename":file.filename,"success":True,"mode":"printed","data":fields})
        except Exception as e:
            print(f"[ERROR] {traceback.format_exc()}")
            results.append({"filename":file.filename,"success":False,"error":str(e)})
    return jsonify({"results": results})

@app.route("/save", methods=["POST","OPTIONS"])
def save():
    if request.method == "OPTIONS": return jsonify({}), 200
    rows = request.json.get("rows", [])
    if not rows: return jsonify({"error":"No data"}), 400
    if not APPS_SCRIPT_URL: return jsonify({"error":"APPS_SCRIPT_URL not configured"}), 500
    try:
        result = sheet_append(rows)
        return jsonify({"success":True,"saved":len(rows),"total":result.get("total","?")})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/records")
def records():
    if not APPS_SCRIPT_URL: return jsonify([])
    try:
        return jsonify(sheet_read())
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route("/sheet_url")
def sheet_url():
    if SHEET_ID:
        return jsonify({"url": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"})
    return jsonify({"url": ""})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
