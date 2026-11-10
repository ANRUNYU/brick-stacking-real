"""Recorded ObservationBundle -> shadow placement review, without inventing evidence."""
from dataclasses import dataclass
from math import isfinite

from brick_stacking.planning.placement_review import Context, ErrorBound, Inspection


def _number(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class BundleBinding:
    camera_id: str
    optical_frame: str
    camera_epoch: str
    host_boot_epoch: str
    profile_hash: str
    clock_evidence_ref: str
    max_age_s: float

    def __post_init__(self):
        if not all(isinstance(v,str) and v for k,v in self.__dict__.items() if k!='max_age_s'):
            raise ValueError('complete source/clock/profile binding required')
        if not _number(self.max_age_s) or self.max_age_s <= 0:
            raise ValueError('positive age limit required')


def audit_bundle(bundle, binding, *, now_s, expected_color):
    """A diagnostic observation/color check, never a placement PASS or object tracker."""
    problems=[]
    rgbd=bundle.get('rgbd',{});timing=bundle.get('timing',{})
    def problem(reason):
        if reason not in problems:problems.append(reason)
    if bundle.get('schema_version')!='0.1':problem('SCHEMA_MISMATCH')
    if (rgbd.get('device_id'),rgbd.get('frame_id'),rgbd.get('epoch'),
            bundle.get('profile_hash')) != (binding.camera_id,binding.optical_frame,
                                          binding.camera_epoch,binding.profile_hash):
        problem('CAMERA_EPOCH_FRAME_OR_PROFILE_MISMATCH')
    if (timing.get('host_clock_domain')!='process_monotonic' or
            timing.get('host_boot_epoch')!=binding.host_boot_epoch or
            timing.get('error_bound_evidence_ref')!=binding.clock_evidence_ref or
            timing.get('device_clock_domain')!=rgbd.get('clock_domain')):
        problem('CLOCK_BINDING_MISMATCH')
    bound=timing.get('clock_error_bound_s');stamp=timing.get('exposure_host_stamp_s')
    output=timing.get('output_monotonic_s')
    timing_ok=(timing.get('validity')=='VALID' and _number(bound) and bound>0 and
               _number(stamp) and stamp>=0 and _number(output) and output>=stamp and
               _number(now_s) and now_s>=output and
               bound <= now_s-stamp <= binding.max_age_s-bound)
    if not timing_ok:problem('TIMING_UNKNOWN_STALE_OR_FUTURE')
    scene=timing.get('scene_consistency',{})
    if rgbd.get('validity')!='VALID' or scene.get('scene_consistent') is not True:
        problem('SCENE_OR_RGBD_NOT_CONFIRMED')
    blocks=bundle.get('blocks',[])
    color='UNKNOWN';selected=None
    if len(blocks)==1:
        b=blocks[0]
        if (b.get('sample_id'),b.get('device_id'),b.get('frame_id'),b.get('epoch')) != (
                rgbd.get('sample_id'),binding.camera_id,binding.optical_frame,binding.camera_epoch):
            problem('BLOCK_SOURCE_MISMATCH')
        if b.get('validity')=='VALID' and b.get('observation_id'):
            selected=b['observation_id']
            color='MATCH' if b.get('color')==expected_color else 'MISMATCH'
        else:problem('CANDIDATE_INVALID')
    else:problem('MISSING_OR_AMBIGUOUS_TARGET')
    return dict(schema_version='m-placement-bundle-audit-1',sample_id=rgbd.get('sample_id'),
                selected_observation_id=selected,observed_candidate_color_check=color,
                # A single candidate in a scene is not proof it is the target slot/object.
                target_association_confirmed=False,placement_verdict='UNKNOWN',
                problems=problems,source_checks_passed=not problems,
                clock_error_bound_s=bound,exposure_to_output_s=(output-stamp if
                    _number(output) and _number(stamp) else None),
                source_control_ready=bundle.get('control_ready'),
                motion_enabled=False,control_ready=False,permit=None)


@dataclass(frozen=True)
class LocalizedReviewEvidence:
    """Explicit M/V result, not generated from candidate dimensions or stability counts."""
    context: Context
    sample_id: str
    observation_id: str
    reference_id: str
    point_kind: str
    target_association_confirmed: bool
    xy_m: ErrorBound
    height_m: ErrorBound
    yaw_rad: ErrorBound
    support_ok: bool | None
    stable: bool | None
    hand_clear: bool
    neighbors_unchanged: bool | None


def to_shadow_inspection(bundle,binding,evidence,*,now_s,expected_color):
    """Refuse missing localization/association. Never copy scene-consistency as support."""
    audit=audit_bundle(bundle,binding,now_s=now_s,expected_color=expected_color)
    if not audit['source_checks_passed']:
        raise ValueError('bundle source checks failed: '+','.join(audit['problems']))
    if (evidence.target_association_confirmed is not True or not evidence.reference_id or
            evidence.point_kind!='visible_top_center' or
            evidence.sample_id!=audit['sample_id'] or
            evidence.observation_id!=audit['selected_observation_id']):
        raise ValueError('localized target/reference association missing or mismatched')
    if (evidence.context.epoch!=binding.camera_epoch or
            evidence.context.clock_domain!='process_monotonic' or
            evidence.context.profile_hash!=binding.profile_hash or
            not bundle.get('calibration_hash') or
            evidence.context.calibration_hash!=bundle['calibration_hash']):
        raise ValueError('localization context/calibration hash mismatch')
    return Inspection(evidence.context,evidence.observation_id,
                      bundle['timing']['exposure_host_stamp_s'],evidence.xy_m,
                      evidence.height_m,evidence.yaw_rad,
                      audit['observed_candidate_color_check']=='MATCH',
                      evidence.support_ok,evidence.stable,evidence.hand_clear,True,
                      evidence.neighbors_unchanged)
