"""Fetch the audited P7 left collision model and verify every Git LFS object.

Public manufacturer files stay outside source control in artifacts. No SDK install.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT='src/linker_robot_assets/assets/components/arms/p7/variants/left/'
RAW='https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/'
MEDIA='https://media.githubusercontent.com/media/linker-bot/linker-sim-assets/main/'
URDF_HASH='b898b9597d7d075cc5e7114d76a90d0ec514c387a5fd59411555455a6d722daa'


def fetch(url):
    with urllib.request.urlopen(url,timeout=30) as r:
        data=r.read(50_000_001)
    if len(data)>50_000_000: raise ValueError('asset size budget exceeded')
    return data


def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('directory',type=Path);args=p.parse_args()
    out=args.directory;out.mkdir(parents=True,exist_ok=True)
    urdf=fetch(RAW+ROOT+'arm.urdf')
    if hashlib.sha256(urdf).hexdigest()!=URDF_HASH: raise ValueError('upstream URDF changed; re-audit before use')
    def mesh(i):
        name=f'meshes/L{i}_Link.STL';pointer=fetch(RAW+ROOT+name).decode('ascii')
        lines=pointer.splitlines()
        if not lines or lines[0]!='version https://git-lfs.github.com/spec/v1': raise ValueError('expected LFS pointer')
        sha=next(x.split('sha256:',1)[1] for x in lines if x.startswith('oid sha256:'))
        size=int(next(x.split()[1] for x in lines if x.startswith('size ')))
        path=out/name
        data=path.read_bytes() if path.exists() else fetch(MEDIA+ROOT+name)
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha: raise ValueError('mesh checksum/size mismatch: '+name)
        if not path.exists():
            path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as f:f.write(data)
        return dict(path=name,sha256=sha,bytes=size,source=MEDIA+ROOT+name)
    with ThreadPoolExecutor(max_workers=4) as pool: meshes=list(pool.map(mesh,range(1,9)))
    path=out/'arm.urdf'
    if path.exists() and path.read_bytes()!=urdf: raise ValueError('existing URDF differs')
    if not path.exists(): path.write_bytes(urdf)
    manifest=dict(schema_version='c-vendor-mesh-lock-1',source_ref='main_at_download; content hashes authoritative',urdf_sha256=URDF_HASH,meshes=meshes,approved_for_motion=False)
    with (out/'asset_lock.json').open('x',encoding='utf-8') as f:json.dump(manifest,f,indent=2)
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
