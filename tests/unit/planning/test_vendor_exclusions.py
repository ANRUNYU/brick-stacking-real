import hashlib
import pytest
from brick_stacking.planning.vendor_exclusions import load_vendor_exclusions


def test_exclusions_require_hash_and_reviewed_pairs(tmp_path):
    p=tmp_path/'model.xml';p.write_text('<mujoco><contact><exclude body1="a" body2="b"/></contact></mujoco>')
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    assert ('a','b') in load_vendor_exclusions(p,expected_sha256=sha,allowed_pairs=[('a','b')])
    with pytest.raises(ValueError): load_vendor_exclusions(p,expected_sha256='wrong',allowed_pairs=[('a','b')])
    with pytest.raises(ValueError): load_vendor_exclusions(p,expected_sha256=sha,allowed_pairs=[])
