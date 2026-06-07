from uuid import UUID

from pydantic import BaseModel, EmailStr


class ProPaymentCreateRequest(BaseModel):
    offer_version_id: UUID
    customer_email: EmailStr | None = None
