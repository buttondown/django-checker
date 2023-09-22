import json
from typing import Dict, Sequence

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.options import ModelAdmin, TabularInline
from django.contrib.auth.models import User
from django.db.models import JSONField, QuerySet
from django.forms import widgets
from django.forms.models import BaseInlineFormSet
from django.http import HttpRequest
from related_admin import RelatedFieldAdmin  # type: ignore

from checker.models import Checker, CheckerFailure, CheckerOverride, CheckerRun
from checker.registry import REGISTERED_CHECKERS
from checker.runner import run_checker


class CheckerFailureInlineAdmin(TabularInline):
    model = CheckerFailure
    fields = (("text", "subtext"),)
    readonly_fields = ("text", "subtext")
    show_change_link = True
    max_num = 0  # Disables 'add another' and the three blank rows.


class CheckerRunInlineFormset(BaseInlineFormSet):
    def get_queryset(self) -> QuerySet:
        qs = super().get_queryset()
        # The expensive part of rendering all checker runs isn't actually serializing them,
        # but is rendering the DOM elements. We force the queryset to a list rather than limiting
        # the queryset to avoid an O(n) issue (that frankly I don't _quite_ understand.)
        # Yes, it's a hack that we ignore typing here, but it's completely fine; all `BaseInlineFormSet`
        # _actually_ cares about is getting an iterable, so passing a list is not problematic.
        return list(qs)[:100]  # type: ignore


class AssignmentFilter(SimpleListFilter):
    title = "assignment"
    parameter_name = "assignment"

    def lookups(self, request, model_admin):
        return [("me", "Assigned to me")]

    def queryset(self, request, queryset):
        if self.value() == "me":
            return queryset.filter(user=request.user)
        return queryset


class CheckerRunInlineAdmin(TabularInline):
    model = CheckerRun
    fields = (("status", "creation_date"),)
    readonly_fields = ("status", "creation_date")
    show_change_link = True
    max_num = 0
    formset = CheckerRunInlineFormset

    def has_add_permission(self, request: HttpRequest, obj: CheckerRun = None) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: CheckerRun = None
    ) -> bool:
        return False


@admin.register(Checker)
class CheckerAdmin(ModelAdmin):
    list_display = (
        "name",
        "user",
        "section",
        "severity",
        "cadence",
        "status",
        "latest_status_change",
        "latest_run_date",
        "human_readable_time_since_status_change",
    )
    list_filter = (AssignmentFilter, "status", "severity", "section", "cadence")
    inlines = (CheckerRunInlineAdmin,)
    prepopulated_fields: Dict[str, Sequence[str]] = {}
    actions = ["run_checkers", "ignore_checkers", "unignore_checkers"]
    readonly_fields = (
        "name",
        "section",
        "severity",
        "cadence",
        "latest_status_change",
        "latest_run_date",
        "description",
    )

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields["user"].queryset = User.objects.filter(is_staff=True)
        return form

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        queryset = super().get_queryset(request)

        # Prelisting all runs is expensive in the list view, but necessary
        # for the change view. This approach stolen from:
        # https://stackoverflow.com/questions/40054325/different-queryset-optimisation-for-list-view-and-change-view-in-django-admin
        if request.resolver_match.func.__name__ == "change_view":  # type: ignore
            queryset = queryset.prefetch_related("runs")
        return queryset

    @admin.action(description="Run selected checkers")
    def run_checkers(self, request: HttpRequest, queryset: QuerySet) -> None:
        for checker in queryset:
            registered_checker = REGISTERED_CHECKERS.get(checker.name)
            if registered_checker:
                run_checker.delay(registered_checker)
                self.message_user(
                    request, f"Enqueued a run of {checker.name}", messages.SUCCESS
                )

    @admin.action(description="Ignore checkers")
    def ignore_checkers(self, request: HttpRequest, queryset: QuerySet) -> None:
        queryset.update(status=Checker.Status.IGNORED)
        for checker in queryset:
            self.message_user(request, f"Started ignoring {checker.name}")

    @admin.action(description="Unignore checkers")
    def unignore_checkers(self, request: HttpRequest, queryset: QuerySet) -> None:
        queryset.update(status=Checker.Status.NEW)
        for checker in queryset:
            self.message_user(request, f"Stopped ignoring {checker.name}")


@admin.register(CheckerRun)
class CheckerRunAdmin(RelatedFieldAdmin):
    list_display = ("id", "checker__name", "creation_date", "status")
    list_filter = ("status", "checker__name")
    inlines = (CheckerFailureInlineAdmin,)
    readonly_fields = ("checker", "status", "data")

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).prefetch_related("checker")


class JSONTableWidget(widgets.Widget):
    template_name = "checkers/admin/json_table_widget.html"

    def get_context(self, name, value, attrs):
        return {
            "widget": {
                "value": json.loads(value) if value else {},
                "template_name": self.template_name,
            },
        }


@admin.register(CheckerFailure)
class CheckerFailureAdmin(RelatedFieldAdmin):
    list_display = ("id", "checker_run__checker__name", "creation_date")
    readonly_fields = ("text", "subtext", "checker_run")

    # Note for future self: this only works when the relevant field being overwritten
    # is not listed in `readonly_fields`. If it is, the widget will not be used.
    formfield_overrides = {
        JSONField: {"widget": JSONTableWidget},
    }

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).prefetch_related("checker_run__checker")


@admin.register(CheckerOverride)
class CheckerOverrideAdmin(RelatedFieldAdmin):
    list_display = ("id", "checker__name", "data", "creation_date")
    list_filter = ("checker",)
    autocomplete_fields = ("user",)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return super().get_queryset(request).prefetch_related("checker")
