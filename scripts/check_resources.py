"""Measure a running app without human microphone capture or GPU inference."""
import argparse
import audioop
import io
import json
from pathlib import Path
import time
import wave

import httpx
import psutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--connection',default='.test-data/light-v2-connection.json')
    args=parser.parse_args()
    c=json.loads((ROOT/args.connection).read_text())
    root=psutil.Process(c['pid'])
    with httpx.Client(base_url=f"http://127.0.0.1:{c['port']}",headers={'X-Pacoca-Token':c['token']},timeout=120,trust_env=False) as h:
        initial=h.get('/api/status').json()
        assert not initial['engine']['loaded'] and not initial['voice']['pid']
        idle_rss=root.memory_info().rss
        h.patch('/api/settings',json={'idle_seconds':300})
        cid=h.post('/api/conversations').json()['id']
        results=[];peak_rss=idle_rss
        samples={};peak_cpu=0
        for index,prompt in enumerate(['Oi! Quem é você? Responda em uma frase.','Vamos chamar meu projeto de Aurora. Só converse comigo.','Qual nome eu dei ao projeto?','Responda em uma frase: para que você serve?']):
            start=time.monotonic()
            rid=h.post('/api/chat',json={'conversation_id':cid,'text':prompt,'voice':index==3}).json()['run_id']
            while True:
                task=h.get('/api/tasks/'+rid).json()
                processes=[root,*root.children(recursive=True)]
                total=0;used=0;now=time.monotonic()
                for process in processes:
                    try:
                        total+=process.memory_info().rss
                        times=process.cpu_times();cpu=times.user+times.system
                        if process.pid in samples:
                            old_time,old_cpu=samples[process.pid]
                            used+=(cpu-old_cpu)/(now-old_time)/psutil.cpu_count()*100
                        samples[process.pid]=(now,cpu)
                    except psutil.Error:pass
                peak_rss=max(peak_rss,total);peak_cpu=max(peak_cpu,used)
                if task['status'] not in ('running','waiting_approval'):break
                if time.monotonic()-start>170:raise TimeoutError('Turn')
                time.sleep(.4)
            assert task['status']=='completed',task
            results.append({'prompt':prompt,'answer':task['output'],'voice':index==3,'seconds':round(time.monotonic()-start,2)})
            print(json.dumps(results[-1],ensure_ascii=True),flush=True)
        status=h.get('/api/status').json()
        assert status['engine']['backend']=='cpu'
        wav=h.post('/api/voice/preview');wav.raise_for_status()
        with wave.open(io.BytesIO(wav.content)) as stream:
            pcm=stream.readframes(stream.getnframes());rate=stream.getframerate()
        pcm,_=audioop.ratecv(pcm,2,1,rate,16000,None)
        import numpy as np
        audio=np.frombuffer(pcm,dtype='<i2').astype('<f4')/32768
        transcript=h.post('/api/transcribe',content=audio.tobytes());transcript.raise_for_status()
        print('TRANSCRIPT',json.dumps(transcript.json(),ensure_ascii=True),flush=True)
        assert 'paçoca' in transcript.json()['text'].casefold()
        all_loaded=h.get('/api/status').json()
        assert all_loaded['engine']['loaded'] and all_loaded['voice']['stt_loaded'] and all_loaded['voice']['tts_loaded']
        total=sum(p.memory_info().rss for p in [root,*root.children(recursive=True)] if p.is_running())
        peak_rss=max(peak_rss,total)
        h.patch('/api/settings',json={'idle_seconds':15})
        time.sleep(23)
        released=h.get('/api/status').json()
        assert not released['engine']['loaded'] and not released['voice']['pid']
        report={'idle_backend_rss_mb':round(idle_rss/2**20),'peak_process_tree_rss_mb':round(peak_rss/2**20),
                'peak_cpu_percent_of_host':round(peak_cpu,1),'turns':results,'backend':'cpu',
                'includes_model_and_tts_overlap':True,
                'includes_stt_tts_and_llm_resident':True,
                'audio_process_released':True,'model_released':True,'human_microphone_used':False,
                'released_backend_rss_mb':round(root.memory_info().rss/2**20),'transcript':transcript.json()['text']}
        (ROOT/'.test-data/evidence/resources.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=True),flush=True)


if __name__=='__main__':main()
