from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag
def split_portal_url(urls_dict, name_key, **extra_kwargs):
    url_name = urls_dict[name_key]
    kwargs = {urls_dict["url_kwarg_key"]: urls_dict["url_kwarg_val"]}
    kwargs.update(extra_kwargs)
    return reverse(url_name, kwargs=kwargs)
