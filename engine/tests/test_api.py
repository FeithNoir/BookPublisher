import json

from fastapi.testclient import TestClient

from bookpublisher.server.app import create_app


def events(client, job_id):
    with client.stream("GET", f"/api/jobs/{job_id}/events") as s:
        for line in s.iter_lines():
            if line.startswith("data:"):
                ev = json.loads(line[5:])
                if "type" in ev:
                    yield ev


def test_api_flow(samples, runtime):
    c = TestClient(create_app(runtime, static_dir=None))
    assert c.get("/api/health").json()["ok"]
    assert {t["id"] for t in c.get("/api/themes").json()} == {"codice", "novela", "manual", "sencillo"}
    with open(samples / "guia-formato.md", "rb") as f:
        doc = c.post("/api/documents", files={"file": ("guia.md", f, "text/markdown")}).json()
    assert len(doc["chapters"]) == 4 and doc["words"] > 300
    p = c.post(f"/api/documents/{doc['id']}/preview?target=1", json={"theme": "manual"}).json()
    assert c.get(p["pages"][0]["url"]).status_code == 200
    job = c.post("/api/exports", json={"document": doc["id"], "format": "pdf", "options": {"theme": "manual"}}).json()
    evs = list(events(c, job["id"]))
    assert evs[-1]["type"] == "finished"
    assert all(e.get("result", {}).get("path") is None for e in evs if e["type"] == "done")
    pdf = c.get(f"/api/jobs/{job['id']}/files/pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    job = c.post("/api/exports", json={"document": doc["id"], "format": "docx"}).json()
    list(events(c, job["id"]))
    assert c.get(f"/api/jobs/{job['id']}/files/docx").status_code == 200


def test_api_rejects_bad_input(runtime):
    c = TestClient(create_app(runtime, static_dir=None))
    assert c.post("/api/imports", files={"file": ("a.pdf", b"nope", "application/pdf")}).status_code == 415
    assert c.post("/api/documents", files={"file": ("a.exe", b"x")}).status_code == 415
    assert c.get("/api/previews/..%2F..%2Fetc.png").status_code == 404
    assert c.get("/api/no-existe").status_code == 404
    r = c.get("/..%2F..%2F..%2Fetc%2Fpasswd")
    assert "root:" not in r.text
    assert c.get("/api/jobs/nope/files/pdf").status_code == 404
