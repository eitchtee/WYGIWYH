from crispy_forms.layout import BaseInput


class NoClassSubmit(BaseInput):
    """
    Used to create a Submit button descriptor for the {% crispy %} template tag.

    Attributes
    ----------
    template: str
        The default template which this Layout Object will be rendered
        with.
    field_classes: str
        CSS classes to be applied to the ``<input>``.
    input_type: str
        The ``type`` attribute of the ``<input>``.

    Parameters
    ----------
    name : str
        The name attribute of the button.
    value : str
        The value attribute of the button.
    css_id : str, optional
        A custom DOM id for the layout object. If not provided the name
        argument is slugified and turned into the id for the submit button.
        By default None.
    css_class : str, optional
        Additional CSS classes to be applied to the ``<input>``. By default
        None.
    template : str, optional
        Overrides the default template, if provided. By default None.
    **kwargs : dict, optional
        Additional attributes are passed to `flatatt` and converted into
        key="value", pairs. These attributes are added to the ``<input>``.

    Examples
    --------
    Note: ``form`` arg to ``render()`` is not required for ``BaseInput``
    inherited objects.

    >>> submit = Submit('Search the Site', 'search this site')
    >>> submit.render("", "", Context())
    '<input type="submit" name="search-the-site" value="search this site" '
    'class="btn btn-primary" id="submit-id-search-the-site"/>'

    >>> submit = Submit('Search the Site', 'search this site', css_id="custom-id",
                         css_class="custom class", my_attr=True, data="my-data")
    >>> submit.render("", "", Context())
    '<input type="submit" name="search-the-site" value="search this site" '
    'class="btn btn-primary custom class" id="custom-id" data="my-data" my-attr/>'

    Usually you will not call the render method on the object directly. Instead
    add it to your ``Layout`` manually or use the `add_input` method::

        class ExampleForm(forms.Form):
        [...]
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.helper = FormHelper()
            self.helper.add_input(Submit('submit', 'Submit'))
    """

    input_type = "submit"
    field_classes = ""
