from django.urls import path

from checker.views import checker_detail, checker_list, run_detail

urlpatterns = [
    path(
        "checkers",
        checker_list.view,
        name="checker-list",
    ),
    path(
        "checkers/<str:checker_name>",
        checker_detail.view,
        name="checker-detail",
    ),
    path(
        "checkers/<str:checker_name>/runs/<str:run_id>",
        run_detail.view,
        name="run-detail",
    ),
]
