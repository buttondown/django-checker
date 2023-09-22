from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.http.request import HttpRequest
from django.shortcuts import render

from checker.models import CheckerRun


@staff_member_required
def view(request: HttpRequest, checker_name: str, run_id: str) -> HttpResponse:
    run = CheckerRun.objects.get(id=run_id)
    failure = run.failures.all()[0]
    if not failure.data:
        keys = []
    else:
        keys = failure.data.keys()
    return render(
        request,
        "checkers/run_detail.html",
        {"run": run, "checker": run.checker, "keys": keys},
    )
