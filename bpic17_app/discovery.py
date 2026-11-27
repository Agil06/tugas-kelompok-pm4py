"""PM4Py Process Discovery (DFG, Alpha, Heuristics, Inductive) & Sugiyama hierarchical layout."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd
import pm4py


@dataclass
class GraphNode:
    id: str
    label: str
    kind: str  # start, end, activity, place, transition, tau, operator
    x: float = 0.0
    y: float = 0.0
    subtitle: str = ""
    heat: float = 0.0
    detail: str = ""


@dataclass
class GraphEdge:
    source: str
    target: str
    label: str = ""
    weight: float = 1.0
    heat: float = 0.0
    detail: str = ""


@dataclass
class DiscoveryResult:
    algorithm: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    table_df: pd.DataFrame
    kpis: List[Tuple[str, str, str]] = field(default_factory=list)
    direction: str = "LR"


def _format_duration(seconds: float) -> str:
    if seconds is None or pd.isna(seconds) or seconds <= 0:
        return "0 s"
    if seconds >= 86400:
        return f"{seconds / 86400.0:.1f} d"
    if seconds >= 3600:
        return f"{seconds / 3600.0:.1f} h"
    if seconds >= 60:
        return f"{seconds / 60.0:.1f} m"
    return f"{seconds:.1f} s"


def prepare_discovery_log(
    df: pd.DataFrame,
    lifecycle: str = "complete",
    top_k_variants: int = 20,
) -> Tuple[pd.DataFrame, int, int]:
    """Filter log by lifecycle and optional top-K variants before running miners."""
    total_cases = int(df["case:concept:name"].nunique())
    sub = df
    if (
        lifecycle
        and lifecycle.lower() != "all"
        and "lifecycle:transition" in df.columns
    ):
        mask = (
            df["lifecycle:transition"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
            == lifecycle.strip().lower()
        )
        filtered = df[mask]
        if not filtered.empty:
            sub = filtered

    if top_k_variants and top_k_variants > 0:
        sub = pm4py.filter_variants_top_k(sub, int(top_k_variants))

    kept_cases = int(sub["case:concept:name"].nunique()) if not sub.empty else 0
    return sub, kept_cases, total_cases


def compute_sugiyama_layout(
    nodes: List[GraphNode],
    edges: List[GraphEdge],
    direction: str = "LR",
) -> None:
    """Assign hierarchical (x, y) coordinates via cycle-breaking + longest-path layering + barycenter ordering."""
    if not nodes:
        return

    node_map = {n.id: n for n in nodes}
    adj: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        if e.source != e.target and e.source in node_map and e.target in node_map:
            adj[e.source].append(e.target)

    # 1. Cycle breaking via DFS to collect DAG edges
    visited: Set[str] = set()
    in_stack: Set[str] = set()
    dag_adj: Dict[str, List[str]] = defaultdict(list)
    dag_rev: Dict[str, List[str]] = defaultdict(list)

    # Start DFS from start/source nodes first
    in_deg = defaultdict(int)
    for u, vs in adj.items():
        for v in vs:
            in_deg[v] += 1

    start_order = sorted(
        [n.id for n in nodes],
        key=lambda nid: (
            0 if node_map[nid].kind == "start" else (2 if node_map[nid].kind == "end" else 1),
            in_deg[nid],
            nid,
        ),
    )

    def dfs(u: str) -> None:
        visited.add(u)
        in_stack.add(u)
        for v in adj.get(u, []):
            if v in in_stack:
                continue  # back-edge skipped for layering
            dag_adj[u].append(v)
            dag_rev[v].append(u)
            if v not in visited:
                dfs(v)
        in_stack.remove(u)

    for nid in start_order:
        if nid not in visited:
            dfs(nid)

    # 2. Longest-path layer assignment (Kahn topological order)
    dag_in = {n.id: 0 for n in nodes}
    for u, vs in dag_adj.items():
        for v in vs:
            dag_in[v] += 1

    queue = [nid for nid in start_order if dag_in[nid] == 0]
    layer: Dict[str, int] = {nid: 0 for nid in queue}
    idx = 0
    while idx < len(queue):
        u = queue[idx]
        idx += 1
        for v in dag_adj.get(u, []):
            layer[v] = max(layer.get(v, 0), layer[u] + 1)
            dag_in[v] -= 1
            if dag_in[v] == 0:
                queue.append(v)

    for n in nodes:
        if n.id not in layer:
            layer[n.id] = 0

    max_layer = max(layer.values()) if layer else 0
    for n in nodes:
        if n.kind == "start":
            layer[n.id] = 0
        elif n.kind == "end" and max_layer > 0:
            layer[n.id] = max_layer

    layers: Dict[int, List[str]] = defaultdict(list)
    for nid, lv in layer.items():
        layers[lv].append(nid)
    for lv in layers:
        layers[lv].sort()

    # 3. Barycenter crossing minimization (4 sweeps)
    sorted_lvs = sorted(layers.keys())
    pos_in_layer: Dict[str, float] = {}

    def refresh_positions() -> None:
        for lv in sorted_lvs:
            for i, nid in enumerate(layers[lv]):
                pos_in_layer[nid] = float(i)

    refresh_positions()
    for _ in range(4):
        for lv in sorted_lvs[1:]:
            layers[lv].sort(
                key=lambda nid: (
                    sum(pos_in_layer[p] for p in dag_rev[nid] if p in pos_in_layer)
                    / max(len([p for p in dag_rev[nid] if p in pos_in_layer]), 1)
                    if dag_rev[nid]
                    else pos_in_layer[nid]
                )
            )
            refresh_positions()
        for lv in reversed(sorted_lvs[:-1]):
            layers[lv].sort(
                key=lambda nid: (
                    sum(pos_in_layer[c] for c in dag_adj[nid] if c in pos_in_layer)
                    / max(len([c for c in dag_adj[nid] if c in pos_in_layer]), 1)
                    if dag_adj[nid]
                    else pos_in_layer[nid]
                )
            )
            refresh_positions()

    # 4. Coordinate assignment
    if direction == "TB":
        x_gap, y_gap = 200.0, 125.0
        for lv in sorted_lvs:
            row = layers[lv]
            width = (len(row) - 1) * x_gap
            for i, nid in enumerate(row):
                node_map[nid].x = i * x_gap - width / 2.0
                node_map[nid].y = lv * y_gap
    else:
        x_gap, y_gap = 250.0, 105.0
        for lv in sorted_lvs:
            col = layers[lv]
            height = (len(col) - 1) * y_gap
            for i, nid in enumerate(col):
                node_map[nid].x = lv * x_gap
                node_map[nid].y = i * y_gap - height / 2.0


def _petri_net_to_graph(
    net: Any,
    im: Any,
    fm: Any,
    algorithm_name: str,
) -> Tuple[List[GraphNode], List[GraphEdge], pd.DataFrame]:
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    in_deg = defaultdict(int)
    out_deg = defaultdict(int)

    for arc in net.arcs:
        in_deg[arc.target.name] += 1
        out_deg[arc.source.name] += 1

    table_rows = []
    im_places = set(im.keys())
    fm_places = set(fm.keys())

    for p in net.places:
        nid = f"p::{p.name}"
        if p in im_places:
            kind = "start"
            lbl = "Start"
        elif p in fm_places:
            kind = "end"
            lbl = "End"
        else:
            kind = "place"
            lbl = ""
        nodes.append(
            GraphNode(
                id=nid,
                label=lbl,
                kind=kind,
                detail=f"Place: {p.name} | in={in_deg[p.name]}, out={out_deg[p.name]}",
            )
        )
        table_rows.append(
            {
                "element_type": "Place",
                "name": p.name,
                "label": lbl or p.name,
                "in_degree": in_deg[p.name],
                "out_degree": out_deg[p.name],
            }
        )

    for t in net.transitions:
        nid = f"t::{t.name}"
        is_tau = t.label is None
        kind = "tau" if is_tau else "transition"
        lbl = "τ" if is_tau else str(t.label)
        nodes.append(
            GraphNode(
                id=nid,
                label=lbl,
                kind=kind,
                detail=(
                    f"Silent Transition (τ): {t.name}"
                    if is_tau
                    else f"Transition: {lbl} | in={in_deg[t.name]}, out={out_deg[t.name]}"
                ),
            )
        )
        table_rows.append(
            {
                "element_type": "Silent Transition (tau)" if is_tau else "Transition",
                "name": t.name,
                "label": lbl,
                "in_degree": in_deg[t.name],
                "out_degree": out_deg[t.name],
            }
        )

    place_names = {p.name for p in net.places}
    for arc in net.arcs:
        src_prefix = "p::" if arc.source.name in place_names else "t::"
        tgt_prefix = "p::" if arc.target.name in place_names else "t::"
        edges.append(
            GraphEdge(
                source=f"{src_prefix}{arc.source.name}",
                target=f"{tgt_prefix}{arc.target.name}",
                label="",
                weight=1.0,
                heat=0.25,
                detail=f"{arc.source.name} → {arc.target.name}",
            )
        )

    compute_sugiyama_layout(nodes, edges, direction="LR")
    table_df = pd.DataFrame(table_rows)
    return nodes, edges, table_df


def discover_process_model(
    df: pd.DataFrame,
    algorithm: str = "dfg_frequency",
    lifecycle: str = "complete",
    top_k_variants: int = 20,
    min_edge_freq: int = 1,
    dependency_threshold: float = 0.5,
    noise_threshold: float = 0.2,
) -> DiscoveryResult:
    """Run selected PM4Py discovery algorithm and return laid-out graph + table + KPIs."""
    sub_df, kept_cases, total_cases = prepare_discovery_log(
        df, lifecycle=lifecycle, top_k_variants=top_k_variants
    )
    if sub_df.empty:
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=[],
            edges=[],
            table_df=pd.DataFrame(),
            kpis=[("Cases Used", "0", f"of {total_cases:,}")],
        )

    act_counts = sub_df["concept:name"].value_counts().to_dict()
    max_act_count = max(act_counts.values()) if act_counts else 1
    case_coverage = (kept_cases / total_cases * 100.0) if total_cases else 0.0

    # ------------------------------------------------------------------
    # 1. DFG (Frequency or Performance)
    # ------------------------------------------------------------------
    if algorithm in ("dfg_frequency", "dfg_performance"):
        freq_dfg, start_acts, end_acts = pm4py.discover_dfg(sub_df)
        perf_dfg: Dict[Tuple[str, str], Any] = {}
        if algorithm == "dfg_performance":
            perf_dfg, _, _ = pm4py.discover_performance_dfg(sub_df)

        filtered_edges = [
            (pair, cnt) for pair, cnt in freq_dfg.items() if cnt >= min_edge_freq
        ]
        used_acts: Set[str] = set()
        for (a, b), _ in filtered_edges:
            used_acts.add(a)
            used_acts.add(b)
        for a, cnt in start_acts.items():
            if cnt >= min_edge_freq:
                used_acts.add(a)
        for a, cnt in end_acts.items():
            if cnt >= min_edge_freq:
                used_acts.add(a)
        if not used_acts:
            used_acts = set(act_counts.keys())

        nodes: List[GraphNode] = [
            GraphNode(id="__START__", label="Start", kind="start", detail="Process Start"),
            GraphNode(id="__END__", label="End", kind="end", detail="Process End"),
        ]
        for act in sorted(used_acts):
            cnt = int(act_counts.get(act, 0))
            nodes.append(
                GraphNode(
                    id=act,
                    label=act,
                    kind="activity",
                    subtitle=f"{cnt:,}",
                    heat=min(cnt / max_act_count, 1.0),
                    detail=f"Activity: {act} | Events: {cnt:,}",
                )
            )

        edges: List[GraphEdge] = []
        table_rows = []

        max_freq = max((cnt for _, cnt in filtered_edges), default=1)
        perf_means: Dict[Tuple[str, str], float] = {}
        if algorithm == "dfg_performance":
            for pair, _ in filtered_edges:
                val = perf_dfg.get(pair, 0.0)
                if isinstance(val, dict):
                    perf_means[pair] = float(val.get("mean", 0.0))
                else:
                    perf_means[pair] = float(val or 0.0)
        max_perf = max(perf_means.values(), default=1.0) or 1.0

        for a, cnt in start_acts.items():
            if a in used_acts and cnt >= min_edge_freq:
                edges.append(
                    GraphEdge(
                        source="__START__",
                        target=a,
                        label=f"{cnt:,}",
                        weight=float(cnt),
                        heat=0.2,
                        detail=f"Start → {a} ({cnt:,} cases)",
                    )
                )

        for (a, b), cnt in filtered_edges:
            if algorithm == "dfg_performance":
                mean_sec = perf_means.get((a, b), 0.0)
                heat = min(mean_sec / max_perf, 1.0)
                lbl = _format_duration(mean_sec)
                detail = f"{a} → {b} | Mean: {lbl} | Freq: {cnt:,}"
                table_rows.append(
                    {
                        "source": a,
                        "target": b,
                        "frequency": int(cnt),
                        "mean_hours": round(mean_sec / 3600.0, 2),
                        "mean_days": round(mean_sec / 86400.0, 3),
                    }
                )
            else:
                heat = min(cnt / max_freq, 1.0)
                lbl = f"{cnt:,}"
                detail = f"{a} → {b} | Freq: {cnt:,}"
                table_rows.append(
                    {
                        "source": a,
                        "target": b,
                        "frequency": int(cnt),
                    }
                )
            edges.append(
                GraphEdge(
                    source=a,
                    target=b,
                    label=lbl,
                    weight=float(cnt),
                    heat=heat,
                    detail=detail,
                )
            )

        for a, cnt in end_acts.items():
            if a in used_acts and cnt >= min_edge_freq:
                edges.append(
                    GraphEdge(
                        source=a,
                        target="__END__",
                        label=f"{cnt:,}",
                        weight=float(cnt),
                        heat=0.2,
                        detail=f"{a} → End ({cnt:,} cases)",
                    )
                )

        compute_sugiyama_layout(nodes, edges, direction="LR")
        table_df = pd.DataFrame(table_rows)
        if not table_df.empty:
            sort_col = "mean_days" if algorithm == "dfg_performance" else "frequency"
            table_df = table_df.sort_values(sort_col, ascending=False).reset_index(
                drop=True
            )

        kpis = [
            ("Cases Covered", f"{kept_cases:,}", f"{case_coverage:.1f}% of {total_cases:,}"),
            ("Activities", f"{len(used_acts):,}", f"Lifecycle: {lifecycle}"),
            ("DFG Edges", f"{len(filtered_edges):,}", f"Min freq ≥ {min_edge_freq:,}"),
            (
                "Peak Metric",
                _format_duration(max_perf) if algorithm == "dfg_performance" else f"{max_freq:,}",
                "Slowest edge" if algorithm == "dfg_performance" else "Highest edge freq",
            ),
        ]
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            table_df=table_df,
            kpis=kpis,
            direction="LR",
        )

    # ------------------------------------------------------------------
    # 2. Alpha Miner
    # ------------------------------------------------------------------
    if algorithm == "alpha":
        net, im, fm = pm4py.discover_petri_net_alpha(sub_df)
        nodes, edges, _ = _petri_net_to_graph(net, im, fm, "alpha")

        # Build footprint / causal relation table from directly-follows relation
        freq_dfg, _, _ = pm4py.discover_dfg(sub_df)
        acts = sorted(act_counts.keys())
        rel_rows = []
        causal_cnt = 0
        parallel_cnt = 0
        for i, a in enumerate(acts):
            for b in acts[i + 1 :]:
                ab = int(freq_dfg.get((a, b), 0))
                ba = int(freq_dfg.get((b, a), 0))
                if ab > 0 and ba == 0:
                    rel = "→ (Causal A → B)"
                    causal_cnt += 1
                elif ba > 0 and ab == 0:
                    rel = "← (Causal B → A)"
                    causal_cnt += 1
                elif ab > 0 and ba > 0:
                    rel = "|| (Parallel)"
                    parallel_cnt += 1
                else:
                    continue
                rel_rows.append(
                    {
                        "activity_a": a,
                        "activity_b": b,
                        "count_a_to_b": ab,
                        "count_b_to_a": ba,
                        "alpha_relation": rel,
                    }
                )
        rel_df = pd.DataFrame(rel_rows)
        if not rel_df.empty:
            rel_df = rel_df.sort_values(
                ["count_a_to_b", "count_b_to_a"], ascending=False
            ).reset_index(drop=True)

        kpis = [
            ("Cases Covered", f"{kept_cases:,}", f"{case_coverage:.1f}% of {total_cases:,}"),
            ("Places", f"{len(net.places):,}", f"Init: {len(im)} | Final: {len(fm)}"),
            ("Transitions", f"{len(net.transitions):,}", f"Arcs: {len(net.arcs):,}"),
            ("Footprint Pairs", f"{causal_cnt:,} → | {parallel_cnt:,} ||", "Causal vs Parallel"),
        ]
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            table_df=rel_df,
            kpis=kpis,
            direction="LR",
        )

    # ------------------------------------------------------------------
    # 3. Heuristics Miner
    # ------------------------------------------------------------------
    if algorithm == "heuristics":
        heu_net = pm4py.discover_heuristics_net(
            sub_df,
            dependency_threshold=float(dependency_threshold),
            min_act_count=1,
            min_dfg_occurrences=max(1, int(min_edge_freq)),
        )

        nodes = [
            GraphNode(id="__START__", label="Start", kind="start", detail="Process Start"),
            GraphNode(id="__END__", label="End", kind="end", detail="Process End"),
        ]
        used_acts = set(heu_net.nodes.keys())
        for act in sorted(used_acts):
            cnt = int(heu_net.activities_occurrences.get(act, act_counts.get(act, 0)))
            nodes.append(
                GraphNode(
                    id=act,
                    label=act,
                    kind="activity",
                    subtitle=f"{cnt:,}",
                    heat=min(cnt / max_act_count, 1.0),
                    detail=f"Activity: {act} | Occurrences: {cnt:,}",
                )
            )

        edges = []
        table_rows = []

        # Start & End activities from heuristics net
        if heu_net.start_activities:
            for a, cnt in heu_net.start_activities[0].items():
                if a in used_acts:
                    edges.append(
                        GraphEdge(
                            source="__START__",
                            target=a,
                            label=f"{cnt:,}",
                            weight=float(cnt),
                            heat=0.2,
                            detail=f"Start → {a} ({cnt:,})",
                        )
                    )
        if heu_net.end_activities:
            for a, cnt in heu_net.end_activities[0].items():
                if a in used_acts:
                    edges.append(
                        GraphEdge(
                            source=a,
                            target="__END__",
                            label=f"{cnt:,}",
                            weight=float(cnt),
                            heat=0.2,
                            detail=f"{a} → End ({cnt:,})",
                        )
                    )

        for act, node_obj in heu_net.nodes.items():
            for out_node, edge_list in node_obj.output_connections.items():
                tgt = out_node.node_name
                if tgt not in used_acts:
                    continue
                freq = int(heu_net.dfg_matrix.get(act, {}).get(tgt, 0))
                dep = float(heu_net.dependency_matrix.get(act, {}).get(tgt, 0.0))
                edges.append(
                    GraphEdge(
                        source=act,
                        target=tgt,
                        label=f"{freq:,} ({dep:.2f})",
                        weight=float(freq),
                        heat=max(0.0, min(dep, 1.0)),
                        detail=f"{act} → {tgt} | Freq: {freq:,} | Dependency: {dep:.3f}",
                    )
                )
                table_rows.append(
                    {
                        "source": act,
                        "target": tgt,
                        "frequency": freq,
                        "dependency_score": round(dep, 4),
                    }
                )

        compute_sugiyama_layout(nodes, edges, direction="LR")
        table_df = pd.DataFrame(table_rows)
        if not table_df.empty:
            table_df = table_df.sort_values(
                ["dependency_score", "frequency"], ascending=False
            ).reset_index(drop=True)

        kpis = [
            ("Cases Covered", f"{kept_cases:,}", f"{case_coverage:.1f}% of {total_cases:,}"),
            ("Nodes", f"{len(used_acts):,}", f"Min occ ≥ {min_edge_freq:,}"),
            ("Dependency Edges", f"{len(table_rows):,}", f"Threshold ≥ {dependency_threshold:.2f}"),
            (
                "Avg Dependency",
                f"{table_df['dependency_score'].mean():.3f}" if not table_df.empty else "0.000",
                "Heuristics Net",
            ),
        ]
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            table_df=table_df,
            kpis=kpis,
            direction="LR",
        )

    # ------------------------------------------------------------------
    # 4. Inductive Miner (Petri Net)
    # ------------------------------------------------------------------
    if algorithm == "inductive_petri":
        net, im, fm = pm4py.discover_petri_net_inductive(
            sub_df, noise_threshold=float(noise_threshold)
        )
        nodes, edges, table_df = _petri_net_to_graph(net, im, fm, "inductive_petri")
        tau_cnt = sum(1 for t in net.transitions if t.label is None)
        vis_cnt = len(net.transitions) - tau_cnt
        kpis = [
            ("Cases Covered", f"{kept_cases:,}", f"{case_coverage:.1f}% of {total_cases:,}"),
            ("Places", f"{len(net.places):,}", f"Noise threshold: {noise_threshold:.2f}"),
            ("Visible Transitions", f"{vis_cnt:,}", f"Silent (τ): {tau_cnt:,}"),
            ("Arcs", f"{len(net.arcs):,}", "Sound Petri Net"),
        ]
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            table_df=table_df,
            kpis=kpis,
            direction="LR",
        )

    # ------------------------------------------------------------------
    # 5. Inductive Miner (Process Tree)
    # ------------------------------------------------------------------
    if algorithm == "inductive_tree":
        tree = pm4py.discover_process_tree_inductive(
            sub_df, noise_threshold=float(noise_threshold)
        )
        nodes = []
        edges = []
        table_rows = []
        counter = [0]

        def walk(node: Any, parent_id: Optional[str], depth: int) -> str:
            counter[0] += 1
            nid = f"pt_{counter[0]}"
            if node.operator is not None:
                op_str = str(node.operator)
                kind = "operator"
                lbl = op_str
                detail = f"Operator: {op_str} | Children: {len(node.children)}"
            elif node.label is None:
                kind = "tau"
                lbl = "τ"
                detail = "Silent leaf (τ)"
            else:
                kind = "activity"
                lbl = str(node.label)
                cnt = int(act_counts.get(lbl, 0))
                detail = f"Activity: {lbl} | Events: {cnt:,}"

            nodes.append(
                GraphNode(
                    id=nid,
                    label=lbl,
                    kind=kind,
                    heat=0.5 if kind == "operator" else 0.3,
                    detail=detail,
                )
            )
            table_rows.append(
                {
                    "node_id": nid,
                    "depth": depth,
                    "kind": kind,
                    "label": lbl,
                    "parent": parent_id or "-",
                }
            )
            if parent_id is not None:
                edges.append(
                    GraphEdge(
                        source=parent_id,
                        target=nid,
                        label="",
                        weight=1.0,
                        heat=0.35,
                        detail=f"{parent_id} → {nid}",
                    )
                )
            for child in node.children:
                walk(child, nid, depth + 1)
            return nid

        walk(tree, None, 0)
        compute_sugiyama_layout(nodes, edges, direction="TB")
        table_df = pd.DataFrame(table_rows)

        op_cnt = sum(1 for n in nodes if n.kind == "operator")
        tau_cnt = sum(1 for n in nodes if n.kind == "tau")
        leaf_cnt = sum(1 for n in nodes if n.kind == "activity")
        kpis = [
            ("Cases Covered", f"{kept_cases:,}", f"{case_coverage:.1f}% of {total_cases:,}"),
            ("Operators", f"{op_cnt:,}", f"Noise threshold: {noise_threshold:.2f}"),
            ("Activity Leaves", f"{leaf_cnt:,}", f"Silent (τ) leaves: {tau_cnt:,}"),
            ("Total Tree Nodes", f"{len(nodes):,}", "Process Tree"),
        ]
        return DiscoveryResult(
            algorithm=algorithm,
            nodes=nodes,
            edges=edges,
            table_df=table_df,
            kpis=kpis,
            direction="TB",
        )

    raise ValueError(f"Unsupported discovery algorithm: {algorithm}")
