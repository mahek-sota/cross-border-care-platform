"""Object-level access control for cases.

These tests are the contract for ``get_case_for_user`` / ``case_access_filter``:
- patients only ever reach their own cases,
- coordinators reach cases assigned to them plus unassigned ones in the queue,
- admins reach everything,
and crucially that *listing* and *fetching* agree -- a case a user cannot GET must
never appear in their list, and vice versa.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.enums import CaseStatus, UserRole
from app.services import cases as case_service


@pytest.fixture
def make_case(db):
    def _make_case(patient, *, coordinator=None, status: CaseStatus = CaseStatus.DRAFT):
        case = case_service.create_case(
            db, patient=patient, procedure_code="TKR-001", target_countries=["IN", "TH"]
        )
        if coordinator is not None or status is not CaseStatus.DRAFT:
            if coordinator is not None:
                case.coordinator_id = coordinator.id
            case.status = status
            db.add(case)
            db.commit()
            db.refresh(case)
        return case

    return _make_case


def _ids(payload: dict) -> set[str]:
    return {item["id"] for item in payload["items"]}


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #


def test_patient_can_read_their_own_case(client, auth_headers, patient, make_case) -> None:
    case = make_case(patient)
    response = client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(patient))
    assert response.status_code == 200
    assert response.json()["id"] == str(case.id)


def test_patient_cannot_read_another_patients_case(
    client, auth_headers, patient, other_patient, make_case
) -> None:
    case = make_case(other_patient)
    response = client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(patient))
    # 404, not 403: the endpoint must not confirm the case exists.
    assert response.status_code == 404


def test_patient_list_excludes_other_patients_cases(
    client, auth_headers, patient, other_patient, make_case
) -> None:
    mine = make_case(patient)
    theirs = make_case(other_patient)

    body = client.get("/api/v1/cases", headers=auth_headers(patient)).json()
    assert _ids(body) == {str(mine.id)}
    assert str(theirs.id) not in _ids(body)
    assert body["meta"]["total"] == 1


def test_patient_cannot_read_another_patients_case_events(
    client, auth_headers, patient, other_patient, make_case
) -> None:
    case = make_case(other_patient)
    response = client.get(f"/api/v1/cases/{case.id}/events", headers=auth_headers(patient))
    assert response.status_code == 404


def test_unknown_case_id_is_404_for_everyone(client, auth_headers, admin) -> None:
    response = client.get(f"/api/v1/cases/{uuid.uuid4()}", headers=auth_headers(admin))
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Coordinators
# --------------------------------------------------------------------------- #


def test_coordinator_sees_unassigned_cases_in_the_queue(
    client, auth_headers, patient, coordinator, make_case
) -> None:
    case = make_case(patient)  # no coordinator yet
    assert (
        client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(coordinator)).status_code
        == 200
    )
    listed = client.get("/api/v1/cases", headers=auth_headers(coordinator)).json()
    assert str(case.id) in _ids(listed)


def test_coordinator_sees_cases_assigned_to_them(
    client, auth_headers, patient, coordinator, make_case
) -> None:
    case = make_case(patient, coordinator=coordinator)
    assert (
        client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(coordinator)).status_code
        == 200
    )


def test_coordinator_cannot_see_a_case_assigned_to_a_peer(
    client, auth_headers, patient, coordinator, other_coordinator, make_case
) -> None:
    case = make_case(patient, coordinator=other_coordinator)
    assert (
        client.get(f"/api/v1/cases/{case.id}", headers=auth_headers(coordinator)).status_code
        == 404
    )
    body = client.get("/api/v1/cases", headers=auth_headers(coordinator)).json()
    assert str(case.id) not in _ids(body)


def test_list_and_fetch_agree_for_coordinators(
    client, auth_headers, patient, other_patient, coordinator, other_coordinator, make_case
) -> None:
    """Every case in the list must be fetchable, and nothing else must be."""
    visible = [
        make_case(patient),  # unassigned
        make_case(other_patient, coordinator=coordinator),  # assigned to them
    ]
    hidden = [make_case(patient, coordinator=other_coordinator)]

    headers = auth_headers(coordinator)
    listed = _ids(client.get("/api/v1/cases", headers=headers).json())
    assert listed == {str(case.id) for case in visible}

    for case in visible:
        assert client.get(f"/api/v1/cases/{case.id}", headers=headers).status_code == 200
    for case in hidden:
        assert client.get(f"/api/v1/cases/{case.id}", headers=headers).status_code == 404


# --------------------------------------------------------------------------- #
# Admins
# --------------------------------------------------------------------------- #


def test_admin_sees_every_case(
    client, auth_headers, patient, other_patient, other_coordinator, admin, make_case
) -> None:
    cases = [
        make_case(patient),
        make_case(other_patient, coordinator=other_coordinator),
    ]
    headers = auth_headers(admin)
    listed = _ids(client.get("/api/v1/cases", headers=headers).json())
    assert listed == {str(case.id) for case in cases}
    for case in cases:
        assert client.get(f"/api/v1/cases/{case.id}", headers=headers).status_code == 200


# --------------------------------------------------------------------------- #
# require_role
# --------------------------------------------------------------------------- #


def test_only_patients_create_cases(client, auth_headers, coordinator, admin, patient) -> None:
    payload = {"procedure_code": "TKR-001", "target_countries": ["in"]}

    def create_as(user) -> int:
        return client.post("/api/v1/cases", json=payload, headers=auth_headers(user)).status_code

    assert create_as(patient) == 201
    assert create_as(coordinator) == 403
    assert create_as(admin) == 403


def test_case_endpoints_require_authentication(client, patient, make_case) -> None:
    case = make_case(patient)
    assert client.get("/api/v1/cases").status_code == 401
    assert client.get(f"/api/v1/cases/{case.id}").status_code == 401


def test_country_codes_are_normalized_on_create(client, auth_headers, patient) -> None:
    response = client.post(
        "/api/v1/cases",
        json={"procedure_code": "TKR-001", "target_countries": ["in", "TH", "in"]},
        headers=auth_headers(patient),
    )
    assert response.status_code == 201
    assert response.json()["target_countries"] == ["IN", "TH"]


def test_invalid_country_code_is_rejected(client, auth_headers, patient) -> None:
    response = client.post(
        "/api/v1/cases",
        json={"procedure_code": "TKR-001", "target_countries": ["India"]},
        headers=auth_headers(patient),
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# Assignment
# --------------------------------------------------------------------------- #


def test_coordinator_claims_an_unassigned_case(
    client, auth_headers, patient, coordinator, make_case
) -> None:
    case = make_case(patient)
    response = client.post(
        f"/api/v1/cases/{case.id}/assign", json={}, headers=auth_headers(coordinator)
    )
    assert response.status_code == 200
    assert response.json()["coordinator_id"] == str(coordinator.id)


def test_coordinator_cannot_claim_for_someone_else(
    client, auth_headers, patient, coordinator, other_coordinator, make_case
) -> None:
    case = make_case(patient)
    response = client.post(
        f"/api/v1/cases/{case.id}/assign",
        json={"coordinator_id": str(other_coordinator.id)},
        headers=auth_headers(coordinator),
    )
    assert response.status_code == 403


def test_admin_can_reassign_a_claimed_case(
    client, auth_headers, patient, coordinator, other_coordinator, admin, make_case
) -> None:
    case = make_case(patient, coordinator=coordinator)
    response = client.post(
        f"/api/v1/cases/{case.id}/assign",
        json={"coordinator_id": str(other_coordinator.id)},
        headers=auth_headers(admin),
    )
    assert response.status_code == 200
    assert response.json()["coordinator_id"] == str(other_coordinator.id)


def test_assigning_a_non_coordinator_is_rejected(
    client, auth_headers, patient, other_patient, admin, make_case
) -> None:
    case = make_case(patient)
    response = client.post(
        f"/api/v1/cases/{case.id}/assign",
        json={"coordinator_id": str(other_patient.id)},
        headers=auth_headers(admin),
    )
    assert response.status_code == 422


def test_patients_cannot_assign_cases(client, auth_headers, patient, make_case) -> None:
    case = make_case(patient)
    response = client.post(
        f"/api/v1/cases/{case.id}/assign", json={}, headers=auth_headers(patient)
    )
    assert response.status_code == 403


# --------------------------------------------------------------------------- #
# Status transitions + audit trail
# --------------------------------------------------------------------------- #


def test_patient_can_submit_their_draft(client, auth_headers, patient, make_case) -> None:
    case = make_case(patient)
    response = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "submitted"},
        headers=auth_headers(patient),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"


def test_patient_cannot_drive_staff_transitions(client, auth_headers, patient, make_case) -> None:
    case = make_case(patient, status=CaseStatus.SUBMITTED)
    response = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "under_review"},
        headers=auth_headers(patient),
    )
    assert response.status_code == 403


def test_coordinator_must_claim_before_driving_a_case(
    client, auth_headers, patient, coordinator, make_case
) -> None:
    case = make_case(patient, status=CaseStatus.SUBMITTED)  # visible but unclaimed
    blocked = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "under_review"},
        headers=auth_headers(coordinator),
    )
    assert blocked.status_code == 403

    client.post(f"/api/v1/cases/{case.id}/assign", json={}, headers=auth_headers(coordinator))
    allowed = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "under_review"},
        headers=auth_headers(coordinator),
    )
    assert allowed.status_code == 200


def test_illegal_transition_is_rejected(client, auth_headers, patient, make_case) -> None:
    case = make_case(patient)  # draft
    response = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "completed"},
        headers=auth_headers(patient),
    )
    assert response.status_code == 409


def test_terminal_status_cannot_be_left(
    client, auth_headers, patient, coordinator, admin, make_case
) -> None:
    case = make_case(patient, coordinator=coordinator, status=CaseStatus.CANCELLED)
    response = client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "submitted"},
        headers=auth_headers(admin),
    )
    assert response.status_code == 409


def test_every_change_writes_a_case_event(
    client, auth_headers, patient, coordinator, make_case
) -> None:
    case = make_case(patient)
    client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "submitted", "reason": "ready"},
        headers=auth_headers(patient),
    )
    client.post(f"/api/v1/cases/{case.id}/assign", json={}, headers=auth_headers(coordinator))

    events = client.get(f"/api/v1/cases/{case.id}/events", headers=auth_headers(patient)).json()
    types = [event["event_type"] for event in events]
    assert types == ["case_created", "status_changed", "coordinator_assigned"]

    status_event = events[1]
    assert status_event["actor_id"] == str(patient.id)
    assert status_event["payload"] == {"from": "draft", "to": "submitted", "reason": "ready"}


def test_failed_transition_writes_no_event(client, auth_headers, patient, make_case) -> None:
    """The audit trail must not record changes that did not happen."""
    case = make_case(patient)
    client.patch(
        f"/api/v1/cases/{case.id}/status",
        json={"status": "completed"},
        headers=auth_headers(patient),
    )
    events = client.get(f"/api/v1/cases/{case.id}/events", headers=auth_headers(patient)).json()
    assert [event["event_type"] for event in events] == ["case_created"]


def test_role_is_read_from_the_database_not_the_token(
    client, auth_headers, patient, make_case, db
) -> None:
    """A token minted before a demotion must not keep its old powers."""
    from app.models.user import User

    headers = auth_headers(patient)
    db.get(User, patient.id).role = UserRole.COORDINATOR
    db.commit()

    # Now treated as a coordinator despite the token saying "patient".
    assert client.post(
        "/api/v1/cases",
        json={"procedure_code": "TKR-001", "target_countries": []},
        headers=headers,
    ).status_code == 403
