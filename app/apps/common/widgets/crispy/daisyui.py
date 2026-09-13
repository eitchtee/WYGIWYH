from crispy_forms.layout import Field


class Switch(Field):
    template = "crispy-daisyui/layout/switch.html"


class Range(Field):
    template = "crispy-daisyui/layout/range.html"

    def render(self, form, context, extra_context=None, **kwargs):
        extra_context = extra_context or {}

        # Build the measure (ticks + labels) from the field's min/max/step
        attrs = form.fields[self.fields[0]].widget.attrs
        if "min" in attrs and "max" in attrs:
            step = attrs.get("step") or 1
            extra_context["range_steps"] = list(
                range(int(attrs["min"]), int(attrs["max"]) + 1, int(step))
            )

        return super().render(form, context, extra_context=extra_context, **kwargs)
