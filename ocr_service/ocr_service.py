import os
import json
import tempfile
from io import BytesIO
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from pdfminer.high_level import extract_text
import requests

import cv2
import numpy as np
from flask import Flask, request, jsonify
from paddleocr import PaddleOCR
from PIL import Image

# -----------------------------------------------------------------------------
# Environment & global config
# -----------------------------------------------------------------------------
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")
os.environ.setdefault("FLAGS_log_dir", tempfile.gettempdir())

app = Flask(__name__)
# Debug image dumping via env var or ?mode=debug
DEBUG_IMAGES_ENV = os.getenv("DEBUG_IMAGES", "0") == "1"
DEBUG_DIR = Path("debug_images")
DEBUG_DIR.mkdir(exist_ok=True)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def box_area(box: List[List[float]] | np.ndarray) -> float:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    if pts.shape[0] < 3:
        _, _, w, h = cv2.boundingRect(pts.astype(np.int32))
        return float(w * h)
    return float(cv2.contourArea(pts))

def box_origin(box: List[List[float]] | np.ndarray) -> Tuple[float, float]:
    pts = np.asarray(box, dtype=np.float32).reshape(-1, 2)
    return float(pts[:, 0].min()), float(pts[:, 1].min())

def resize_to_max_side(img: Image.Image, max_side: int) -> Image.Image:
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    new_w, new_h = int(w * scale), int(h * scale)
    return img.resize((new_w, new_h))

def pil_to_cv(img: Image.Image) -> np.ndarray:
    arr = np.array(img.convert("RGB"))
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

def preprocess_array(img: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

# -----------------------------------------------------------------------------
# Initialize OCR model
# -----------------------------------------------------------------------------
try:
    ocr_model = PaddleOCR(
        lang="en",
        det_model_dir=None,
        rec_model_dir=None,
        use_angle_cls=True
    )
except Exception as e:
    raise RuntimeError(f"Failed to initialize PaddleOCR: {e}")

# -----------------------------------------------------------------------------
# Health check
# -----------------------------------------------------------------------------
@app.route("/gpu-check")
def gpu_check():
    import paddle
    compiled = getattr(paddle, "is_compiled_with_cuda", lambda: False)()
    try:
        count = paddle.device.cuda.device_count()
    except Exception:
        count = 0
    return jsonify({"cuda_compiled": compiled, "device_count": count})

# -----------------------------------------------------------------------------
# OCR endpoint
# -----------------------------------------------------------------------------
@app.route('/ocr', methods=['POST'])
def ocr():
    print("[OCR] Form keys:", list(request.form.keys()), "Files:", list(request.files.keys()))

    file = request.files.get('image')
    if not file:
        return jsonify({'error': 'No image uploaded'}), 400

    try:
        left = int(request.form.get('left', 0))
        top = int(request.form.get('top', 0))
        width = int(request.form.get('width', 0))
        height = int(request.form.get('height', 0))
    except ValueError:
        left = top = width = height = 0

    if width == 0 and height == 0 and 'crop' in request.form:
        try:
            c = json.loads(request.form['crop'])
            left = int(c.get('left', 0))
            top = int(c.get('top', 0))
            width = int(c.get('width', 0))
            height = int(c.get('height', 0))
        except Exception:
            left = top = width = height = 0

    debug_mode = request.args.get('mode') == 'debug'
    save_images = DEBUG_IMAGES_ENV or debug_mode
    tag = datetime.utcnow().strftime('%Y%m%dT%H%M%S_%f')

    img_stream = BytesIO(file.read())
    full = Image.open(img_stream)
    if save_images:
        full_path = DEBUG_DIR / f"{tag}_full.jpg"
        full.save(full_path)
        print(f"[OCR] Saved full image to {full_path}")

    try:
        screen_w = float(request.form.get('screenWidth', 0))
        screen_h = float(request.form.get('screenHeight', 0))
    except ValueError:
        screen_w = screen_h = 0.0
    sx = full.width / screen_w if screen_w > 0 else 1.0
    sy = full.height / screen_h if screen_h > 0 else 1.0

    if width > 0 and height > 0:
        l = int(left * sx)
        t = int(top * sy)
        w = int(width * sx)
        h = int(height * sy)
        roi = full.crop((l, t, l + w, t + h))
    else:
        roi = full
    if save_images:
        crop_path = DEBUG_DIR / f"{tag}_crop.jpg"
        roi.save(crop_path)

    scaled = resize_to_max_side(roi, max_side=4000)
    if save_images:
        scaled_path = DEBUG_DIR / f"{tag}_scaled.jpg"
        scaled.save(scaled_path)

    try:
        proc = preprocess_array(pil_to_cv(scaled))
    except Exception as e:
        return jsonify({'error': f'Preprocess failed: {e}'}), 400
    if save_images:
        proc_path = DEBUG_DIR / f"{tag}_proc.jpg"
        cv2.imwrite(str(proc_path), proc)

    try:
        result = ocr_model.predict(proc)
    except Exception as e:
        return jsonify({'error': f'OCR failed: {e}'}), 500

    lines: List[Dict[str, Any]] = []
    text_parts: List[str] = []

    if isinstance(result, list) and len(result) > 0 and isinstance(result[0], dict):
        ocr_out = result[0]
        texts = ocr_out.get('rec_texts', [])
        scores = ocr_out.get('rec_scores', [])
        boxes = ocr_out.get('rec_boxes', [])
        for txt, score, box in zip(texts, scores, boxes):
            lines.append({
                "text": txt,
                "confidence": float(score),
                "box": box.tolist() if hasattr(box, 'tolist') else [list(map(float, pt)) for pt in box]
            })
            text_parts.append(txt)
    else:
        for block in result:
            if not block:
                continue
            for entry in block:
                try:
                    box = entry[0]
                    txt = entry[1][0]
                    score = entry[1][1]
                except Exception as e:
                    continue
                lines.append({
                    "text": txt,
                    "confidence": float(score),
                    "box": [list(map(float, pt)) for pt in box]
                })
                text_parts.append(txt)

    text = "\n".join(text_parts)
    resp = {'lines': lines, 'text': text}
    if save_images or debug_mode:
        resp['debug'] = {'tag': tag, 'saved_images': save_images}

    return jsonify(resp), 200

# -----------------------------------------------------------------------------
# PDF SDS Verification Endpoint
# -----------------------------------------------------------------------------
def verify_pdf_sds(url: str, product_name: str, keywords=None) -> bool:
    keywords = keywords or ["SDS", "MSDS", "Safety Data Sheet"]
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        text = extract_text(BytesIO(response.content)).lower()

        product_match = product_name.lower() in text
        keyword_match = any(kw.lower() in text for kw in keywords)

        return product_match and keyword_match
    except Exception as e:
        print(f"[verify_pdf_sds] Failed to verify {url}: {e}")
        return False

@app.route('/verify-sds', methods=['POST'])
def verify_sds():
    data = request.json or {}
    url = data.get('url', '')
    name = data.get('name', '')
    if not url or not name:
        return jsonify({'error': 'Missing url or name'}), 400

    verified = verify_pdf_sds(url, name)
    return jsonify({'verified': verified}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)