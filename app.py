import csv
import hashlib
import io
import json
import logging
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager, contextmanager, nullcontext
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from recognition import MAX_BYTES, ROOT, PlateEngine, decode_image, format_plate, is_vietnamese_plate, jpeg_bytes, normalize_plate
from temporal import StreamConsensus

DATA = Path(os.getenv('PLATE_DATA_DIR', str(ROOT / 'runtime'))).resolve()
API_KEY = os.getenv('PLATE_API_KEY', '')
log = logging.getLogger(__name__)


@contextmanager
def connect():
    connection = sqlite3.connect(DATA / 'history.sqlite3', timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


@asynccontextmanager
async def lifespan(application):
    application.state.streams = StreamConsensus()
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / 'images').mkdir(exist_ok=True)
    with connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS records (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, source TEXT NOT NULL,
            plate TEXT NOT NULL, display_plate TEXT NOT NULL, detector_confidence REAL NOT NULL,
            ocr_confidence REAL NOT NULL, needs_review INTEGER NOT NULL, bbox TEXT NOT NULL,
            image_id TEXT NOT NULL, crop_id TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS plate_index ON records(plate)')
        db.execute('CREATE INDEX IF NOT EXISTS time_index ON records(created_at)')
        if 'review_details' not in {row[1] for row in db.execute('PRAGMA table_info(records)')}:
            db.execute("ALTER TABLE records ADD COLUMN review_details TEXT NOT NULL DEFAULT '{}'")
        db.execute('''CREATE TABLE IF NOT EXISTS parking_sessions (
            id TEXT PRIMARY KEY, plate TEXT NOT NULL, entered_at TEXT NOT NULL, exited_at TEXT,
            entry_record_id TEXT NOT NULL REFERENCES records(id),
            exit_record_id TEXT REFERENCES records(id),
            entry_corrected INTEGER NOT NULL, exit_corrected INTEGER)''')
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS one_open_session ON parking_sessions(plate) WHERE exited_at IS NULL')
    if not getattr(application.state, 'engine', None):
        try:
            application.state.engine = PlateEngine(device=os.getenv('PLATE_DEVICE', 'auto'))
            application.state.model_error = None
        except Exception as error:
            log.exception('Cannot initialize recognition models')
            application.state.engine = None
            application.state.model_error = type(error).__name__
    yield


def authorized(request: Request):
    if API_KEY and not secrets.compare_digest(request.headers.get('X-API-Key', ''), API_KEY):
        raise HTTPException(401, 'API key không hợp lệ.')


app = FastAPI(title='Biển Số Việt · Recognition API', version='1.3.0', lifespan=lifespan)


@app.middleware('http')
async def reject_large_requests(request, call_next):
    length = request.headers.get('content-length')
    if request.method == 'POST' and request.url.path == '/api/recognize' and length is None:
        return Response('Content-Length required for bounded image uploads', status_code=411)
    try:
        if length is not None and int(length) < 0:
            raise ValueError()
        oversized = length is not None and int(length) > MAX_BYTES + 64 * 1024
    except ValueError:
        return Response('Invalid Content-Length', status_code=400)
    if oversized:
        return Response('Upload exceeds 10 MB', status_code=413)
    return await call_next(request)


@app.get('/api/health')
def health():
    return {'status': 'ready' if getattr(app.state, 'engine', None) else 'model_unavailable',
            'detector': 'YOLO11n · fine-tuned Vietnamese plates', 'ocr': 'CCT S v2 · pretrained',
            'device': getattr(getattr(app.state, 'engine', None), 'device', None), 'auth_required': bool(API_KEY),
            'version': app.version, 'storage_free_mb': round(shutil.disk_usage(DATA).free / 1024**2),
            'detector_weights_sha256': getattr(getattr(app.state, 'engine', None), 'detector_weights_sha256', None),
            'model_error': getattr(app.state, 'model_error', None)}


@app.get('/api/model', dependencies=[Depends(authorized)])
def model_report():
    reports = {}
    for name in ('training', 'robustness', 'ocr_evaluation', 'hardening', 'ocr_weather', 'real_video'):
        path = ROOT / 'reports' / (name + '.json')
        if path.exists():
            reports[name] = json.loads(path.read_text(encoding='utf-8'))
            if name == 'real_video':
                for clip in reports[name]['clips']:
                    clip.pop('frames',None)
    return reports


@app.post('/api/recognize', dependencies=[Depends(authorized)])
def recognize(file: Annotated[UploadFile, File()], source: Annotated[str, Form(max_length=80)] = 'upload',
              confidence: Annotated[float, Form(ge=.1, le=.95)] = .35,
              save: Annotated[bool, Form()] = True,
              stream_id: Annotated[uuid.UUID | None, Form()] = None,
              sample_time: Annotated[float | None, Form(ge=0, le=86400, allow_inf_nan=False)] = None):
    if not getattr(app.state, 'engine', None):
        raise HTTPException(503, 'Mô hình chưa sẵn sàng. Xem hướng dẫn tải model và /api/health.')
    raw = file.file.read(MAX_BYTES + 1)
    try:
        image = decode_image(raw)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    if (stream_id is None) != (sample_time is None):
        raise HTTPException(422, 'Gửi stream_id và sample_time cùng nhau cho camera/video.')
    streams = app.state.streams
    with streams.lock if stream_id else nullcontext():
        session = None
        if stream_id:
            try:
                session = streams.session(str(stream_id))
            except ValueError as error:
                raise HTTPException(429, str(error)) from error
            signature = (hashlib.sha256(raw).hexdigest(), source, confidence)
            if sample_time <= session['time']:
                if sample_time == session['time'] and signature == session['signature']:
                    return session['reply']
                raise HTTPException(409, 'Mốc khung phải tăng trong một phiên. Quét lại cần stream_id mới.')
            previous = streams.snapshot(session)
        try:
            reply = recognize_image(image, source, confidence, save, session, sample_time)
            if session is not None:
                session.update(reply=reply, signature=signature)
            return reply
        except Exception:
            if session is not None:
                streams.sessions[str(stream_id)] = previous
            raise


def recognize_image(image, source, confidence, save, session=None, sample_time=None):
    start = time.perf_counter()
    detections = app.state.engine.predict(image, confidence=confidence)
    if session is not None:
        app.state.streams.update(session, detections, sample_time, image.shape[1], image.shape[0])
    selected, selected_plates = [], set()
    for item in detections:
        if save and (session is None or item['temporal']['new_event'] and item['plate'] not in selected_plates):
            selected.append(item)
            selected_plates.add(item['plate'])
    request_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    files_written, records = [], []
    try:
        if selected:
            path = DATA / 'images' / (request_id + '.jpg')
            path.write_bytes(jpeg_bytes(image))
            files_written.append(path)
        with connect() as db:
            for detection in detections:
                should_save = any(item is detection for item in selected)
                crop = detection.pop('crop')
                record_id = uuid.uuid4().hex
                detection.update({'id': record_id, 'created_at': now, 'source': source,
                                  'image_url': f'/api/images/{request_id}' if should_save else None,
                                  'crop_url': f'/api/images/{record_id}' if should_save else None, 'saved': should_save})
                if should_save:
                    path = DATA / 'images' / (record_id + '.jpg')
                    path.write_bytes(jpeg_bytes(crop))
                    files_written.append(path)
                    details = {key: detection.get(key) for key in ('quality','ocr_disagreement','valid_format','temporal')}
                    db.execute('INSERT INTO records (id,created_at,source,plate,display_plate,detector_confidence,ocr_confidence,needs_review,bbox,image_id,crop_id,review_details) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                               (record_id, now, source, detection['plate'], detection['display_plate'],
                                detection['detector_confidence'], detection['ocr_confidence'],
                                int(detection['needs_review']), json.dumps(detection['bbox']), request_id, record_id, json.dumps(details)))
                records.append(detection)
    except Exception:
        for path in files_written:
            path.unlink(missing_ok=True)
        raise
    if session is not None:
        for item in selected:
            app.state.streams.mark_saved(session, item, sample_time)
    return {'request_id': request_id, 'created_at': now, 'width': image.shape[1], 'height': image.shape[0],
            'latency_ms': round((time.perf_counter()-start)*1000, 1), 'detections': records,
            'message': 'Không phát hiện biển số ở ngưỡng hiện tại.' if not records else None}


