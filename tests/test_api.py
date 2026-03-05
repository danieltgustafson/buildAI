"""API endpoint tests."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_create_and_list_jobs(client):
    # Create a job
    resp = client.post(
        "/jobs",
        json={
            "job_name": "Test Project",
            "customer_name": "Acme Corp",
            "contract_value": 75000,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["job_name"] == "Test Project"
    job_id = data["job_id"]

    # List jobs
    resp = client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert len(jobs) >= 1
    assert any(j["job_id"] == job_id for j in jobs)


def test_list_jobs_with_filters(client):
    client.post("/jobs", json={"job_name": "Alpha Job", "customer_name": "Alpha Inc"})
    client.post("/jobs", json={"job_name": "Beta Job", "customer_name": "Beta LLC"})

    # Filter by customer
    resp = client.get("/jobs?customer=Alpha")
    assert resp.status_code == 200
    assert len(resp.json()) == 1

    # Search by name
    resp = client.get("/jobs?search=Beta")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_auth_token(client):
    resp = client.post("/auth/token", json={"username": "admin", "password": "admin"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # Bad password
    resp = client.post("/auth/token", json={"username": "admin", "password": "wrong"})
    assert resp.status_code == 401


def test_exceptions_empty(client):
    resp = client.get("/exceptions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_mappings_empty(client):
    resp = client.get("/mappings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_wip_empty(client):
    resp = client.get("/wip")
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_mapping(client):
    # Get an auth token first (mapping creation requires admin/ops role)
    token_resp = client.post("/auth/token", json={"username": "admin", "password": "admin"})
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create a job first
    job_resp = client.post("/jobs", json={"job_name": "Mapped Job"})
    job_id = job_resp.json()["job_id"]

    resp = client.post(
        "/mappings",
        json={
            "source_system": "adp",
            "source_key": "PROJ-100",
            "job_id": job_id,
            "confidence": 1.0,
            "created_by": "test",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    assert resp.json()["source_key"] == "PROJ-100"


def test_upload_ui_page(client):
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "Upload UI" in resp.text
    assert "WIP Report" in resp.text
    assert "Download CSV" in resp.text


def test_seed_profile_validation(client):
    token_resp = client.post("/auth/token", json={"username": "admin", "password": "admin"})
    token = token_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/seed/demo?background=true&profile=invalid", headers=headers)
    assert resp.status_code == 400
