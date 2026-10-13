"""
Employee Attendance & Analytics API - STARTER

Run:  uvicorn app.main:app --port 8000
Env:  MONGO_URI, MONGO_DB (a local .env is loaded for convenience)

This file was written quickly by a colleague who has left the company. The happy path
works, but nobody has reviewed it. Read PROBLEM_STATEMENT.docx for what is expected of you,
openapi.yaml for the contract and DATA_MODEL.md for what is stored in MongoDB.
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from decimal import Decimal, ROUND_HALF_UP
from bson.json_util import dumps, loads, RELAXED_JSON_OPTIONS
from fastapi.responses import JSONResponse
from fastapi.responses import Response

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI", "mongodb://localhost:27017"))
db = client[os.getenv("MONGO_DB", "attendance_db")]

IST = timezone(timedelta(hours=5, minutes=30))

app = FastAPI(title="Employee Attendance & Analytics API", version="2.0.0")
@app.on_event("startup")
def create_indexes():
    db.employees.create_index("emp_code", unique=True)
    db.attendance_logs.create_index(
        [("emp_code", 1), ("date", 1)],
        unique=True
    )

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def compute_late_minutes(punch_in: datetime, shift_start: str) -> int:
    h, m = map(int, shift_start.split(":"))

    start = punch_in.replace(
        hour=h,
        minute=m,
        second=0,
        microsecond=0
    )

    # Handle shifts that start the previous evening.
    if punch_in < start:
        start -= timedelta(days=1)

    minutes = int((punch_in - start).total_seconds() // 60)

    # First 10 minutes are the grace period.
    return max(0, minutes - 10)


def compute_work_hours(punch_in: datetime, punch_out: datetime) -> float:
    seconds = int((punch_out - punch_in).total_seconds())
    hours = Decimal(seconds) / Decimal(3600)
    return float(hours.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))



def compute_overtime(
    punch_out: datetime,
    shift_start: str,
    shift_end: str,
    date_str: str
) -> int:
    start_h, start_m = map(int, shift_start.split(":"))
    end_h, end_m = map(int, shift_end.split(":"))

    shift_end_date = datetime.fromisoformat(date_str).date()

    # If the shift ends at or before its start time, it ends the next day.
    if (end_h, end_m) <= (start_h, start_m):
        shift_end_date += timedelta(days=1)

    end = datetime.combine(
        shift_end_date,
        datetime.min.time()
    ).replace(
        hour=end_h,
        minute=end_m,
        tzinfo=IST
    )

    minutes = int((punch_out - end).total_seconds() // 60)

    return minutes if minutes >= 30 else 0


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
class EmployeeIn(BaseModel):
    emp_code: str
    name: str
    email: str
    department: str
    shift_start: str = "09:30"
    shift_end: str = "18:30"
    joined_on: str


class PunchInIn(BaseModel):
    emp_code: str
    punched_at: Optional[int] = None
    status: str = "PRESENT"
class AttendanceCorrectionIn(BaseModel):
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    status: Optional[str] = None
    reason: str



# --------------------------------------------------------------------------- #
# Endpoints provided
# --------------------------------------------------------------------------- #
@app.get("/health")
def health():
    try:
        db.command("ping")
        return {"status": "ok"}
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="MongoDB unavailable"
        )
@app.post("/employees", status_code=201)
def create_employee(body: EmployeeIn):
    if db.employees.find_one({"emp_code": body.emp_code}):
        raise HTTPException(409, "emp_code already exists")

    doc = body.model_dump()
    doc["created_at"] = datetime.now()

    try:
        db.employees.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(409, "emp_code already exists")

    doc.pop("_id", None)
    return doc
@app.get("/employees")
def list_employees(
    department: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(422, "Invalid pagination parameters")
    q = {}
    if department:
        q["department"] = department
    skip = (page - 1) * page_size
    total = db.employees.count_documents(q)
    items = list(db.employees.find(q, {"_id": 0}).skip(skip).limit(page_size))
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.post("/attendance/punch-in", status_code=201)
def punch_in(body: PunchInIn):
    emp = db.employees.find_one({"emp_code": body.emp_code})

    if not emp:
        raise HTTPException(404, "Employee not found")
    if body.status not in {"PRESENT", "WFH", "ON_DUTY"}:
        raise HTTPException(422, "Invalid attendance status")

    ts = (
        datetime.fromtimestamp(body.punched_at / 1000, tz=IST)
        if body.punched_at is not None
        else datetime.now(IST)
    )

    ts = ts.replace(microsecond=0)

    shift_start = datetime.strptime(emp["shift_start"], "%H:%M").time()
    shift_end = datetime.strptime(emp["shift_end"], "%H:%M").time()

    if shift_end <= shift_start and ts.time() < shift_end:
        d = (ts.date() - timedelta(days=1)).isoformat()
    else:
        d = ts.date().isoformat()

    if db.attendance_logs.find_one({"emp_code": body.emp_code, "date": d}):
        raise HTTPException(409, "already punched in for this date")


    doc = {
        "emp_code": body.emp_code,
        "date": d,
        "status": body.status,
        "punch_in": ts,
        "punch_out": None,
        "work_hours": None,
        "late_minutes": compute_late_minutes(ts, emp["shift_start"]),
        "overtime_minutes": 0,
        "half_day": False,
        "history": [],
    }
    try:
        res = db.attendance_logs.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="already punched in for this date"
        )
    doc.pop("_id", None)
    return doc
@app.post("/attendance/punch-out")
def punch_out(emp_code: str):
    today = datetime.now(IST).strftime("%Y-%m-%d")

    record = db.attendance_logs.find_one({
        "emp_code": emp_code,
        "date": today
    })

    if not record:
        raise HTTPException(404, "No punch-in record found for today")

    if record.get("punch_out"):
        raise HTTPException(409, "Already punched out")

    punch_out_time = datetime.now(IST).replace(microsecond=0)

    punch_in_time = record["punch_in"]

    if isinstance(punch_in_time, str):
        punch_in_time = datetime.fromisoformat(punch_in_time)

    if punch_in_time.tzinfo is None:
        punch_in_time = punch_in_time.replace(tzinfo=IST)

    # Calculate work hours using the existing helper
    work_hours = compute_work_hours(
        punch_in_time,
        punch_out_time
    )

    # Calculate overtime using the employee's shift end
    emp = db.employees.find_one({"emp_code": emp_code})

    overtime_minutes = compute_overtime(
    punch_out_time,
    emp["shift_start"],
    emp["shift_end"],
    record["date"])
# Mark half-day when work hours are below 4.5
    half_day = work_hours < 4.5

    db.attendance_logs.update_one(
        {"_id": record["_id"]},
        {"$set": {
            "punch_out": punch_out_time,
            "work_hours": work_hours,
            "overtime_minutes": overtime_minutes,
            "half_day": half_day
        }}
    )

    return {
        "message": "Punch-out successful",
        "emp_code": emp_code,
        "punch_out": punch_out_time.isoformat(),
        "work_hours": work_hours,
        "overtime_minutes": overtime_minutes,
        "half_day": half_day
    }


@app.patch("/attendance/{emp_code}/{date}")
def correct_attendance(
    emp_code: str,
    date: str,
    body: AttendanceCorrectionIn
):
    record = db.attendance_logs.find_one({
        "emp_code": emp_code,
        "date": date
    })

    if not record:
        raise HTTPException(404, "Attendance record not found")

    if not body.reason.strip():
        raise HTTPException(422, "Correction reason is required")

    try:
        attendance_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(422, "Date must use YYYY-MM-DD format")

    updates = {}

    def normalize_time(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=IST)
        return value.astimezone(IST)

    if body.punch_in is not None:
        updates["punch_in"] = normalize_time(body.punch_in)

    if body.punch_out is not None:
        updates["punch_out"] = normalize_time(body.punch_out)

    if body.status is not None:
        if body.status not in {"PRESENT", "WFH", "ON_DUTY", "ABSENT"}:
            raise HTTPException(422, "Invalid attendance status")
        updates["status"] = body.status

    if not updates:
        raise HTTPException(422, "No correction fields provided")

    # Use the corrected times, or existing times if unchanged.
    punch_in = updates.get("punch_in", record.get("punch_in"))
    punch_out = updates.get("punch_out", record.get("punch_out"))

    if isinstance(punch_in, str):
        punch_in = normalize_time(datetime.fromisoformat(punch_in))

    if isinstance(punch_out, str):
        punch_out = normalize_time(datetime.fromisoformat(punch_out))

    if punch_in is not None and punch_out is not None:
        punch_in = normalize_time(punch_in)
        punch_out = normalize_time(punch_out)

        if punch_out <= punch_in:
            raise HTTPException(
                422,
                "Punch-out must be later than punch-in"
            )

        emp = db.employees.find_one({"emp_code": emp_code})

        if not emp:
            raise HTTPException(404, "Employee not found")

        work_hours = compute_work_hours(punch_in, punch_out)

        start_h, start_m = map(int, emp["shift_start"].split(":"))
        end_h, end_m = map(int, emp["shift_end"].split(":"))

        shift_start_dt = datetime.combine(
            attendance_date,
            datetime.min.time()
        ).replace(
            hour=start_h,
            minute=start_m,
            tzinfo=IST
        )

        if (end_h, end_m) <= (start_h, start_m):
            shift_end_date = attendance_date + timedelta(days=1)
        else:
            shift_end_date = attendance_date

        shift_end_dt = datetime.combine(
            shift_end_date,
            datetime.min.time()
        ).replace(
            hour=end_h,
            minute=end_m,
            tzinfo=IST
        )

        late_minutes = max(
            0,
            int((punch_in - shift_start_dt).total_seconds() // 60) - 10
        )

        overtime_raw = int(
            (punch_out - shift_end_dt).total_seconds() // 60
        )
        overtime_minutes = overtime_raw if overtime_raw >= 30 else 0

        updates["work_hours"] = work_hours
        updates["late_minutes"] = late_minutes
        updates["overtime_minutes"] = overtime_minutes
        updates["half_day"] = work_hours < 4.5

    history_entry = {
        "reason": body.reason.strip(),
        "corrected_at": datetime.now(IST),
        "changes": {
            key: {
                "old": str(record.get(key)),
                "new": str(value)
            }
            for key, value in updates.items()
        }
    }

    db.attendance_logs.update_one(
        {"_id": record["_id"]},
        {
            "$set": updates,
            "$push": {"history": history_entry}
        }
    )

    return {
        "message": "Attendance corrected successfully",
        "emp_code": emp_code,
        "date": date,
        "changes": history_entry["changes"]
    }
@app.get("/analytics/employees/{emp_code}/monthly")
def monthly_analytics(emp_code: str, month: str):
    try:
        start_date = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            422,
            "Invalid month format. Use YYYY-MM, for example 2026-10"
        )

    next_month = (
        start_date.replace(day=28) + timedelta(days=4)
    ).replace(day=1)

    employee = db.employees.find_one(
        {"emp_code": emp_code},
        {"_id": 0}
    )

    if not employee:
        raise HTTPException(404, "Employee not found")

    pipeline = [
        {
            "$match": {
                "emp_code": emp_code,
                "date": {
                    "$gte": start_date.strftime("%Y-%m-%d"),
                    "$lt": next_month.strftime("%Y-%m-%d")
                }
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "attendance_days": {"$sum": 1},
                "total_work_hours": {
                    "$sum": {"$ifNull": ["$work_hours", 0]}
                },
                "late_days": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0
                        ]
                    }
                },
                "half_days": {
                    "$sum": {
                        "$cond": ["$half_day", 1, 0]
                    }
                }
            }
        }
    ]

    result = list(db.attendance_logs.aggregate(pipeline))

    summary = result[0] if result else {
        "attendance_days": 0,
        "total_work_hours": 0,
        "late_days": 0,
        "half_days": 0
    }

    summary.pop("_id", None)

    return {
        "emp_code": emp_code,
        "name": employee["name"],
        "department": employee["department"],
        "month": month,
        **summary
    }


@app.get("/analytics/departments/summary")
def department_summary():
    pipeline = [
        {
            "$group": {
                "_id": "$department",
                "employee_count": {"$addToSet": "$emp_code"},
                "attendance_records": {"$sum": 1},
                "total_work_hours": {
                    "$sum": {"$ifNull": ["$work_hours", 0]}
                },
                "late_days": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {
            "$project": {
                "_id": 0,
                "department": "$_id",
                "employee_count": {"$size": "$employee_count"},
                "attendance_records": 1,
                "total_work_hours": 1,
                "late_days": 1
            }
        },
        {"$sort": {"department": 1}}
    ]

    # Join each attendance record with its employee's department
    pipeline = [
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$set": {
                "department": "$employee.department"
            }
        }
    ] + pipeline

    results = list(db.attendance_logs.aggregate(pipeline))

    return {"departments": results}

@app.get("/analytics/leaderboard/late")
def late_arrival_leaderboard(month: str):
    try:
        start_date = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            422,
            "Invalid month format. Use YYYY-MM"
        )

    next_month = (
        start_date.replace(day=28) + timedelta(days=4)
    ).replace(day=1)

    pipeline = [
        {
            "$match": {
                "date": {
                    "$gte": start_date.strftime("%Y-%m-%d"),
                    "$lt": next_month.strftime("%Y-%m-%d")
                },
                "late_minutes": {"$gt": 0}
            }
        },
        {
            "$group": {
                "_id": "$emp_code",
                "late_days": {"$sum": 1},
                "total_late_minutes": {"$sum": "$late_minutes"}
            }
        },
        {
            "$lookup": {
                "from": "employees",
                "localField": "_id",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$project": {
                "_id": 0,
                "emp_code": "$_id",
                "name": "$employee.name",
                "department": "$employee.department",
                "late_days": 1,
                "total_late_minutes": 1
            }
        },
        {"$sort": {"total_late_minutes": -1}},
        {"$limit": 10}
    ]

    results = list(db.attendance_logs.aggregate(pipeline))

    return {
        "month": month,
        "leaderboard": results
    }

@app.get("/analytics/departments/{department}/trend")
def department_trend(department: str, month: str):
    try:
        start_date = datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(
            422,
            "Invalid month format. Use YYYY-MM"
        )

    next_month = (
        start_date.replace(day=28) + timedelta(days=4)
    ).replace(day=1)

    pipeline = [
        {
            "$lookup": {
                "from": "employees",
                "localField": "emp_code",
                "foreignField": "emp_code",
                "as": "employee"
            }
        },
        {"$unwind": "$employee"},
        {
            "$match": {
                "employee.department": {
                    "$regex": f"^{department}$",
                    "$options": "i"
                },
                "date": {
                    "$gte": start_date.strftime("%Y-%m-%d"),
                    "$lt": next_month.strftime("%Y-%m-%d")
                }
            }
        },
        {
            "$group": {
                "_id": "$date",
                "attendance_records": {"$sum": 1},
                "total_work_hours": {
                    "$sum": {"$ifNull": ["$work_hours", 0]}
                },
                "late_days": {
                    "$sum": {
                        "$cond": [
                            {"$gt": ["$late_minutes", 0]},
                            1,
                            0
                        ]
                    }
                }
            }
        },
        {"$sort": {"_id": 1}},
        {
            "$project": {
                "_id": 0,
                "date": "$_id",
                "attendance_records": 1,
                "total_work_hours": 1,
                "late_days": 1
            }
        }
    ]

    results = list(db.attendance_logs.aggregate(pipeline))

    return {
        "department": department,
        "month": month,
        "trend": results
    }

@app.get("/admin/explain/{endpoint}")
def explain_endpoint(endpoint: str):
    if endpoint == "attendance":
        explanation = db.command({
            "explain": {
                "find": "attendance_logs",
                "filter": {"emp_code": "EMP1001"}
            },
            "verbosity": "executionStats"
        })

    elif endpoint == "monthly":
        explanation = db.command({
            "explain": {
                "aggregate": "attendance_logs",
                "pipeline": [
                    {"$match": {"emp_code": "EMP1001"}},
                    {"$group": {
                        "_id": "$emp_code",
                        "total_hours": {
                            "$sum": {"$ifNull": ["$work_hours", 0]}
                        }
                    }}
                ],
                "cursor": {}
            },
            "verbosity": "executionStats"
        })

    else:
        raise HTTPException(
            404,
            "Unsupported endpoint. Use attendance or monthly"
        )
    return Response(
    content=dumps(explanation, json_options=RELAXED_JSON_OPTIONS),
    media_type="application/json"
)

@app.get("/attendance")
def list_attendance(
    emp_code: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination parameters")

    q = {}

    if emp_code:
        q["emp_code"] = emp_code

    if date_from or date_to:
        q["date"] = {}

        if date_from:
            q["date"]["$gte"] = date_from

        if date_to:
            q["date"]["$lte"] = date_to

    if status:
        q["status"] = status

    total = db.attendance_logs.count_documents(q)

    page_docs = list(
        db.attendance_logs.find(q, {"_id": 0})
        .sort([("date", -1), ("emp_code", 1)])
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    return {
        "items": page_docs,
        "total": total,
        "page": page,
        "page_size": page_size,
    }




# --------------------------------------------------------------------------- #
# TODO - the rest of the contract (see openapi.yaml):
#   POST  /attendance/punch-out
#   PATCH /attendance/{emp_code}/{date}
#   GET   /analytics/employees/{emp_code}/monthly
#   GET   /analytics/departments/summary
#   GET   /analytics/leaderboard/late
#   GET   /analytics/departments/{department}/trend
#   GET   /admin/explain/{endpoint}
# --------------------------------------------------------------------------- #
