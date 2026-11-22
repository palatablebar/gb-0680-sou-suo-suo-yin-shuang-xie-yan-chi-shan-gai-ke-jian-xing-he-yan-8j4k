import csv,io,json
from app.closure import closure_of
def build_archive(run):
    stream=io.StringIO(newline="");writer=csv.writer(stream)
    writer.writerow(["run_id","input_sha256","rule_version","kind","source_lines","reason","evidence"])
    meta=run["manifest"]
    for row in run["stages"][-1]["rows"]:
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"accepted",json.dumps(row.get("_sources",[])),row.get("status",""),json.dumps(row,ensure_ascii=False)])
    for row in run["stages"][-1].get("cumulative_quarantine",[]):
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"quarantine",json.dumps(row.get("_sources",[])),row.get("reason",""),json.dumps(row,ensure_ascii=False)])
    closure=closure_of(run)
    writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"closure","",closure["closed_at"],json.dumps({"threshold_seconds":closure["threshold_seconds"],"metrics":closure["metrics"]},ensure_ascii=False)])
    for row in closure["rows"]:
        writer.writerow([run["run_id"],meta["input_sha256"],meta["rule_version"],"handover",json.dumps(row.get("_sources",[])),row["responsibility"],json.dumps(row,ensure_ascii=False)])
    return "﻿"+stream.getvalue()
