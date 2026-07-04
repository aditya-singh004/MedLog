from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    message: str


class NotificationOut(ORMModel):
    id: str
    title: str
    message: str
    status: str
    created_at: datetime
