from pydantic import BaseModel

class CreateSessionRequest(BaseModel):
    title: str | None = None