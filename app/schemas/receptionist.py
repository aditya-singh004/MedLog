from datetime import datetime

from pydantic import BaseModel, model_validator


class ScheduleRequest(BaseModel):
    doctor_id: str
    scheduled_start_time: datetime
    scheduled_end_time: datetime

    @model_validator(mode="after")
    def validate_times(self):
        if self.scheduled_end_time <= self.scheduled_start_time:
            raise ValueError("End time must be after start time")
        return self


class CancelRequest(BaseModel):
    reason: str
