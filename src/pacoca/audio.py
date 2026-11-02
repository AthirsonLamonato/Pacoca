from __future__ import annotations

import io
import json
import multiprocessing
import os
from pathlib import Path
import re
import threading
import time
import wave


class _LocalVoice:
    def __init__(self, runtime, settings):
        self.runtime, self.settings = runtime, settings
        self.whisper = self.piper = None
        self.stt_lock, self.tts_lock = threading.Lock(), threading.Lock()

    def transcribe(self, audio):
        import numpy as np
        audio = np.frombuffer(audio,dtype='<f4') if isinstance(audio,bytes) else np.asarray(audio,dtype=np.float32)
        if audio.ndim != 1 or len(audio) < 1600 or len(audio) > 16000*45 or not np.isfinite(audio).all():
            raise ValueError("Áudio inválido. Grave uma fala de até 45 segundos.")
        with self.stt_lock:
            if self.whisper is None:
                from faster_whisper import WhisperModel
                self.whisper = WhisperModel(str(self.runtime.resource("whisper")),device="cpu",compute_type="int8",
                                            cpu_threads=1,num_workers=1,local_files_only=True)
            segments, _ = self.whisper.transcribe(audio,language="pt",beam_size=1,vad_filter=True,
                condition_on_previous_text=False,no_speech_threshold=.65,
                initial_prompt="Uma conversa em português brasileiro com a assistente Paçoca.")
            text = " ".join(s.text.strip() for s in segments).strip()
            if text.casefold().strip(".! ") in ("obrigado por assistir","legendas pela comunidade amara.org"):
                return ""
            return text

    def synthesize(self, text):
        cleaned = re.sub(r"```[\s\S]*?```", "O código está na conversa.", text)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)",r"\1",cleaned)
        cleaned = re.sub(r"[*_#`]|https?://\S+", "", cleaned).strip()
        if not cleaned:
            return b""
        with self.tts_lock:
            from piper import PiperVoice, SynthesisConfig
            if self.piper is None:
                import onnxruntime as ort
                from piper.config import PiperConfig
                options=ort.SessionOptions()
                options.intra_op_num_threads=1;options.inter_op_num_threads=1
                options.add_session_config_entry('session.intra_op.allow_spinning','0')
                options.add_session_config_entry('session.inter_op.allow_spinning','0')
                path=self.runtime.resource('voice')
                config=json.loads(Path(str(path)+'.json').read_text(encoding='utf-8'))
                self.piper=PiperVoice(config=PiperConfig.from_dict(config),session=ort.InferenceSession(
                    str(path),sess_options=options,providers=['CPUExecutionProvider']))
            output = io.BytesIO()
            speed = float(self.settings.get("voice_speed",1.0))
            with wave.open(output,"wb") as wav:
                self.piper.synthesize_wav(cleaned,wav,syn_config=SynthesisConfig(length_scale=1/max(.7,min(1.4,speed))))
            return output.getvalue()

    def info(self):
        return {"engine":"Piper · Português BR", "transcription":"Whisper small · Português",
                "local":True,"stt_loaded":self.whisper is not None,"tts_loaded":self.piper is not None}

    def warmup(self):
        """Load the local models before the first conversation; no capture or playback."""
        import numpy as np
        self.synthesize("Olá.")
        self.transcribe(np.zeros(16000,dtype=np.float32))


class _Values:
    def __init__(self,values):self.values=values
    def get(self,key,default=None):return self.values.get(key,default)


class _Assets:
    def __init__(self,root,manifest):self.root,self.manifest=Path(root),manifest
    def resource(self,key):
        path=(self.root/self.manifest[key]).resolve()
        if not path.is_relative_to(self.root.resolve()) or not path.is_file() and not path.is_dir():
            raise FileNotFoundError('Recurso de áudio ausente: '+key)
        return path


def _voice_worker(connection,assets,manifest):
    os.environ['OMP_NUM_THREADS']='1'
    os.environ['OPENBLAS_NUM_THREADS']='1'
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TOKENIZERS_PARALLELISM']='false'
    if os.name=='nt':
        import psutil
        psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    values=_Values({})
    local=_LocalVoice(_Assets(assets,manifest),values)
    try:
        while True:
            method,payload,speed=connection.recv()
            if method=='close':return
            try:
                values.values['voice_speed']=speed
                if method=='synthesize':result=local.synthesize(str(payload)[:5000])
                elif method=='transcribe':result=local.transcribe(payload)
                else:raise ValueError('Operação de áudio inválida')
                connection.send({'ok':True,'data':result,'state':local.info()})
            except Exception as exc:
                connection.send({'ok':False,'error':str(exc)[:500]})
    except (EOFError,BrokenPipeError,OSError):
        pass
    finally:
        connection.close()


class Voice:
    """Lazy audio process: one CPU thread, no ORT spinning, disposable on idle."""
    def __init__(self,runtime,settings):
        self.runtime,self.settings=runtime,settings
        self.process=self.connection=self.job=None
        self.gate=threading.Lock()
        self.lifecycle=threading.RLock()
        self.last_used=0
        self.busy=False
        self.state={'engine':'Piper · Português BR','transcription':'Whisper small · Português',
                    'local':True,'stt_loaded':False,'tts_loaded':False}

    def _ensure_worker(self):
        with self.lifecycle:
            if self.process and self.process.is_alive():return
            if self.process:self.close()
            import psutil
            if psutil.virtual_memory().available<1200*1024**2:
                raise RuntimeError('Pouca memória livre para a voz. Feche um programa antes de tentar novamente.')
            from .processes import ProcessJob
            context=multiprocessing.get_context('spawn')
            self.connection,child=context.Pipe()
            self.process=context.Process(target=_voice_worker,args=(child,str(self.runtime.assets),self.runtime.manifest),daemon=True)
            self.process.start();child.close()
            self.job=ProcessJob();self.job.cpu_limit(10);self.job.attach_pid(self.process.pid)

    def _call(self,method,payload):
        with self.gate:
            self.busy=True
            try:
                self._ensure_worker()
                connection=self.connection
                connection.send((method,payload,float(self.settings.get('voice_speed',1))))
                if not connection.poll(90):
                    self.close()
                    raise TimeoutError('O áudio demorou demais e foi interrompido para liberar o computador.')
                result=connection.recv()
                if not result['ok']:raise RuntimeError(result['error'])
                self.state=result['state']
                return result['data']
            except (EOFError,OSError) as exc:
                self.close()
                raise RuntimeError('O processo de áudio foi encerrado. Você pode tentar novamente.') from exc
            finally:
                self.last_used=time.monotonic();self.busy=False

    def transcribe(self,audio):return self._call('transcribe',audio)
    def synthesize(self,text):return self._call('synthesize',text)
    def info(self):
        with self.lifecycle:
            return {**self.state,'pid':self.process.pid if self.process and self.process.is_alive() else None,
                    'busy':self.busy,'cpu_threads':1}

    def release_idle(self):
        if self.process and not self.busy and time.monotonic()-self.last_used>=self.settings.get('idle_seconds',60):
            self.close()

    def close(self):
        with self.lifecycle:
            process,connection,job=self.process,self.connection,self.job
            self.process=self.connection=self.job=None
            if process:
                if process.is_alive():
                    process.terminate()
                process.join(timeout=3)
                if process.is_alive():process.kill();process.join(timeout=2)
                process.close()
            if connection:
                connection.close()
            if job:job.close()
            self.state.update(stt_loaded=False,tts_loaded=False)
