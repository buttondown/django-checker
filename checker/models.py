from typing import Optional

import humanize  # type: ignore
from django.contrib.auth.models import User
from django.db import models
from django.db.models import JSONField

from .models import BaseModel, BaseTransition


class CheckerFailure(BaseModel):
    """
    Represents a deterministic failure of a checker run.
    """

    text = models.CharField(max_length=500)
    subtext = models.TextField(blank=True, default="")
    checker_run = models.ForeignKey(
        "CheckerRun",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="failures",
    )
    data = JSONField(null=True)

    class Meta:
        ordering = ("-creation_date",)

    def __str__(self) -> str:
        return f"{self.text} ({self.checker_run.checker.name if self.checker_run_id else 'unknown'})"


class CheckerRun(BaseModel):
    """
    Represents a run of a checker.
    """

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress"
        SUCCEEDED = "succeeded"
        FAILED = "failed"
        ERRORED = "errored"

    checker = models.ForeignKey(
        "Checker",
        null=False,
        blank=False,
        on_delete=models.CASCADE,
        related_name="runs",
    )
    completion_date = models.DateTimeField(blank=True, null=True)
    status = models.TextField(
        max_length=50, choices=Status.choices, default=Status.SUCCEEDED
    )
    data = JSONField(null=True)

    class Meta:
        ordering = ("-creation_date",)


class CheckerOverride(BaseModel):
    checker = models.ForeignKey(
        "Checker",
        on_delete=models.CASCADE,
        null=True,
        related_name="overrides",
    )
    apply_to_all_checkers = models.BooleanField(default=False)
    data = JSONField(null=True)
    note = models.CharField(max_length=500, blank=True, default="")
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checker_overrides",
    )

    class Meta:
        ordering = ("-creation_date",)


class Checker(BaseModel):
    """
    Represents a Checker and its status. These are dynamically created
    by `run_checker`.

    """

    section = models.TextField(max_length=50, blank=True)
    name = models.TextField(max_length=50, unique=True)
    description = models.TextField(max_length=5000, blank=True)
    user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="checkers",
    )

    class Cadence(models.TextChoices):
        EVERY_TEN_MINUTES = "every_ten_minutes"
        HOURLY = "hourly"
        DAILY = "daily"

    cadence = models.TextField(
        max_length=50, choices=Cadence.choices, default=Cadence.HOURLY
    )

    # Right now, severity correspond with "do we page or not". Severity is declared
    # when you register the checker, e.g.: `@register_checker(Checker.Severity.HIGH)`.
    class Severity(models.TextChoices):
        LOW = "low"
        HIGH = "high"

    severity = models.TextField(
        max_length=50, choices=Severity.choices, default=Severity.LOW
    )

    # It is not obvious why we have to declare the status of the checker independent of
    # just looking at the latest CheckerRun. The answer is twofold:
    # 1. We want to act on _changes_ in status, and doing so by looking at modifications
    #    to the Checker.status is slightly more graceful than having to always pull the
    #    second-to-latest CheckerRun.
    # 2. It makes ignoring failures (e.g. by setting the status to IGNORED) slightly more
    #    graceful.
    class Status(models.TextChoices):
        NEW = "new"
        IGNORED = "ignored"
        SUCCEEDING = "succeeding"
        FAILING = "failing"
        ERRORED = "errored"

    status = models.TextField(max_length=50, choices=Status.choices, default=Status.NEW)
    latest_status_change = models.DateTimeField(null=True)
    latest_run_date = models.DateTimeField(null=True)

    @property
    def human_readable_time_since_status_change(self) -> Optional[str]:
        if not self.latest_run_date or not self.latest_status_change:
            return None
        return humanize.naturaldelta(self.latest_run_date - self.latest_status_change)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class CheckerStatusTransition(BaseTransition):
    parent = BaseTransition.construct_parent(Checker)
    old_value = BaseTransition.construct_old_value(Checker.Status.choices)
    new_value = BaseTransition.construct_new_value(Checker.Status.choices)
