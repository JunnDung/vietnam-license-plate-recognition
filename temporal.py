"""Bounded plate tracks and conservative voting for one recognition worker."""
from collections import Counter, deque
from copy import deepcopy
import threading
import time
import uuid


def overlap(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - area
    return area / union if union > 0 else 0.


class StreamConsensus:
    # ponytail: in-memory sessions require one API worker; use shared state if multiple workers are needed.
    def __init__(self):
        self.sessions = {}
        self.lock = threading.RLock()

    def session(self, stream_id):
        now = time.monotonic()
        self.sessions = {key: value for key, value in self.sessions.items() if now-value['touched'] < 600}
        if stream_id not in self.sessions:
            if len(self.sessions) >= 128:
                raise ValueError('Quá nhiều phiên nhận diện. Thử lại sau hoặc khởi động lại API.')
            self.sessions[stream_id] = {'touched': now, 'time': -1., 'tracks': [], 'saved': {}, 'reply': None, 'signature': None}
        session = self.sessions[stream_id]
        session['touched'] = now
        return session

    def update(self, session, detections, sample_time, width, height):
        session['tracks'] = [track for track in session['tracks'] if sample_time-track['time'] <= 2.5]
        session['saved'] = {plate: moment for plate, moment in session['saved'].items() if sample_time-moment < 30}
        available = list(session['tracks'])
        for item in detections:
            bbox = [value / (width if index % 2 == 0 else height) for index, value in enumerate(item['bbox'])]
            candidates = []
            for track in available:
                elapsed = sample_time-track['time']
                predicted = [value+speed*elapsed for value,speed in zip(track['bbox'],track['velocity'])]
                candidates.append((max(overlap(bbox,track['bbox']),overlap(bbox,predicted)),track))
            candidates.sort(key=lambda pair: pair[0],reverse=True)
            # Ambiguous crossings start a new track instead of silently mixing two vehicles.
            matched = candidates and candidates[0][0] >= .2 and (len(candidates) < 2 or candidates[0][0]-candidates[1][0] >= .15)
            if matched:
                track = candidates[0][1]
                available.remove(track)
            else:
                track = {'id': uuid.uuid4().hex, 'votes': deque(maxlen=7), 'time': sample_time, 'bbox': bbox, 'emitted': set(), 'velocity': [0.]*4}
                session['tracks'].append(track)
            clean = bool(item['plate']) and item.get('valid_format', False) and not item['needs_review']
            track['votes'].append(item['plate'] if clean else '')
            elapsed = sample_time-track['time']
            if elapsed > 0:
                track['velocity'] = [(current-previous)/elapsed for current,previous in zip(bbox,track['bbox'])]
            track.update(bbox=bbox, time=sample_time)
            votes = Counter(plate for plate in track['votes'] if plate)
            plate, count = votes.most_common(1)[0] if votes else ('', 0)
            stable = count >= 3 and count / len(track['votes']) >= .6
            current_agrees = clean and item['plate'] == plate
            status = 'stable' if stable and current_agrees else ('review' if item['needs_review'] or stable else 'pending')
            item['temporal'] = {'track_id': track['id'], 'status': status, 'plate': plate if stable else '',
                                'votes': count, 'observations': len(track['votes']),
                                'new_event': status == 'stable' and plate not in track['emitted'] and plate not in session['saved']}
        session['tracks'] = session['tracks'][-40:]
        session['time'] = sample_time

    def snapshot(self, session):
        return deepcopy(session)

    def mark_saved(self, session, item, sample_time):
        plate = item['plate']
        session['saved'][plate] = sample_time
        for track in session['tracks']:
            if track['id'] == item['temporal']['track_id']:
                track['emitted'].add(plate)
