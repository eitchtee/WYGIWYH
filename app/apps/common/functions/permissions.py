from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404

READ = "read"
EDIT = "edit"


def get_shared_object_or_error(klass, request, *, level=EDIT, via=None, **kwargs):
    """Fetch an object like ``get_object_or_404`` while enforcing access control.

    ``SharedObjectManager`` scopes querysets to what a user may *see*, which is
    not the same as what they may *change*. Views that resolve an object from a
    URL id must state which of the two they need, otherwise a shared or public
    object becomes writable by anyone who can see it.

    ``level`` selects the check applied to the governing ``SharedObject``:

    ``READ``
        The object must be visible to the user. Denial raises :class:`Http404`
        so the response does not confirm that the id exists.
    ``EDIT``
        The object must be owned by the user. Denial raises
        :class:`~django.core.exceptions.PermissionDenied` (HTTP 403), which the
        frontend surfaces as an "Access Denied" dialog. An object the user
        cannot even see raises :class:`Http404` instead, so 403 never confirms
        the existence of an object they were not allowed to know about.

    Objects with no owner stay accessible to everyone, preserving the existing
    behaviour for legacy/unowned objects.

    ``via`` is a dotted path to the ``SharedObject`` that governs access, for
    models owned through a relation, e.g. a rule action governed by its parent
    rule::

        get_shared_object_or_error(
            TransactionRuleAction, request, id=pk, level=EDIT, via="rule"
        )

    The path is resolved with a plain ``getattr``, so a path that does not
    resolve raises ``AttributeError`` rather than silently granting access.
    """
    obj = get_object_or_404(klass, **kwargs)

    guard = obj
    for attr in via.split(".") if via else []:
        guard = getattr(guard, attr)

    if level not in (READ, EDIT):
        raise ValueError(f"Unknown access level: {level!r}")

    if not guard.is_visible_to(request.user):
        raise Http404

    if level == EDIT and not guard.is_editable_by(request.user):
        raise PermissionDenied

    return obj
