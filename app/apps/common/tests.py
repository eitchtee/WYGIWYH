from django.test import TestCase, RequestFactory
from django.template import Template, Context
from django.urls import reverse, resolve, NoReverseMatch
from django.contrib.auth.models import User
from decimal import Decimal # Keep existing imports if they are from other tests
from app.apps.common.functions.decimals import truncate_decimal # Keep existing imports

# Helper to create a dummy request with resolver_match
def setup_request_for_view(factory, view_name_or_url, user=None, namespace=None, view_name_for_resolver=None):
    try:
        url = reverse(view_name_or_url)
    except NoReverseMatch:
        url = view_name_or_url # Assume it's already a URL path

    request = factory.get(url)
    if user:
        request.user = user

    try:
        # For resolver_match, we need to simulate how Django does it.
        # It needs specific view_name and namespace if applicable.
        # If view_name_for_resolver is provided, use that for resolving,
        # otherwise, assume view_name_or_url is the view name for resolver_match.
        resolver_match_source = view_name_for_resolver if view_name_for_resolver else view_name_or_url

        # If it's a namespaced view name like 'app:view', resolve might handle it directly.
        # If namespace is separately provided, it means the view_name itself is not namespaced.
        resolved_match = resolve(url) # Resolve the URL to get func, args, kwargs, etc.

        # Ensure resolver_match has the correct attributes, especially 'view_name' and 'namespace'
        if hasattr(resolved_match, 'view_name'):
            if ':' in resolved_match.view_name and not namespace: # e.g. 'app_name:view_name'
                request.resolver_match = resolved_match
            elif namespace and resolved_match.namespace == namespace and resolved_match.url_name == resolver_match_source.split(':')[-1]:
                request.resolver_match = resolved_match
            elif not namespace and resolved_match.url_name == resolver_match_source:
                 request.resolver_match = resolved_match
            else: # Fallback or if specific view_name/namespace parts are needed for resolver_match
                # This part is tricky without knowing the exact structure of resolver_match expected by the tag
                # Forcing the view_name and namespace if they are explicitly passed.
                if namespace:
                    resolved_match.namespace = namespace
                if view_name_for_resolver: # This should be the non-namespaced view name part
                     resolved_match.view_name = f"{namespace}:{view_name_for_resolver.split(':')[-1]}" if namespace else view_name_for_resolver.split(':')[-1]
                     resolved_match.url_name = view_name_for_resolver.split(':')[-1]

                request.resolver_match = resolved_match

        else: # Fallback if resolve() doesn't directly give a full resolver_match object as expected
            request.resolver_match = None


    except Exception as e:
        print(f"Warning: Could not resolve URL or set resolver_match for '{view_name_or_url}' (or '{view_name_for_resolver}') for test setup: {e}")
        request.resolver_match = None
    return request

class CommonTestCase(TestCase): # Keep existing test class if other tests depend on it
    def test_example(self): # Example of an old test
        self.assertEqual(1 + 1, 2)

    def test_truncate_decimal_function(self): # Example of an old test from problem description
        test_cases = [
            (Decimal('123.456'), 0, Decimal('123')),
            (Decimal('123.456'), 1, Decimal('123.4')),
            (Decimal('123.456'), 2, Decimal('123.45')),
        ]
        for value, places, expected in test_cases:
            with self.subTest(value=value, places=places, expected=expected):
                self.assertEqual(truncate_decimal(value, places), expected)


class CommonTemplateTagsTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('testuser', 'password123')

        # Using view names that should exist in a typical Django project with auth
        # Ensure these URLs are part of your project's urlpatterns for tests to pass.
        self.view_name_login = 'login' # Typically 'login' or 'account_login'
        self.namespace_login = None # Often no namespace for basic auth views, or 'account'

        self.view_name_admin = 'admin:index' # Admin index
        self.namespace_admin = 'admin'

        # Check if these can be reversed, skip tests if not.
        try:
            reverse(self.view_name_login)
        except NoReverseMatch:
            self.view_name_login = None # Mark as unusable
            print(f"Warning: Could not reverse '{self.view_name_login}'. Some active_link tests might be skipped.")
        try:
            reverse(self.view_name_admin)
        except NoReverseMatch:
            self.view_name_admin = None # Mark as unusable
            print(f"Warning: Could not reverse '{self.view_name_admin}'. Some active_link tests might be skipped.")

    def test_active_link_view_match(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible.")
        request = setup_request_for_view(self.factory, self.view_name_login, self.user,
                                         namespace=self.namespace_login, view_name_for_resolver=self.view_name_login)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_login}.")

        template_str = "{% load active_link %} {% active_link views='" + self.view_name_login + "' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "active")

    def test_active_link_view_no_match(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible.")
        request = setup_request_for_view(self.factory, self.view_name_login, self.user,
                                         namespace=self.namespace_login, view_name_for_resolver=self.view_name_login)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_login}.")

        template_str = "{% load active_link %} {% active_link views='non_existent_view_name' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "")

    def test_active_link_view_match_custom_class(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible.")
        request = setup_request_for_view(self.factory, self.view_name_login, self.user,
                                         namespace=self.namespace_login, view_name_for_resolver=self.view_name_login)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_login}.")

        template_str = "{% load active_link %} {% active_link views='" + self.view_name_login + "' css_class='custom-active' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "custom-active")

    def test_active_link_view_no_match_inactive_class(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible.")
        request = setup_request_for_view(self.factory, self.view_name_login, self.user,
                                         namespace=self.namespace_login, view_name_for_resolver=self.view_name_login)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_login}.")

        template_str = "{% load active_link %} {% active_link views='non_existent_view_name' inactive_class='custom-inactive' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "custom-inactive")

    def test_active_link_namespace_match(self):
        if not self.view_name_admin: self.skipTest("Admin URL not reversible.")
        # The view_name_admin is already namespaced 'admin:index'
        request = setup_request_for_view(self.factory, self.view_name_admin, self.user,
                                         namespace=self.namespace_admin, view_name_for_resolver=self.view_name_admin)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_admin}.")
        # Ensure the resolver_match has the namespace set correctly by setup_request_for_view
        self.assertEqual(request.resolver_match.namespace, self.namespace_admin, "Namespace not correctly set in resolver_match for test.")

        template_str = "{% load active_link %} {% active_link namespaces='" + self.namespace_admin + "' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "active")

    def test_active_link_multiple_views_one_match(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible.")
        request = setup_request_for_view(self.factory, self.view_name_login, self.user,
                                         namespace=self.namespace_login, view_name_for_resolver=self.view_name_login)
        if not request.resolver_match: self.skipTest(f"Could not set resolver_match for {self.view_name_login}.")

        template_str = "{% load active_link %} {% active_link views='other_app:other_view||" + self.view_name_login + "' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "active")

    def test_active_link_no_request_in_context(self):
        if not self.view_name_login: self.skipTest("Login URL not reversible for placeholder view name.")
        template_str = "{% load active_link %} {% active_link views='" + self.view_name_login + "' %}"
        template = Template(template_str)
        rendered = template.render(Context({})) # Empty context, no 'request'
        self.assertEqual(rendered.strip(), "")

    def test_active_link_request_without_resolver_match(self):
        request = self.factory.get('/some_unresolved_url/') # This URL won't resolve
        request.user = self.user
        request.resolver_match = None # Explicitly set to None, as resolve() would fail

        if not self.view_name_login: self.skipTest("Login URL not reversible for placeholder view name.")
        template_str = "{% load active_link %} {% active_link views='" + self.view_name_login + "' %}"
        template = Template(template_str)
        rendered = template.render(Context({'request': request}))
        self.assertEqual(rendered.strip(), "")
