from typing import Self

from fastapi import APIRouter

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.onboarding.handlers import OnboardingStatus, OnboardingStep

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"], responses=ERROR_RESPONSES)


class OnboardingStepResponse(ApiModel):
    key: OnboardingStep
    done: bool


class OnboardingResponse(ApiModel):
    steps: list[OnboardingStepResponse]
    """In the order they are shown."""
    dismissed: bool
    complete: bool

    @classmethod
    def of(cls, status: OnboardingStatus) -> Self:
        return cls(
            steps=[OnboardingStepResponse(key=key, done=done) for key, done in status.steps],
            dismissed=status.dismissed,
            complete=status.complete,
        )


@router.get("")
def get_onboarding(_user: CurrentUser, container: ContainerDep) -> OnboardingResponse:
    return OnboardingResponse.of(container.onboarding.status())


@router.post("/numbering-checked")
def check_numbering(_user: CurrentUser, container: ContainerDep) -> OnboardingResponse:
    """Mark the number sequences as checked; the step counts as done."""
    return OnboardingResponse.of(container.onboarding.check_numbering())


@router.post("/dismiss")
def dismiss(_user: CurrentUser, container: ContainerDep) -> OnboardingResponse:
    """Hide the checklist for good."""
    return OnboardingResponse.of(container.onboarding.dismiss())


@router.post("/show")
def show(_user: CurrentUser, container: ContainerDep) -> OnboardingResponse:
    """Show the hidden checklist again."""
    return OnboardingResponse.of(container.onboarding.show())
