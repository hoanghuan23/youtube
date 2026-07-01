def test_health_and_source_crud(client):
    assert client.get("/health").json() == {"status": "ok"}

    payload = {"source_type": "channel", "identifier": "@demo", "display_name": "Demo"}
    created = client.post("/sources", json=payload)
    assert created.status_code == 201
    source_id = created.json()["id"]
    assert created.json()["identifier"] == "demo"

    duplicate = client.post("/sources", json=payload)
    assert duplicate.status_code == 400

    listed = client.get("/sources")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = client.patch(f"/sources/{source_id}", json={"display_name": "Updated"})
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Updated"

    deleted = client.delete(f"/sources/{source_id}")
    assert deleted.status_code == 204


def test_invalid_source_type_rejected(client):
    response = client.post("/sources", json={"source_type": "user", "identifier": "demo"})
    assert response.status_code == 422
