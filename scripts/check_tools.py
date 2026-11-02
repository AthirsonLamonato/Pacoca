"""End-to-end tool scenarios, limited to read-only OS queries and disposable app data."""
import asyncio
from datetime import datetime,timedelta
import json
import os
from pathlib import Path
import time

import httpx
import websockets

ROOT=Path(__file__).resolve().parents[1]


async def main():
    c=json.loads((ROOT/os.getenv('PACOCA_CONNECTION','.test-data/cuda-connection.json')).read_text())
    base='http://127.0.0.1:'+str(c['port'])
    async with httpx.AsyncClient(base_url=base,headers={'X-Pacoca-Token':c['token']},timeout=180,trust_env=False) as client:
        cid=(await client.post('/api/conversations')).json()['id']
        async def approvals(ws):
            async for payload in ws:
                e=json.loads(payload)
                if e.get('type')!='approval' or e.get('conversation_id')!=cid:continue
                args=e['arguments'];name=e['tool']
                allowed=(name=='write_file' and Path(args.get('path','')).name=='pacoca-bench.txt') or (
                    name=='remember' and 'teste' in args.get('content','').lower()) or (
                    name=='browser' and args.get('action')=='open' and args.get('url','').rstrip('/')=='https://example.com')
                await client.post('/api/approvals/'+e['id'],json={'allowed':allowed})
        due=(datetime.now().astimezone()+timedelta(days=1)).replace(second=0,microsecond=0).isoformat()
        scenarios=[
            ('hora','Consulte a data e hora reais deste computador. Responda brevemente.','current_time'),
            ('sistema','Consulte a memória RAM e o sistema operacional reais.','computer_info'),
            ('aplicativos','Liste os aplicativos instalados que tenham Notas no nome. Não abra nenhum.','list_applications'),
            ('janelas','Consulte as janelas abertas e diga somente quantas encontrou. Não interaja com elas.','list_windows'),
            ('volume','Consulte o volume atual sem alterá-lo.','volume'),
            ('escrita','Crie pacoca-bench.txt no seu Workspace com exatamente este texto: O orçamento do projeto Aurora é 321 reais.','write_file'),
            ('leitura','Leia o arquivo pacoca-bench.txt e me diga o orçamento encontrado nele.','files'),
            ('memoria','Guarde explicitamente esta memória: Esta é uma preferência de teste: gosto de respostas breves.','remember'),
            ('consulta_memoria','Consulte as memórias salvas e me diga qual preferência de teste você encontrou.','list_memories'),
            ('lembrete',f'Crie um lembrete chamado Teste da Paçoca para {due}.','create_reminder'),
            ('consulta_lembrete','Consulte os lembretes locais pendentes.','list_reminders'),
            ('navegador','Abra https://example.com no seu navegador e consulte o título.','browser'),
        ]
        results=[]
        async with websockets.connect(f"ws://127.0.0.1:{c['port']}/events?token={c['token']}") as ws:
            await ws.recv();approver=asyncio.create_task(approvals(ws))
            try:
                for label,prompt,expected in scenarios:
                    start=time.monotonic()
                    r=await client.post('/api/chat',json={'conversation_id':cid,'text':prompt,'voice':False})
                    r.raise_for_status();id=r.json()['run_id']
                    while True:
                        task=(await client.get('/api/tasks/'+id)).json()
                        if task['status'] not in ('running','waiting_approval'):break
                        if time.monotonic()-start>170:
                            await client.post('/api/stop');raise TimeoutError(label)
                        await asyncio.sleep(.3)
                    events=[e['data'] for e in task['events'] if e['kind']=='tool']
                    matched=[e for e in events if e['name']==expected]
                    passed=task['status']=='completed' and any(e['result']['ok'] for e in matched)
                    result={'scenario':label,'passed':passed,'tools':[e['name'] for e in events],
                            'seconds':round(time.monotonic()-start,2),'answer':task['output']}
                    results.append(result)
                    print(json.dumps(result,ensure_ascii=True),flush=True)
            finally:
                approver.cancel()
        out=ROOT/'.test-data/evidence/tools-test.json';out.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
        print('SCENARIOS',sum(r['passed'] for r in results),'/',len(results),flush=True)


if __name__=='__main__':asyncio.run(main())
