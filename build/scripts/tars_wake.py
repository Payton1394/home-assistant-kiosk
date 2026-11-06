#!/usr/bin/env python3
"""TARS's wake word on a kiosk with a ReSpeaker: "TARS" / "Hey TARS" (Payton 2026-10-27).

Listens all the time on the shared microphone (ALSA pcm `tars_mic`, a dsnoop of the ReSpeaker's echo-cancelled voice
channel, so the panel's intercom and doorbell Talk can open the mic too) with openWakeWord's two custom models, and
when one fires tells the Scarth Wall Panel add-on: POST <panel>/api/tars/wake {kiosk, word, score, noise}. The add-on
picks the room that heard it best and that kiosk's page listens and answers (scarth-panel src/lib/tarsKiosk.js).
Audio never leaves the kiosk until the page records the question itself. The 2.56 s that set off each wake are kept ON
THE KIOSK (~/tars-wake/clips, newest 400) for retraining the models on what falsely wakes them (Payton 2026-11-01: the
Family Room TV woke TARS 17 times in a day); Claude fetches them over SSH.

BACKUP MODE (Payton 2026-11-03): when the add-on can't be reached at all (the Home Assistant Pi is down), the sentence after
a wake goes straight to the TARS server on TrueNAS (POST <backup>/v1/backup/turn?audio=wav with this kiosk's backup
code from ~/.config/tars-backup-token) and its answer, which starts "Backup mode.", is played here with aplay.

Kiosk id and panel address come from [kiosk] url in kiosk_config.ini (https://host:8443/<room>?kiosk=<id>).
Optional [tars_wake] backup = the TARS server (default http://192.168.1.2:8770).
Optional [tars_wake]: pcm, hey_tars (threshold), tars (threshold), cooldown (s), models (dir).
Models: ~/tars-wake/models/{hey_tars,tars}.onnx plus openWakeWord's melspectrogram.onnx and embedding_model.onnx.
Runs from ~/tars-wake/.venv (onnxruntime, numpy, scipy, scikit-learn, requests, openwakeword 0.6.0 --no-deps).
"""
import configparser, io, json, math, os, subprocess, sys, threading, time, urllib.parse, wave
from collections import deque

import numpy as np
import requests
from openwakeword.model import Model

HOME = os.path.expanduser('~')
INI = os.environ.get('KIOSK_CONFIG', os.path.join(HOME, 'kiosk_config.ini'))
FRAME = 1280                       # 80 ms at 16 kHz, what openWakeWord takes
NOISE_WINDOW = 62                  # ~5 s of frames for the room's noise floor
BEAT_S = 60                        # heartbeat to the add-on
CLIP_FRAMES = 32                   # 2.56 s kept per wake
CLIP_KEEP = 400
CLIPS = os.path.join(HOME, 'tars-wake', 'clips')
# Say it in one breath (Payton 2026-11-02: "say hey tars and then whatever I want without waiting"): after a wake this
# listener keeps recording the sentence itself (no gap while the page opens its microphone) and posts it to the add-on
# (/api/tars/wake-turn); the add-on answers only the room that won the wake.
PRE_FRAMES = 6                     # 0.48 s before the wake fired, in case the sentence ran straight on
START_WAIT = 50                    # 4 s for speech to start (someone who still waits for the tone)
END_QUIET = 11                     # 0.88 s of quiet ends the sentence
MAX_FRAMES = 150                   # 12 s at most


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def keep_clip(frames, word, score):
    """The audio that set off a wake, kept on the kiosk for retraining (the newest CLIP_KEEP)."""
    try:
        os.makedirs(CLIPS, exist_ok=True)
        name = os.path.join(CLIPS, f"{time.strftime('%Y%m%d-%H%M%S')}-{word}-{score:.2f}.wav")
        with wave.open(name, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b''.join(frames))
        old = sorted(os.listdir(CLIPS))
        for f in old[:-CLIP_KEEP]:
            os.remove(os.path.join(CLIPS, f))
    except OSError as e:
        log('could not keep the clip:', e)


