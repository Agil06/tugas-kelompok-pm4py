"""Core PM4Py event log analysis engine for interactive Process Mining exploration."""

from __future__ import annotations

import csv
import os
import platform
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import pm4py

REQUIRED_COLUMNS = ("case:concept:name", "concept:name", "time:timestamp")
INVALID_RESOURCES = {"", "unknown", "none", "nan", "null", "<na>"}


@dataclass
class AnalysisBundle:
    """Container holding the parsed event log and precomputed base tables."""

    file_path: str
    file_name: str
    df: pd.DataFrame
    validation: Dict[str, Any]
    case_stats: pd.DataFrame
    overview: Dict[str, Any]
    ex_11_7: Dict[str, Any]
    ex_11_15: Dict[str, Any]
    ex_11_18: Dict[str, Any]
    ex_11_22: Dict[str, Any]
    fast_slow: Dict[str, Any]


def get_environment_info() -> Dict[str, str]:
    """Return runtime and library versions for reproducibility."""
    info = {
        "Python": platform.python_version(),
        "PM4Py": getattr(pm4py, "__version__", "unknown"),
        "pandas": getattr(pd, "__version__", "unknown"),
        "numpy": getattr(np, "__version__", "unknown"),
        "Platform": platform.platform(),
    }
    try:
        import PySide6

        info["PySide6"] = PySide6.__version__
    except Exception:
        pass
    return info


def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validate required columns and normalize event ordering deterministically."""
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise ValueError("Event log is empty or not a valid DataFrame.")

    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required XES attributes: {', '.join(missing)}")

    df = df.copy()
    df["@@orig_pos"] = np.arange(len(df), dtype=np.int64)
    df["case:concept:name"] = df["case:concept:name"].astype(str)
    df["concept:name"] = df["concept:name"].astype(str)
    df["time:timestamp"] = pd.to_datetime(
        df["time:timestamp"], utc=True, errors="coerce"
    )

    if df["time:timestamp"].isna().any():
        bad_count = int(df["time:timestamp"].isna().sum())
        df = df.dropna(subset=["case:concept:name", "concept:name", "time:timestamp"])
        if df.empty:
            raise ValueError(f"All {bad_count} events had invalid timestamps.")

    df = (
        df.sort_values(
            ["case:concept:name", "time:timestamp", "@@orig_pos"],
            kind="mergesort",
        )
        .drop(columns=["@@orig_pos"])
        .reset_index(drop=True)
    )
    return df


def load_and_validate_xes(file_path: str) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Import an XES file via PM4Py and inspect available attributes and lifecycles."""
    if not file_path or not os.path.isfile(file_path):
        raise FileNotFoundError(f"XES file not found: {file_path}")

    try:
        raw_df = pm4py.read_xes(file_path)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse XES file with PM4Py: {exc}") from exc

    if not isinstance(raw_df, pd.DataFrame):
        raw_df = pm4py.convert_to_dataframe(raw_df)

    df = prepare_dataframe(raw_df)
    attributes = sorted(pm4py.get_event_attributes(df))
    has_lifecycle = "lifecycle:transition" in df.columns
    has_resource = "org:resource" in df.columns

    lifecycle_values: List[str] = []
    if has_lifecycle:
        lifecycle_values = sorted(
            df["lifecycle:transition"].dropna().astype(str).unique().tolist()
        )

    activities = sorted(df["concept:name"].dropna().astype(str).unique().tolist())

    validation = {
        "file_path": os.path.abspath(file_path),
        "file_name": os.path.basename(file_path),
        "status": "Valid XES Event Log",
        "total_cases": int(df["case:concept:name"].nunique()),
        "total_events": int(len(df)),
        "has_case_id": "case:concept:name" in df.columns,
        "has_activity": "concept:name" in df.columns,
        "has_timestamp": "time:timestamp" in df.columns,
        "has_lifecycle": has_lifecycle,
        "has_resource": has_resource,
        "lifecycle_values": lifecycle_values,
        "activities": activities,
        "attributes": attributes,
    }
    return df, validation


