from typing import Any, Dict

from django.dispatch import receiver
from django.utils import timezone
from fieldsignals import post_save_changed  # type: ignore

from checker import reactions
from checker.models import Checker, CheckerRun, CheckerStatusTransition


@receiver(post_save_changed, sender=Checker, fields=["status"])
def checker_update_actions(
    sender: Any, instance: Checker, changed_fields: Dict, **kwargs: str
) -> None:
    old_value, new_value = list(changed_fields.values())[0]
    if new_value == Checker.Status.ERRORED:
        # There can be a bit of a race condition here where
        # a non-errored run sneaks in before we process the error.
        # I don't quite understand the timing of why this would happen,
        # but to err on the safe side we go ahead and filter to just
        # errored runs, rather than grab the latest run regardless of
        # status (since that status might not be an error, and thus not contain
        # exception information.)
        errored_run = instance.runs.filter(status=CheckerRun.Status.ERRORED).latest(
            "creation_date"
        )
        reactions.handle_low_priority_error(errored_run)
        if instance.severity == Checker.Severity.HIGH:
            reactions.handle_high_priority_error(errored_run)
    elif new_value == Checker.Status.FAILING:
        failed_run = instance.runs.latest("creation_date")
        # At one point, I emailed for every single failure. This became
        # extremely noisy in certain circumstances. I think the best option
        # is to have a "dossier" (that is, modify `handle_priority_error` should
        # take a CheckerRun object and not a CheckerFailure object); in the short
        # term, we'll just only process the first failure.
        failure = failed_run.failures.first()
        if failure:
            reactions.handle_low_priority_failure(failure)
            if instance.severity == Checker.Severity.HIGH:
                reactions.handle_high_priority_failure(failure)
    elif new_value == Checker.Status.SUCCEEDING:
        reactions.handle_success(instance)
    CheckerStatusTransition.objects.create(
        creation_date=timezone.now(),
        parent=instance,
        old_value=old_value,
        new_value=new_value,
    )
