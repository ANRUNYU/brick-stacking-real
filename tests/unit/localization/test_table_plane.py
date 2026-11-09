import numpy as np
import pytest
from brick_stacking.localization.table_plane import fit_table_plane
from brick_stacking.vision.heightmap import build_heightmap


def test_plane_with_outliers_and_normal_direction():
    rng = np.random.default_rng(2)
    xy = rng.uniform(-1, 1, (300, 2))
    points = np.column_stack((xy, .1 * xy[:, 0] + .2 + rng.normal(0, .0002, 300)))
    points[:30, 2] += .05
    plane = fit_table_plane(points, normal_hint=[0, 0, 1], distance_threshold_m=.001,
                            iterations=100, min_inlier_ratio=.8)
    assert plane.normal[2] > 0 and plane.rms_m < .001
    assert abs(plane.heights([[0, 0, .2]])[0]) < .001


def test_collinear_rejected():
    with pytest.raises(ValueError):
        fit_table_plane([[0, 0, 0], [1, 0, 0], [2, 0, 0]], normal_hint=[0, 0, 1],
                        distance_threshold_m=.01, iterations=10, min_inlier_ratio=.8)


def test_heightmap_preserves_unknown_and_bounds():
    grid = build_heightmap([[.1, .1, .05], [.1, .1, .1], [1, 0, 9], [np.nan, 0, 0]],
                          bounds_xy_m=[[0, 1], [0, 1]], resolution_m=.5)
    assert grid.shape == (2, 2) and grid[0, 0] == .1
    assert np.isnan(grid[1, 1]) and np.isnan(grid[0, 1])


def test_optional_ransac_confidence_stops_supported_plane_without_spending_budget():
    rng=np.random.default_rng(20)
    xy=rng.uniform(-1,1,(300,2));points=np.column_stack((xy,np.ones(300)))
    stats={}
    plane=fit_table_plane(points,normal_hint=[0,0,-1],distance_threshold_m=.001,
        iterations=1000,min_inlier_ratio=.8,confidence=.9999,statistics=stats)
    assert stats['trials']==64 and stats['budget']==1000
    assert plane.rms_m<1e-10


@pytest.mark.parametrize('confidence',[0.,1.,float('nan')])
def test_bad_ransac_confidence_rejected(confidence):
    with pytest.raises(ValueError,match='confidence'):
        fit_table_plane([[0,0,1],[1,0,1],[0,1,1]],normal_hint=[0,0,-1],
            distance_threshold_m=.001,iterations=100,min_inlier_ratio=.8,confidence=confidence)
