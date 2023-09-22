from typing import Any, Iterable, List

import pytest
import requests
from django.core.mail.message import EmailMessage
from django.test import override_settings

from checker.models import Checker, CheckerFailure, CheckerOverride, CheckerRun
from checker.registry import REGISTERED_CHECKERS, RegisteredChecker
from checker.runner import run_checker, run_checkers


def test_autodiscovery_works_well() -> None:
    assert len(REGISTERED_CHECKERS) != 0


def succeeding_checker() -> None:
    pass


def succeeding_checker_as_generator() -> Iterable[str]:
    for _ in []:
        yield "foo"


def erroring_checker() -> Iterable[str]:
    raise Exception()


def failing_checker() -> Iterable[CheckerFailure]:
    yield CheckerFailure(text="Oh no!")


def failing_checker_with_data() -> Iterable[CheckerFailure]:
    yield CheckerFailure(text="Oh no!", data={"foo": "bar"})


def multiple_failing_checker() -> Iterable[CheckerFailure]:
    for _ in range(10):
        yield CheckerFailure(text="Oh no!")


def infinitely_failing_checker() -> Iterable[CheckerFailure]:
    while True:
        yield CheckerFailure(text="Oh no!")


CHECKER_NAME = "basic_checker"
CHECKER_SECTION = "checker"
REGISTERED_CHECKER = RegisteredChecker(
    CHECKER_NAME,
    CHECKER_SECTION,
    "",  # Description
    1,  # tries
    Checker.Severity.LOW,
    Checker.Cadence.HOURLY,
    failing_checker,
)


@pytest.fixture(autouse=True)
def no_requests(monkeypatch: Any) -> None:
    response = requests.Response()
    response.status_code = 200
    monkeypatch.setattr("requests.get", lambda _: response)


@override_settings(DISABLED_CHECKERS=[CHECKER_NAME])
@pytest.mark.django_db
def test_nacks_checker_if_individual_killswitch_is_active() -> None:
    run_checkers(Checker.Cadence.HOURLY)
    assert not Checker.objects.filter(name=CHECKER_NAME).exists()


@override_settings(DISABLE_CHECKERS=True)
@pytest.mark.django_db
def test_nacks_checker_if_killswitch_is_active() -> None:
    run_checkers(Checker.Cadence.HOURLY)
    assert not Checker.objects.filter(name=CHECKER_NAME).exists()


@pytest.mark.django_db
def test_creates_checker() -> None:
    run_checker(REGISTERED_CHECKER)
    assert Checker.objects.get(name=CHECKER_NAME) is not None


@pytest.mark.django_db
def test_updates_severity() -> None:
    run_checker(REGISTERED_CHECKER)
    checker = Checker.objects.get(name=CHECKER_NAME)
    assert checker.severity == Checker.Severity.LOW

    REGISTERED_CHECKER.severity = Checker.Severity.HIGH
    run_checker(REGISTERED_CHECKER)
    checker.refresh_from_db()
    assert checker.severity == Checker.Severity.HIGH


@pytest.mark.django_db
def test_honors_retry_if_latter_one_succeeds() -> None:
    attempt = 1

    def failure_then_success() -> Iterable[CheckerFailure]:
        nonlocal attempt
        if attempt == 1:
            yield CheckerFailure(text="Oh no!")
            attempt += 1

    REGISTERED_CHECKER.tries = 3
    REGISTERED_CHECKER.function = failure_then_success
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.SUCCEEDED


@pytest.mark.django_db
def test_handles_retries_as_expected() -> None:
    REGISTERED_CHECKER.tries = 3
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.FAILED
    assert checker_run.failures.count() == 1


@pytest.mark.django_db
def test_doesnt_nack_failure_if_override_doesnt_match() -> None:
    run_checker(REGISTERED_CHECKER)
    REGISTERED_CHECKER.function = failing_checker_with_data
    checker = Checker.objects.get(name=CHECKER_NAME)
    CheckerOverride.objects.create(data={"foo": "baz"}, checker=checker)
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.status == CheckerRun.Status.FAILED
    assert checker_run.failures.count() == 1
    CheckerOverride.objects.all().delete()


