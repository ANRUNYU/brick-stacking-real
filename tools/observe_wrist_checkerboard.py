"""Detect a measured table board in recorded raw wrist RGB using its own K/D.

RGB-only geometric observation: no depth validation or robot transform approval.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def observe(image, metadata, *, columns, rows, square_m):
    if min(columns, rows) < 3 or not np.isfinite(square_m) or square_m <= 0:
        raise ValueError('explicit board dimensions and measured square length required')
    if metadata.get('rectified') is not False:
        raise ValueError('this entry point requires raw, unrectified RGB')
    k = np.asarray(metadata['K'], float)
    d = metadata['distortion']
    distortion = np.array([d[n] for n in ('k1', 'k2', 'p1', 'p2', 'k3', 'k4', 'k5', 'k6')], float)
    if k.shape != (3, 3) or not np.isfinite(k).all() or not np.isfinite(distortion).all():
        raise ValueError('finite camera intrinsics required')
    if image is None or image.shape[:2] != (metadata['height'], metadata['width']):
        raise ValueError('image must match the captured camera profile')
    found, corners = cv2.findChessboardCornersSB(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY),
        (columns, rows), flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE)
    result = dict(schema_version='c-wrist-checkerboard-observation-1', source=metadata['source'],
        camera_serial=metadata['camera_serial'], board_inner_corners=[columns, rows], square_m=square_m,
        camera_metadata=metadata, center_camera_m=None, corners_camera_m=None,
        approved=False, motion_enabled=False,
        depth_validation='NOT_PERFORMED', robot_pose_association='NOT_PERFORMED')
    if not found:
        result['status'] = 'BOARD_NOT_VISIBLE'
        return result
    obj = np.zeros((columns * rows, 3), np.float32)
    obj[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2) * square_m
    # IPPE takes undistorted normalized rays. Reprojection uses original K/D.
    rays = cv2.undistortPoints(corners, k, distortion)
    ok, rotations, translations, _ = cv2.solvePnPGeneric(obj, rays, np.eye(3), None, flags=cv2.SOLVEPNP_IPPE)
    candidates = []
    if ok:
        for rv, tv in zip(rotations, translations):
            xyz = obj @ cv2.Rodrigues(rv)[0].T + tv.ravel()
            if np.any(xyz[:, 2] <= 0):
                continue
            predicted = cv2.projectPoints(obj, rv, tv, k, distortion)[0].reshape(-1, 2)
            error = np.linalg.norm(predicted - corners.reshape(-1, 2), axis=1)
            candidates.append(dict(center_camera_m=xyz.mean(0).tolist(),
                corners_camera_m=xyz.tolist(),
                reprojection_rms_px=float(np.sqrt(np.mean(error ** 2))), reprojection_max_px=float(error.max())))
    candidates.sort(key=lambda c: c['reprojection_rms_px'])
    result.update(status='RGB_CANDIDATE' if candidates else 'PNP_FAILED', candidates=candidates,
        corners_xy=corners.reshape(-1, 2).tolist())
    if candidates:
        result['center_camera_m'] = candidates[0]['center_camera_m']
        result['corners_camera_m'] = candidates[0]['corners_camera_m']
        result['center_ambiguity_m'] = max(float(np.linalg.norm(np.array(c['center_camera_m']) - result['center_camera_m'])) for c in candidates)
    return result


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('image', type=Path); p.add_argument('metadata', type=Path); p.add_argument('output', type=Path)
    p.add_argument('--columns', type=int, required=True); p.add_argument('--rows', type=int, required=True)
    p.add_argument('--square-mm', type=float, required=True)
    a = p.parse_args()
    result = observe(cv2.imread(str(a.image)), json.loads(a.metadata.read_text(encoding='utf-8')),
        columns=a.columns, rows=a.rows, square_m=a.square_mm / 1000)
    with a.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(result['status'])


if __name__ == '__main__':
    main()
