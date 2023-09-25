import typing
from dataclasses import dataclass
from functools import partial

from django.conf import settings
from django.core.checks import Error, register

from checker.models import Checker
from .utils import import_submodules


@dataclass
class RegisteredChecker:
    name: str
    section: str
    description: str
    tries: int
    severity: Checker.Severity
    cadence: Checker.Cadence
    function: typing.Callable


REGISTERED_CHECKERS = {}

DUPLICATE_CHECKERS = []


def extract_name(runner_function: typing.Callable) -> str:
    if runner_function.__name__ == "check":
        return runner_function.__module__.split(".")[-1]
    return runner_function.__name__


def register_checker(
    runner_function: typing.Callable = None,
    *,
    description: str = "",
    tries: int = 1,
    severity: Checker.Severity = Checker.Severity.LOW,
    cadence: Checker.Cadence = Checker.Cadence.HOURLY,
) -> typing.Callable:
    if runner_function is None:
        return partial(
            register_checker,
            description=description,
            tries=tries,
            severity=severity,
            cadence=cadence,
        )

    name = extract_name(runner_function)
    section = runner_function.__module__.split(".")[0]
    registration = RegisteredChecker(
        name, section, description, tries, severity, cadence, runner_function
    )
    if registration.name not in REGISTERED_CHECKERS:
        REGISTERED_CHECKERS[registration.name] = registration
    else:
        DUPLICATE_CHECKERS.append(registration)
    return runner_function


for app_name in settings.INSTALLED_APPS:
    try:
        import_submodules(f"{app_name}.checkers")
    except ModuleNotFoundError:
        pass


@register()
def no_duplicate_checkers(
    app_configs: typing.Any, **kwargs: typing.Any
) -> typing.List[Error]:
    errors = []
    for checker in DUPLICATE_CHECKERS:
        errors.append(
            Error(
                f"Duplicate checker '{checker.name}' found in {checker.section}",
                hint=f"Check {checker.section} for duplicates",
                id=f"{checker.name}.duplicate_checker",
            )
        )
    return errors
