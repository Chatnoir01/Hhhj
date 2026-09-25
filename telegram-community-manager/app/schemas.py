from pydantic import BaseModel, Field


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_group: str = Field(min_length=1, max_length=255)


class UsernameImport(BaseModel):
    usernames: list[str] = Field(default_factory=list, max_length=10000)


class CampaignRunRequest(BaseModel):
    live: bool = False
    limit: int = Field(default=25, ge=1, le=100)


class LiveActivationRequest(BaseModel):
    confirmation: str


class CampaignActionResult(BaseModel):
    ok: bool
    detail: str | None = None
