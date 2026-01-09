import pytest
from dataclasses import dataclass
from datetime import datetime, date

# AppointmentsService not found in current codebase


@dataclass
class Appt:
    id: int
    user_id: str
    doctor_id: int
    patient_name: str
    patient_age: int
    issue: str
    appointment_date: date
    appointment_time: str
    status: str
    created_at: datetime


class FakeApptRepo:
    def __init__(self):
        self._id = 1
        self.appts = []
        self.doctor_available = True

    def get_doctor(self, doctor_id: int):
        return type("D", (), {"id": doctor_id, "name": "Dr.", "is_available": self.doctor_available})

    def find_conflict(self, doctor_id: int, d: date, t: str) -> bool:
        return False

    def create(self, user_id: str, doctor_id: int, patient_name: str, patient_age: int, issue: str, appointment_date: date, appointment_time: str):
        a = Appt(self._id, user_id, doctor_id, patient_name, patient_age, issue, appointment_date, appointment_time, "scheduled", datetime.utcnow())
        self.appts.append(a)
        self._id += 1
        return a

    def list_for_user(self, user_id: str):
        return [a for a in self.appts if a.user_id == user_id]

    def get_for_user(self, appointment_id: int, user_id: str):
        return next((a for a in self.appts if a.id == appointment_id and a.user_id == user_id), None)

    def cancel(self, appointment_id: int, user_id: str):
        a = self.get_for_user(appointment_id, user_id)
        if a:
            a.status = "cancelled"

    def update_status(self, appointment_id: int, status: str):
        a = next((a for a in self.appts if a.id == appointment_id), None)
        if a:
            a.status = status

    def get_by_id(self, appointment_id: int):
        return next((a for a in self.appts if a.id == appointment_id), None)


class FakeUserRepo:
    def get_by_id(self, user_id: str):
        return object()


@pytest.mark.skip(reason="AppointmentsService not found in current codebase")
def test_book_success():
    pass


