import uuid
from typing import Any, List, Tuple

from django.db import models
import importlib
import pkgutil


def import_submodules(package, recursive=True):
    """Import all submodules of a module, recursively, including subpackages

    :param package: package (name or actual module)
    :type package: str | module
    :rtype: dict[str, types.ModuleType]
    """
    if isinstance(package, str):
        package = importlib.import_module(package)
    results = {}
    for _, name, is_pkg in pkgutil.walk_packages(package.__path__):
        full_name = package.__name__ + "." + name
        # Skip test files so we don't unnecessarily pull in test dependencies.
        if "--test" in full_name:
            continue
        results[full_name] = importlib.import_module(full_name)
        if recursive and is_pkg:
            results.update(import_submodules(full_name))
    return results


class BaseModel(models.Model):
    creation_date = models.DateTimeField(auto_now_add=True)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseTransition(BaseModel):
    @staticmethod
    def construct_parent(
        cls: Any, name: str = "status_transitions"
    ) -> models.ForeignKey:
        return models.ForeignKey(cls, related_name=name, on_delete=models.CASCADE)

    @staticmethod
    def construct_old_value(choices: List[Tuple[str, str]]) -> models.TextField:
        return models.TextField(choices=choices, max_length=50, null=True, blank=True)

    @staticmethod
    def construct_new_value(choices: List[Tuple[str, str]]) -> models.TextField:
        return models.TextField(choices=choices, max_length=50)

    parent: models.ForeignKey
    old_value: models.TextField
    new_value: models.TextField

    class Meta:
        ordering = ("creation_date",)
        get_latest_by = "creation_date"
        abstract = True

    def __str__(self) -> str:
        return f"{self.id}: {self.old_value} → {self.new_value}"
