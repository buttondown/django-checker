from django.conf import settings
from django.core.mail import mail_admins, send_mail
from django.template.loader import render_to_string

from checker.models import Checker, CheckerFailure, CheckerRun
from utils import slack


def handle_low_priority_error(checker_run: CheckerRun) -> None:
    error_title = f"Error while running {checker_run.checker.name}"
    error_content = str(checker_run.data["exception"])
    if checker_run.checker.user:
        send_mail(
            error_title,
            error_content,
            settings.SERVER_EMAIL,
            [checker_run.checker.user.email],
        )
    mail_admins(error_title, error_content)


def handle_high_priority_error(checker_run: CheckerRun) -> None:
    error_title = f"Error while running {checker_run.checker.name}"
    error_content = str(checker_run.data["exception"])
    send_mail(
        error_title,
        error_content,
        settings.SERVER_EMAIL,
        [settings.PAGING_EMAIL],
    )


def render_email_content_for_checker_failure(failure: CheckerFailure) -> str:
    return render_to_string(
        "checker_failure.txt",
        context={
            "failure": failure,
            "SITE_URL": settings.SITE_URL,
        },
    )


def render_email_content_for_checker_success(checker: Checker) -> str:
    return render_to_string(
        "checker_success.txt",
        context={
            "checker": checker,
            "SITE_URL": settings.SITE_URL,
        },
    )


def handle_success(checker: Checker) -> None:
    mail_admins(
        f"{checker.name} is now succeeding",
        render_email_content_for_checker_success(checker),
    )


def handle_low_priority_failure(failure: CheckerFailure) -> None:
    slack.notify.delay(
        slack.Notification(failure.text, text=failure.subtext, channel="#alerts")
    )
    mail_admins(failure.text, render_email_content_for_checker_failure(failure))


def handle_high_priority_failure(failure: CheckerFailure) -> None:
    send_mail(
        failure.text,
        render_email_content_for_checker_failure(failure),
        settings.SERVER_EMAIL,
        [settings.PAGING_EMAIL],
    )
