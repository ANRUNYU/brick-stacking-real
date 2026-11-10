import json,runpy,subprocess
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[3]
main=runpy.run_path(str(ROOT/'tools/m_slot_reference_capture.py'))['main']


def test_preview_never_invokes_camera(tmp_path):
    def forbidden(*args,**kwargs):raise AssertionError('camera invoked')
    out=tmp_path/'new'
    assert main(['--output',str(out)],runner=forbidden)==0
    assert not out.exists()


def test_operator_confirmation_required(tmp_path):
    with pytest.raises(SystemExit):main(['--execute','--output',str(tmp_path/'new')])


@pytest.mark.parametrize('fault',[None,'missing_camera','incomplete','timeout'])
def test_capture_packages_success_or_failure_and_never_invents_pose(tmp_path,fault):
    commands=[];out=tmp_path/'capture'
    def fake(command,**kwargs):
        commands.append(command);dest=Path(command[-1]);dest.mkdir(parents=True)
        is_capture='--capture' in command
        if is_capture and fault=='timeout':raise subprocess.TimeoutExpired(command,90,output=b'timeout evidence')
        report=dict(result='CAPTURED' if is_capture else 'INVENTORY',errors=[],cleanup_errors=[],
                    devices=[] if fault=='missing_camera' else [{'serial':'CP2L863000KL'}],frames=[])
        if is_capture:
            count=1 if fault=='incomplete' else 2
            for i in range(count):
                file=dest/f'frame_{i}.npz';file.write_bytes(b'SYNTHETIC MOCK BYTES, NOT RGB-D')
                report['frames'].append({'file':file.name})
        (dest/'camera_report.json').write_text(json.dumps(report),encoding='utf-8')
        return subprocess.CompletedProcess(command,0,'mock stdout','')
    code=main(['--execute','--marker-clear-confirmed','--frames','2','--output',str(out)],runner=fake)
    r=json.loads((out/'slot_reference_capture.json').read_text(encoding='utf-8'))
    assert code==(0 if fault is None else 2)
    assert r['camera_expectations'] is None and r['calibration_binding'] is None
    assert r['commands_sent_to_robot']==0 and not r['target_association_confirmed']
    assert Path(str(out)+'.zip').exists()
    assert len(commands)==(1 if fault=='missing_camera' else 2)
    with pytest.raises(SystemExit):main(['--output',str(out)])
