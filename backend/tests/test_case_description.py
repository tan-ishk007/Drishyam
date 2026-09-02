def test_case_description_is_required_and_preserved_exactly(client, account):
    _, headers = account("Synthetic Case Description Test")
    missing = client.post("/api/v1/cases", headers=headers, json={"title": "Synthetic missing description", "crime_type": "synthetic_test"})
    assert missing.status_code == 422
    assert missing.json()["detail"] == "Case description is required."
    blank = client.post("/api/v1/cases", headers=headers, json={"title": "Synthetic blank description", "crime_type": "synthetic_test", "description": "   "})
    assert blank.status_code == 422
    assert blank.json()["detail"] == "Case description is required."
    exact = "  SYNTHETIC ONLY â€” preserve this exact punctuation and spacing.  "
    created = client.post("/api/v1/cases", headers=headers, json={"title": "Synthetic exact description", "crime_type": "synthetic_test", "description": exact})
    assert created.status_code == 201, created.text
    assert created.json()["description"] == exact