from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404


def get_owned_object_or_403(klass, request, *args, owner_path="owner", **kwargs):
    """Fetch an object like ``get_object_or_404`` while enforcing ownership.

    Returns the object when it has no owner, or when it is owned by
    ``request.user``; otherwise raises :class:`~django.core.exceptions.PermissionDenied`
    (HTTP 403). This mirrors the owner check used by ``transaction_rule_edit``
    (``if obj.owner and obj.owner != request.user``) so authorization is applied
    uniformly across handlers that resolve an object from a URL id.

    An object with no owner stays accessible to everyone, preserving the
    existing behaviour for legacy/unowned objects.

    ``owner_path`` is a dotted attribute path to the owning user, so nested
    ownership is supported for objects owned through a relation, e.g. a rule
    action owned via its parent rule::

        get_owned_object_or_403(
            TransactionRuleAction, request, id=pk, owner_path="rule.owner"
        )
    """
    obj = get_object_or_404(klass, *args, **kwargs)

    owner = obj
    for attr in owner_path.split("."):
        owner = getattr(owner, attr, None)
        if owner is None:
            break

    if owner is not None and owner != request.user:
        raise PermissionDenied

    return obj
