from dataclasses import dataclass
from typing import Iterable, List

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import render

from checker.models import Checker, CheckerFailure


@dataclass
class CheckerGroup:
    status: str
    checkers: List[Checker]


def fetch_current_failures() -> Iterable[CheckerFailure]:
    failing_checkers = Checker.objects.filter(status=Checker.Status.FAILING)
    for checker in failing_checkers:
        latest_run = checker.runs.latest("creation_date")
        for failure in latest_run.failures.all():
            yield failure


@staff_member_required
def view(request: HttpRequest) -> HttpResponse:
    checkers = Checker.objects.all()
    checker_to_status = {checker: checker.status for checker in checkers}
    checker_groups = sorted(
        [
            CheckerGroup(
                status,
                sorted(
                    [checker for checker in checkers if checker.status == status],
                    key=lambda checker: checker.latest_status_change
                    or checker.creation_date,
                    reverse=True,
                ),
            )
            for status in set(checker_to_status.values())
        ],
        key=lambda checker_group: ["failing", "errored", "ignored", "succeeding"].index(
            checker_group.status
        ),
    )
    current_failures = list(fetch_current_failures())
    return render(
        request,
        "checkers/checker_list.html",
        {"checker_groups": checker_groups, "current_failures": current_failures},
    )
