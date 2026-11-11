"""J6/J7 audited readonly hard-block skeleton (no CAN / no Rest / no motion)."""
from __future__ import annotations

import pytest

from brick_stacking.arm import v2_wrist_readonly as wrist
from brick_stacking.arm.arm_state_validity import classify_arm_state
from brick_stacking.arm.v2_wrist_readonly import (
    AUDITED_READONLY_POSITION_QUERY_BYTES,
    ENABLE_PENDING_PROTOCOL_AUDIT,
    EXTERNAL_PROTOCOL_SEARCH,
    HARD_BLOCK_ID,
    J6J7ReadonlyPositionHardBlock,
    PENDING_PROTOCOL_AUDIT,
    POSITION_READONLY_CANDIDATES,
    candidate_search_report,
    decode_audited_wrist_position_reply,
    hard_block_report,
    try_read_wrist_positions_readonly,
)


def test_hard_block_report_refuses_live_valid_via_readonly():
    report = hard_block_report()
    assert report["id"] == HARD_BLOCK_ID
    assert report["status"] == "HARD_BLOCK"
    assert report["audited_readonly_position_query_available"] is False
    assert report["counts_as_live_valid_reachable_via_readonly"] is False
    assert report["allows_rest"] is False
    assert report["allows_enable_motion"] is False
    assert report["allows_large_joint_motion"] is False
    assert AUDITED_READONLY_POSITION_QUERY_BYTES is None
    assert report["position_readonly_candidate_found"] is False
    assert report["enable_pending_protocol_audit"] is False
    assert report["schema_version"] == "j6j7-readonly-position-hard-block-0.2"


def test_candidate_search_finds_no_pending_payload():
    search = candidate_search_report()
    assert search["position_readonly_candidate_found"] is False
    assert search["pending_protocol_audit_eligible_ids"] == []
    assert search["goal_software_only_completable"] is False
    assert ENABLE_PENDING_PROTOCOL_AUDIT is False
    assert PENDING_PROTOCOL_AUDIT["position_query_bytes"] is None
    assert len(POSITION_READONLY_CANDIDATES) >= 6
    assert all(not c["pending_protocol_audit_eligible"] for c in POSITION_READONLY_CANDIDATES)
    assert any(c["id"] == "rest_ff7_fd_read_initial_state" for c in POSITION_READONLY_CANDIDATES)
    assert any(
        c["id"] == "flash_generic_read_unknown_theta_indices"
        for c in POSITION_READONLY_CANDIDATES
    )


def test_external_protocol_search_negative_no_payload():
    assert EXTERNAL_PROTOCOL_SEARCH["motorevo_protocol_manual_found"] is False
    assert EXTERNAL_PROTOCOL_SEARCH["flash_theta_index_map_found"] is False
    assert EXTERNAL_PROTOCOL_SEARCH["pure_position_query_bytes_found"] is False
    assert EXTERNAL_PROTOCOL_SEARCH["pending_protocol_audit_payload_landed"] is False
    assert EXTERNAL_PROTOCOL_SEARCH["goal_complete"] is False
    report = hard_block_report()
    assert report["goal_complete"] is False
    assert report["external_protocol_search"]["pure_position_query_bytes_found"] is False
    search = candidate_search_report()
    assert search["external_protocol_search"]["motorevo_protocol_manual_found"] is False


def test_try_read_refuses_even_when_bus_handle_passed():
    sentinel = object()
    result = try_read_wrist_positions_readonly(bus=sentinel)
    assert result["attempted"] is False
    assert result["bus_touched"] is False
    assert result["q_rad"] == (None, None)
    assert result["counts_as_live_valid"] is False
    assert HARD_BLOCK_ID in (result.get("error") or "")


def test_pending_flag_true_still_refuses_without_payload():
    sentinel = object()
    result = try_read_wrist_positions_readonly(
        bus=sentinel, enable_pending_protocol_audit=True
    )
    assert result["enable_pending_protocol_audit_effective"] is True
    assert result["attempted"] is False
    assert result["bus_touched"] is False
    assert result["q_rad"] == (None, None)
    assert result["live_draft"] is None
    assert result["counts_as_live_valid"] is False
    assert "position_query_bytes is empty" in (result.get("error") or "")


def test_decode_skeleton_raises_hard_block():
    with pytest.raises(J6J7ReadonlyPositionHardBlock, match="AUDITED_READONLY"):
        decode_audited_wrist_position_reply(motor_id=66, reply=b"\x00" * 8)


def test_decode_rejects_non_wrist_ids():
    with pytest.raises(ValueError, match="not a V2 wrist"):
        decode_audited_wrist_position_reply(motor_id=61, reply=b"\x00" * 8)


def test_classify_embeds_hard_block():
    classified = classify_arm_state(None)
    block = classified["j6j7_readonly_hard_block"]
    assert block["id"] == HARD_BLOCK_ID
    assert block["status"] == "HARD_BLOCK"
    assert block["position_readonly_candidate_found"] is False
    assert classified["counts_as_live_valid"] is False


def test_known_non_readonly_paths_documented():
    text = " ".join(wrist.KNOWN_NON_READONLY_OR_UNAUDITED)
    assert "Rest" in text
    assert "read_initial_state" in text
    assert "quantization" in text.lower() or "COM Theta" in text or "U16" in text
