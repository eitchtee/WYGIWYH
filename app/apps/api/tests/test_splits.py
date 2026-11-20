import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.currencies.models import Currency
from apps.splits.models import SplitEvent, SplitExpense, SplitParticipant, SplitPayment
from apps.users.models import APIToken

User = get_user_model()


class SplitsAPITests(APITestCase):
    def setUp(self):
        self.brl = Currency.objects.create(code="BRL", name="Real", decimal_places=2)
        self.alice = User.objects.create_user(email="alice@example.com", password="x", first_name="Alice")
        self.bob = User.objects.create_user(email="bob@example.com", password="x", first_name="Bob")
        self.stranger = User.objects.create_user(email="eve@example.com", password="x")

        self.client.force_authenticate(self.alice)
        event = self.client.post(
            "/api/splits/events/", {"name": "Trip", "currency": self.brl.id}, format="json"
        ).json()
        self.event = SplitEvent.objects.get(id=event["id"])
        self.p_alice = self.event.participants.get(user=self.alice)
        self.p_bob = self._post(
            "/api/splits/participants/", {"event": self.event.id, "user": self.bob.id}
        ).json()["id"]
        self.p_ana = self._post(
            "/api/splits/participants/", {"event": self.event.id, "name": "Ana"}
        ).json()["id"]

    def _post(self, url, data, user=None):
        if user:
            self.client.force_authenticate(user)
        return self.client.post(url, data, format="json")

    def test_event_creation_adds_organizer_and_hides_events_from_strangers(self):
        self.assertTrue(self.p_alice.is_creator)
        self.assertEqual(self.event.participants.count(), 3)
        self.client.force_authenticate(self.stranger)
        self.assertEqual(self.client.get("/api/splits/events/").json()["count"], 0)
        self.assertEqual(self.client.get(f"/api/splits/events/{self.event.id}/summary/").status_code, 404)

    def test_only_organizer_edits_event_and_people(self):
        self.client.force_authenticate(self.bob)
        self.assertEqual(
            self.client.patch(f"/api/splits/events/{self.event.id}/", {"name": "X"}, format="json").status_code, 403
        )
        self.assertEqual(
            self._post("/api/splits/participants/", {"event": self.event.id, "name": "Zed"}).status_code, 403
        )

    def test_expense_shares_and_summary(self):
        # Equal split by default between all three
        resp = self._post(
            "/api/splits/expenses/",
            {"event": self.event.id, "description": "Dinner", "amount": "100", "date": "2026-11-20", "paid_by": self.p_alice.id},
            user=self.bob,  # any member can add
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(sorted(Decimal(s["amount"]) for s in resp.json()["shares"]), [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])

        # Exact amounts must add up
        bad = self._post(
            "/api/splits/expenses/",
            {
                "event": self.event.id, "description": "Taxi", "amount": "30", "date": "2026-11-20",
                "paid_by": self.p_bob, "split_type": "EXACT",
                "split_between": [{"participant": self.p_bob, "value": "10"}, {"participant": self.p_ana, "value": "10"}],
            },
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("split_between", bad.json())

        summary = self.client.get(f"/api/splits/events/{self.event.id}/summary/").json()
        balances = {b["participant"]: Decimal(b["balance"]) for b in summary["balances"]}
        self.assertEqual(balances[self.p_alice.id], Decimal("66.66"))
        self.assertEqual(sum(Decimal(t["amount"]) for t in summary["settle_up"]), Decimal("66.66"))

    def test_payment_rules(self):
        payment = {"event": self.event.id, "amount": "5", "date": "2026-11-20"}
        # Bob can't record a payment between Ana and Alice
        resp = self._post("/api/splits/payments/", {**payment, "from_participant": self.p_ana, "to_participant": self.p_alice.id}, user=self.bob)
        self.assertEqual(resp.status_code, 400)
        # ...but can record his own, and the organizer can record anyone's
        resp = self._post("/api/splits/payments/", {**payment, "from_participant": self.p_bob, "to_participant": self.p_alice.id})
        self.assertEqual(resp.status_code, 201)
        resp = self._post("/api/splits/payments/", {**payment, "from_participant": self.p_ana, "to_participant": self.p_bob}, user=self.alice)
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(SplitPayment.objects.count(), 2)

    def test_leave_and_remove(self):
        self._post("/api/splits/expenses/", {"event": self.event.id, "description": "x", "amount": "9", "date": "2026-11-20", "paid_by": self.p_ana})
        # Ana has history: can't be removed, only deactivated
        self.assertEqual(self.client.delete(f"/api/splits/participants/{self.p_ana}/").status_code, 400)
        # Bob leaves; deactivated because he shares in Ana's expense
        self.assertEqual(self._post(f"/api/splits/events/{self.event.id}/leave/", {}, user=self.bob).status_code, 204)
        self.assertFalse(SplitParticipant.objects.get(id=self.p_bob).is_active)
        self.assertEqual(self.client.get("/api/splits/events/").json()["count"], 0)
        # The organizer can't leave
        self.assertEqual(self._post(f"/api/splits/events/{self.event.id}/leave/", {}, user=self.alice).status_code, 403)

    @override_settings(MCP_ENABLED=True, PUBLIC_BASE_URL="https://money.example")
    def test_reachable_over_mcp(self):
        _token, raw = APIToken.objects.create_token(user=self.alice, name="mcp")
        self.client.force_authenticate(None)

        def tool(name, **arguments):
            body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
            resp = self.client.post("/mcp", json.dumps(body), content_type="application/json", HTTP_AUTHORIZATION=f"Token {raw}")
            result = resp.json()["result"]
            return result["isError"], json.loads(result["content"][0]["text"])

        _err, found = tool("search_api", query="splits summary")
        self.assertIn("/api/splits/events/{id}/summary/", [op["path"] for op in found])
        is_error, summary = tool("call_api", method="GET", path=f"/api/splits/events/{self.event.id}/summary/")
        self.assertFalse(is_error)
        self.assertEqual(summary["currency"], "BRL")
