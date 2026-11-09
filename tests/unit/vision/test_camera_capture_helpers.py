import numpy as np
import pytest
from tools.orbbec_camera_probe import decode_rgb, depth_to_metres, rectify_pair, choose_profile,exposure_window_stable


def test_rgb_bgr_and_strict_buffer_size():
    raw = np.array([[[10, 20, 30], [40, 50, 60]]], np.uint8)
    np.testing.assert_array_equal(decode_rgb(raw, "OBFormat.RGB", 2, 1), raw)
    np.testing.assert_array_equal(decode_rgb(raw, "OBFormat.BGR", 2, 1), raw[:, :, ::-1])
    with pytest.raises(ValueError): decode_rgb(raw, "RGB", 3, 1)
    with pytest.raises(ValueError): decode_rgb(raw, "UNKNOWN", 2, 1)


def test_device_depth_scale_mm_to_metres_preserves_invalid():
    result = depth_to_metres(np.array([[0, 1000, 2000]],np.uint16), .5)
    assert np.isnan(result[0,0])
    np.testing.assert_allclose(result[0,1:], [.5, 1.])
    with pytest.raises(ValueError): depth_to_metres([[1]], 0)


def distortion(model):
    return {"model": model, **{name: 0. for name in ["k1","k2","k3","k4","k5","k6","p1","p2"]}}


def test_zero_distortion_keeps_values_and_depth_unknown():
    rgb = np.full((4,4,3), 100, np.uint8)
    depth = np.ones((4,4),np.float32)
    depth[0,0] = np.nan
    k = np.array([[100,0,2],[0,100,2],[0,0,1]],float)
    out_rgb, out_depth = rectify_pair(rgb,depth,k,distortion("NONE"))
    np.testing.assert_array_equal(out_rgb,rgb)
    np.testing.assert_allclose(out_depth,depth,equal_nan=True)
    _, brown_depth = rectify_pair(rgb,depth,k,distortion("BROWN_CONRADY"))
    np.testing.assert_allclose(brown_depth,depth,equal_nan=True)


@pytest.mark.parametrize("model", ["MODIFIED_BROWN_CONRADY", "INVERSE_BROWN_CONRADY", "KANNALA_BRANDT4", "UNKNOWN"])
def test_unverified_distortion_models_rejected(model):
    with pytest.raises(ValueError):
        rectify_pair(np.zeros((4,4,3),np.uint8),np.ones((4,4)),np.eye(3),distortion(model))


class Profile:
    def __init__(self,w,h,fps,format):self.w,self.h,self.fps,self.format=w,h,fps,format
    def get_width(self):return self.w
    def get_height(self):return self.h
    def get_fps(self):return self.fps
    def get_format(self):return self.format
    def as_video_stream_profile(self):return self


class Profiles:
    def __init__(self,*profiles):self.profiles=profiles
    def get_count(self):return len(self.profiles)
    def get_stream_profile_by_index(self,i):return self.profiles[i]


def test_native_resolution_request_is_exact_and_prefers_uncompressed_rgb():
    low=Profile(640,480,15,'RGB');high=Profile(1280,800,15,'RGB')
    profiles=Profiles(low,Profile(1280,800,15,'MJPG'),high)
    assert choose_profile(profiles,['RGB','MJPG']) is low
    assert choose_profile(profiles,['RGB','MJPG'],size=(1280,800),fps=15) is high


def test_missing_requested_stream_does_not_silently_fall_back():
    with pytest.raises(ValueError,match='no fallback'):
        choose_profile(Profiles(Profile(640,480,15,'RGB')),['RGB'],size=(1280,800),fps=15)


def test_capture_waits_for_photometric_stability_not_just_elapsed_frames():
    assert not exposure_window_stable([[100,100,100]]*4)
    assert exposure_window_stable([[100,100,100]]*5)
    assert not exposure_window_stable([[v,v,v] for v in [80,90,100,110,120]])


def test_equal_brightness_white_balance_drift_is_not_stable():
    assert not exposure_window_stable([[100+v,100,100-v] for v in [0,5,10,15,20]])