def compute_case_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Compute per-case start, end, duration (days), event count, and start/end activities on unfiltered traces."""
    grouped = df.groupby("case:concept:name", sort=False)
    first_ts = grouped["time:timestamp"].first()
    last_ts = grouped["time:timestamp"].last()
    event_counts = grouped.size()
    start_act = grouped["concept:name"].first()
    end_act = grouped["concept:name"].last()

    duration_seconds = (last_ts - first_ts).dt.total_seconds()
    duration_days = duration_seconds / 86400.0

    case_stats = pd.DataFrame(
        {
            "case_id": first_ts.index.astype(str),
            "event_count": event_counts.to_numpy(dtype=np.int64),
            "start_time": first_ts.to_numpy(),
            "end_time": last_ts.to_numpy(),
            "duration_days": duration_days.to_numpy(dtype=np.float64),
            "start_activity": start_act.to_numpy(dtype=str),
            "end_activity": end_act.to_numpy(dtype=str),
        }
    ).reset_index(drop=True)
    return case_stats


def compute_overview(df: pd.DataFrame, case_stats: pd.DataFrame) -> Dict[str, Any]:
    """Compute log-level overview metrics and activity summary table."""
    total_cases = int(len(case_stats))
    total_events = int(len(df))
    min_ts = df["time:timestamp"].min()
    max_ts = df["time:timestamp"].max()

    mean_days = float(case_stats["duration_days"].mean()) if total_cases else 0.0
    median_days = float(case_stats["duration_days"].median()) if total_cases else 0.0
    min_days = float(case_stats["duration_days"].min()) if total_cases else 0.0
    max_days = float(case_stats["duration_days"].max()) if total_cases else 0.0

    act_events = df.groupby("concept:name").size().rename("event_count")
    act_cases = (
        df.groupby("concept:name")["case:concept:name"]
        .nunique()
        .rename("case_count")
    )
    act_df = pd.concat([act_events, act_cases], axis=1).reset_index()
    act_df = act_df.rename(columns={"concept:name": "activity"})
    act_df["case_pct"] = (
        (act_df["case_count"] / total_cases * 100.0).round(2) if total_cases else 0.0
    )

    if "lifecycle:transition" in df.columns:
        is_complete = (
            df["lifecycle:transition"].astype(str).str.strip().str.lower() == "complete"
        )
        comp_counts = (
            df[is_complete]
            .groupby("concept:name")
            .size()
            .rename("complete_event_count")
        )
        act_df = act_df.merge(
            comp_counts, left_on="activity", right_index=True, how="left"
        )
        act_df["complete_event_count"] = (
            act_df["complete_event_count"].fillna(0).astype(np.int64)
        )

    act_df = act_df.sort_values("event_count", ascending=False).reset_index(drop=True)

    return {
        "total_cases": total_cases,
        "total_events": total_events,
        "min_timestamp": str(min_ts),
        "max_timestamp": str(max_ts),
        "mean_cycle_time_days": mean_days,
        "median_cycle_time_days": median_days,
        "min_cycle_time_days": min_days,
        "max_cycle_time_days": max_days,
        "activity_table": act_df,
    }


def act_res_res_invalid(series: pd.Series) -> pd.Series:
    """Return boolean mask for empty/unknown resource strings."""
    return series.str.lower().isin(INVALID_RESOURCES)


# ======================================================================
# General User-Parameterized Filter Functions
# ======================================================================


def filter_by_activity_rule(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    activity: str,
    mode: str = "contains",
    lifecycle: str = "All",
) -> Dict[str, Any]:
    """General case filter by activity presence or endpoint rule.

    Modes:
      - 'contains': trace contains >= 1 occurrence of `activity`
      - 'not_contains': trace contains 0 occurrences of `activity`
      - 'ends_with': last event of trace is `activity`
      - 'starts_with': first event of trace is `activity`
    Cycle time is always computed from the full unfiltered trace in `case_stats`.
    """
    total_cases = int(len(case_stats))
    use_lc = (
        lifecycle
        and lifecycle != "All"
        and "lifecycle:transition" in df.columns
    )

    if mode == "ends_with" and not use_lc:
        matched_cases = case_stats[case_stats["end_activity"] == activity].reset_index(
            drop=True
        )
        rule_label = f"Ends With '{activity}'"
    elif mode == "starts_with" and not use_lc:
        matched_cases = case_stats[
            case_stats["start_activity"] == activity
        ].reset_index(drop=True)
        rule_label = f"Starts With '{activity}'"
    else:
        sub = df
        if use_lc:
            lc_mask = (
                sub["lifecycle:transition"].fillna("").astype(str).str.strip().str.lower()
                == lifecycle.strip().lower()
            )
            sub = sub[lc_mask]

        if mode == "contains":
            if not use_lc:
                filt_df = pm4py.filter_event_attribute_values(
                    df, "concept:name", [activity], level="case", retain=True
                )
                ids = set(filt_df["case:concept:name"].unique())
            else:
                ids = set(
                    sub.loc[sub["concept:name"] == activity, "case:concept:name"].unique()
                )
            matched_cases = case_stats[case_stats["case_id"].isin(ids)].reset_index(
                drop=True
            )
            rule_label = f"Contains '{activity}'"
        elif mode == "not_contains":
            ids = set(
                sub.loc[sub["concept:name"] == activity, "case:concept:name"].unique()
            )
            matched_cases = case_stats[~case_stats["case_id"].isin(ids)].reset_index(
                drop=True
            )
            rule_label = f"Does Not Contain '{activity}'"
        elif mode == "ends_with":
            tail_df = df.groupby("case:concept:name", sort=False).tail(1)
            cond = tail_df["concept:name"] == activity
            if use_lc:
                cond = cond & (
                    tail_df["lifecycle:transition"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    == lifecycle.strip().lower()
                )
            ids = set(tail_df.loc[cond, "case:concept:name"].unique())
            matched_cases = case_stats[case_stats["case_id"].isin(ids)].reset_index(
                drop=True
            )
            rule_label = f"Ends With '{activity}'"
        elif mode == "starts_with":
            head_df = df.groupby("case:concept:name", sort=False).head(1)
            cond = head_df["concept:name"] == activity
            if use_lc:
                cond = cond & (
                    head_df["lifecycle:transition"]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                    == lifecycle.strip().lower()
                )
            ids = set(head_df.loc[cond, "case:concept:name"].unique())
            matched_cases = case_stats[case_stats["case_id"].isin(ids)].reset_index(
                drop=True
            )
            rule_label = f"Starts With '{activity}'"
        else:
            raise ValueError(f"Unsupported filter mode: {mode}")

    if use_lc:
        rule_label += f" ({lifecycle})"

    count = int(len(matched_cases))
    pct = (count / total_cases * 100.0) if total_cases else 0.0
    mean_d = float(matched_cases["duration_days"].mean()) if count else 0.0
    med_d = float(matched_cases["duration_days"].median()) if count else 0.0
    min_d = float(matched_cases["duration_days"].min()) if count else 0.0
    max_d = float(matched_cases["duration_days"].max()) if count else 0.0

    return {
        "rule_label": rule_label,
        "mode": mode,
        "activity": activity,
        "lifecycle": lifecycle if use_lc else "All",
        "case_count": count,
        "total_cases": total_cases,
        "case_pct": pct,
        "mean_cycle_time_days": mean_d,
        "median_cycle_time_days": med_d,
        "min_cycle_time_days": min_d,
        "max_cycle_time_days": max_d,
        "cases_table": matched_cases,
    }


def filter_rework_and_resource(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    activity: str,
    lifecycle: str = "complete",
    min_count: int = 2,
    same_resource: bool = False,
    exclude_empty_resource: bool = True,
) -> Dict[str, Any]:
    """General filter for repeated activity occurrences and resource constraints."""
    total_cases = int(len(case_stats))
    duration_map = dict(zip(case_stats["case_id"], case_stats["duration_days"]))
    min_count = max(1, int(min_count))

    act_norm = df["concept:name"].astype(str).str.strip().str.lower()
    target_norm = activity.strip().lower()
    act_df = df[act_norm == target_norm].copy()

    has_lifecycle = "lifecycle:transition" in df.columns
    use_lc = has_lifecycle and lifecycle and lifecycle.lower() != "all"
    if use_lc:
        lc_norm = (
            act_df["lifecycle:transition"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )
        filtered_events = act_df[lc_norm == lifecycle.strip().lower()].copy()
        lc_label = lifecycle
    else:
        filtered_events = act_df.copy()
        lc_label = "All"

    all_lc_counts = act_df.groupby("case:concept:name").size()

    if not same_resource:
        if exclude_empty_resource and "org:resource" in filtered_events.columns:
            # Keep all events for case-level repetition unless user is filtering by resource
            pass
        counts = filtered_events.groupby("case:concept:name").size()
        qualifying_ids = counts[counts >= min_count].index.astype(str).tolist()

        rows = []
        for cid in qualifying_ids:
            c_ev = filtered_events[filtered_events["case:concept:name"] == cid]
            res_list = (
                c_ev["org:resource"].fillna("MISSING").astype(str).tolist()
                if "org:resource" in c_ev.columns
                else []
            )
            ts_list = [
                ts.strftime("%Y-%m-%d %H:%M:%S") for ts in c_ev["time:timestamp"]
            ]
            rows.append(
                {
                    "case_id": cid,
                    "matching_occurrences": int(len(c_ev)),
                    "all_lifecycle_events": int(all_lc_counts.get(cid, len(c_ev))),
                    "resources_involved": ", ".join(res_list),
                    "timestamps": " | ".join(ts_list),
                    "duration_days": round(float(duration_map.get(cid, 0.0)), 2),
                }
            )
        cases_df = pd.DataFrame(
            rows,
            columns=[
                "case_id",
                "matching_occurrences",
                "all_lifecycle_events",
                "resources_involved",
                "timestamps",
                "duration_days",
            ],
        )
        evidence_df = filtered_events[
            filtered_events["case:concept:name"].isin(set(qualifying_ids))
        ].copy()
        unique_cases = int(len(cases_df))
    else:
        rows = []
        evidence_indices: List[int] = []
        case_total_matches = filtered_events.groupby("case:concept:name").size()

        if "org:resource" in filtered_events.columns:
            res_series = (
                filtered_events["org:resource"].fillna("").astype(str).str.strip()
            )
            if exclude_empty_resource:
                valid_mask = ~act_res_res_invalid(res_series)
                work_df = filtered_events[valid_mask].copy()
                work_df["@@clean_resource"] = res_series[valid_mask]
            else:
                work_df = filtered_events.copy()
                work_df["@@clean_resource"] = res_series.replace("", "MISSING")

            if not work_df.empty:
                grouped_res = work_df.groupby(
                    ["case:concept:name", "@@clean_resource"], sort=False
                )
                for (cid, res_id), grp in grouped_res:
                    if len(grp) >= min_count:
                        evidence_indices.extend(grp.index.tolist())
                        ts_list = [
                            ts.strftime("%Y-%m-%d %H:%M:%S")
                            for ts in grp["time:timestamp"]
                        ]
                        rows.append(
                            {
                                "case_id": str(cid),
                                "resource": str(res_id),
                                "same_resource_occurrences": int(len(grp)),
                                "total_case_occurrences": int(
                                    case_total_matches.get(cid, len(grp))
                                ),
                                "timestamps": " | ".join(ts_list),
                                "duration_days": round(
                                    float(duration_map.get(str(cid), 0.0)), 2
                                ),
                            }
                        )

        cases_df = pd.DataFrame(
            rows,
            columns=[
                "case_id",
                "resource",
                "same_resource_occurrences",
                "total_case_occurrences",
                "timestamps",
                "duration_days",
            ],
        )
        unique_cases = (
            int(cases_df["case_id"].nunique()) if not cases_df.empty else 0
        )
        evidence_df = (
            filtered_events.loc[sorted(set(evidence_indices))].copy()
            if evidence_indices
            else filtered_events.iloc[0:0].copy()
        )

    distinct_resources = (
        int(evidence_df["org:resource"].dropna().nunique())
        if ("org:resource" in evidence_df.columns and not evidence_df.empty)
        else 0
    )

    return {
        "activity": activity,
        "lifecycle": lc_label,
        "min_count": min_count,
        "same_resource": same_resource,
        "exclude_empty_resource": exclude_empty_resource,
        "case_count": unique_cases,
        "total_cases": total_cases,
        "case_pct": round(unique_cases / total_cases * 100.0, 4)
        if total_cases
        else 0.0,
        "evidence_event_count": int(len(evidence_df)),
        "distinct_resources": distinct_resources,
        "cases_table": cases_df,
        "evidence_events": evidence_df,
    }


def filter_sequence_relation(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    first_activity: str,
    second_activity: str,
    relation: str = "eventually_follows",
    lifecycle: str = "All",
) -> Dict[str, Any]:
    """General sequence filter checking if `first_activity` is followed by `second_activity`.

    Relations:
      - 'eventually_follows': exists i < j in trace with event[i] == first and event[j] == second
      - 'directly_follows': exists i in trace with event[i] == first and event[i + 1] == second
    """
    total_cases = int(len(case_stats))
    duration_map = dict(zip(case_stats["case_id"], case_stats["duration_days"]))
    end_act_map = dict(zip(case_stats["case_id"], case_stats["end_activity"]))

    work_df = df
    if (
        lifecycle
        and lifecycle.lower() != "all"
        and "lifecycle:transition" in df.columns
    ):
        lc_mask = (
            df["lifecycle:transition"].fillna("").astype(str).str.strip().str.lower()
            == lifecycle.strip().lower()
        )
        work_df = df[lc_mask]

    cases_with_first = set(
        work_df.loc[
            work_df["concept:name"] == first_activity, "case:concept:name"
        ].unique()
    )
    cases_with_second = set(
        work_df.loc[
            work_df["concept:name"] == second_activity, "case:concept:name"
        ].unique()
    )
    candidate_ids = cases_with_first.intersection(cases_with_second)

    witness_rows = []
    if candidate_ids:
        sub = work_df[work_df["case:concept:name"].isin(candidate_ids)].copy()
        sub["@@pos_in_case"] = sub.groupby("case:concept:name").cumcount()

        if relation == "eventually_follows":
            first_rows = sub[sub["concept:name"] == first_activity]
            second_rows = sub[sub["concept:name"] == second_activity]

            earliest_first = first_rows.groupby("case:concept:name", sort=False).first()
            latest_second = second_rows.groupby("case:concept:name", sort=False).last()
            first_counts = first_rows.groupby("case:concept:name").size()
            second_counts = second_rows.groupby("case:concept:name").size()

            joined = pd.merge(
                earliest_first[["@@pos_in_case", "time:timestamp"]],
                latest_second[["@@pos_in_case", "time:timestamp"]],
                left_index=True,
                right_index=True,
                suffixes=("_first", "_second"),
                how="inner",
            )
            matched = joined[
                joined["@@pos_in_case_first"] < joined["@@pos_in_case_second"]
            ]

            for cid, row in matched.iterrows():
                cid_str = str(cid)
                pos_i = int(row["@@pos_in_case_first"])
                pos_j = int(row["@@pos_in_case_second"])
                ts_i = row["time:timestamp_first"]
                ts_j = row["time:timestamp_second"]
                witness_rows.append(
                    {
                        "case_id": cid_str,
                        "first_step": pos_i + 1,
                        "first_timestamp": ts_i.strftime("%Y-%m-%d %H:%M:%S"),
                        "second_step": pos_j + 1,
                        "second_timestamp": ts_j.strftime("%Y-%m-%d %H:%M:%S"),
                        "events_between": int(pos_j - pos_i - 1),
                        "first_activity_count": int(first_counts.get(cid, 1)),
                        "second_activity_count": int(second_counts.get(cid, 1)),
                        "end_activity": str(end_act_map.get(cid_str, "")),
                        "duration_days": round(
                            float(duration_map.get(cid_str, 0.0)), 2
                        ),
                    }
                )
        elif relation == "directly_follows":
            sub["@@next_act"] = sub.groupby("case:concept:name")["concept:name"].shift(-1)
            sub["@@next_ts"] = sub.groupby("case:concept:name")["time:timestamp"].shift(-1)
            df_matches = sub[
                (sub["concept:name"] == first_activity)
                & (sub["@@next_act"] == second_activity)
            ]
            first_match_per_case = df_matches.groupby(
                "case:concept:name", sort=False
            ).first()
            for cid, row in first_match_per_case.iterrows():
                cid_str = str(cid)
                pos_i = int(row["@@pos_in_case"])
                ts_i = row["time:timestamp"]
                ts_j = row["@@next_ts"]
                witness_rows.append(
                    {
                        "case_id": cid_str,
                        "first_step": pos_i + 1,
                        "first_timestamp": ts_i.strftime("%Y-%m-%d %H:%M:%S"),
                        "second_step": pos_i + 2,
                        "second_timestamp": ts_j.strftime("%Y-%m-%d %H:%M:%S")
                        if pd.notna(ts_j)
                        else "",
                        "events_between": 0,
                        "first_activity_count": 1,
                        "second_activity_count": 1,
                        "end_activity": str(end_act_map.get(cid_str, "")),
                        "duration_days": round(
                            float(duration_map.get(cid_str, 0.0)), 2
                        ),
                    }
                )
        else:
            raise ValueError(f"Unsupported sequence relation: {relation}")

    witness_df = pd.DataFrame(
        witness_rows,
        columns=[
            "case_id",
            "first_step",
            "first_timestamp",
            "second_step",
            "second_timestamp",
            "events_between",
            "first_activity_count",
            "second_activity_count",
            "end_activity",
            "duration_days",
        ],
    )
    matched_count = int(len(witness_df))
    pct = (matched_count / total_cases * 100.0) if total_cases else 0.0

    return {
        "first_activity": first_activity,
        "second_activity": second_activity,
        "relation": relation,
        "lifecycle": lifecycle,
        "case_count": matched_count,
        "denominator_total_cases": total_cases,
        "percentage": pct,
        "answer_yes_no": "Yes" if matched_count > 0 else "No",
        "witness_table": witness_df,
    }


# ======================================================================
# Preset / Compatibility Wrappers
# ======================================================================


def analyze_11_7(df: pd.DataFrame, case_stats: pd.DataFrame) -> Dict[str, Any]:
    """Compute default outcome & endpoint comparison rows."""
    total_cases = int(len(case_stats))
    mean_cycle_days = float(case_stats["duration_days"].mean()) if total_cases else 0.0

    res_c = filter_by_activity_rule(df, case_stats, "O_Accepted", mode="contains")
    res_d = filter_by_activity_rule(df, case_stats, "O_Refused", mode="contains")
    res_e = filter_by_activity_rule(df, case_stats, "O_Cancelled", mode="ends_with")

    accepted_ids = set(res_c["cases_table"]["case_id"])
    refused_ids = set(res_d["cases_table"]["case_id"])
    both_accept_refuse_count = int(len(accepted_ids.intersection(refused_ids)))

    summary_df = pd.DataFrame(
        [
            {
                "filter_rule": "All Cases (Unfiltered Log)",
                "activity": "All",
                "lifecycle": "All",
                "case_count": total_cases,
                "total_cases": total_cases,
                "case_pct": 100.0 if total_cases else 0.0,
                "mean_cycle_time_days": round(mean_cycle_days, 2),
                "median_cycle_time_days": round(
                    float(case_stats["duration_days"].median()) if total_cases else 0.0,
                    2,
                ),
                "max_cycle_time_days": round(
                    float(case_stats["duration_days"].max()) if total_cases else 0.0,
                    2,
                ),
            },
            {
                "filter_rule": res_c["rule_label"],
                "activity": "O_Accepted",
                "lifecycle": "All",
                "case_count": res_c["case_count"],
                "total_cases": total_cases,
                "case_pct": round(res_c["case_pct"], 2),
                "mean_cycle_time_days": round(res_c["mean_cycle_time_days"], 2),
                "median_cycle_time_days": round(res_c["median_cycle_time_days"], 2),
                "max_cycle_time_days": round(res_c["max_cycle_time_days"], 2),
            },
            {
                "filter_rule": res_d["rule_label"],
                "activity": "O_Refused",
                "lifecycle": "All",
                "case_count": res_d["case_count"],
                "total_cases": total_cases,
                "case_pct": round(res_d["case_pct"], 2),
                "mean_cycle_time_days": round(res_d["mean_cycle_time_days"], 2),
                "median_cycle_time_days": round(res_d["median_cycle_time_days"], 2),
                "max_cycle_time_days": round(res_d["max_cycle_time_days"], 2),
            },
            {
                "filter_rule": res_e["rule_label"],
                "activity": "O_Cancelled",
                "lifecycle": "All",
                "case_count": res_e["case_count"],
                "total_cases": total_cases,
                "case_pct": round(res_e["case_pct"], 2),
                "mean_cycle_time_days": round(res_e["mean_cycle_time_days"], 2),
                "median_cycle_time_days": round(res_e["median_cycle_time_days"], 2),
                "max_cycle_time_days": round(res_e["max_cycle_time_days"], 2),
            },
        ]
    )

    return {
        "total_cases": total_cases,
        "mean_cycle_days": mean_cycle_days,
        "accepted_count": res_c["case_count"],
        "accepted_mean_days": res_c["mean_cycle_time_days"],
        "refused_count": res_d["case_count"],
        "refused_mean_days": res_d["mean_cycle_time_days"],
        "canceled_count": res_e["case_count"],
        "canceled_mean_days": res_e["mean_cycle_time_days"],
        "overlap_accepted_and_refused": both_accept_refuse_count,
        "summary_table": summary_df,
        "cases_11_7_c": res_c["cases_table"],
        "cases_11_7_d": res_d["cases_table"],
        "cases_11_7_e": res_e["cases_table"],
    }


def analyze_11_15_and_11_18(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    target_activity: str = "W_Assess Potential Fraud",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Wrapper returning case-level and same-resource repetition results."""
    res_15 = filter_rework_and_resource(
        df,
        case_stats,
        activity=target_activity,
        lifecycle="complete",
        min_count=2,
        same_resource=False,
        exclude_empty_resource=True,
    )
    res_18 = filter_rework_and_resource(
        df,
        case_stats,
        activity=target_activity,
        lifecycle="complete",
        min_count=2,
        same_resource=True,
        exclude_empty_resource=True,
    )

    # Keep backwards-compatible column aliases for unit tests
    c15 = res_15["cases_table"].rename(
        columns={
            "matching_occurrences": "complete_count",
            "timestamps": "complete_timestamps",
        }
    )
    c18 = res_18["cases_table"].rename(
        columns={
            "same_resource_occurrences": "same_resource_complete_count",
            "total_case_occurrences": "total_case_completes",
            "timestamps": "complete_timestamps",
        }
    )
    res_15["cases_table"] = c15
    res_15["filter_rule"] = (
        f"activity == '{target_activity}' AND lifecycle == 'complete' (>= 2)"
    )
    res_18["cases_table"] = c18
    res_18["filter_rule"] = (
        f"activity == '{target_activity}' AND lifecycle == 'complete' (>= 2 by same resource)"
    )
    return res_15, res_18


