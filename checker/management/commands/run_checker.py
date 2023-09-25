from typing import Any

from django.core.management import BaseCommand
from django.core.management.base import CommandParser

from checker.models import Checker
from checker.registry import REGISTERED_CHECKERS
from checker.runner import run_checker

PAGE_SIZE = 100


class Command(BaseCommand):
    help = "Runs a specific checker."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("checker_name", type=str)
        parser.add_argument("--failing", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        if options.get("failing"):
            checker_names = list(
                Checker.objects.filter(status=Checker.Status.FAILING).values_list(
                    "name", flat=True
                )
            )
        else:
            checker_names = [options["checker_name"]]
        for checker_name in checker_names:
            checker = REGISTERED_CHECKERS[checker_name]
            checker_run = run_checker(checker)
            print(f"Running {checker_name}.")
            print(f"Checker run {checker_run.id} completed.")
            print(f"Checker run {checker_run.id} status: {checker_run.status}")
