"""Install the single artifact, including its automatic model download, in QA."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    installer = ROOT / 'release/Pacoca-Setup.exe'
    target = ROOT / '.test-data/installed-app'
    log = ROOT / '.test-data/installation.log'
    manifest = json.loads((ROOT / 'assets/manifest.json').read_text(encoding='utf-8'))
    expected_model_hash = next(f['sha256'] for f in manifest['files'] if f['path'] == manifest['model'])
    model = target / 'assets' / manifest['model']
    existing_model_valid = model.is_file() and sha256(model) == expected_model_hash
    started = time.monotonic()
    result = subprocess.run([str(installer), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        '/NOICONS', '/TASKS=', '/DIR=' + str(target), '/LOG=' + str(log)], cwd=ROOT,
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=1200)
    assert result.returncode == 0, f'Installer exit {result.returncode}; see {log}'
    for name in ('Pacoca.exe', 'assets/manifest.json', 'source/Pacoca-source.zip',
                 'licenses/DISTRIBUTION.txt', 'assets/engine/llama-server.exe',
                 'assets/engine-cuda/llama-server.exe', 'assets/models/voice.onnx',
                 'assets/models/whisper/model.bin', 'unins000.exe'):
        assert (target / name).is_file(), name
    assert sha256(model) == expected_model_hash
    for name in ('icuuc.dll', 'icudt78.dll'):
        assert not (target / '_internal' / name).exists(), f'Obsolete incompatible DLL remains: {name}'
    model_download_observed = 'Downloading file from' in log.read_text(encoding='utf-8',errors='replace')
    if existing_model_valid:
        assert not model_download_observed, 'A valid model must be reused on upgrade'
    report = {'exit_code': result.returncode, 'seconds': round(time.monotonic() - started, 2),
              'target': str(target), 'installer_bytes': installer.stat().st_size,
              'installer_sha256': sha256(installer), 'installed_model_sha256_matches': True,
              'source_and_licenses_included': True, 'additional_installer_required': False,
              'initial_installation_requires_internet': True,
              'model_download_observed': model_download_observed,
              'existing_model_reused': existing_model_valid and not model_download_observed,
              'obsolete_icu_dlls_removed': True}
    (ROOT / '.test-data/evidence/installation.json').write_text(
        json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
