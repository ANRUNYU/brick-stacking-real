"""Download the audited O6 candidate's collision OBJ files, content-locked."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib,json
from pathlib import Path
import urllib.request
import xml.etree.ElementTree as ET

BASE='src/linker_robot_assets/assets/components/hands/linkerhand_o6/'
RAW='https://raw.githubusercontent.com/linker-bot/linker-sim-assets/main/'
MEDIA='https://media.githubusercontent.com/media/linker-bot/linker-sim-assets/main/'
MJCF_HASH='3d0ca932028277620c234b984d2dd570fc9d8d82311db988e53ab4618485b643'
HASH='e1e42ccd1ff55a28153acb025046f42d810ac97367f7bbfdaebe042d01cd75ba'

def fetch(url):
    with urllib.request.urlopen(url,timeout=25) as r:data=r.read(10_000_001)
    if len(data)>10_000_000:raise ValueError('asset budget exceeded')
    return data

def main():
    p=argparse.ArgumentParser(__doc__);p.add_argument('directory',type=Path);a=p.parse_args()
    urdf=fetch(RAW+BASE+'linkerhand_o6_left.urdf')
    if hashlib.sha256(urdf).hexdigest()!=HASH:raise ValueError('O6 candidate changed; re-audit')
    mjcf=fetch(RAW+BASE+'linkerhand_o6_left.xml')
    if hashlib.sha256(mjcf).hexdigest()!=MJCF_HASH:raise ValueError('O6 mimic/contact source changed; re-audit')
    a.directory.mkdir(parents=True,exist_ok=True)
    names=[]
    for link in ET.fromstring(urdf).findall('link'):
        for mesh in link.findall('collision/geometry/mesh'):
            name=mesh.get('filename')
            if not name.startswith('meshes/collision/') or '..' in Path(name).parts or Path(name).suffix!='.obj':raise ValueError('unexpected mesh reference')
            names.append((link.get('name'),name))
    def download(item):
        link,name=item;data=fetch(RAW+BASE+name)
        if data.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pointer=data.decode('ascii').splitlines()
            sha=next(x.split('sha256:')[1] for x in pointer if x.startswith('oid sha256:'))
            size=int(next(x.split()[1] for x in pointer if x.startswith('size ')))
            data=fetch(MEDIA+BASE+name)
            if len(data)!=size or hashlib.sha256(data).hexdigest()!=sha:raise ValueError('LFS checksum mismatch')
        path=a.directory/name;path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as f:f.write(data)
        return dict(link=link,path=name,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
    with ThreadPoolExecutor(max_workers=4) as pool:meshes=list(pool.map(download,names))
    with (a.directory/'hand.urdf').open('xb') as f:f.write(urdf)
    with (a.directory/'hand.xml').open('xb') as f:f.write(mjcf)
    lock=dict(mjcf_sha256=MJCF_HASH,source_ref='manufacturer main, content hashes authoritative',urdf_sha256=HASH,meshes=meshes,approved_for_motion=False)
    with (a.directory/'asset_lock.json').open('x',encoding='utf-8') as f:json.dump(lock,f,indent=2)
    print(json.dumps(dict(meshes=len(meshes),bytes=sum(x['bytes'] for x in meshes))))
if __name__=='__main__':main()