def history_query(plate, since, until):
    clauses, values = [], []
    text = normalize_plate(plate)
    if text:
        clauses.append('plate LIKE ?')
        values.append('%' + text + '%')
    for value, operator in ((since, '>='), (until, '<=')):
        if value:
            try:
                moment = datetime.fromisoformat(value.replace('Z', '+00:00'))
                if moment.tzinfo is None:
                    raise ValueError()
                value = moment.astimezone(timezone.utc).isoformat()
            except ValueError as error:
                raise HTTPException(400, 'Thời gian phải là ISO 8601 kèm múi giờ.') from error
            clauses.append('created_at ' + operator + ' ?')
            values.append(value)
    return (' WHERE ' + ' AND '.join(clauses) if clauses else ''), values


@app.get('/api/history', dependencies=[Depends(authorized)])
def history(plate: str = '', since: str = '', until: str = '',
            limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    where, params = history_query(plate, since, until)
    with connect() as db:
        total = db.execute('SELECT COUNT(*) FROM records' + where, params).fetchone()[0]
        rows = db.execute('SELECT * FROM records' + where + ' ORDER BY created_at DESC, id LIMIT ? OFFSET ?',
                          params + [limit, offset]).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item['bbox'] = json.loads(item['bbox'])
        item['needs_review'] = bool(item['needs_review'])
        item['review_details'] = json.loads(item['review_details'])
        item['image_url'] = '/api/images/' + item.pop('image_id')
        item['crop_url'] = '/api/images/' + item.pop('crop_id')
        items.append(item)
    return {'total': total, 'items': items, 'offset': offset, 'limit': limit}


@app.get('/api/history.csv', dependencies=[Depends(authorized)])
def export_history(plate: str = '', since: str = '', until: str = ''):
    where, params = history_query(plate, since, until)
    with connect() as db:
        rows = db.execute('SELECT created_at,source,plate,display_plate,detector_confidence,ocr_confidence,needs_review '
                          'FROM records' + where + ' ORDER BY created_at DESC', params).fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['created_at_utc', 'source', 'plate', 'display_plate', 'detector_confidence', 'ocr_confidence', 'needs_review'])
    for row in rows:
        # Prevent spreadsheet formula execution through user-supplied source names.
        writer.writerow(["'" + value if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r')))
                         else value for value in row])
    return Response('\ufeff' + output.getvalue(), media_type='text/csv; charset=utf-8',
                    headers={'Content-Disposition': 'attachment; filename="plate-history.csv"'})


