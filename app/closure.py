from app.reasons import sources
from app.values import instant, number

DEFAULT_AS_OF = "2026-11-16T10:10:00Z"
DEFAULT_THRESHOLD = "120"
TIMED_OUT = {"延迟", "缺失", "内容差异"}


def attribute(row):
    """关账口径：只凭核对过的两端记录定责，单端证据不凑数。"""
    state = row["visibility_state"]
    gate = row["gate"]
    if state == "DELETE_NOT_CONFIRMED":
        return "未归责", "已撤文档删除回执未到，仅源端时刻可核，不凑数定责"
    if state == "MISSING_INDEX":
        return "未归责", "索引端记录未到，仅源端时刻可核，不凑数定责"
    if state == "ORPHAN_INDEX":
        return "未归责", "源端记录缺失，仅凭索引端单端记录不定责"
    if state == "INDEX_AHEAD":
        return "源端", "索引版本高于源端已核版本，源端高版本记录缺失"
    if gate == "延迟":
        return "索引端", "两端时刻已核，索引可见超预算"
    if gate == "内容差异":
        return "索引端", "两端记录已核，索引端与源端裁决不一致"
    return "未归责", "证据不足，不凑数定责"


def build_closure(stage5_rows, parameters=None):
    """按关账时刻为每篇超时文档落一行交接单；通过/等待中不上单。"""
    parameters = parameters or {}
    as_of = instant(parameters.get("as_of", DEFAULT_AS_OF))
    threshold = number(parameters.get("max_delay_seconds", DEFAULT_THRESHOLD))
    rows = []
    for row in stage5_rows:
        if row["gate"] not in TIMED_OUT:
            continue
        responsibility, reason = attribute(row)
        rows.append({
            "doc_id": row["doc_id"],
            "gate": row["gate"],
            "visibility_state": row["visibility_state"],
            "responsibility": responsibility,
            "reason": reason,
            "source_at": row.get("source_at"),
            "visible_at": row.get("visible_at"),
            "delay_seconds": row.get("delay_seconds"),
            "threshold_seconds": row.get("threshold_seconds"),
            "tombstone": row.get("source_op") == "delete",
            "superseded_versions": row.get("superseded_versions", []),
            "_sources": sources(row),
        })
    metrics = {
        "total": len(rows),
        "source_side": sum(r["responsibility"] == "源端" for r in rows),
        "index_side": sum(r["responsibility"] == "索引端" for r in rows),
        "unattributed": sum(r["responsibility"] == "未归责" for r in rows),
        "tombstoned": sum(r["tombstone"] for r in rows),
    }
    return {"closed_at": as_of.isoformat(), "threshold_seconds": str(threshold), "rows": rows, "metrics": metrics}


def closure_of(run):
    """页面与导出共用入口：优先读批次内已封存的关账结论，旧批次按同一口径补算。"""
    closure = run.get("closure")
    if closure:
        return closure
    stages = run.get("stages", [])
    rows = stages[4]["rows"] if len(stages) > 4 else []
    return build_closure(rows, run.get("parameters", {}))
