"""Read explicitly declared, hash-locked vendor installation exclusions."""
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET


def load_vendor_exclusions(path,*,expected_sha256,allowed_pairs):
    data=Path(path).read_bytes()
    if not expected_sha256 or hashlib.sha256(data).hexdigest()!=expected_sha256:
        raise ValueError('vendor exclusion source hash mismatch')
    result={};allowed={tuple(sorted(p)) for p in allowed_pairs}
    for e in ET.fromstring(data).findall('.//contact/exclude'):
        a,b=e.get('body1'),e.get('body2')
        if not a or not b or a==b: raise ValueError('invalid vendor pair')
        pair=tuple(sorted((a,b)))
        if pair not in allowed or pair in result: raise ValueError('unreviewed or duplicate vendor pair')
        result[pair]='vendor MJCF installation exclusion; sha256='+expected_sha256
    return result
