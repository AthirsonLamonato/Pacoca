import asyncio
import json
import os
from pathlib import Path
import time
import httpx
import websockets

ROOT=Path(__file__).resolve().parents[1]


async def main():
    c=json.loads((ROOT/os.getenv('PACOCA_CONNECTION','.test-data/grounded-connection.json')).read_text())
    base='http://127.0.0.1:'+str(c['port'])
    async with httpx.AsyncClient(base_url=base,headers={'X-Pacoca-Token':c['token']},timeout=180,trust_env=False) as client:
        cid=(await client.post('/api/conversations')).json()['id']
        async def decisions(ws):
            async for line in ws:
                e=json.loads(line)
                if e.get('type')=='approval' and e.get('conversation_id')==cid:
                    allowed=e['tool']=='write_file' and Path(e['arguments'].get('path','')).name in ('bench-one.txt','bench-two.txt')
                    await client.post('/api/approvals/'+e['id'],json={'allowed':allowed})
        results=[]
        async with websockets.connect(f"ws://127.0.0.1:{c['port']}/events?token={c['token']}") as ws:
            await ws.recv();worker=asyncio.create_task(decisions(ws))
            try:
                for prompt,expected in [
                    ('Consulte a hora real e também as informações reais de memória RAM. Use as ferramentas necessárias e responda brevemente.',{'current_time','computer_info'}),
                    ('Crie dois arquivos separados no Workspace: bench-one.txt com o texto Primeiro teste e bench-two.txt com o texto Segundo teste. Não diga que criou um arquivo se a ferramenta não o salvou.',{'write_file'}),
                    ('Leia o arquivo bench-one.txt e também bench-two.txt; mostre o conteúdo de cada um.',{'files'}),
                ]:
                    run=(await client.post('/api/chat',json={'conversation_id':cid,'text':prompt})).json()['run_id']
                    start=time.monotonic()
                    while True:
                        task=(await client.get('/api/tasks/'+run)).json()
                        if task['status'] not in ('running','waiting_approval'):break
                        if time.monotonic()-start>170:raise TimeoutError(prompt)
                        await asyncio.sleep(.3)
                    calls=[e['data'] for e in task['events'] if e['kind']=='tool']
                    passed=task['status']=='completed' and expected.issubset({e['name'] for e in calls}) and all(e['result']['ok'] for e in calls)
                    if prompt.startswith(('Crie dois','Leia o arquivo')):passed=passed and len(calls)>=2
                    results.append({'prompt':prompt,'passed':passed,'calls':[e['name'] for e in calls],'seconds':round(time.monotonic()-start,2),'answer':task['output']})
                    print(json.dumps(results[-1],ensure_ascii=True),flush=True)
            finally:worker.cancel()
        (ROOT/'.test-data/evidence/multistep.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':asyncio.run(main())
