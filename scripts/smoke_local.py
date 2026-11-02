"""Real local model + voice smoke, without operating the user's desktop."""
import asyncio
import json
import os
from pathlib import Path
import time
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / "src"))
os.environ["PACOCA_DATA"]=str(ROOT / ".test-data" / "smoke")

from pacoca.config import Settings
from pacoca.runtime import LocalRuntime
from pacoca.audio import Voice


async def main():
    settings=Settings()
    runtime=LocalRuntime(settings)
    start=time.monotonic()
    try:
        await runtime.start()
        print(json.dumps(runtime.info(),ensure_ascii=False),flush=True)
        if runtime.status!="ready":
            raise RuntimeError(runtime.detail)
        loaded=time.monotonic()-start
        start=time.monotonic()
        reply=await runtime.complete([{"role":"system","content":"Você é Paçoca. Responda em português brasileiro, em uma frase curta."},
                                      {"role":"user","content":"Se apresente e explique onde você funciona."}])
        print("MODEL",reply,flush=True)
        voice=Voice(runtime,settings)
        wav=await asyncio.to_thread(voice.synthesize,"Olá! Eu sou a Paçoca e funciono no seu computador.")
        (settings.directory / "voice-sample.wav").write_bytes(wav)
        import wave,numpy as np,io
        with wave.open(io.BytesIO(wav)) as w:
            rate=w.getframerate()
            samples=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)/32768
        samples=np.interp(np.arange(0,len(samples),rate/16000),np.arange(len(samples)),samples).astype(np.float32)
        transcript=await asyncio.to_thread(voice.transcribe,samples)
        print("TRANSCRIPT",transcript,flush=True)
        result={"engine":runtime.info(),"load_seconds":round(loaded,2),"voice_bytes":len(wav),"transcript":transcript,"reply":reply,"total_seconds":round(time.monotonic()-start,2)}
        (settings.directory / "result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    finally:
        await runtime.close()


if __name__=="__main__":
    asyncio.run(main())