def analyze_11_22(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    first_activity: str = "O_Cancelled",
    second_activity: str = "O_Accepted",
) -> Dict[str, Any]:
    """Wrapper for sequence relation O_Cancelled -> O_Accepted."""
    res = filter_sequence_relation(
        df,
        case_stats,
        first_activity=first_activity,
        second_activity=second_activity,
        relation="eventually_follows",
    )
    res["filter_rule"] = (
        f"'{first_activity}' eventually followed by '{second_activity}' (i < j)"
    )
    return res


def analyze_fast_slow(
    df: pd.DataFrame,
    case_stats: pd.DataFrame,
    threshold_days: float = 45.0,
) -> Dict[str, Any]:
    """Split cases by cycle time threshold (< threshold_days vs >= threshold_days)."""
    total_cases = int(len(case_stats))
    fast_cases = case_stats[case_stats["duration_days"] < threshold_days].reset_index(
        drop=True
    )
    slow_cases = case_stats[case_stats["duration_days"] >= threshold_days].reset_index(
        drop=True
    )

    fast_count = int(len(fast_cases))
    slow_count = int(len(slow_cases))
    fast_pct = (fast_count / total_cases * 100.0) if total_cases else 0.0
    slow_pct = (slow_count / total_cases * 100.0) if total_cases else 0.0

    slow_end_o_cancelled = int((slow_cases["end_activity"] == "O_Cancelled").sum())
    fast_end_o_cancelled = int((fast_cases["end_activity"] == "O_Cancelled").sum())

    slow_ids = set(slow_cases["case_id"])
    df_is_slow = df["case:concept:name"].isin(slow_ids)

    slow_df = df[df_is_slow]
    fast_df = df[~df_is_slow]

    slow_act_events = slow_df.groupby("concept:name").size().rename("slow_events")
    slow_act_cases = (
        slow_df.groupby("concept:name")["case:concept:name"]
        .nunique()
        .rename("slow_cases")
    )
    fast_act_events = fast_df.groupby("concept:name").size().rename("fast_events")
    fast_act_cases = (
        fast_df.groupby("concept:name")["case:concept:name"]
        .nunique()
        .rename("fast_cases")
    )

    comp_df = (
        pd.concat(
            [slow_act_cases, slow_act_events, fast_act_cases, fast_act_events], axis=1
        )
        .fillna(0)
        .astype(np.int64)
        .reset_index()
        .rename(columns={"concept:name": "activity"})
    )

    comp_df["slow_case_pct"] = (
        (comp_df["slow_cases"] / slow_count * 100.0).round(2) if slow_count else 0.0
    )
    comp_df["fast_case_pct"] = (
        (comp_df["fast_cases"] / fast_count * 100.0).round(2) if fast_count else 0.0
    )
    comp_df["slow_events_per_case"] = np.where(
        comp_df["slow_cases"] > 0,
        (comp_df["slow_events"] / comp_df["slow_cases"]).round(2),
        0.0,
    )
    comp_df["fast_events_per_case"] = np.where(
        comp_df["fast_cases"] > 0,
        (comp_df["fast_events"] / comp_df["fast_cases"]).round(2),
        0.0,
    )
    comp_df["case_pct_diff"] = (
        comp_df["slow_case_pct"] - comp_df["fast_case_pct"]
    ).round(2)
    comp_df = comp_df.sort_values("case_pct_diff", ascending=False).reset_index(
        drop=True
    )

    return {
        "threshold_days": threshold_days,
        "total_cases": total_cases,
        "fast_count": fast_count,
        "fast_pct": fast_pct,
        "fast_mean_days": float(fast_cases["duration_days"].mean())
        if fast_count
        else 0.0,
        "slow_count": slow_count,
        "slow_pct": slow_pct,
        "slow_mean_days": float(slow_cases["duration_days"].mean())
        if slow_count
        else 0.0,
        "slow_max_days": float(slow_cases["duration_days"].max())
        if slow_count
        else 0.0,
        "slow_end_o_cancelled": slow_end_o_cancelled,
        "slow_end_o_cancelled_pct": (slow_end_o_cancelled / slow_count * 100.0)
        if slow_count
        else 0.0,
        "fast_end_o_cancelled": fast_end_o_cancelled,
        "comparison_table": comp_df,
        "slow_cases_table": slow_cases.sort_values(
            "duration_days", ascending=False
        ).reset_index(drop=True),
        "fast_cases_table": fast_cases,
    }


