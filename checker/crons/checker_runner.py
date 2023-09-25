from django_cron import Schedule

from checker.models import Checker
from checker.runner import run_checkers
from utils.cron import CronJob


class CheckerRunnerEveryTenMinutesCronJob(CronJob):
    RUN_EVERY_MINS = 10

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "checker.checker_runner.every_ten_minutes"

    def handle(self) -> None:
        run_checkers(Checker.Cadence.EVERY_TEN_MINUTES)


class CheckerRunnerHourlyCronJob(CronJob):
    RUN_EVERY_MINS = 60

    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = "checker.checker_runner.every_hour"

    def handle(self) -> None:
        run_checkers(Checker.Cadence.HOURLY)


class CheckerRunnerDailyCronJob(CronJob):
    RUN_AT_TIMES = ["9:30"]

    schedule = Schedule(run_at_times=RUN_AT_TIMES)
    code = "checker.checker_runner.every_day"

    def handle(self) -> None:
        run_checkers(Checker.Cadence.DAILY)
