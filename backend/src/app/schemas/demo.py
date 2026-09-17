from pydantic import BaseModel


class DemoUserOut(BaseModel):
    """Presentation-safe only. No groups, org id, ACLs, or hidden-resource
    counts — see app/routers/dev_identities.py.
    """

    id: int
    name: str
    email: str
    label: str | None
