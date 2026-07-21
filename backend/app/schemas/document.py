from datetime import datetime
from pydantic import BaseModel

class DocumentOut(BaseModel):
    id: int
    filename: str
    file_type: str
    page_count: int
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}