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


class SetupRequest(BaseModel):
    admin_password: str = Field(min_length=12, max_length=256)
    telegram_api_id: int = Field(gt=0)
    telegram_api_hash: str = Field(min_length=16, max_length=256)
    telegram_phone: str = Field(min_length=5, max_length=32)
    telegram_bot_token: str | None = Field(default=None, max_length=256)


class LoginRequest(BaseModel):
    admin_password: str = Field(min_length=1, max_length=256)


class TelegramCodeRequest(BaseModel):
    code: str = Field(min_length=3, max_length=16)


class TelegramPasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class TelegramGroupCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    about: str = Field(default="", max_length=255)
    username: str | None = Field(default=None, min_length=5, max_length=32)