def get_case_trace(df: pd.DataFrame, case_id: str) -> pd.DataFrame:
    """Extract ordered event timeline for a single case ID."""
    sub = df[df["case:concept:name"] == str(case_id)].copy()
    if sub.empty:
        return pd.DataFrame(
            columns=["step", "timestamp", "activity", "lifecycle", "resource"]
        )

    out = pd.DataFrame()
    out["step"] = np.arange(1, len(sub) + 1, dtype=np.int64)
    out["timestamp"] = (
        sub["time:timestamp"]
        .dt.strftime("%Y-%m-%d %H:%M:%S.%f")
        .str.slice(0, 23)
        .to_numpy()
    )
    out["activity"] = sub["concept:name"].astype(str).to_numpy()
    out["lifecycle"] = (
        sub["lifecycle:transition"].fillna("").astype(str).to_numpy()
        if "lifecycle:transition" in sub.columns
        else ""
    )
    out["resource"] = (
        sub["org:resource"].fillna("").astype(str).to_numpy()
        if "org:resource" in sub.columns
        else ""
    )
    for extra_col in ("EventOrigin", "EventID", "OfferID", "Action"):
        if extra_col in sub.columns:
            out[extra_col] = sub[extra_col].fillna("").astype(str).to_numpy()
    return out


