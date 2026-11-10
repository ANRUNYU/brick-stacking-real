"""Join H0/C35/V and C49 reports, without planning unverified physical motion."""
import argparse,hashlib,json
from pathlib import Path
from brick_stacking.planning.first_grasp_bundle import diagnostic_bundle


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--localized',type=Path,required=True);p.add_argument('--c35',type=Path,required=True)
    p.add_argument('--c49',type=Path,required=True);p.add_argument('--h0',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    paths={k:getattr(a,k) for k in ('localized','c35','c49','h0')}
    data={k:json.loads(v.read_text(encoding='utf-8')) for k,v in paths.items()}
    refs={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()}
    refs['localized_report']=a.localized.as_posix()
    result=diagnostic_bundle(data['localized'],data['c35'],data['c49'],refs=refs,h0=data['h0'])
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    print(json.dumps(dict(status=result['status'],reasons=result['reasons'],motion_enabled=False)))


if __name__=='__main__':main()
