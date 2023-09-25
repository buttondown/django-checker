from dataclasses import dataclass

from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import render
from django.utils import timezone

from checker.models import Checker, CheckerRun


@dataclass
class CheckerStats:
    average_runtime: float  # in seconds
    success_rate: float
    age_in_days: int


def calculate_average_runtime(checker: Checker) -> float:
    runs = list(checker.runs.exclude(status=CheckerRun.Status.IN_PROGRESS))
    return sum(
        [
            (run.completion_date - run.creation_date).seconds
            for run in runs
            if run.completion_date
        ]
    ) / len(runs)


def calculate_success_rate(checker: Checker) -> float:
    runs = list(checker.runs.exclude(status=CheckerRun.Status.IN_PROGRESS))
    return (
        len([run for run in runs if run.status == CheckerRun.Status.SUCCEEDED])
        / len(runs)
    ) * 100


@staff_member_required
def view(request: HttpRequest, checker_name: str) -> HttpResponse:
    checker = Checker.objects.get(name=checker_name)
    runs = checker.runs.order_by("-creation_date")[:50]
    return render(
        request,
        "checkers/checker_detail.html",
        {
            "checker": checker,
            "runs": runs,
            "stats": CheckerStats(
                calculate_average_runtime(checker),
                calculate_success_rate(checker),
                (timezone.now() - checker.creation_date).days,
            ),
        },
    )
