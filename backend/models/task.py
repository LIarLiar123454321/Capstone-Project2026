from pydantic import BaseModel, Field
from typing import Optional

class Task(BaseModel):
    name: str = Field(description="任務名稱")

    category: str = Field(
        description="任務類型，例如 study、work、exercise、travel"
    )

    location: Optional[str]= Field(
        default=None,
        description="活動地點"
    )

    duration_minutes: int = Field(
        gt=0,
        description="任務預計花費時間（分鐘）"
    )

    date: Optional[str] = Field(
        default=None,
        description="預定日期"
    )

    time_preference: Optional[str] = Field(
        default=None,
        description="偏好時段，例如 morning、afternoon、evening"
    )

    priority: str = Field(
        default="normal",
        description="優先程度：low、normal、high"
    )

    deadline: Optional[str] = Field(
        default=None,
        description="最晚完成時間"
    )

class ParsedRequest(BaseModel):
    tasks: list[Task] = Field(
        default_factory=list,
        description="從使用者需求中解析出的任務列表"
    )

    missing_information: list[str] = Field(
        default_factory=list,
        description="目前還缺少的必要資訊"
    )

    clarification_needed: bool = Field(
        default=False,
        description="是否需要向使用者詢問更多資訊"
    )
