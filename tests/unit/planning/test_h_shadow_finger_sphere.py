"""A revolute mesh can reach its largest edge projection between joint limits."""
from pathlib import Path
import sys
import tempfile

import numpy as np
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
from h_shadow_lift_fingertip_envelope import finger_spheres


def check_two_joint_reach(test, kind):
    urdf = f"""<robot>
      <link name="tip"><collision><geometry><mesh filename="tip.obj"/></geometry></collision></link>
      <joint type="revolute"><origin xyz="0.5 0 0"/><parent link="lh_hand_base_link"/><child link="prox"/></joint>
      <joint type="{kind}"><origin xyz="0.2 0 0"/><parent link="prox"/><child link="tip"/></joint>
    </robot>"""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "hand.urdf"
        path.write_text(urdf, encoding="utf-8")
        args = (path, {"tip": np.array([[0.1, 0., 0.]])},
                {"meshes": [{"link": "tip", "path": "tip.obj"}]})
        if kind == "prismatic":
            with test.assertRaisesRegex(ValueError, "translation"):
                finger_spheres(*args)
            return
        anchor, radius = finger_spheres(*args)["tip"]
    # Proximal joint ranges from -pi/2 to +pi/2, distal joint held at zero.
    edge_x = 0.75
    corner = anchor[0] + 0.3 * np.cos(np.pi / 2) - edge_x
    interior = anchor[0] + 0.3 - edge_x
    assert corner < 0 < interior
    np.testing.assert_allclose(anchor, [0.5, 0, 0])
    test.assertAlmostEqual(anchor[0] + radius - edge_x, interior)



class FingerSphereTest(unittest.TestCase):
    def test_interior_reaches_past_corner_samples(self):
        check_two_joint_reach(self, "revolute")

    def test_rejects_prismatic_joint(self):
        check_two_joint_reach(self, "prismatic")


if __name__ == "__main__":
    unittest.main()
