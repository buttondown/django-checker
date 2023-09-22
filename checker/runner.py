import traceback
from typing import Iterable, Iterator

import structlog
from django.conf import settings
from django.utils import timezone
from django_rq import get_queue, job  # type: ignore

from checker.models import Checker, CheckerFailure, CheckerOverride, CheckerRun
from checker.registry import REGISTERED_CHECKERS, RegisteredChecker
from utils.rq import Queue

logger = structlog.get_logger(__name__)

# Ideally checks wouldn't run this long; the only one that really does
# is `no_unclean_newsletters` at the moment, since it needs to full_clean
# every newsletter.
CHECKER_RUN_TIMEOUT = 3600

# We can run into O(n) issues with checkers, and often that's just
# unnecessarily noisy from a database or email perspective.
MAXIMUM_NUMBER_OF_CHECKER_FAILURES = 100


def update_checker_for_run(checker: Checker, checker_run: CheckerRun) -> None:
    # We don't implement this as a signal specifically because we can't act on changes
    # in the overall checker status until all of the failures/errors/etc. in the checker
    # have been persisted.
    if checker.status == Checker.Status.IGNORED:
        return
    previous_checker_runs = checker.runs.exclude(id=checker_run.id)
    previous_checker_run = (
        previous_checker_runs.latest("creation_date")
        if previous_checker_runs.exists()
        else None
    )
    # (N.B. — the logic below is definitely a janky implementation that would be better suited
    # by a state machine like `transitions`. It's not _so_ painful that we need to rethink it,
    # but we should feel comfortable re-evaluating doing so if we start tripping over ourselves.)
    # If there's no previous run, then this is the first and thus a source of truth.
    if checker_run.status == Checker.Status.NEW or not previous_checker_run:
        if checker_run.status == CheckerRun.Status.FAILED:
            checker.status = Checker.Status.FAILING
        elif checker_run.status == CheckerRun.Status.SUCCEEDED:
            checker.status = Checker.Status.SUCCEEDING
        else:
            checker.status = Checker.Status.ERRORED
        checker.latest_status_change = timezone.now()
        checker.latest_run_date = timezone.now()
        checker.save()
    else:
        if (
            checker_run.status == CheckerRun.Status.FAILED
            and checker.status != Checker.Status.FAILING
        ):
            checker.status = Checker.Status.FAILING
            checker.latest_status_change = timezone.now()
            checker.save()
        elif (
            checker_run.status == CheckerRun.Status.SUCCEEDED
            and checker.status != Checker.Status.SUCCEEDING
        ):
            checker.status = Checker.Status.SUCCEEDING
            checker.latest_status_change = timezone.now()
            checker.save()
        elif (
            checker_run.status == CheckerRun.Status.ERRORED
            and checker.status != Checker.Status.ERRORED
        ):
            checker.status = Checker.Status.ERRORED
            checker.latest_status_change = timezone.now()
        checker.latest_run_date = timezone.now()
        checker.save()


def is_relevant_failure(failure: CheckerFailure, checker: Checker) -> bool:
    if not failure.data:
        return True
    for override in checker.overrides.all():
        if override.data.items() <= failure.data.items():
            return False
    for override in CheckerOverride.objects.filter(apply_to_all_checkers=True):
        if override.data.items() <= failure.data.items():
            return False
    return True


def update_checker_metadata(
    checker: Checker, registered_checker: RegisteredChecker
) -> Checker:
    # Update and persist changes to the checker if any have happened since the
    # previous run.
    cleaned_checker_description = registered_checker.description.lstrip().rstrip()
    if checker.description != cleaned_checker_description:
        checker.description = cleaned_checker_description
        checker.save()
    if checker.severity != registered_checker.severity:
        checker.severity = registered_checker.severity
        checker.save()
    if checker.cadence != registered_checker.cadence:
        checker.cadence = registered_checker.cadence
        checker.save()
    return checker


@job(Queue.one_hour.value, timeout=CHECKER_RUN_TIMEOUT)
def run_checker(
    registered_checker: RegisteredChecker, dry_run: bool = False
) -> CheckerRun:
    logger.info("checker.started", name=registered_checker.name)
    checker, _ = Checker.objects.get_or_create(
        name=registered_checker.name, section=registered_checker.section
    )
    update_checker_metadata(checker, registered_checker)
    if not dry_run:
        checker_run = CheckerRun.objects.create(
            checker=checker, status=CheckerRun.Status.IN_PROGRESS
        )
    try:
        for _ in range(registered_checker.tries):
            # This logic is a little circuitous because it accounts for
            # handling both unwrapping failures (which are iterable) and
            # successes (which are not).
            failures = registered_checker.function()
            collected_failures = []
            if not isinstance(failures, Iterator):
                break
            for failure in failures:
                if not is_relevant_failure(failure, checker):
                    continue
                collected_failures.append(failure)
                if len(collected_failures) >= MAXIMUM_NUMBER_OF_CHECKER_FAILURES:
                    break
            if not collected_failures:
                break
        if collected_failures:
            if dry_run:
                return CheckerRun(status=CheckerRun.Status.FAILED)
            checker_run.status = CheckerRun.Status.FAILED
            checker_run.completion_date = timezone.now()
            checker_run.save()
            for failure in collected_failures:
                failure.checker_run = checker_run
            CheckerFailure.objects.bulk_create(collected_failures)
        else:
            if dry_run:
                return CheckerRun(status=CheckerRun.Status.SUCCEEDED)
            checker_run.status = CheckerRun.Status.SUCCEEDED
            checker_run.completion_date = timezone.now()
            checker_run.save()
    except Exception as e:
        traceback.print_exc()
        logger.info("checker.errored", name=registered_checker.name, exception=e)
        if dry_run:
            return CheckerRun(status=CheckerRun.Status.ERRORED)
        checker_run.status = CheckerRun.Status.ERRORED
        checker_run.data = {"exception": traceback.format_exc()}
        checker_run.completion_date = timezone.now()
        checker_run.save()
    update_checker_for_run(checker, checker_run)
    return checker_run


def checkers_for_cadence(cadence: Checker.Cadence) -> Iterable[RegisteredChecker]:
    for checker in REGISTERED_CHECKERS.values():
        if (
            checker.cadence == cadence
            and checker.name not in settings.DISABLED_CHECKERS
        ):
            yield checker


CHECKER_CADENCE_TO_QUEUE = {
    Checker.Cadence.EVERY_TEN_MINUTES: Queue.five_minutes.value,
    Checker.Cadence.HOURLY: Queue.one_hour.value,
    Checker.Cadence.DAILY: Queue.one_day.value,
}


def run_checkers(cadence: Checker.Cadence) -> None:
    if settings.DISABLE_CHECKERS:
        logger.info("checker.disabled", cadence=cadence)
        return

    for checker in checkers_for_cadence(cadence):
        print(f"Running checker: {checker.name}")
        get_queue(CHECKER_CADENCE_TO_QUEUE[cadence]).enqueue(run_checker, checker)
