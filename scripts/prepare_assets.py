"""Prepare an offline distribution. Network access happens here, never at app startup."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import urllib.request
import zipfile
import zlib
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
LOCK = ROOT / "packaging" / "assets.lock.json"
HEADERS = {"User-Agent": "Pacoca-Build/1.0"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as r:
        return json.load(r)


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def resolve():
    items = []
    release = get_json("https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/b12032")
    asset = next(a for a in release["assets"] if a["name"] == "llama-b12032-bin-win-vulkan-x64.zip")
    items.append(dict(url=asset["browser_download_url"], path="downloads/llama.zip", size=asset["size"],
                      sha256=asset["digest"].split(":")[-1], extract="engine"))
    for name in ['llama-b12032-bin-win-cuda-12.4-x64.zip','cudart-llama-bin-win-cuda-12.4-x64.zip']:
        asset=next(a for a in release['assets'] if a['name']==name)
        items.append(dict(url=asset['browser_download_url'],path='downloads/'+name,size=asset['size'],
                          sha256=asset['digest'].split(':')[-1],extract='engine-cuda'))
    specs = [
        ('unsloth/Qwen3-1.7B-GGUF',{'Qwen3-1.7B-Q4_K_M.gguf':'models/chat-light-q4.gguf'}),
        ("Qwen/Qwen3-8B-GGUF", {"Qwen3-8B-Q4_K_M.gguf": "models/chat-8b.gguf"}),
        ("Systran/faster-whisper-small", {n: "models/whisper/" + n for n in ["model.bin", "config.json", "tokenizer.json", "vocabulary.txt"]}),
        ("rhasspy/piper-voices", {"pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx": "models/voice.onnx",
                                 "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json": "models/voice.onnx.json",
                                 "pt/pt_BR/faber/medium/MODEL_CARD": "licenses/voice-MODEL_CARD"}),
    ]
    for repo, names in specs:
        info = get_json(f"https://huggingface.co/api/models/{repo}?blobs=true")
        indexed = {s["rfilename"]: s for s in info["siblings"]}
        for remote, local in names.items():
            entry = indexed[remote]
            items.append(dict(url=f"https://huggingface.co/{repo}/resolve/{info['sha']}/{remote}",
                              path=local, size=entry.get("size", 0), sha256=entry.get("lfs", {}).get("sha256", "")))
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"engine": "llama.cpp b12032 Vulkan / CPU", "model": "Qwen3 1.7B Q4_K_M (Unsloth) + 8B opcional",
                                "items": items}, indent=2), encoding="utf-8")
    return items


def download(item):
    path = ASSETS / item["path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and (not item["size"] or path.stat().st_size == item["size"]):
        if not item["sha256"] or sha256(path) == item["sha256"]:
            if not item["sha256"]:
                item["sha256"] = sha256(path)
            print("OK", item["path"], flush=True)
            return
    part = path.with_suffix(path.suffix + ".part")
    for attempt in range(5):
        try:
            start = part.stat().st_size if part.exists() else 0
            headers = {**HEADERS, **({"Range": f"bytes={start}-"} if start else {})}
            with urllib.request.urlopen(urllib.request.Request(item["url"], headers=headers), timeout=120) as r:
                mode = "ab" if start and r.status == 206 else "wb"
                with part.open(mode) as f:
                    shutil.copyfileobj(r, f, 2 * 1024 * 1024)
            if item["size"] and part.stat().st_size != item["size"]:
                raise RuntimeError("Incomplete download")
            digest = sha256(part)
            if item["sha256"] and digest != item["sha256"]:
                part.unlink()
                raise RuntimeError("Checksum mismatch")
            item["sha256"] = digest
            part.replace(path)
            print("DOWNLOADED", item["path"], path.stat().st_size, flush=True)
            return
        except Exception as exc:
            print("RETRY", item["path"], str(exc), flush=True)
            if attempt == 4:
                raise
            time.sleep(min(2 ** attempt, 15))


def get_speech_items():
    return json.loads((ROOT/'packaging/speech-model.lock.json').read_text(encoding='utf-8'))['items']


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--resolve", action="store_true")
    args = p.parse_args()
    items = resolve() if args.resolve or not LOCK.exists() else json.loads(LOCK.read_text(encoding="utf-8"))["items"]
    speech_items = get_speech_items()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(download, items + speech_items))
    for item in items:
        if item.get("extract"):
            out = (ASSETS / item["extract"]).resolve()
            out.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(ASSETS / item["path"]) as z:
                for entry in z.infolist():
                    if not (out / entry.filename).resolve().is_relative_to(out):
                        raise ValueError("Unsafe archive path")
                for entry in z.infolist():
                    target=out/entry.filename
                    if entry.is_dir():
                        target.mkdir(parents=True,exist_ok=True)
                        continue
                    if target.exists() and target.stat().st_size==entry.file_size:
                        crc=0
                        with target.open('rb') as f:
                            for block in iter(lambda:f.read(1024*1024),b''):
                                crc=zlib.crc32(block,crc)
                        if crc==entry.CRC:
                            continue
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(entry) as source,target.open('wb') as dest:
                        shutil.copyfileobj(source,dest)
    engine = next((ASSETS / "engine").rglob("llama-server.exe"))
    light=next(i for i in items if i['path']=='models/chat-light-q4.gguf')
    advanced=next(i for i in items if i['path']=='models/chat-8b.gguf')
    manifest = {"schema": 2, "name": "Qwen3 1.7B · Leve", "engine": str(engine.relative_to(ASSETS)).replace("\\", "/"),
                "engine_cuda":"engine-cuda/llama-server.exe",
                "model": light['path'], "whisper": "models/whisper", "voice": "models/voice.onnx",
                'models':{name:{'path':item['path'],'name':label,'sha256':item['sha256'],'size':item['size']}
                          for name,item,label in [('light',light,'Qwen3 1.7B · Leve'),('advanced',advanced,'Qwen3 8B · Avançado')]},
                "files": [{"path": i["path"], "sha256": i["sha256"], "size": i["size"]} for i in items if not i.get("extract")]}
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    lock["items"] = items
    LOCK.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    if not (ASSETS/'browser').exists():
        env={**os.environ,'PLAYWRIGHT_BROWSERS_PATH':str(ASSETS/'browser')}
        subprocess.run([sys.executable,'-m','playwright','install','chromium'],env=env,check=True)
    print("Offline assets ready.", flush=True)


if __name__ == "__main__":
    main()
