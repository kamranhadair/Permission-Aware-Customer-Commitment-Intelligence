from pydantic import BaseModel


class AccountOut(BaseModel):
    id: str
    name: str
