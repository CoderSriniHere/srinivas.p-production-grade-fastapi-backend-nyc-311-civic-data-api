from pydantic import BaseModel, EmailStr, Field


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    agency_code: str = Field(max_length=10)
    # No role field here on purpose -- self-registration always lands as
    # "staff". Promoting someone to analyst/admin is an admin-only action,
    # see UserRoleUpdate + PATCH /auth/users/{user_id}/role.


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiKeyCreate(BaseModel):
    scopes: list[str]
    expires_in_days: int | None = 90


class UserRoleUpdate(BaseModel):
    role: str = Field(pattern="^(staff|analyst|admin)$")