"""Sign-in for the two human audiences.

Deliberately two doors, not one with a role flag. A buyer and a seller have
opposed interests: the buyer sets the spending boundary, the merchant wants
sales inside it. Neither should be able to reach the other's console, and the
cleanest way to guarantee that is for their sessions to be different kinds of
thing that the dependencies refuse to interchange.
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentMerchant, CurrentUser, DbSession
from app.auth import hash_password, issue_session, verify_password
from app.models import Merchant, User
from app.schemas.api import (
    LoginIn,
    MerchantOut,
    MerchantSelf,
    MerchantSession,
    UserOut,
    UserSession,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_BAD_CREDENTIALS = "Email or password is incorrect."


@router.post("/login", response_model=UserSession)
def user_login(payload: LoginIn, db: DbSession):
    """Buyer sign-in: the person who sets policies and approves purchases."""
    user = db.scalars(
        select(User).where(User.email == payload.email.strip().lower())
    ).first()

    # Same message and same work whether the account is missing or the
    # password is wrong, so this cannot be used to enumerate accounts.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS
        )

    return UserSession(
        token=issue_session(user.id, "user"),
        user=UserOut.model_validate(user),
    )


@router.post("/merchant/login", response_model=MerchantSession)
def merchant_login(payload: LoginIn, db: DbSession):
    """Seller sign-in: the merchant console, catalog and revenue."""
    merchant = db.scalars(
        select(Merchant).where(Merchant.email == payload.email.strip().lower())
    ).first()

    if merchant is None or not verify_password(payload.password, merchant.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_BAD_CREDENTIALS
        )
    if merchant.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"This merchant account is {merchant.status.lower()}.",
        )

    return MerchantSession(
        token=issue_session(merchant.id, "merchant"),
        merchant=MerchantSelf.model_validate(merchant),
    )


@router.get("/me", response_model=UserOut)
def whoami(user: CurrentUser):
    """Who the current buyer session belongs to."""
    return UserOut.model_validate(user)


@router.get("/merchant/me", response_model=MerchantOut)
def merchant_whoami(merchant: CurrentMerchant):
    """Who the current merchant session belongs to."""
    return MerchantOut.model_validate(merchant)


def set_password(subject, raw: str) -> None:
    """Helper for the seed script and future account management."""
    subject.password_hash = hash_password(raw)
