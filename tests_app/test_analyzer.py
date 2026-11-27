"""Unit tests for BPIC17 analyzer covering all Section 8 synthetic edge cases."""

from __future__ import annotations

import os
import tempfile
import unittest

import pandas as pd
import pm4py

from bpic17_app.analyzer import (
    analyze_11_7,
    analyze_11_15_and_11_18,
    analyze_11_22,
    analyze_fast_slow,
    compute_case_stats,
    compute_overview,
    export_dataframe_csv,
    export_summary_csv,
    filter_by_activity_rule,
    filter_rework_and_resource,
    filter_sequence_relation,
    get_case_trace,
    prepare_dataframe,
    run_full_analysis,
)


def _make_df(rows):
    df = pd.DataFrame(rows)
    return prepare_dataframe(df)


class TestBPIC17AnalyzerEdgeCases(unittest.TestCase):
    """Test suite verifying all mandatory edge-case rules from Section 8 of the spec."""

    def test_11_7_c_duplicate_accepted_counted_once(self):
        """Edge Case 1: One case has O_Accepted twice -> 11.7 C counts the case once."""
        df = _make_df(
            [
                {
                    "case:concept:name": "C1",
                    "concept:name": "A_Create Application",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C1",
                    "concept:name": "O_Accepted",
                    "time:timestamp": "2016-01-05T00:00:00Z",
                },
                {
                    "case:concept:name": "C1",
                    "concept:name": "O_Accepted",
                    "time:timestamp": "2016-01-11T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        res = analyze_11_7(df, cs)
        self.assertEqual(res["total_cases"], 1)
        self.assertEqual(res["accepted_count"], 1)
        # Full trace duration: Jan 1 to Jan 11 = 10.0 days (not Jan 5 to Jan 11)
        self.assertAlmostEqual(res["accepted_mean_days"], 10.0, places=4)

    def test_11_7_e_o_cancelled_in_middle_not_canceled(self):
        """Edge Case 2: O_Cancelled in the middle followed by another event -> NOT counted in 11.7 E."""
        df = _make_df(
            [
                {
                    "case:concept:name": "C_MID",
                    "concept:name": "A_Create Application",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_MID",
                    "concept:name": "O_Cancelled",
                    "time:timestamp": "2016-01-03T00:00:00Z",
                },
                {
                    "case:concept:name": "C_MID",
                    "concept:name": "W_Call after offers",
                    "time:timestamp": "2016-01-05T00:00:00Z",
                },
                {
                    "case:concept:name": "C_END",
                    "concept:name": "A_Create Application",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_END",
                    "concept:name": "O_Cancelled",
                    "time:timestamp": "2016-01-09T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        res = analyze_11_7(df, cs)
        self.assertEqual(res["canceled_count"], 1)
        self.assertEqual(res["cases_11_7_e"]["case_id"].tolist(), ["C_END"])
        self.assertAlmostEqual(res["canceled_mean_days"], 8.0, places=4)

    def test_11_7_c_and_d_not_mutually_exclusive(self):
        """Edge Case 3: Case has both O_Refused and O_Accepted -> passes both 11.7 C and 11.7 D."""
        df = _make_df(
            [
                {
                    "case:concept:name": "C_BOTH",
                    "concept:name": "O_Refused",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_BOTH",
                    "concept:name": "O_Accepted",
                    "time:timestamp": "2016-01-07T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        res = analyze_11_7(df, cs)
        self.assertEqual(res["accepted_count"], 1)
        self.assertEqual(res["refused_count"], 1)
        self.assertEqual(res["overlap_accepted_and_refused"], 1)

    def test_11_15_scheduled_twice_completed_once_rejected(self):
        """Edge Case 4: W_Assess Potential Fraud scheduled twice but completed once -> NOT in 11.15."""
        df = _make_df(
            [
                {
                    "case:concept:name": "C_SCHED",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "schedule",
                    "org:resource": "User_1",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_SCHED",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "schedule",
                    "org:resource": "User_1",
                    "time:timestamp": "2016-01-02T00:00:00Z",
                },
                {
                    "case:concept:name": "C_SCHED",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "User_1",
                    "time:timestamp": "2016-01-03T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        ex15, ex18 = analyze_11_15_and_11_18(df, cs)
        self.assertEqual(ex15["case_count"], 0)
        self.assertEqual(ex18["case_count"], 0)

    def test_11_15_and_11_18_different_vs_same_and_empty_resources(self):
        """Edge Cases 5 & 6: Two completes with different resources vs same resource vs empty resource."""
        df = _make_df(
            [
                # Case DIFF: 2 completes by different resources -> in 11.15, NOT in 11.18
                {
                    "case:concept:name": "C_DIFF",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "User_A",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_DIFF",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "User_B",
                    "time:timestamp": "2016-01-02T00:00:00Z",
                },
                # Case SAME: 2 completes by same resource -> in both 11.15 and 11.18
                {
                    "case:concept:name": "C_SAME",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "User_X",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_SAME",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "User_X",
                    "time:timestamp": "2016-01-03T00:00:00Z",
                },
                # Case EMPTY: 2 completes with empty/UNKNOWN resource -> in 11.15, NOT in 11.18
                {
                    "case:concept:name": "C_EMPTY",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_EMPTY",
                    "concept:name": "W_Assess Potential Fraud",
                    "lifecycle:transition": "complete",
                    "org:resource": "UNKNOWN",
                    "time:timestamp": "2016-01-02T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        ex15, ex18 = analyze_11_15_and_11_18(df, cs)
        self.assertEqual(ex15["case_count"], 3)
        self.assertEqual(
            set(ex15["cases_table"]["case_id"].tolist()),
            {"C_DIFF", "C_SAME", "C_EMPTY"},
        )
        self.assertEqual(ex18["case_count"], 1)
        self.assertEqual(ex18["cases_table"]["case_id"].tolist(), ["C_SAME"])
        self.assertEqual(ex18["cases_table"]["resource"].tolist(), ["User_X"])

    def test_11_22_eventual_ordering_non_adjacent_vs_reverse(self):
        """Edge Cases 7 & 8: O_Cancelled -> other -> O_Accepted matches; O_Accepted -> O_Cancelled does not."""
        df = _make_df(
            [
                # Matches 11.22 (non-adjacent)
                {
                    "case:concept:name": "C_MATCH",
                    "concept:name": "O_Cancelled",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_MATCH",
                    "concept:name": "W_Call after offers",
                    "time:timestamp": "2016-01-02T00:00:00Z",
                },
                {
                    "case:concept:name": "C_MATCH",
                    "concept:name": "O_Accepted",
                    "time:timestamp": "2016-01-03T00:00:00Z",
                },
                # Does NOT match 11.22 (O_Accepted before O_Cancelled, no O_Accepted after)
                {
                    "case:concept:name": "C_REV",
                    "concept:name": "O_Accepted",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "C_REV",
                    "concept:name": "O_Cancelled",
                    "time:timestamp": "2016-01-04T00:00:00Z",
                },
            ]
        )
        cs = compute_case_stats(df)
        res = analyze_11_22(df, cs)
        self.assertEqual(res["case_count"], 1)
        self.assertEqual(res["denominator_total_cases"], 2)
        self.assertAlmostEqual(res["percentage"], 50.0, places=4)
        self.assertEqual(res["witness_table"]["case_id"].tolist(), ["C_MATCH"])
        self.assertEqual(int(res["witness_table"].iloc[0]["events_between"]), 1)

    def test_fast_slow_and_exports_and_trace(self):
        """Verify Example 11.10 Fast (<45d) vs Slow (>=45d), Case Explorer trace, and CSV exports."""
        df = _make_df(
            [
                {
                    "case:concept:name": "FAST_1",
                    "concept:name": "A_Create Application",
                    "lifecycle:transition": "complete",
                    "org:resource": "U1",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "FAST_1",
                    "concept:name": "O_Accepted",
                    "lifecycle:transition": "complete",
                    "org:resource": "U1",
                    "time:timestamp": "2016-01-11T00:00:00Z",
                },
                {
                    "case:concept:name": "SLOW_1",
                    "concept:name": "A_Create Application",
                    "lifecycle:transition": "complete",
                    "org:resource": "U2",
                    "time:timestamp": "2016-01-01T00:00:00Z",
                },
                {
                    "case:concept:name": "SLOW_1",
                    "concept:name": "O_Cancelled",
                    "lifecycle:transition": "complete",
                    "org:resource": "U2",
                    "time:timestamp": "2016-03-01T00:00:00Z",
                },
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            xes_path = os.path.join(tmpdir, "synthetic.xes")
            pm4py.write_xes(df, xes_path)
            bundle = run_full_analysis(xes_path)

            self.assertEqual(bundle.fast_slow["fast_count"], 1)
            self.assertEqual(bundle.fast_slow["slow_count"], 1)
            self.assertEqual(bundle.fast_slow["slow_end_o_cancelled"], 1)

            trace_df = get_case_trace(bundle.df, "FAST_1")
            self.assertEqual(len(trace_df), 2)

            summary_csv = os.path.join(tmpdir, "summary.csv")
            cases_csv = os.path.join(tmpdir, "cases.csv")
            export_summary_csv(bundle, summary_csv)
            export_dataframe_csv(bundle.case_stats, cases_csv)
            self.assertTrue(os.path.isfile(summary_csv))
            self.assertTrue(os.path.isfile(cases_csv))

            # Verify PySide6 MainWindow populates all tabs cleanly in offscreen mode
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication
            from bpic17_app.gui import MainWindow

            app = QApplication.instance() or QApplication([])
            win = MainWindow()
            win.populate_from_bundle(bundle)
            self.assertEqual(win.tabs.count(), 7)
            win.apply_outcome_filter()
            win.pin_current_outcome_filter()
            win.apply_rework_filter()
            win.swap_sequence_activities()
            win.open_case_in_explorer("FAST_1")
            self.assertEqual(win.tabs.currentIndex(), 5)
            app.processEvents()

            # Verify parameterized filter functions directly
            r_starts = filter_by_activity_rule(
                bundle.df, bundle.case_stats, "A_Create Application", mode="starts_with"
            )
            self.assertEqual(r_starts["case_count"], 2)
            r_direct = filter_sequence_relation(
                bundle.df,
                bundle.case_stats,
                "A_Create Application",
                "O_Accepted",
                relation="directly_follows",
            )
            self.assertEqual(r_direct["case_count"], 1)

    def test_synthetic_xes_file_all_edge_cases(self):
        """Verify the permanent tests_app/synthetic_edge_cases.xes demo file covers all 8 edge cases."""
        xes_path = os.path.join(os.path.dirname(__file__), "synthetic_edge_cases.xes")
        self.assertTrue(os.path.isfile(xes_path), f"Missing synthetic demo log: {xes_path}")
        bundle = run_full_analysis(xes_path)

        # 11.7 A & B: 10 cases, exact mean 10.0 days
        self.assertEqual(bundle.ex_11_7["total_cases"], 10)
        self.assertAlmostEqual(bundle.ex_11_7["mean_cycle_days"], 10.0, places=4)

        # 11.7 C: 4 cases (CASE_01 counted once despite 2 O_Accepted; CASE_04 overlaps with D)
        self.assertEqual(bundle.ex_11_7["accepted_count"], 4)
        self.assertEqual(
            set(bundle.ex_11_7["cases_11_7_c"]["case_id"].tolist()),
            {
                "CASE_01_DUP_ACCEPTED",
                "CASE_04_BOTH_ACCEPT_REFUSE",
                "CASE_09_CANCEL_THEN_ACCEPT",
                "CASE_10_ACCEPT_THEN_CANCEL",
            },
        )

        # 11.7 D: 1 case (CASE_04)
        self.assertEqual(bundle.ex_11_7["refused_count"], 1)
        self.assertEqual(
            bundle.ex_11_7["cases_11_7_d"]["case_id"].tolist(),
            ["CASE_04_BOTH_ACCEPT_REFUSE"],
        )

        # 11.7 E: 2 cases ending with O_Cancelled (CASE_02 mid-cancelled excluded)
        self.assertEqual(bundle.ex_11_7["canceled_count"], 2)
        self.assertEqual(
            set(bundle.ex_11_7["cases_11_7_e"]["case_id"].tolist()),
            {"CASE_03_END_CANCELLED", "CASE_10_ACCEPT_THEN_CANCEL"},
        )

        # 11.15: 3 cases (CASE_05 scheduled 2x / completed 1x excluded)
        self.assertEqual(bundle.ex_11_15["case_count"], 3)
        self.assertEqual(
            set(bundle.ex_11_15["cases_table"]["case_id"].tolist()),
            {
                "CASE_06_FRAUD_DIFF_RES",
                "CASE_07_FRAUD_SAME_RES",
                "CASE_08_FRAUD_EMPTY_RES",
            },
        )

        # 11.18: 1 case (only CASE_07 by User_X; CASE_06 diff resources & CASE_08 empty/UNKNOWN excluded)
        self.assertEqual(bundle.ex_11_18["case_count"], 1)
        self.assertEqual(
            bundle.ex_11_18["cases_table"]["case_id"].tolist(),
            ["CASE_07_FRAUD_SAME_RES"],
        )
        self.assertEqual(
            bundle.ex_11_18["cases_table"]["resource"].tolist(),
            ["User_X"],
        )

        # 11.22: 1 / 10 cases = 10.0% (CASE_09 non-adjacent matches; CASE_10 reverse order excluded)
        self.assertEqual(bundle.ex_11_22["case_count"], 1)
        self.assertAlmostEqual(bundle.ex_11_22["percentage"], 10.0, places=4)
        self.assertEqual(
            bundle.ex_11_22["witness_table"]["case_id"].tolist(),
            ["CASE_09_CANCEL_THEN_ACCEPT"],
        )

        # Fast (< 45d) vs Slow (>= 45d): 9 fast, 1 slow (CASE_09 = 50d)
        self.assertEqual(bundle.fast_slow["fast_count"], 9)
        self.assertEqual(bundle.fast_slow["slow_count"], 1)

    def test_process_discovery_all_algorithms(self):
        """Verify DFG (freq/perf), Alpha, Heuristics, Inductive (Petri/Tree) & ProcessGraphView rendering."""
        from bpic17_app.discovery import discover_process_model

        xes_path = os.path.join(os.path.dirname(__file__), "synthetic_edge_cases.xes")
        bundle = run_full_analysis(xes_path)

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from bpic17_app.graph_view import ProcessGraphView

        app = QApplication.instance() or QApplication([])
        view = ProcessGraphView()

        algos = (
            "dfg_frequency",
            "dfg_performance",
            "alpha",
            "heuristics",
            "inductive_petri",
            "inductive_tree",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            for algo in algos:
                res = discover_process_model(
                    bundle.df,
                    algorithm=algo,
                    lifecycle="complete",
                    top_k_variants=0,
                    min_edge_freq=1,
                    dependency_threshold=0.5,
                    noise_threshold=0.2,
                )
                self.assertGreater(len(res.nodes), 0, f"{algo} produced no nodes")
                self.assertGreater(len(res.edges), 0, f"{algo} produced no edges")
                self.assertEqual(len(res.kpis), 4, f"{algo} KPIs mismatch")
                view.render_discovery(res)
                app.processEvents()
                png_path = os.path.join(tmpdir, f"{algo}.png")
                view.export_png(png_path)
                self.assertTrue(os.path.isfile(png_path))


if __name__ == "__main__":
    unittest.main()
