#!/usr/bin/env python3
"""TARS's wake word on a kiosk with a ReSpeaker: "TARS" / "Hey TARS" (Payton 2026-10-27).

Listens all the time on the shared microphone (ALSA pcm `tars_mic`, a dsnoop of the ReSpeaker's echo-cancelled voice
channel, so the panel's intercom and doorbell Talk can open the mic too) with openWakeWord's two custom models, and
when one fires tells the Scarth Wall Panel add-on: POST <panel>/api/tars/wake {kiosk, word, score, noise}. The add-on
picks the room that heard it best and that kiosk's page listens and answers (scarth-panel src/lib/tarsKiosk.js).
Audio never leaves the kiosk until the page records the question itself.

Kiosk id and panel address come from [kiosk] url in kiosk_config.ini (https://host:8443/<room>?kiosk=<id>).
Optional [tars_wake]: pcm, hey_tars (threshold), tars (threshold), cooldown (s), models (dir).
Models: ~/tars-wake/models/{hey_tars,tars}.onnx plus openWakeWord's melspectrogram.onnx and embedding_model.onnx.
Runs from ~/tars-wake/.venv (onnxruntime, numpy, scipy, scikit-learn, requests, openwakeword 0.6.0 --no-deps).
"""
import configparser, json, math, os, subprocess, sys, time, urllib.parse
from collections import deque

import numpy as np
import requests
from openwakeword.model import Model

HOME = os.path.expanduser('~')
INI = os.environ.get('KIOSK_CONFIG', os.path.join(HOME, 'kiosk_config.ini'))
FRAME = 1280                       # 80 ms at 16 kHz, what openWakeWord takes
NOISE_WINDOW = 62                  # ~5 s of frames for the room's noise floor


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


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
        'pcm': w.get('pcm', 'tars_mic'),
        'thresholds': {'hey_tars': float(w.get('hey_tars', 0.5)), 'tars': float(w.get('tars', 0.6))},
        'cooldown': float(w.get('cooldown', 3)),
        'models': models,
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
    last = 0.0
    session = requests.Session()
    while True:
        rec = subprocess.Popen(['arecord', '-q', '-D', s['pcm'], '-f', 'S16_LE', '-r', '16000', '-c', '1', '-t', 'raw'],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                buf = rec.stdout.read(FRAME * 2)
                if len(buf) < FRAME * 2:
                    break
                frame = np.frombuffer(buf, dtype=np.int16)
                levels.append(math.sqrt(float(np.mean((frame.astype(np.float32) / 32768.0) ** 2))))
                scores = model.predict(frame)
                now = time.time()
                if now - last < s['cooldown']:
                    continue
                hits = [(scores.get(n, 0.0), n) for n in present if scores.get(n, 0.0) >= s['thresholds'][n]]
                if not hits:
                    continue
                score, word = max(hits)
                last = now
                # The room's background: the quieter part of the last few seconds (speech excluded).
                noise = float(np.percentile(levels, 20)) if levels else 0.0
                model.reset()
                try:
                    r = session.post(s['wake_url'], json={'kiosk': s['kiosk'], 'word': word, 'score': round(float(score), 3),
                                                          'noise': round(noise, 4)}, timeout=3)
                    log(f'{word} {score:.2f} (noise {noise:.3f}) -> {r.status_code} {r.text[:80]}')
                except requests.RequestException as e:
                    log(f'{word} {score:.2f}: add-on unreachable ({e.__class__.__name__})')
        finally:
            rec.kill()
        err = (rec.stderr.read() or b'').decode(errors='replace').strip()
        log('microphone stream ended', err[:200], '- restarting in 3 s')
        time.sleep(3)


if __name__ == '__main__':
    main()
