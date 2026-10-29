#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档隐私遮罩工具 - Flask Web 后端  v3.2

改进:
  1. 路径校验改用 is_relative_to，修掉 startswith 前缀绕过
  2. 任务表带 TTL + 容量上限，不再无限增长
  3. 支持批量文件（一次选多个，逐个处理）
  4. 支持取消任务（cancel_event 贯穿引擎）
  5. 新增遮罩结果预览接口（渲染 PDF 页为图片，可前后翻页对比原图）
  6. 端口自适应：5000 被占用时自动顺延
"""

import os
import re
import sys
import time
import uuid
import socket
import logging
import threading
import subprocess
import traceback
import webbrowser
from pathlib import Path

from flask import Flask, request, jsonify, send_file, Response

import redact_engine as engine

# ── 日志配置 ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)


# ── 路径配置（exe 打包时由 app_exe.py 覆盖）────────────
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE_DIR = get_base_dir()
UPLOAD_FOLDER = BASE_DIR / 'uploads'
OUTPUT_FOLDER = BASE_DIR / 'outputs'
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

ALLOWED_DIRS = [UPLOAD_FOLDER.resolve(), OUTPUT_FOLDER.resolve()]


def get_web_dir():
    """web_ui 目录：打包环境优先用 _MEIPASS 里的资源。"""
    if hasattr(sys, '_MEIPASS'):
        bundled = Path(sys._MEIPASS) / 'web_ui'
        if bundled.exists():
            return bundled
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent / 'web_ui'
    return Path(__file__).parent / 'web_ui'


WEB_DIR = get_web_dir()

# ── Flask 应用 ────────────────────────────────────────
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 300 * 1024 * 1024  # 300MB
try:
    app.json.ensure_ascii = False   # Flask >= 2.3
except Exception:
    app.config['JSON_AS_ASCII'] = False

VERSION = '3.3'
MAX_FILES_PER_JOB = 30
MAX_KEYWORDS = 50
MAX_KEYWORD_LEN = 300

# ── 后台任务管理 ──────────────────────────────────────
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_TTL = 3600        # 已完成任务保留 1 小时
MAX_JOBS = 300        # 任务表上限


def _job_set(job_id, **kwargs):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(kwargs)


def _job_get(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return {}
        # 下划线开头的字段（如取消事件）不对外暴露
        return {k: v for k, v in job.items() if not k.startswith('_')}


def _job_cancel_event(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return job.get('_cancel') if job else None


def _gc_jobs():
    """清理过期任务，防止内存无限增长。"""
    now = time.time()
    with JOBS_LOCK:
        expired = [
            jid for jid, j in JOBS.items()
            if j.get('status') in ('done', 'error', 'cancelled')
            and now - j.get('finished_at', now) > JOB_TTL
        ]
        for jid in expired:
            JOBS.pop(jid, None)

        while len(JOBS) > MAX_JOBS:
            victim = min(JOBS.items(),
                         key=lambda kv: kv[1].get('created_at', now))
            JOBS.pop(victim[0], None)


# ── 路径安全 ──────────────────────────────────────────
def resolve_inside(path_str, dirs=None):
    """
    解析路径并确认落在允许目录内。
    用 is_relative_to（语义正确），不再用字符串 startswith 前缀比较。
    """
    if not path_str:
        return None
    try:
        fp = Path(path_str).resolve()
    except (OSError, ValueError):
        return None

    for d in (dirs or ALLOWED_DIRS):
        try:
            if fp.is_relative_to(d):
                return fp
        except AttributeError:  # Python < 3.9 兜底
            if str(fp).startswith(str(d) + os.sep):
                return fp
    return None


def _clean_keywords(raw):
    """校验并规整关键词列表，支持 str / dict 混合。"""
    if not isinstance(raw, list):
        raise ValueError("keywords 必须是数组")
    if len(raw) > MAX_KEYWORDS:
        raise ValueError(f"关键词最多 {MAX_KEYWORDS} 个")

    out = []
    for item in raw:
        if isinstance(item, dict):
            value = str(item.get('value') or item.get('keyword') or '').strip()
            label = item.get('label')
            regex = bool(item.get('regex', False))
        else:
            value = str(item).strip()
            label = None
            regex = False

        if not value:
            continue
        if len(value) > MAX_KEYWORD_LEN:
            raise ValueError(f"关键词过长（上限 {MAX_KEYWORD_LEN} 字）")

        if regex:
            # 请求阶段就校验正则，避免任务跑起来才报错
            try:
                re.compile(value)
            except re.error as e:
                raise ValueError(f"正则表达式「{value[:30]}」语法错误: {e}")

        entry = {'value': value, 'regex': regex}
        if label:
            entry['label'] = str(label)[:60]
        out.append(entry)

    if not out:
        raise ValueError("没有有效关键词")
    return out


def _run_job(job_id, kind, files, keywords, use_ocr, case_sensitive, save_location):
    """后台线程：批量查找 / 批量遮罩。"""
    try:
        _job_set(job_id, status='running', progress=0, message='开始处理...')
        cancel_event = _job_cancel_event(job_id)
        n_files = max(len(files), 1)

        # 每个文件的进度折算到 0~92%，剩下留给收尾
        def make_cb(index, filepath):
            def cb(cur, total, msg):
                frac = (cur / total) if total else 0
                pct = int((index + frac) / n_files * 92)
                _job_set(job_id, progress=max(0, min(pct, 92)),
                         message=f"[{Path(filepath).name}] {msg}")
            return cb

        if kind == 'scan':
            items = []
            grand_total = 0
            for idx, fp in enumerate(files):
                if cancel_event is not None and cancel_event.is_set():
                    raise engine.Cancelled('任务已取消')
                try:
                    details = engine.scan_file(
                        fp, keywords, use_ocr, case_sensitive,
                        make_cb(idx, fp), cancel_event
                    )
                    total = sum(d['text'] + d['ocr'] for d in details.values())
                    grand_total += total
                    items.append({
                        'filepath': fp,
                        'name': Path(fp).name,
                        'details': details,
                        'total': total,
                    })
                except engine.Cancelled:
                    raise
                except Exception as e:
                    log.error(f"扫描失败 {fp}: {e}")
                    items.append({'filepath': fp, 'name': Path(fp).name,
                                  'details': {}, 'total': 0, 'error': str(e)})

            _job_set(job_id, status='done', progress=100,
                     message=f'完成，共 {grand_total} 处',
                     result={'items': items, 'total': grand_total},
                     finished_at=time.time())

        elif kind == 'redact':
            items = []
            grand_total = 0
            for idx, fp in enumerate(files):
                if cancel_event is not None and cancel_event.is_set():
                    raise engine.Cancelled('任务已取消')

                src = Path(fp)
                out_dir = src.parent if save_location == 'source' else OUTPUT_FOLDER
                out_dir.mkdir(parents=True, exist_ok=True)
                out_path = out_dir / f"{src.stem}_redacted{src.suffix}"
                n = 1
                while out_path.exists():
                    out_path = out_dir / f"{src.stem}_redacted_{n}{src.suffix}"
                    n += 1

                try:
                    count = engine.redact_file(
                        fp, str(out_path), keywords, use_ocr, case_sensitive,
                        make_cb(idx, fp), cancel_event
                    )
                    grand_total += count
                    items.append({
                        'filepath': fp,
                        'name': src.name,
                        'output_path': str(out_path),
                        'output_name': out_path.name,
                        'count': count,
                    })
                    log.info(f"遮罩完成 {src.name}: {count} 处 -> {out_path.name}")
                except engine.Cancelled:
                    raise
                except Exception as e:
                    log.error(f"遮罩失败 {fp}: {e}")
                    items.append({'filepath': fp, 'name': src.name,
                                  'count': 0, 'error': str(e)})

            failed = sum(1 for i in items if i.get('error'))
            if failed and failed == len(items):
                _job_set(job_id, status='error',
                         error='全部文件处理失败，请检查文件格式',
                         finished_at=time.time())
            else:
                _job_set(job_id, status='done', progress=100,
                         message=f'完成，共遮挡 {grand_total} 处',
                         result={'items': items, 'count': grand_total,
                                 'failed': failed},
                         finished_at=time.time())

    except engine.Cancelled:
        log.info(f"任务已取消: {job_id}")
        _job_set(job_id, status='cancelled', message='已取消',
                 finished_at=time.time())
    except Exception as e:
        log.error(f"任务失败: {e}\n{traceback.format_exc()}")
        _job_set(job_id, status='error', error=str(e), finished_at=time.time())


# ── 路由 ──────────────────────────────────────────────
@app.route('/')
def index():
    html_path = WEB_DIR / 'index.html'
    if not html_path.exists():
        return f"错误: 找不到前端页面 {html_path}", 500
    return html_path.read_text(encoding='utf-8')


@app.route('/api/status')
def api_status():
    return jsonify({
        'ok': True,
        'version': VERSION,
        'ocr_available': engine.ocr_available(),
        'ocr_engine': engine.ocr_engine_desc(),
        'supported_formats': sorted(engine.SUPPORTED_EXTENSIONS),
        'max_files': MAX_FILES_PER_JOB,
        'max_keywords': MAX_KEYWORDS,
    })


@app.route('/api/presets')
def api_presets():
    return jsonify({'ok': True, 'presets': engine.PRESETS})


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """批量上传：multipart 里 file 字段可重复。"""
    try:
        files = request.files.getlist('file') or request.files.getlist('files')
        files = [f for f in files if f and f.filename]
        if not files:
            return jsonify({'success': False, 'error': '没有选择文件'}), 400
        if len(files) > MAX_FILES_PER_JOB:
            return jsonify({'success': False,
                            'error': f'一次最多 {MAX_FILES_PER_JOB} 个文件'}), 400

        saved = []
        for file in files:
            ext = Path(file.filename).suffix.lower()
            if ext not in engine.SUPPORTED_EXTENSIONS:
                saved.append({'filename': file.filename, 'error':
                              f'不支持的格式 {ext or "（无扩展名）"}'})
                continue

            safe_name = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
            save_path = UPLOAD_FOLDER / safe_name
            file.save(str(save_path))

            saved.append({
                'filename': file.filename,
                'filepath': str(save_path),
                'size': save_path.stat().st_size,
                'pages': engine.page_count(str(save_path)),
                'kind': engine.detect_kind(str(save_path)),
            })
            log.info(f"上传成功: {file.filename} -> {save_path.name}")

        return jsonify({'success': True, 'files': saved})
    except Exception as e:
        log.error(f"上传失败: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _start_job(kind):
    data = request.get_json(silent=True) or {}

    raw_paths = data.get('filepaths')
    if not raw_paths and data.get('filepath'):
        raw_paths = [data['filepath']]
    if not isinstance(raw_paths, list) or not raw_paths:
        return jsonify({'success': False, 'error': '缺少文件'}), 400
    if len(raw_paths) > MAX_FILES_PER_JOB:
        return jsonify({'success': False,
                        'error': f'一次最多处理 {MAX_FILES_PER_JOB} 个文件'}), 400

    files = []
    for p in raw_paths:
        fp = resolve_inside(p)
        if fp is None or not fp.exists():
            return jsonify({'success': False,
                            'error': f'文件不存在或路径非法: {Path(str(p)).name}'}), 400
        files.append(str(fp))

    try:
        keywords = _clean_keywords(data.get('keywords'))
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    use_ocr = bool(data.get('use_ocr', True))
    case_sensitive = bool(data.get('case_sensitive', False))
    save_location = data.get('save_location', 'downloads')

    _gc_jobs()
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            'status': 'pending', 'progress': 0, 'message': '排队中...',
            'created_at': time.time(),
            '_cancel': threading.Event(),
        }

    threading.Thread(
        target=_run_job,
        args=(job_id, kind, files, keywords, use_ocr, case_sensitive, save_location),
        daemon=True
    ).start()

    return jsonify({'success': True, 'job_id': job_id, 'files': len(files)})


@app.route('/api/find', methods=['POST'])
def api_find():
    return _start_job('scan')


@app.route('/api/redact', methods=['POST'])
def api_redact():
    return _start_job('redact')


@app.route('/api/job/<job_id>')
def api_job(job_id):
    job = _job_get(job_id)
    if not job:
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    return jsonify({'success': True, **job})


@app.route('/api/job/<job_id>/cancel', methods=['POST'])
def api_job_cancel(job_id):
    event = _job_cancel_event(job_id)
    if event is None:
        return jsonify({'success': False, 'error': '任务不存在'}), 404
    event.set()
    _job_set(job_id, message='正在取消（当前页处理完成后停止）...')
    return jsonify({'success': True})


@app.route('/api/preview')
def api_preview():
    """渲染某一页为图片（用于遮罩效果核对），支持 PDF 与图片。"""
    fp = resolve_inside(request.args.get('path', ''))
    if fp is None or not fp.exists():
        return jsonify({'success': False, 'error': '文件不存在或路径非法'}), 404

    kind = engine.detect_kind(str(fp))
    if kind == 'image':
        return send_file(fp, mimetype=None, as_attachment=False)

    if kind != 'pdf':
        return jsonify({'success': False,
                        'error': '该格式暂不支持预览（Word/Excel/PPT 请直接打开文件）'}), 400

    try:
        page_no = int(request.args.get('page', 1) or 1)
    except ValueError:
        page_no = 1
    try:
        dpi = int(request.args.get('dpi', 110) or 110)
    except ValueError:
        dpi = 110
    dpi = max(60, min(dpi, 180))

    try:
        png, pages = engine.render_page_png(str(fp), page_no, dpi)
    except Exception as e:
        log.error(f"预览失败: {e}")
        return jsonify({'success': False, 'error': f'预览失败: {e}'}), 500

    resp = Response(png, mimetype='image/png')
    resp.headers['X-Total-Pages'] = str(pages)
    resp.headers['Cache-Control'] = 'no-store'
    return resp


@app.route('/api/download')
def api_download():
    """下载处理后的文件（仅限 outputs/ uploads/，防路径穿越）。"""
    fp = resolve_inside(request.args.get('path', ''))
    if fp is None:
        return jsonify({'success': False, 'error': '路径非法'}), 403
    if not fp.exists():
        return jsonify({'success': False, 'error': '文件不存在'}), 404

    return send_file(fp, as_attachment=True, download_name=fp.name)


@app.route('/api/reveal', methods=['POST'])
def api_reveal():
    """在系统文件管理器里定位输出文件（仅本机使用）。"""
    data = request.get_json(silent=True) or {}
    fp = resolve_inside(data.get('path', ''))
    if fp is None or not fp.exists():
        return jsonify({'success': False, 'error': '文件不存在或路径非法'}), 404

    try:
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', '/select,' + str(fp)])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', str(fp)])
        else:
            subprocess.Popen(['xdg-open', str(fp.parent)])
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 主程序 ────────────────────────────────────────────
def find_free_port(start=5000, tries=20):
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    return start


def open_browser(port, delay=1.5):
    time.sleep(delay)
    url = f'http://127.0.0.1:{port}'
    try:
        webbrowser.open(url)
    except Exception as e:
        log.warning(f"无法自动打开浏览器: {e}，请手动访问 {url}")


def main():
    port = find_free_port()
    url = f'http://127.0.0.1:{port}'

    log.info("=" * 60)
    log.info(f"📑 文档隐私遮罩工具 v{VERSION}")
    log.info("=" * 60)
    log.info(f"上传目录: {UPLOAD_FOLDER}")
    log.info(f"输出目录: {OUTPUT_FOLDER}")
    log.info(f"OCR 引擎: {engine.ocr_engine_desc() if engine.ocr_available() else '不可用'}")
    log.info(f"👉 浏览器访问: {url}")
    log.info("=" * 60)

    threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False, threaded=True)


if __name__ == '__main__':
    main()
