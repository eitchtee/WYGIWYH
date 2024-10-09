from django import template


register = template.Library()


# https://github.com/valerymelou/django-active-link/
@register.simple_tag(takes_context=True)
def active_link(
    context, views="", namespaces="", css_class="active", inactive_class=""
):
    """
    Renders the given CSS class if the request path matches the path of the view.
    :param context: The context where the tag was called. Used to access the request object.
    :param views: The name of the view or views separated by || (include namespaces if any).
    :param namespaces: The name of the namespace or namespaces separated by ||.
    :param css_class: The CSS class to render.
    :param inactive_class: The CSS class to render if the views is not active.
    :return:
    """
    request = context.get("request")
    if request is None:
        # Can't work without the request object.
        return ""

    if views:
        views = views.split("||")
        current_view = request.resolver_match.view_name

        if current_view in views:
            return css_class
    elif namespaces:
        namespaces = namespaces.split("||")
        current_namespace = request.resolver_match.namespaces

        if any(item in current_namespace for item in namespaces):
            return css_class
    else:
        return ""

    return inactive_class