def run_full_analysis(
    file_path: str,
    progress_cb: Optional[Callable[[str, int], None]] = None,
) -> AnalysisBundle:
    """Load XES log and compute base tables & initial filter states."""

    def report(msg: str, pct: int) -> None:
        if progress_cb is not None:
            progress_cb(msg, pct)

    report("Reading and validating XES event log via PM4Py...", 15)
    df, validation = load_and_validate_xes(file_path)

    report("Computing per-case durations and log overview metrics...", 45)
    case_stats = compute_case_stats(df)
    overview = compute_overview(df, case_stats)

    report("Initializing outcome, rework, sequence, and duration views...", 80)
    ex_11_7 = analyze_11_7(df, case_stats)
    ex_11_15, ex_11_18 = analyze_11_15_and_11_18(df, case_stats)
    ex_11_22 = analyze_11_22(df, case_stats)
    fast_slow = analyze_fast_slow(df, case_stats)

    report("Ready.", 100)
    return AnalysisBundle(
        file_path=validation["file_path"],
        file_name=validation["file_name"],
        df=df,
        validation=validation,
        case_stats=case_stats,
        overview=overview,
        ex_11_7=ex_11_7,
        ex_11_15=ex_11_15,
        ex_11_18=ex_11_18,
        ex_11_22=ex_11_22,
        fast_slow=fast_slow,
    )


