# REVIEW.md

List every defect you found in the starter `app/main.py` (helpers and endpoints). For each one:

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | | | | |

Also note anything you looked at and decided was **not** a defect, and why.
# REVIEW.md

## Defects Found in the Starter `app/main.py`

The starter implementation was reviewed for correctness, edge cases, concurrency, performance, and compliance with the attendance API requirements.

| # | Where (function / line) | What is wrong | How you'd notice it (test, input, or symptom) | How you fixed it |
|---|---|---|---|---|
| 1 | `/health` | Reports the service as healthy without verifying MongoDB connectivity. | Stop MongoDB or simulate a database ping failure. The endpoint may incorrectly return HTTP 200. | Added a MongoDB ping and return an unhealthy response with HTTP 503 when the database is unavailable. |
| 2 | `list_employees` — pagination | Calculates the pagination offset incorrectly using the page number multiplied by the page size. | With a page size of 10, page 1 can skip the first 10 records instead of returning the first page. | Corrected the offset to `(page - 1) * page_size`. |
| 3 | `list_employees` — total count | Counts employees without applying the same filters used for the returned records. | Filter by department or search term and compare `total` with the number of matching employees. | Applied the same MongoDB query filter to `count_documents()`. |
| 4 | `list_employees` — sorting | Does not guarantee the required ascending `emp_code` order. | Insert employees in a different order and request the list repeatedly. The result may not follow the required order. | Added an explicit ascending sort on `emp_code`. |
| 5 | Punch-in endpoint | Does not reliably handle attendance dates and timestamps in the required IST timezone. | Submit timestamps with different UTC offsets around midnight and compare the resulting attendance date. | Normalized timestamps to IST and derived the attendance date consistently. |
| 6 | Punch-in endpoint — input validation | Invalid or malformed timestamps may be handled incorrectly if they are not validated before processing. | Submit malformed timestamps, missing values, or timestamps with unexpected timezone information. | Added timestamp validation and consistent timezone normalization before saving attendance. |
| 7 | Punch-in endpoint — concurrency | Checking for an existing attendance record before inserting is not sufficient to prevent simultaneous duplicate requests. | Send two punch-in requests concurrently for the same employee and date. Both requests could otherwise create records. | Added a unique compound index on `(emp_code, date)` and handled duplicate-key errors as conflicts. |
| 8 | Attendance listing endpoint | Loading all matching attendance records into application memory before filtering or paginating does not scale. | Test with a large attendance collection and observe memory usage and response latency. | Applied filtering, sorting, pagination, and counting in MongoDB instead of loading the entire result set into Python. |
| 9 | Attendance correction endpoint | Manual corrections require an audit trail; changing attendance without retaining the previous values and reason makes changes difficult to trace. | Correct an employee's punch time and inspect the stored record and correction history. | Recorded the correction reason, previous values, updated values, and correction timestamp. |
| 10 | Attendance correction endpoint | Changing punch times without recalculating dependent attendance fields can leave inconsistent records. | Correct punch-in or punch-out and compare work hours, lateness, overtime, and half-day status with the updated times. | Recalculated dependent fields after a valid correction when both punch times were available. |
| 11 | Monthly employee analytics | Monthly analytics must use the requested month and employee filter consistently; incorrect date boundaries can include records from another month or omit valid records. | Test month boundaries, including the first and last day, and compare the response with the employee's attendance records. | Used validated month input and a consistent date range for the selected employee and month. |
| 12 | Department summary analytics | Department-level metrics can be misleading if eligible employees without attendance records are omitted from the denominator. | Add an eligible employee with no attendance record and compare the department totals and averages. | Built the aggregation to account for eligible employees without attendance, where required by the metric definitions. |
| 13 | Late-arrival leaderboard | Ties must be ranked consistently, and the requested month must be applied to the results. | Give multiple employees the same late-arrival total and check ranking around the result limit. | Applied month filtering and competition ranking so tied employees receive the same rank. |
| 14 | Department trend analytics | A daily trend may omit dates with no attendance records, resulting in gaps in the calendar series. | Query a date range containing days without attendance and inspect the returned dates. | Generated the complete daily date series and calculated the required moving average in the database aggregation. |
| 15 | `/admin/explain/{endpoint}` | Query-plan output may contain BSON-specific values that are not directly JSON serializable. | Request an explain plan and check whether serialization fails when the response contains BSON objects. | Serialized the explain output using `bson.json_util` so BSON values can be returned safely. |

## Items Examined and Not Considered Defects

1. **Late-arrival grace period:** The 10-minute grace period is an intentional business rule, not a defect by itself. Lateness should be calculated according to that rule.
2. **Overtime threshold:** The 30-minute minimum overtime threshold is intentional if it matches the assignment's requirements.
3. **Work-hour precision:** Returning work hours rounded to two decimal places is appropriate when the API specifies that precision.
4. **Duplicate attendance prevention:** A unique `(emp_code, date)` index is an appropriate database-level safeguard; an application-level existence check alone is not sufficient for concurrent requests.
5. **Environment configuration:** Reading MongoDB settings from environment variables and loading a local `.env` file for development is acceptable, provided real credentials are not committed to version control.
6. **Database indexes:** Indexes on fields used for frequent filters and lookups are appropriate performance optimizations, not defects.

## Verification

The implemented API was checked with automated tests using `pytest`. The test suite covered health status, invalid attendance input, invalid correction dates, invalid monthly analytics input, department summaries, and the late-arrival leaderboard.

The test suite should be rerun after the final changes. Passing these tests does not, by itself, prove every edge case in this review has been covered.
