from uuid import UUID

from pydantic import BaseModel


class ProPaymentCreateRequest(BaseModel):
    offer_version_id: UUID