def build_overall_summary_rows(bundle: AnalysisBundle) -> List[Dict[str, Any]]:
    """Build consolidated summary table for CSV export."""
    total_cases = bundle.overview["total_cases"]
    rows: List[Dict[str, Any]] = []
    for _, r in bundle.ex_11_7["summary_table"].iterrows():
        rows.append(
            {
                "analysis_category": "Activity & Endpoint Filter",
                "filter_rule": r["filter_rule"],
                "case_count": r["case_count"],
                "denominator_cases": total_cases,
                "percentage": f"{r['case_pct']:.2f}%",
                "mean_cycle_time_days": f"{r['mean_cycle_time_days']:.2f}",
            }
        )

    rows.append(
        {
            "analysis_category": "Rework Filter (Any Resource)",
            "filter_rule": bundle.ex_11_15["filter_rule"],
            "case_count": bundle.ex_11_15["case_count"],
            "denominator_cases": total_cases,
            "percentage": f"{bundle.ex_11_15['case_pct']:.4f}%",
            "mean_cycle_time_days": "-",
        }
    )
    rows.append(
        {
            "analysis_category": "Rework Filter (Same Resource)",
            "filter_rule": bundle.ex_11_18["filter_rule"],
            "case_count": bundle.ex_11_18["case_count"],
            "denominator_cases": total_cases,
            "percentage": f"{bundle.ex_11_18['case_pct']:.4f}%",
            "mean_cycle_time_days": "-",
        }
    )
    rows.append(
        {
            "analysis_category": "Sequence Filter (Eventually Follows)",
            "filter_rule": bundle.ex_11_22["filter_rule"],
            "case_count": bundle.ex_11_22["case_count"],
            "denominator_cases": bundle.ex_11_22["denominator_total_cases"],
            "percentage": f"{bundle.ex_11_22['percentage']:.2f}%",
            "mean_cycle_time_days": "-",
        }
    )
    rows.append(
        {
            "analysis_category": "Duration Split (Fast Cases)",
            "filter_rule": f"Case duration < {bundle.fast_slow['threshold_days']:.1f} days",
            "case_count": bundle.fast_slow["fast_count"],
            "denominator_cases": total_cases,
            "percentage": f"{bundle.fast_slow['fast_pct']:.2f}%",
            "mean_cycle_time_days": f"{bundle.fast_slow['fast_mean_days']:.2f}",
        }
    )
    rows.append(
        {
            "analysis_category": "Duration Split (Slow Cases)",
            "filter_rule": f"Case duration >= {bundle.fast_slow['threshold_days']:.1f} days",
            "case_count": bundle.fast_slow["slow_count"],
            "denominator_cases": total_cases,
            "percentage": f"{bundle.fast_slow['slow_pct']:.2f}%",
            "mean_cycle_time_days": f"{bundle.fast_slow['slow_mean_days']:.2f}",
        }
    )
    return rows


def export_summary_csv(bundle: AnalysisBundle, output_path: str) -> None:
    """Export summary metrics to CSV using stdlib csv."""
    rows = build_overall_summary_rows(bundle)
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_dataframe_csv(df: pd.DataFrame, output_path: str) -> None:
    """Export any table DataFrame to CSV."""
    df.to_csv(output_path, index=False, encoding="utf-8")
