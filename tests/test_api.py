
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_invalid_employee_status():
    response = client.post(
        "/attendance/punch-in",
        json={
            "emp_code": "INVALID_EMPLOYEE",
            "status": "INVALID_STATUS"
        }
    )
    assert response.status_code in (400, 404, 422)


def test_invalid_correction_date():
    response = client.patch(
        "/attendance/EMP1001/invalid-date",
        json={
            "status": "WFH",
            "reason": "Testing invalid date"
        }
    )
    assert response.status_code in (404, 422)


def test_monthly_analytics_invalid_month():
    response = client.get(
        "/analytics/employees/EMP1001/monthly?month=invalid"
    )
    assert response.status_code == 422


def test_department_summary():
    response = client.get("/analytics/departments/summary")
    assert response.status_code == 200
    assert "departments" in response.json()



def test_late_leaderboard():
    response = client.get(
        "/analytics/leaderboard/late?month=2026-10"
    )
    assert response.status_code == 200
