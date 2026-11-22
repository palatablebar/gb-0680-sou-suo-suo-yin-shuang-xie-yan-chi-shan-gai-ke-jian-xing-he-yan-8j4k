import csv,io,json
from app.closure import build_closure,closure_of
from app.pipeline import calculate,execute
from app import store

HEADER="event_id,doc_id,version,op,source_time,visible_time,side,payload,reported,note"
TAKEDOWN_CSV="\n".join([HEADER,
 'e1,d1,5,delete,2026-11-16T10:00:00Z,-,source,{},1,已撤',
 'e2,d1,5,delete,2026-11-16T10:00:00Z,2026-11-16T10:05:00Z,index,{},1,删除确认迟到',
 'e3,d1,4,upsert,2026-11-16T09:59:00Z,2026-11-16T10:06:00Z,index,"{""a"":1}",1,迟到旧写',
 'e4,d2,5,delete,2026-11-16T10:00:00Z,-,source,{},1,已撤未确认',
]).encode()

def rows_by_doc(closure): return {r["doc_id"]:r for r in closure["rows"]}
def timed_out(state,gate="内容差异"): return {"doc_id":"x","visibility_state":state,"gate":gate,"_sources":[1]}

def test_real_sample_handover_conclusions(result):
    docs=rows_by_doc(result["closure"])
    assert set(docs)=={"0090","0091"}
    assert docs["0090"]["responsibility"]=="未归责" and docs["0090"]["gate"]=="缺失"
    assert docs["0091"]["responsibility"]=="索引端" and docs["0091"]["gate"]=="延迟"
    m=result["closure"]["metrics"]
    assert m["total"]==2 and m["index_side"]==1 and m["unattributed"]==1 and m["source_side"]==0

def test_unattributed_keeps_reason_and_original_times(result):
    row=rows_by_doc(result["closure"])["0090"]
    assert "不凑数" in row["reason"]
    assert row["source_at"]=="2026-11-16T10:00:00+00:00" and row["visible_at"] is None

def test_taken_down_not_reattributed_by_late_old_write():
    docs=rows_by_doc(calculate(TAKEDOWN_CSV)["closure"])
    d1=docs["d1"]
    assert d1["responsibility"]=="索引端" and d1["tombstone"] is True
    assert d1["visible_at"]=="2026-11-16T10:05:00+00:00"
    assert d1["superseded_versions"]==["4"]
    d2=docs["d2"]
    assert d2["responsibility"]=="未归责" and d2["tombstone"] is True and "回执未到" in d2["reason"]
    assert len([r for r in docs.values() if r["doc_id"]=="d1"])==1

def test_late_old_write_alone_cannot_reattribute_tombstone():
    "TRAP-13 在关账层成立：删除确认按时则迟到旧写不产生交接单行"
    raw="\n".join([HEADER,
     'e1,d1,5,delete,2026-11-16T10:00:00Z,-,source,{},1,已撤',
     'e2,d1,5,delete,2026-11-16T10:00:00Z,2026-11-16T10:00:30Z,index,{},1,按时确认',
     'e3,d1,4,upsert,2026-11-16T09:59:00Z,2026-11-16T10:06:00Z,index,"{""a"":1}",1,迟到旧写',
    ]).encode()
    assert calculate(raw)["closure"]["rows"]==[]

def test_index_ahead_blames_source():
    row=build_closure([timed_out("INDEX_AHEAD")])["rows"][0]
    assert row["responsibility"]=="源端" and row["reason"]

def test_orphan_index_unattributed():
    row=build_closure([timed_out("ORPHAN_INDEX")])["rows"][0]
    assert row["responsibility"]=="未归责" and "源端记录缺失" in row["reason"]

def test_content_mismatch_blames_index():
    assert build_closure([timed_out("CONTENT_MISMATCH")])["rows"][0]["responsibility"]=="索引端"

def test_waiting_and_pass_not_on_handover():
    assert build_closure([timed_out("MISSING_INDEX","等待"),timed_out("CONSISTENT","通过")])["rows"]==[]

def test_rerun_adds_no_handover_rows_and_keeps_party(sample):
    a=execute(sample);first=closure_of(a)["rows"]
    b=execute(sample)
    assert a["run_id"]==b["run_id"] and len(store.history())==1
    assert closure_of(store.get(a["run_id"]))["rows"]==first

def test_review_cannot_bulk_switch_conclusions(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    before=closure_of(store.get(p["run_id"]))["rows"]
    assert client.post(f"/api/runs/{p['run_id']}/review",json={"version":p["version"],"decision":"已复核"}).status_code==200
    assert closure_of(store.get(p["run_id"]))["rows"]==before

def test_page_and_export_share_one_closure(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    closure=closure_of(store.get(p["run_id"]))
    page=client.get("/parity").get_data(as_text=True)
    for row in closure["rows"]:
        assert row["doc_id"] in page and row["responsibility"] in page and row["reason"] in page
    data=client.get(f"/api/runs/{p['run_id']}/archive").data.decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(data)))
    handover=[r for r in rows[1:] if r[3]=="handover"]
    assert [json.loads(r[6])["doc_id"] for r in handover]==[r["doc_id"] for r in closure["rows"]]
    for r in handover:
        evidence=json.loads(r[6])
        assert evidence["responsibility"]==r[5] and evidence["reason"] and evidence["source_at"]

def test_export_records_closure_terms_once(client):
    p=client.post("/api/runs",json={"sample":"dirty.csv"}).get_json()
    data=client.get(f"/api/runs/{p['run_id']}/archive").data.decode("utf-8-sig")
    rows=list(csv.reader(io.StringIO(data)))
    summary=[r for r in rows[1:] if r[3]=="closure"]
    assert len(summary)==1 and json.loads(summary[0][6])["metrics"]["unattributed"]==1
    again=client.get(f"/api/runs/{p['run_id']}/archive").data
    assert again==client.get(f"/api/runs/{p['run_id']}/archive").data
