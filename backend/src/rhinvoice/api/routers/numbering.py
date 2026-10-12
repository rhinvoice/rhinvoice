from typing import Self

from fastapi import APIRouter
from pydantic import Field

from rhinvoice.api.dependencies import ContainerDep, CurrentUser
from rhinvoice.api.schemas import ERROR_RESPONSES, ApiModel
from rhinvoice.application.numbering.handlers import ConfigureSequence, SequenceView
from rhinvoice.domain.numbering.sequence import MAX_COUNTER, MAX_PATTERN_LENGTH, SequenceKind

router = APIRouter(prefix="/api/number-sequences", tags=["numbering"], responses=ERROR_RESPONSES)


class SequenceRequest(ApiModel):
    pattern: str = Field(min_length=1, max_length=MAX_PATTERN_LENGTH)
    start_value: int = Field(ge=1, lt=MAX_COUNTER)
    yearly_reset: bool
    next_value: int = Field(ge=1, lt=MAX_COUNTER)

    def to_command(self, kind: SequenceKind) -> ConfigureSequence:
        return ConfigureSequence(
            kind=kind,
            pattern=self.pattern,
            start_value=self.start_value,
            yearly_reset=self.yearly_reset,
            next_value=self.next_value,
        )


class SequenceResponse(ApiModel):
    kind: SequenceKind
    pattern: str
    start_value: int
    yearly_reset: bool
    next_value: int
    """Effective counter of the next number (after a possible yearly reset)."""
    next_number: str

    @classmethod
    def of(cls, view: SequenceView) -> Self:
        return cls(
            kind=view.sequence.kind,
            pattern=view.sequence.pattern,
            start_value=view.sequence.start_value,
            yearly_reset=view.sequence.yearly_reset,
            next_value=view.next_counter,
            next_number=view.next_number,
        )


class PreviewResponse(ApiModel):
    next_number: str


@router.get("")
def list_sequences(_user: CurrentUser, container: ContainerDep) -> list[SequenceResponse]:
    return [SequenceResponse.of(view) for view in container.numbering.list()]


@router.put("/{kind}")
def configure_sequence(
    kind: SequenceKind,
    body: SequenceRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> SequenceResponse:
    return SequenceResponse.of(container.numbering.configure(body.to_command(kind)))


@router.post("/{kind}/preview")
def preview_sequence(
    kind: SequenceKind,
    body: SequenceRequest,
    _user: CurrentUser,
    container: ContainerDep,
) -> PreviewResponse:
    """Next number for an unsaved configuration (live preview in the settings)."""
    return PreviewResponse(next_number=container.numbering.preview(body.to_command(kind)))
