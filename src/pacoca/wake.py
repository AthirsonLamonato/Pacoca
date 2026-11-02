"""Local keyword spotting. No microphone API, transcription, network, or audio files."""
from __future__ import annotations

import multiprocessing
import os
from pathlib import Path
import threading
import time

from .config import bundle_root


def acoustic_path():
    import sys
    if getattr(sys, 'frozen', False):
        return bundle_root() / 'wakeword' / 'en-us'
    from pocketsphinx import get_model_path
    return Path(get_model_path()) / 'en-us' / 'en-us'


class KeywordDetector:
    """16 kHz signed little endian PCM; timestamps refer to this stream's samples."""
    def __init__(self, sensitivity='normal'):
        from pocketsphinx import Decoder
        thresholds = {'low': 1e-8, 'normal': 1e-10, 'high': 1e-13}
        self.decoder = Decoder(hmm=str(acoustic_path()), lm=None,
            dict=str(Path(__file__).with_name('wake.dic')), keyphrase='pacoca',
            kws_threshold=thresholds.get(sensitivity, 1e-10), samprate=16000,
            loglevel='ERROR')
        self.samples = self.base = 0
        self.decoder.start_utt()

    def reset(self):
        self.decoder.end_utt()
        self.decoder.start_utt()
        self.samples = self.base = 0

    def feed(self, pcm):
        if not isinstance(pcm, bytes) or not 0 < len(pcm) <= 10240 or len(pcm) % 2:
            raise ValueError('Envie PCM mono de 16 kHz em blocos de até 320 ms.')
        self.decoder.process_raw(pcm, False, False)
        self.samples += len(pcm) // 2
        if self.decoder.hyp():
            segment = next((s for s in self.decoder.seg() if s.word == 'pacoca'), None)
            if segment:
                event = {'type': 'wake', 'start': self.base + segment.start_frame * 160,
                         'end': self.base + (segment.end_frame + 1) * 160,
                         'samples': self.samples}
                self.decoder.end_utt(); self.decoder.start_utt(); self.base = self.samples
                return event
        # Bound the search history without cutting speech at arbitrary intervals.
        if self.samples-self.base > 16000*20:
            import struct
            if max(abs(x[0]) for x in struct.iter_unpack('<h', pcm)) < 180:
                self.decoder.end_utt(); self.decoder.start_utt(); self.base = self.samples
        return {'type': 'ack', 'samples': self.samples}


def _worker(connection, sensitivity):
    if os.name == 'nt':
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    try:
        detector = KeywordDetector(sensitivity)
        connection.send({'type': 'ready'})
        while True:
            data = connection.recv()
            if data is None: break
            if data == 'reset':
                detector.reset(); connection.send({'type': 'reset'})
            else:
                connection.send(detector.feed(data))
    except (EOFError, BrokenPipeError, OSError):
        pass
    except Exception:
        # Never log or echo audio, even on invalid input.
        try: connection.send({'type': 'error', 'message': 'Não consegui iniciar a escuta local.'})
        except (OSError, EOFError): pass
    finally:
        connection.close()


class WakeService:
    def __init__(self, settings):
        self.settings = settings
        self.process = self.connection = self.job = None
        self.owner = None
        self.lock = threading.RLock()
        self.active_until = 0

    def info(self):
        with self.lock:
            return {'enabled': self.settings.get('wake_enabled', False), 'local': True,
                    'keyword': 'Paçoca', 'pid': self.process.pid if self.process and self.process.is_alive() else None,
                    'listening': self.owner is not None, 'cpu_limit_percent': 5}

    def open(self, owner):
        with self.lock:
            if self.owner is not None: raise RuntimeError('A escuta já está aberta em outra janela.')
            if not self.settings.get('wake_enabled'): raise RuntimeError('Ative a escuta nas configurações.')
            from .processes import ProcessJob
            context = multiprocessing.get_context('spawn')
            self.connection, child = context.Pipe()
            self.process = context.Process(target=_worker,
                args=(child, self.settings.get('wake_sensitivity', 'normal')), daemon=True)
            self.owner = owner
            try:
                self.process.start(); child.close()
                self.job = ProcessJob(); self.job.cpu_limit(5); self.job.attach_pid(self.process.pid)
                return self._receive(15)
            except Exception:
                self.close(owner)
                raise

    def _receive(self, timeout=3):
        if not self.connection.poll(timeout): raise TimeoutError('A escuta local demorou demais. Reative o microfone.')
        result = self.connection.recv()
        if result['type'] == 'error': raise RuntimeError(result['message'])
        return result

    def feed(self, owner, data):
        with self.lock:
            if owner != self.owner or not self.settings.get('wake_enabled'):
                raise RuntimeError('A escuta foi pausada.')
            if data != 'reset' and (not isinstance(data, bytes) or not 0 < len(data) <= 10240 or len(data) % 2):
                raise ValueError('Bloco de áudio inválido.')
            self.connection.send(data)
            result = self._receive()
            if result['type'] == 'wake': self.active_until = time.monotonic() + 8
            return result

    def close(self, owner=None):
        with self.lock:
            if owner is not None and owner != self.owner: return
            process, connection, job = self.process, self.connection, self.job
            self.process = self.connection = self.job = self.owner = None
            if process:
                if process.is_alive(): process.terminate()
                process.join(timeout=2)
                if process.is_alive(): process.kill(); process.join(timeout=2)
                process.close()
            if connection: connection.close()
            if job: job.close()
