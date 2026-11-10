"""Exercise Git's actual Windows checkout conversion, not just JSON parsing."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT=Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('autocrlf',['true','false'])
def test_calibration_bytes_survive_cross_platform_git_checkout(tmp_path,autocrlf):
    if shutil.which('git') is None:
        pytest.skip('requires Git to exercise checkout conversion')
    request=json.loads((ROOT/'config/planning/first_placement_review_request.template.json').read_text(encoding='utf-8'))
    candidate=request['calibration_candidate'];relative=Path(candidate['path'])
    source=tmp_path/'src';source.mkdir()
    (source/'.gitattributes').write_bytes((ROOT/'.gitattributes').read_bytes())
    file=source/relative;file.parent.mkdir(parents=True)
    file.write_bytes((ROOT/relative).read_bytes())
    def git(*args,cwd=source):
        result=subprocess.run(['git','-c','core.longpaths=true',*args],cwd=cwd,
                              capture_output=True,text=True,encoding='utf-8')
        assert result.returncode==0,result.stderr
        return result
    git('init')
    git('-c','core.autocrlf='+autocrlf,'add','.gitattributes',relative.as_posix())
    checkout=tmp_path/'out';checkout.mkdir()
    git('-c','core.autocrlf='+autocrlf,'checkout-index','--all',
        '--prefix='+checkout.as_posix()+'/')
    data=(checkout/relative).read_bytes()
    assert hashlib.sha256(data).hexdigest()==candidate['file_sha256']
    # Same setting must not merely disable conversion for the whole repository.
    assert git('check-attr','text','--',relative.as_posix()).stdout.strip().endswith(': unset')
