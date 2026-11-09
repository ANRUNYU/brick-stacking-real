import json
import sys

import pytest

from brick_stacking.arm.wrist_tracking import main, summarize_tracking


def test_tracking_metrics_keep_target_and_feedback_clock_intervals_separate():
    result = summarize_tracking([
        (0, 0, 0.125, 0),
        (1, 1, 1, 0.875),
        (2, 1, 2.125, 0.75),
    ], max_skew_s=0.125, max_gap_s=1.125)
    assert result == {
        "sample_count": 3, "feedback_duration_s": 2, "max_skew_s": 0.125,
        "p95_abs_error_rad": 0.25, "max_abs_error_rad": 0.25, "final_abs_error_rad": 0.25,
        "peak_sampled_target_speed_rad_s": 1, "peak_sampled_feedback_speed_rad_s": 1,
    }


def test_nearest_rank_p95_does_not_report_the_largest_outlier():
    result = summarize_tracking(
        ((i, 0, i, i) for i in range(20)), max_skew_s=0, max_gap_s=1,
    )
    assert result["p95_abs_error_rad"] == 18
    assert result["max_abs_error_rad"] == 19


@pytest.mark.parametrize(("rows", "reason"), [
    ([], "at least two"),
    ([(0, 0, 0, 0)], "at least two"),
    ([(0, 0, 0, 0), (1, float("nan"), 1, 0)], "non-finite"),
    ([(0, 0, 0, 0), (1, 0, float("inf"), 0)], "non-finite"),
    ([(0, 0, 0, 0), (1, 0, 0.5, 0)], "maximum skew"),
    ([(0, 0, 0, 0), (0.125, 0, 0, 0)], "non-increasing"),
    ([(1, 0, 1, 0), (0, 0, 0, 0)], "non-increasing"),
    ([(0, 0, 0, 0), (1, 0, 1.125, 0)], "maximum gap"),
    ([(0, -1e308, 0, 1e308), (1, 0, 1, 0)], "error overflow"),
    ([(0, -1e308, 0, -1e308), (1, 1e308, 1, 1e308)], "rate overflow"),
])
def test_unusable_tracking_data_produces_no_metrics(rows, reason):
    with pytest.raises(ValueError, match=reason):
        summarize_tracking(rows, max_skew_s=0.125, max_gap_s=1)


@pytest.mark.parametrize(("skew", "gap"), [(-1, 1), (0, 0), (0, float("inf"))])
def test_invalid_timing_thresholds(skew, gap):
    with pytest.raises(ValueError, match="must be finite"):
        summarize_tracking([], max_skew_s=skew, max_gap_s=gap)


def test_csv_cli(tmp_path, monkeypatch, capsys):
    trace = tmp_path / "tracking.csv"
    header = "target_stamp_s,target_rad,feedback_stamp_s,actual_rad\n"
    trace.write_text(header + "0,0,0,0\n1,1,1,0.75\n", encoding="utf-8-sig")
    monkeypatch.setattr(sys, "argv", ["wrist_tracking", str(trace), "--max-skew-s", "0", "--max-gap-s", "1"])
    main()
    assert json.loads(capsys.readouterr().out)["final_abs_error_rad"] == 0.25

    trace.write_text(header + "0,0,0,0\n1,1,1\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        main()
    output = capsys.readouterr()
    assert exit_info.value.code == 2 and "CSV row 3" in output.err and not output.out