@app.delete('/api/history/{record_id}', dependencies=[Depends(authorized)])
def delete_record(record_id: str):
    with connect() as db:
        row = db.execute('SELECT image_id,crop_id FROM records WHERE id=?', (record_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Không có lượt nhận diện.')
        used = db.execute('SELECT 1 FROM parking_sessions WHERE entry_record_id=? OR exit_record_id=? LIMIT 1',
                          (record_id, record_id)).fetchone()
        if used:
            raise HTTPException(409, 'Ảnh đang là bằng chứng xe vào/ra; không thể xóa riêng lượt nhận diện này.')
        db.execute('DELETE FROM records WHERE id=?', (record_id,))
        remaining = db.execute('SELECT 1 FROM records WHERE image_id=? LIMIT 1', (row['image_id'],)).fetchone()
    (DATA / 'images' / (row['crop_id'] + '.jpg')).unlink(missing_ok=True)
    if remaining is None:
        (DATA / 'images' / (row['image_id'] + '.jpg')).unlink(missing_ok=True)
    return {'deleted': record_id}


class ParkingEvent(BaseModel):
    record_id: str = Field(min_length=32, max_length=32, pattern='^[0-9a-f]{32}$')
    plate: str = Field(min_length=7, max_length=20)
    direction: Literal['in', 'out']
    confirmed: Literal[True]


def parking_item(row):
    item = dict(row)
    item['display_plate'] = format_plate(item['plate'])
    end = datetime.fromisoformat(item['exited_at']) if item['exited_at'] else datetime.now(timezone.utc)
    item['duration_seconds'] = max(0, int((end-datetime.fromisoformat(item['entered_at'])).total_seconds()))
    item['status'] = 'closed' if item['exited_at'] else 'active'
    return item


@app.post('/api/parking/events', dependencies=[Depends(authorized)])
def parking_event(event: ParkingEvent):
    plate = normalize_plate(event.plate)
    if not is_vietnamese_plate(plate):
        raise HTTPException(400, 'Biển số chưa đúng định dạng dân dụng Việt Nam được hỗ trợ. Hãy đối chiếu và nhập lại.')
    now = datetime.now(timezone.utc).isoformat()
    with connect() as db:
        # Serialize gate decisions; the partial unique index also enforces one active visit per plate.
        db.execute('BEGIN IMMEDIATE')
        record = db.execute('SELECT plate FROM records WHERE id=?', (event.record_id,)).fetchone()
        if record is None:
            raise HTTPException(404, 'Cần một lượt nhận diện đã lưu kèm ảnh để xác nhận xe vào/ra.')
        used = db.execute('SELECT 1 FROM parking_sessions WHERE entry_record_id=? OR exit_record_id=? LIMIT 1',
                          (event.record_id, event.record_id)).fetchone()
        if used:
            raise HTTPException(409, 'Ảnh này đã xác nhận một sự kiện. Hãy nhận diện một khung hình mới.')
        active = db.execute('SELECT * FROM parking_sessions WHERE plate=? AND exited_at IS NULL', (plate,)).fetchone()
        corrected = int(plate != record['plate'])
        if event.direction == 'in':
            if active is not None:
                raise HTTPException(409, 'Xe đã được ghi nhận đang trong bãi. Đối chiếu lượt vào hiện tại.')
            session_id = uuid.uuid4().hex
            db.execute('INSERT INTO parking_sessions VALUES (?,?,?,NULL,?,NULL,?,NULL)',
                       (session_id, plate, now, event.record_id, corrected))
        else:
            if active is None:
                raise HTTPException(409, 'Không có lượt vào đang mở cho biển số này. Đối chiếu ảnh vào và biển số trước khi xác nhận.')
            session_id = active['id']
            db.execute('UPDATE parking_sessions SET exited_at=?,exit_record_id=?,exit_corrected=? WHERE id=? AND exited_at IS NULL',
                       (now, event.record_id, corrected, session_id))
        row = db.execute('SELECT * FROM parking_sessions WHERE id=?', (session_id,)).fetchone()
    return {'direction': event.direction, 'session': parking_item(row), 'manually_confirmed': True}


@app.get('/api/parking', dependencies=[Depends(authorized)])
def parking_sessions(plate: str = '', status: Literal['active', 'closed', 'all'] = 'active',
                     limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0)):
    clauses, params = [], []
    normalized = normalize_plate(plate)
    if normalized:
        clauses.append('s.plate LIKE ?')
        params.append('%' + normalized + '%')
    if status != 'all':
        clauses.append('s.exited_at IS ' + ('NULL' if status == 'active' else 'NOT NULL'))
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    today_vn = datetime.now(timezone(timedelta(hours=7))).replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc, tomorrow_utc = (today_vn.astimezone(timezone.utc).isoformat(),
                               (today_vn+timedelta(days=1)).astimezone(timezone.utc).isoformat())
    with connect() as db:
        total = db.execute('SELECT COUNT(*) FROM parking_sessions s' + where, params).fetchone()[0]
        inside = db.execute('SELECT COUNT(*) FROM parking_sessions WHERE exited_at IS NULL').fetchone()[0]
        entered = db.execute('SELECT COUNT(*) FROM parking_sessions WHERE entered_at>=? AND entered_at<?',
                             (today_utc, tomorrow_utc)).fetchone()[0]
        exited = db.execute('SELECT COUNT(*) FROM parking_sessions WHERE exited_at>=? AND exited_at<?',
                            (today_utc, tomorrow_utc)).fetchone()[0]
        rows = db.execute('SELECT s.*,e.image_id AS entry_image_id,e.crop_id AS entry_crop_id,'
                          'x.image_id AS exit_image_id,x.crop_id AS exit_crop_id FROM parking_sessions s '
                          'JOIN records e ON e.id=s.entry_record_id LEFT JOIN records x ON x.id=s.exit_record_id' +
                          where + ' ORDER BY s.entered_at DESC,s.id LIMIT ? OFFSET ?', params + [limit, offset]).fetchall()
    items = []
    for row in rows:
        item = parking_item(row)
        for kind in ('entry_image', 'entry_crop', 'exit_image', 'exit_crop'):
            value = item.pop(kind + '_id')
            item[kind + '_url'] = '/api/images/' + value if value else None
        items.append(item)
    return {'inside': inside, 'entered_today': entered, 'exited_today': exited,
            'date_timezone': 'Asia/Ho_Chi_Minh', 'total': total, 'limit': limit, 'offset': offset, 'items': items}


@app.get('/api/images/{image_id}', dependencies=[Depends(authorized)])
def stored_image(image_id: str):
    if len(image_id) != 32 or any(c not in '0123456789abcdef' for c in image_id):
        raise HTTPException(404, 'Không có ảnh.')
    path = DATA / 'images' / (image_id + '.jpg')
    if not path.exists():
        raise HTTPException(404, 'Không có ảnh.')
    return FileResponse(path, media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=60'})


app.mount('/', StaticFiles(directory=ROOT / 'web', html=True), name='web')
