"""Recurring invoice plans and their runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from rhinvoice.domain.recurring.plan import (
    Interval,
    PlanAction,
    PlanRun,
    RecurringPlan,
    RunOutcome,
)
from rhinvoice.infrastructure.db.serialization import template_from_json, template_to_json
from rhinvoice.infrastructure.db.tables import recurring_plans, recurring_runs

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import date
    from uuid import UUID

    from sqlalchemy import Connection, RowMapping


def _plan_from_row(row: RowMapping) -> RecurringPlan:
    return RecurringPlan(
        id=row["id"],
        name=row["name"],
        customer_id=row["customer_id"],
        interval=Interval(row["interval"]),
        start_date=row["start_date"],
        next_date=row["next_date"],
        end_date=row["end_date"],
        action=PlanAction(row["action"]),
        service_period=row["service_period"],
        active=row["active"],
        template=template_from_json(row["template"]),
        created_at=row["created_at"],
    )


def _plan_values(plan: RecurringPlan) -> dict[str, object]:
    return {
        "id": plan.id,
        "name": plan.name,
        "customer_id": plan.customer_id,
        "interval": plan.interval.value,
        "start_date": plan.start_date,
        "next_date": plan.next_date,
        "end_date": plan.end_date,
        "action": plan.action.value,
        "service_period": plan.service_period,
        "active": plan.active,
        "template": template_to_json(plan.template),
        "created_at": plan.created_at,
    }


def _run_from_row(row: RowMapping) -> PlanRun:
    return PlanRun(
        plan_id=row["plan_id"],
        period_start=row["period_start"],
        at=row["at"],
        outcome=RunOutcome(row["outcome"]),
        document_id=row["document_id"],
        code=row["code"],
        message=row["message"],
    )


class SqlRecurringRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def all(self) -> list[RecurringPlan]:
        statement = select(recurring_plans).order_by(recurring_plans.c.name, recurring_plans.c.id)
        return [_plan_from_row(row) for row in self._connection.execute(statement).mappings()]

    def get(self, plan_id: UUID, *, for_update: bool = False) -> RecurringPlan | None:
        statement = select(recurring_plans).where(recurring_plans.c.id == plan_id)
        if for_update:
            statement = statement.with_for_update()
        row = self._connection.execute(statement).mappings().first()
        return None if row is None else _plan_from_row(row)

    def add(self, plan: RecurringPlan) -> None:
        self._connection.execute(insert(recurring_plans).values(_plan_values(plan)))

    def update(self, plan: RecurringPlan) -> None:
        self._connection.execute(
            update(recurring_plans)
            .where(recurring_plans.c.id == plan.id)
            .values(_plan_values(plan))
        )

    def delete(self, plan_id: UUID) -> None:
        self._connection.execute(delete(recurring_plans).where(recurring_plans.c.id == plan_id))

    def due(self, today: date) -> list[UUID]:
        statement = (
            select(recurring_plans.c.id)
            .where(
                recurring_plans.c.active,
                recurring_plans.c.next_date <= today,
                (recurring_plans.c.end_date.is_(None))
                | (recurring_plans.c.next_date <= recurring_plans.c.end_date),
            )
            .order_by(recurring_plans.c.next_date, recurring_plans.c.id)
        )
        return list(self._connection.execute(statement).scalars())

    def claim(self, run: PlanRun) -> bool:
        statement = (
            pg_insert(recurring_runs)
            .values(_run_values(run))
            .on_conflict_do_nothing(constraint="uq_recurring_runs_plan_period")
            .returning(recurring_runs.c.id)
        )
        return self._connection.execute(statement).scalar_one_or_none() is not None

    def finish(self, run: PlanRun) -> None:
        values = _run_values(run)
        self._connection.execute(
            update(recurring_runs)
            .where(
                recurring_runs.c.plan_id == run.plan_id,
                recurring_runs.c.period_start == run.period_start,
            )
            .values(values)
        )

    def runs(self, plan_ids: Collection[UUID], *, limit: int) -> dict[UUID, list[PlanRun]]:
        if not plan_ids:
            return {}
        rank = (
            func.row_number()
            .over(
                partition_by=recurring_runs.c.plan_id,
                order_by=recurring_runs.c.period_start.desc(),
            )
            .label("rank")
        )
        ranked = (
            select(recurring_runs, rank).where(recurring_runs.c.plan_id.in_(plan_ids)).subquery()
        )
        statement = (
            select(ranked)
            .where(ranked.c.rank <= limit)
            .order_by(ranked.c.plan_id, ranked.c.period_start.desc())
        )
        found: dict[UUID, list[PlanRun]] = {}
        for row in self._connection.execute(statement).mappings():
            found.setdefault(row["plan_id"], []).append(_run_from_row(row))
        return found


def _run_values(run: PlanRun) -> dict[str, object]:
    return {
        "plan_id": run.plan_id,
        "period_start": run.period_start,
        "at": run.at,
        "outcome": run.outcome.value,
        "document_id": run.document_id,
        "code": run.code,
        "message": run.message[:500],
    }