@pytest.mark.django_db
def test_nacks_failure_if_universal_override() -> None:
    run_checker(REGISTERED_CHECKER)
    REGISTERED_CHECKER.function = failing_checker_with_data
    CheckerOverride.objects.create(data={"foo": "bar"}, apply_to_all_checkers=True)
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.status == CheckerRun.Status.SUCCEEDED
    assert checker_run.failures.count() == 0
    CheckerOverride.objects.all().delete()


@pytest.mark.django_db
def test_nacks_failure_if_override_matches() -> None:
    run_checker(REGISTERED_CHECKER)
    REGISTERED_CHECKER.function = failing_checker_with_data
    checker = Checker.objects.get(name=CHECKER_NAME)
    CheckerOverride.objects.create(data={"foo": "bar"}, checker=checker)
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.status == CheckerRun.Status.SUCCEEDED
    assert checker_run.failures.count() == 0
    CheckerOverride.objects.all().delete()


@pytest.mark.django_db
def test_marks_run_as_failed() -> None:
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.FAILED
    assert checker_run.failures.count() == 1


@pytest.mark.django_db
def test_marks_run_as_failed_and_spits_out_multiple_failures() -> None:
    REGISTERED_CHECKER.function = multiple_failing_checker
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.FAILED
    assert checker_run.failures.count() == 10


@pytest.mark.django_db
def test_respects_maximum_number_of_failures() -> None:
    REGISTERED_CHECKER.function = infinitely_failing_checker
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.FAILED
    assert checker_run.failures.count() == 100


@pytest.mark.django_db
def test_marks_run_as_successful() -> None:
    REGISTERED_CHECKER.function = succeeding_checker
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.SUCCEEDED
    assert checker_run.failures.count() == 0


@pytest.mark.django_db
def test_marks_run_as_successful_from_empty_generator() -> None:
    REGISTERED_CHECKER.function = succeeding_checker_as_generator
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.SUCCEEDED
    assert checker_run.failures.count() == 0


@pytest.mark.django_db
def test_marks_run_as_errored() -> None:
    REGISTERED_CHECKER.function = erroring_checker
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.name == CHECKER_NAME
    assert checker_run.status == CheckerRun.Status.ERRORED
    assert checker_run.failures.count() == 0
    assert checker_run.data["exception"] is not None


@pytest.mark.django_db
def test_errors_should_set_new_checker() -> None:
    REGISTERED_CHECKER.function = erroring_checker
    checker_run = run_checker(REGISTERED_CHECKER)
    assert checker_run.checker.status == Checker.Status.ERRORED


@pytest.mark.django_db
def test_failures_send_out_errors(mailoutbox: List[EmailMessage]) -> None:
    run_checker(REGISTERED_CHECKER)
    assert (
        len(mailoutbox) >= 1
    ), f"Outbox mail: {','.join(email.subject for email in mailoutbox)}"


@pytest.mark.django_db
def test_failures_only_send_out_one_error(mailoutbox: List[EmailMessage]) -> None:
    REGISTERED_CHECKER.severity = Checker.Severity.LOW
    run_checker(REGISTERED_CHECKER)
    run_checker(REGISTERED_CHECKER)
    assert (
        len(mailoutbox) == 1
    ), f"Outbox mail: {','.join(email.subject for email in mailoutbox)}"


@pytest.mark.django_db
def test_failures_dont_send_on_ignored_checkers(mailoutbox: List[EmailMessage]) -> None:
    Checker.objects.create(
        name=CHECKER_NAME,
        section=CHECKER_SECTION,
        status=Checker.Status.IGNORED,
    )
    run_checker(REGISTERED_CHECKER)
    assert len(mailoutbox) == 0
