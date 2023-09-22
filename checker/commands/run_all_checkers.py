from typing import Iterator

from rich.console import Console

from checker.models import Checker, CheckerRun
from checker.runner import checkers_for_cadence, run_checker
from commands.registry import register_command

CADENCES = [
    Checker.Cadence.DAILY,
    Checker.Cadence.HOURLY,
    Checker.Cadence.EVERY_TEN_MINUTES,
]

IGNORED_CHECKER_NAMES = ["no_custom_domains_without_webhooks"]


@register_command(name="Run all checkers")
def run_all_checkers() -> Iterator[str]:
    console = Console()

    for cadence in CADENCES:
        for checker in checkers_for_cadence(cadence):
            if checker.name in IGNORED_CHECKER_NAMES:
                console.log(
                    "[bold yellow]SKIPPED[/bold yellow] {}".format(checker.name)
                )
                continue
            with console.status(f"[bold green]Running {checker.name}"):
                result = run_checker(checker, dry_run=True)
                status = (
                    "[bold green]SUCCESS[/bold green]"
                    if result.status == CheckerRun.Status.SUCCEEDED
                    else "[bold red]FAILURE[/bold red]"
                )
                console.log(f"{status} {checker.name}")
    yield ""
