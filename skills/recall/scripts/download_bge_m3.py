"""Download the local bge-m3 ONNX embedding model for midnight-recall.

WHY this script exists (model strategy):
  - The 2.2GB weight file is NEVER committed to git (GitHub refuses files >100MB
    and it would bloat the repo). Instead this script reproduces the exact same
    model locally so any clone can get a working real vectorizer.
  - After running it, point `reembed.py` / recall at the directory via legend:
        MIDNIGHT_EMBEDDING=local
        MIDNIGHT_MODEL_DIR=<output-dir>
    and ingest/recall will use real semantic vectors.

It downloads BAAI/bge-m3 official ONNX export: model.onnx (graph, ~0.7MB),
model.onnx_data (weights, ~2.2GB), tokenizer.json. Uses HuggingFace, or
hf-mirror.com if you set HF_ENDPOINT. Resumable vía `curl -C -` (restart-safe).

Usage:
    python download_bge_m3.py --output-dir d:/models/bge-m3
    python download_bge_m3.py --output-dir d:/models/bge-m3 --endpoint https://hf-mirror.com
"""
import argparse
import os
import subprocess
import sys
import urllib.request

FILES = [
    ('model.onnx', 'onnx/model.onnx'),
    ('model.onnx_data', 'onnx/model.onnx_data'),
    ('tokenizer.json', 'onnx/tokenizer.json'),
]
DEFAULT_ENDPOINT = 'https://huggingface.co'
REPO = 'BAAI/bge-m3'


def _resolvable_endpoint(endpoint: str) -> str:
    # Accept either the base domain or a full repo path.
    if 'resolve/main' in endpoint:
        return endpoint
    return f'{endpoint.rstrip("/")}/{REPO}/resolve/main'


def download(url: str, dest_path: str) -> None:
    """Resumable download via curl (reuses partial file with -C -)."""
    print(f'  {os.path.basename(dest_path)}  <-  {url}', flush=True)
    cmd = ['curl', '-L', '-C', '-', '-sS', '-o', dest_path, url]
    if subprocess.run(cmd).returncode != 0:
        raise RuntimeError(f'failed to download {url}')
    if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
        raise RuntimeError(f'download produced an empty/missing file: {dest_path}')


def _complete(output_dir: str) -> bool:
    return all(
        os.path.isfile(os.path.join(output_dir, name)) and
        os.path.getsize(os.path.join(output_dir, name)) > 0
        for name, _ in FILES
    )


def download_model(output_dir: str, endpoint: str = '') -> str:
    """Download bge-m3 ONNX into `output_dir` and return the absolute path.

    `endpoint` overrides the HF base (default: HF_ENDPOINT, then HF official).
    Uses resumable curl so re-runs can continue an interrupted download.
    """
    out = os.path.abspath(os.path.expanduser(output_dir))
    os.makedirs(out, exist_ok=True)
    base = _resolvable_endpoint(endpoint or os.environ.get('HF_ENDPOINT') or DEFAULT_ENDPOINT)
    for local_name, remote_path in FILES:
        download(f'{base}/{remote_path}', os.path.join(out, local_name))
    if not _complete(out):
        raise RuntimeError(f'model download incomplete in {out}')
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--output-dir', required=True,
                   help='directory to store model.onnx/model.onnx_data/tokenizer.json')
    p.add_argument('--endpoint', default=os.environ.get('HF_ENDPOINT') or DEFAULT_ENDPOINT,
                   help=f'HuggingFace base URL (default {DEFAULT_ENDPOINT})')
    args = p.parse_args(argv)

    download_model(args.output_dir, args.endpoint)

    print('\nDone. Point recall at it with:')
    print('  $env:MIDNIGHT_EMBEDDING="local"')
    print(f'  $env:MIDNIGHT_MODEL_DIR="{os.path.abspath(args.output_dir)}"')
    print('  python skills/recall/scripts/reembed.py --all')
    return 0


if __name__ == '__main__':
    sys.exit(main())