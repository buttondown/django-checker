from django.apps import AppConfig


class CheckerConfig(AppConfig):
    name = "checker"

    def ready(self) -> None:
        import checker.registry  # noqa: F401
        import checker.signals  # noqa: F401
