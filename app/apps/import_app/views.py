import shutil

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _

from apps.common.decorators.htmx import only_htmx
from apps.import_app.forms import ImportRunFileUploadForm, ImportProfileForm
from apps.import_app.models import ImportRun, ImportProfile
from apps.import_app.tasks import process_import


def import_view(request):
    import_profile = ImportProfile.objects.get(id=2)
    shutil.copyfile(
        "/usr/src/app/apps/import_app/teste2.csv", "/usr/src/app/temp/teste2.csv"
    )
    ir = ImportRun.objects.create(profile=import_profile, file_name="teste.csv")
    process_import.defer(
        import_run_id=ir.id,
        file_path="/usr/src/app/temp/teste2.csv",
    )
    return HttpResponse("Hello, world. You're at the polls page.")


@login_required
@require_http_methods(["GET", "POST"])
def import_profile_index(request):
    return render(
        request,
        "import_app/pages/profiles_index.html",
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_profile_list(request):
    profiles = ImportProfile.objects.all()

    return render(
        request,
        "import_app/fragments/profiles/list.html",
        {"profiles": profiles},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_profile_add(request):
    if request.method == "POST":
        form = ImportProfileForm(request.POST)

        if form.is_valid():
            form.save()
            messages.success(request, _("Import Profile added successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = ImportProfileForm()

    return render(
        request,
        "import_app/fragments/profiles/add.html",
        {"form": form},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_profile_edit(request, profile_id):
    profile = get_object_or_404(ImportProfile, id=profile_id)

    if request.method == "POST":
        form = ImportProfileForm(request.POST, instance=profile)

        if form.is_valid():
            form.save()
            messages.success(request, _("Import Profile update successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = ImportProfileForm(instance=profile)

    return render(
        request,
        "import_app/fragments/profiles/edit.html",
        {"form": form, "profile": profile},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def import_profile_delete(request, profile_id):
    profile = ImportProfile.objects.get(id=profile_id)

    profile.delete()

    messages.success(request, _("Import Profile deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated",
        },
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_runs_list(request, profile_id):
    profile = ImportProfile.objects.get(id=profile_id)

    runs = ImportRun.objects.filter(profile=profile).order_by("-id")

    return render(
        request,
        "import_app/fragments/runs/list.html",
        {"profile": profile, "runs": runs},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_run_log(request, profile_id, run_id):
    run = ImportRun.objects.get(profile__id=profile_id, id=run_id)

    return render(
        request,
        "import_app/fragments/runs/log.html",
        {"run": run},
    )


@only_htmx
@login_required
@require_http_methods(["GET", "POST"])
def import_run_add(request, profile_id):
    profile = ImportProfile.objects.get(id=profile_id)

    if request.method == "POST":
        form = ImportRunFileUploadForm(request.POST, request.FILES)

        if form.is_valid():
            uploaded_file = request.FILES["file"]
            fs = FileSystemStorage(location="/usr/src/app/temp")
            filename = fs.save(uploaded_file.name, uploaded_file)
            file_path = fs.path(filename)

            import_run = ImportRun.objects.create(profile=profile, file_name=filename)

            # Defer the procrastinate task
            process_import.defer(import_run_id=import_run.id, file_path=file_path)

            messages.success(request, _("Import Run queued successfully"))

            return HttpResponse(
                status=204,
                headers={
                    "HX-Trigger": "updated, hide_offcanvas",
                },
            )
    else:
        form = ImportRunFileUploadForm()

    return render(
        request,
        "import_app/fragments/runs/add.html",
        {"form": form, "profile": profile},
    )


@only_htmx
@login_required
@csrf_exempt
@require_http_methods(["DELETE"])
def import_run_delete(request, profile_id, run_id):
    run = ImportRun.objects.get(profile__id=profile_id, id=run_id)

    run.delete()

    messages.success(request, _("Run deleted successfully"))

    return HttpResponse(
        status=204,
        headers={
            "HX-Trigger": "updated",
        },
    )