def wav_bytes(frames):
    b = io.BytesIO()
    with wave.open(b, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(b''.join(frames))
    return b.getvalue()


def post_turn(session, url, kiosk, frames):
    """The sentence to the add-on, off the audio loop (the answer takes seconds)."""
    def go():
        try:
            r = session.post(url, data=wav_bytes(frames) if frames else b'', timeout=120,
                             headers={'content-type': 'audio/wav', 'x-tars-kiosk': kiosk})
            log(f'sentence ({len(frames) * 0.08:.1f} s) -> {r.status_code} {r.text[:60]}')
        except requests.RequestException as e:
            log(f'sentence: add-on unreachable ({e.__class__.__name__})')
    threading.Thread(target=go, daemon=True).start()


def post_backup_turn(url, token, frames):
    """Backup mode: the sentence to the TARS server itself, and its spoken answer played on this kiosk."""
    def go():
        try:
            r = requests.post(url, data=wav_bytes(frames), timeout=120,
                              headers={'content-type': 'audio/wav', 'authorization': f'Bearer {token}'})
            d = r.json()
            log(f"backup turn ({len(frames) * 0.08:.1f} s) -> {r.status_code} {d.get('mode')}: {d.get('reply', d)!s:.80}")
            if d.get('audio'):
                import base64
                subprocess.run(['aplay', '-q'], input=base64.b64decode(d['audio']), timeout=120)
        except (requests.RequestException, ValueError, subprocess.SubprocessError) as e:
            log(f'backup turn failed ({e.__class__.__name__}: {str(e)[:80]})')
    threading.Thread(target=go, daemon=True).start()


def backup_token():
    p = os.path.join(HOME, '.config', 'tars-backup-token')
    try:
        return open(p).read().strip()
    except OSError:
        return ''


def settings():
    c = configparser.ConfigParser()
    c.read(INI)
    url = c.get('kiosk', 'url', fallback='')
    u = urllib.parse.urlparse(url)
    kiosk = (urllib.parse.parse_qs(u.query).get('kiosk') or [''])[0]
    if not kiosk or not u.netloc:
        sys.exit(f'tars-wake: no kiosk id in [kiosk] url of {INI}')
    w = c['tars_wake'] if c.has_section('tars_wake') else {}
    models = os.path.expanduser(w.get('models', '~/tars-wake/models'))
    return {
        'kiosk': kiosk,
        'wake_url': f'{u.scheme}://{u.netloc}/api/tars/wake',
        'turn_url': f'{u.scheme}://{u.netloc}/api/tars/wake-turn',
        'pcm': w.get('pcm', 'tars_mic'),
        'thresholds': {'hey_tars': float(w.get('hey_tars', 0.5)), 'tars': float(w.get('tars', 0.6))},
        'cooldown': float(w.get('cooldown', 3)),
        'models': models,
        'backup_url': w.get('backup', 'http://192.168.1.2:8770').rstrip('/') + '/v1/backup/turn?audio=wav',
    }


def main():
    s = settings()
    paths = {n: os.path.join(s['models'], f'{n}.onnx') for n in s['thresholds']}
    present = {n: p for n, p in paths.items() if os.path.exists(p)}
    if not present:
        log('no wake-word models in', s['models'], '- waiting for them')
        while not any(os.path.exists(p) for p in paths.values()):
            time.sleep(60)
        return main()
    model = Model(wakeword_models=list(present.values()), inference_framework='onnx',
                  melspec_model_path=os.path.join(s['models'], 'melspectrogram.onnx'),
                  embedding_model_path=os.path.join(s['models'], 'embedding_model.onnx'))
    log(f"kiosk {s['kiosk']}: listening for {', '.join(present)} on {s['pcm']} -> {s['wake_url']}",
        {n: s['thresholds'][n] for n in present})
    levels = deque(maxlen=NOISE_WINDOW)
    recent = deque(maxlen=CLIP_FRAMES)
    last = 0.0
    session = requests.Session()
    # A heartbeat to the add-on every minute from inside the audio loop (TARS's health checks, add-on 0.1.192): no
    # beat means the service, the microphone stream or the kiosk is down; a level near zero means a dead microphone.
    alive_url = s['wake_url'].replace('/api/tars/wake', '/api/tars/alive')
    last_beat = 0.0
    while True:
        rec = subprocess.Popen(['arecord', '-q', '-D', s['pcm'], '-f', 'S16_LE', '-r', '16000', '-c', '1', '-t', 'raw'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                buf = rec.stdout.read(FRAME * 2)
                if len(buf) < FRAME * 2:
                    break
                recent.append(buf)
                frame = np.frombuffer(buf, dtype=np.int16)
                levels.append(math.sqrt(float(np.mean((frame.astype(np.float32) / 32768.0) ** 2))))
                scores = model.predict(frame)
                now = time.time()
                if now - last_beat >= BEAT_S:
                    last_beat = now
                    try:
                        session.post(alive_url, json={'kiosk': s['kiosk'], 'level': round(float(np.median(levels)) if levels else 0.0, 5),
                                                      'models': sorted(present)}, timeout=3)
                    except requests.RequestException:
                        pass
                if now - last < s['cooldown']:
                    continue
                hits = [(scores.get(n, 0.0), n) for n in present if scores.get(n, 0.0) >= s['thresholds'][n]]
                if not hits:
                    continue
                score, word = max(hits)
                last = now
                keep_clip(list(recent), word, float(score))
                # The room's background: the quieter part of the last few seconds (speech excluded).
                noise = float(np.percentile(levels, 20)) if levels else 0.0
                model.reset()
                try:
                    r = session.post(s['wake_url'], json={'kiosk': s['kiosk'], 'word': word, 'score': round(float(score), 3),
                                                          'noise': round(noise, 4), 'streams': True}, timeout=3)
                    log(f'{word} {score:.2f} (noise {noise:.3f}) -> {r.status_code} {r.text[:80]}')
                    heard = r.ok and r.json().get('result') == 'heard'
                    backup = False
                except (requests.RequestException, ValueError) as e:
                    # The add-on is gone (the Home Assistant Pi is down): TARS on TrueNAS answers here directly.
                    backup = isinstance(e, requests.RequestException) and bool(backup_token())
                    log(f'{word} {score:.2f}: add-on unreachable ({e.__class__.__name__})' + ('; backup mode' if backup else ''))
                    heard = backup
                if not heard:
                    continue
                # Keep listening: the sentence from just before the wake to the first pause after speech.
                pre = list(recent)[-PRE_FRAMES:]
                said, started, quiet, n = [], False, 0, 0
                gate = max(noise * 3.0, 0.004)
                while n < MAX_FRAMES:
                    b2 = rec.stdout.read(FRAME * 2)
                    if len(b2) < FRAME * 2:
                        break
                    n += 1
                    said.append(b2)
                    lv = math.sqrt(float(np.mean((np.frombuffer(b2, dtype=np.int16).astype(np.float32) / 32768.0) ** 2)))
                    if lv > gate:
                        started, quiet = True, 0
                    elif started:
                        quiet += 1
                        if quiet >= END_QUIET:
                            break
                    elif n >= START_WAIT:
                        break
                if backup:
                    if started:
                        post_backup_turn(s['backup_url'], backup_token(), pre + said)
                else:
                    post_turn(session, s['turn_url'], s['kiosk'], pre + said if started else [])
                model.reset()
                recent.clear()
                last = time.time()
        finally:
            rec.kill()
        err = (rec.stderr.read() or b'').decode(errors='replace').strip()
        log('microphone stream ended', err[:200], '- restarting in 3 s')
        time.sleep(3)


if __name__ == '__main__':
    main()
