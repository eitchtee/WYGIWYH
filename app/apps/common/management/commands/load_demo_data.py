"""Builds the demo dataset with every date relative to today.

Run on an empty database (the demo reset flushes first). Covers every feature:
multi-currency accounts, exchange rates, an ETF and Bitcoin tracked as
currencies with DCA strategies, transfers, a credit card using reference
dates, installment plans, recurring transactions, quick transactions, rules,
filter presets, muted/unpaid/archived/deactivated examples.
"""

import calendar
import random
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Account, AccountGroup
from apps.common.middleware.thread_local import delete_current_user, write_current_user
from apps.currencies.models import Currency, ExchangeRate
from apps.dca.models import DCAEntry, DCAStrategy
from apps.rules.models import TransactionRule, TransactionRuleAction
from apps.transactions.models import (
    FilterPreset,
    InstallmentPlan,
    QuickTransaction,
    RecurringTransaction,
    Transaction,
    TransactionCategory,
    TransactionEntity,
    TransactionTag,
)

DEMO_EMAIL = "demo@demo.com"
DEMO_PASSWORD = "wygiwyhdemo"
HISTORY_MONTHS = 12  # months of history before the current one

IN = Transaction.Type.INCOME
EX = Transaction.Type.EXPENSE


def q(value, places=2):
    return Decimal(str(value)).quantize(Decimal(1).scaleb(-places), ROUND_HALF_UP)


class Command(BaseCommand):
    help = "Loads demo data with dates relative to today. Expects an empty database."

    def handle(self, *args, **options):
        User = get_user_model()
        if User.objects.filter(email=DEMO_EMAIL).exists():
            if options["verbosity"]:
                self.stdout.write("Demo user already exists, skipping.")
            return

        self.today = timezone.localdate()
        self.rng = random.Random(42)  # same demo every day, only shifted in time

        with db_transaction.atomic():
            user = User.objects.create_user(
                email=DEMO_EMAIL,
                password=DEMO_PASSWORD,
                first_name="Demo",
                last_name="User",
            )
            # SharedObject/OwnedObject.save() pick the owner from here
            write_current_user(user)
            try:
                self._build(user)
            finally:
                delete_current_user()

        if options["verbosity"]:
            self.stdout.write(self.style.SUCCESS("Demo data loaded."))

    # ---------- helpers ----------

    def day(self, months, day):
        """Date `months` away from the current month, day clamped to the month."""
        first = self.today.replace(day=1) + relativedelta(months=months)
        last = calendar.monthrange(first.year, first.month)[1]
        return first.replace(day=min(day, last))

    def tx(self, account, kind, amount, when, description, category=None,
           tags=(), entities=(), reference=None, paid=None, mute=False, notes=""):
        t = Transaction.objects.create(
            account=account,
            type=kind,
            amount=amount,
            date=when,
            reference_date=(reference or when).replace(day=1),
            description=description,
            category=self.cats[category] if category else None,
            is_paid=(when <= self.today) if paid is None else paid,
            mute=mute,
            notes=notes,
        )
        if tags:
            t.tags.set([self.tags[n] for n in tags])
        if entities:
            t.entities.set([self.ents[n] for n in entities])
        return t

    def transfer(self, source, target, amount, when, description,
                 to_amount=None, mute=True, category=None):
        """Same shape as TransferForm.save(): an expense and an income."""
        out = self.tx(source, EX, amount, when, description, category, mute=mute)
        inc = self.tx(target, IN, to_amount or amount, when, description, category, mute=mute)
        inc.linked_transaction = out
        inc.save()
        out.linked_transaction = inc
        out.save()
        return out, inc

    def rate(self, series, months):
        return series[months + HISTORY_MONTHS]

    # ---------- data ----------

    def _build(self, user):
        today = self.today
        rng = self.rng

        # Currencies, including an ETF and airline miles tracked as currencies
        usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2, prefix="$ ")
        eur = Currency.objects.create(
            code="EUR", name="Euro", decimal_places=2, prefix="€ ", exchange_currency=usd
        )
        btc = Currency.objects.create(
            code="BTC", name="Bitcoin", decimal_places=8, prefix="₿ ", exchange_currency=usd
        )
        vwce = Currency.objects.create(
            code="VWCE", name="Vanguard FTSE All-World ETF", decimal_places=4,
            suffix=" VWCE", exchange_currency=eur,
        )
        miles = Currency.objects.create(
            code="MILES", name="Airline Miles", decimal_places=0, suffix=" mi",
            exchange_currency=usd,
        )

        # Monthly rate history so net worth charts move; index 0 = oldest month
        n = HISTORY_MONTHS + 1
        eur_usd = [q(1.06 + 0.04 * i / n + rng.uniform(-0.01, 0.01), 4) for i in range(n)]
        btc_usd = [q(58000 + 40000 * i / n + rng.uniform(-4000, 4000)) for i in range(n)]
        vwce_eur = [q(112 + 20 * i / n + rng.uniform(-2, 2)) for i in range(n)]
        for i in range(n):
            months = i - HISTORY_MONTHS
            first = self.day(months, 1)
            when = timezone.make_aware(datetime.combine(first, time(12)))
            if months == 0:
                when = timezone.now()  # latest rate is "today"
            for src, dst, series in [
                (eur, usd, eur_usd), (btc, usd, btc_usd), (vwce, eur, vwce_eur)
            ]:
                ExchangeRate.objects.create(
                    from_currency=src, to_currency=dst, rate=series[i], date=when
                )
        ExchangeRate.objects.create(
            from_currency=miles, to_currency=usd, rate=Decimal("0.012"),
            date=timezone.make_aware(datetime.combine(self.day(-HISTORY_MONTHS, 1), time(12))),
        )

        # Accounts
        everyday = AccountGroup.objects.create(name="Everyday")
        investing = AccountGroup.objects.create(name="Savings & Investing")
        rewards = AccountGroup.objects.create(name="Rewards")

        checking = Account.objects.create(name="Checking", group=everyday, currency=usd)
        card = Account.objects.create(name="Credit Card", group=everyday, currency=usd)
        cash = Account.objects.create(name="Cash Wallet", group=everyday, currency=usd)
        savings = Account.objects.create(
            name="High-Yield Savings", group=investing, currency=usd, is_asset=True
        )
        euro = Account.objects.create(
            name="Euro Account", group=investing, currency=eur, exchange_currency=usd
        )
        brokerage = Account.objects.create(
            name="Brokerage (VWCE)", group=investing, currency=vwce, is_asset=True
        )
        btc_wallet = Account.objects.create(
            name="Bitcoin Wallet", group=investing, currency=btc, is_asset=True
        )
        miles_acc = Account.objects.create(name="Airline Miles", group=rewards, currency=miles)
        old_bank = Account.objects.create(
            name="Old Bank (closed)", group=everyday, currency=usd, is_archived=True
        )

        self.cats = {
            name: TransactionCategory.objects.create(name=name)
            for name in [
                "Salary", "Freelance", "Interest", "Rent", "Groceries", "Dining",
                "Transport", "Utilities", "Subscriptions", "Health", "Travel",
                "Shopping", "Investments", "Fees", "Rewards", "Gifts", "Transfers",
            ]
        }
        self.cats["Cable TV"] = TransactionCategory.objects.create(
            name="Cable TV", active=False  # deactivated: hidden from new transactions
        )
        self.tags = {
            name: TransactionTag.objects.create(name=name)
            for name in ["essentials", "fun", "work", "home", "travel", "reimbursable"]
        }
        self.ents = {
            name: TransactionEntity.objects.create(name=name)
            for name in [
                "Acme Corp", "Northwind (client)", "Landlord", "Power & Light Co.",
                "FiberNet", "Fresh Market", "Corner Bistro", "Sushi House", "Uber",
                "City Transit", "StreamFlix", "Iron Gym", "Pharma Plus", "BuyMore",
                "Alex", "Sky Airlines",
            ]
        }

        btc_dca = DCAStrategy.objects.create(
            name="Bitcoin monthly", target_currency=btc, payment_currency=usd,
            notes="Buy $100 of Bitcoin every month, no matter the price.",
        )
        etf_dca = DCAStrategy.objects.create(
            name="World ETF (VWCE)", target_currency=vwce, payment_currency=eur,
            notes="€250 into a global index ETF every month.",
        )

        # Installment plans and recurring transactions first, so card statements
        # below include them
        laptop = InstallmentPlan.objects.create(
            account=card, type=EX, description="New laptop", number_of_installments=12,
            start_date=self.day(-4, 14), recurrence=InstallmentPlan.Recurrence.MONTHLY,
            installment_amount=Decimal("108.25"), category=self.cats["Shopping"],
            notes="12 interest-free installments on the credit card.",
        )
        laptop.entities.set([self.ents["BuyMore"]])
        laptop.create_transactions()
        dental = InstallmentPlan.objects.create(
            account=checking, type=EX, description="Dental treatment",
            number_of_installments=3, start_date=self.day(-1, 16),
            recurrence=InstallmentPlan.Recurrence.MONTHLY,
            installment_amount=Decimal("240.00"), category=self.cats["Health"],
        )
        dental.create_transactions()

        # Recurring transactions
        def recurring(account, amount, description, category, start, entity=None,
                      recurrence=RecurringTransaction.RecurrenceType.MONTH, paused=False):
            r = RecurringTransaction.objects.create(
                account=account, type=EX, amount=amount, description=description,
                category=self.cats[category], start_date=start, recurrence_type=recurrence,
                recurrence_interval=1, keep_at_most=3, is_paused=paused,
            )
            if entity:
                r.entities.set([self.ents[entity]])
            if not paused:
                r.create_upcoming_transactions()
            return r

        recurring(card, Decimal("15.99"), "StreamFlix", "Subscriptions",
                  self.day(-HISTORY_MONTHS, 3), "StreamFlix")
        recurring(checking, Decimal("59.99"), "Internet", "Utilities",
                  self.day(-HISTORY_MONTHS, 15), "FiberNet")
        recurring(checking, Decimal("39.90"), "Gym membership", "Health",
                  self.day(-HISTORY_MONTHS, 2), "Iron Gym")
        recurring(card, Decimal("14.99"), "Domain renewal", "Subscriptions",
                  self.day(-10, 9), recurrence=RecurringTransaction.RecurrenceType.YEAR)
        recurring(card, Decimal("6.99"), "Magazine subscription", "Subscriptions",
                  self.day(-3, 11), paused=True)

        # Work trip paid on the card, muted so it stays out of monthly totals
        self.tx(card, EX, Decimal("230.00"), self.day(-2, 9), "Client visit (reimbursable)",
                "Travel", ["work", "reimbursable"], mute=True,
                notes="Muted: Acme pays this back, so it shouldn't count as spending.")
        self.tx(checking, IN, Decimal("230.00"), self.day(-1, 5), "Expense reimbursement",
                tags=["work", "reimbursable"], entities=["Acme Corp"], mute=True)

        # ---- month by month ----
        for m in range(-HISTORY_MONTHS, 2):
            past_or_current = m <= 0

            self.tx(checking, IN, Decimal("5400.00") if m >= -6 else Decimal("5100.00"),
                    self.day(m, 5), "Salary", "Salary", ["work"], ["Acme Corp"])
            self.tx(checking, EX, Decimal("1650.00"), self.day(m, 1), "Rent", "Rent",
                    ["home", "essentials"], ["Landlord"])
            self.tx(checking, EX, q(rng.uniform(70, 135)), self.day(m, 12), "Electricity bill",
                    "Utilities", ["home", "essentials"], ["Power & Light Co."])
            self.transfer(checking, savings, Decimal("600.00"), self.day(m, 6),
                          "Monthly savings", category="Transfers")

            if not past_or_current:
                continue

            # Credit card: closes on the 25th, later purchases count for next month
            for _ in range(rng.randint(5, 7)):
                d = self.day(m, rng.randint(1, 28))
                if d > today:
                    continue
                kind = rng.choice(["groceries", "groceries", "dining", "uber", "shopping"])
                ref = self.day(m + 1, 1) if d.day > 25 else d
                if kind == "groceries":
                    self.tx(card, EX, q(rng.uniform(45, 160)), d, "Groceries", "Groceries",
                            ["essentials"], ["Fresh Market"], reference=ref)
                elif kind == "dining":
                    place = rng.choice(["Corner Bistro", "Sushi House"])
                    self.tx(card, EX, q(rng.uniform(28, 95)), d, f"Dinner at {place}", "Dining",
                            ["fun"], [place], reference=ref)
                elif kind == "uber":
                    self.tx(card, EX, q(rng.uniform(9, 32)), d, "Uber ride", "Transport",
                            entities=["Uber"], reference=ref)
                else:
                    self.tx(card, EX, q(rng.uniform(25, 140)), d, "Household stuff", "Shopping",
                            ["home"], ["BuyMore"], reference=ref)

            # Pay last month's card statement (a transfer between your own accounts)
            statement = sum(
                Transaction.objects.filter(
                    account=card, type=EX, reference_date=self.day(m - 1, 1)
                ).values_list("amount", flat=True),
                Decimal("0"),
            )
            if statement:
                self.transfer(checking, card, statement, self.day(m, 10),
                              "Credit card payment", category="Transfers")

            # Miles earned on card spending; small cash expenses
            if self.day(m, 27) <= today:
                self.tx(miles_acc, IN, Decimal(rng.randint(400, 900)), self.day(m, 27),
                        "Miles earned on card spending", "Rewards", entities=["Sky Airlines"])
            for _ in range(2):
                d = self.day(m, rng.randint(1, 28))
                if d <= today:
                    self.tx(cash, EX, q(rng.choice([3.5, 4.25, 4.5, 2.75])), d,
                            rng.choice(["Coffee", "Bus ticket"]),
                            rng.choice(["Dining", "Transport"]))

            # Interest on savings
            if self.day(m, 28) <= today:
                self.tx(savings, IN, q(rng.uniform(18, 32)), self.day(m, 28),
                        "Savings interest", "Interest")

            # Bitcoin DCA: $100 per month at that month's price
            d = self.day(m, 22)
            if d <= today:
                price = self.rate(btc_usd, m)
                sats = q(Decimal(100) / price, 8)
                out, inc = self.transfer(checking, btc_wallet, Decimal("100.00"), d,
                                         "Bitcoin DCA", to_amount=sats, mute=False,
                                         category="Investments")
                DCAEntry.objects.create(strategy=btc_dca, date=d, amount_paid=Decimal("100.00"),
                                        amount_received=sats, expense_transaction=out,
                                        income_transaction=inc)

            # ETF DCA: €250 per month from the Euro account
            d = self.day(m, 20)
            if d <= today:
                price = self.rate(vwce_eur, m)
                shares = q(Decimal(250) / price, 4)
                out, inc = self.transfer(euro, brokerage, Decimal("250.00"), d,
                                         "Buy VWCE", to_amount=shares, mute=False,
                                         category="Investments")
                DCAEntry.objects.create(strategy=etf_dca, date=d, amount_paid=Decimal("250.00"),
                                        amount_received=shares, expense_transaction=out,
                                        income_transaction=inc)
                self.tx(euro, EX, Decimal("1.50"), d, "Broker fee", "Fees")

            # Every 3 months: convert dollars to euros at that month's rate
            if m % 3 == 0 and self.day(m, 7) <= today:
                usd_amount = Decimal("1000.00")
                self.transfer(checking, euro, usd_amount, self.day(m, 7),
                              "Currency exchange USD → EUR",
                              to_amount=q(usd_amount / self.rate(eur_usd, m)),
                              category="Transfers")

            # Freelance paid in euros, every other month
            if m % 2 == 0 and self.day(m, 15) <= today:
                self.tx(euro, IN, q(rng.choice([650, 800, 1200])), self.day(m, 15),
                        "Freelance project", "Freelance", ["work"], ["Northwind (client)"])

            # ATM withdrawal every other month
            if m % 2 == 1 and self.day(m, 3) <= today:
                self.transfer(checking, cash, Decimal("100.00"), self.day(m, 3),
                              "ATM withdrawal", category="Transfers")

        # ---- one-offs ----
        self.tx(miles_acc, IN, Decimal("30000"), self.day(-HISTORY_MONTHS, 4),
                "Credit card sign-up bonus", "Rewards", entities=["Sky Airlines"])
        trip = -5
        self.tx(miles_acc, EX, Decimal("25000"), self.day(trip, 2), "Flight to Lisbon",
                "Travel", ["travel"], ["Sky Airlines"], notes="Paid entirely with miles!")
        self.tx(euro, EX, Decimal("420.00"), self.day(trip, 14), "Hotel in Lisbon", "Travel",
                ["travel", "fun"])
        self.tx(euro, EX, Decimal("96.40"), self.day(trip, 15), "Pastéis & dinners", "Dining",
                ["travel", "fun"])
        # Someone owes you: unpaid income in the past shows up as late
        self.tx(checking, IN, Decimal("85.00"), self.day(-1, 20),
                "Alex owes me for concert tickets", "Gifts", entities=["Alex"], paid=False,
                notes="Unpaid income is a projection until you mark it as paid.")
        # Upcoming expense that isn't paid yet
        self.tx(checking, EX, Decimal("612.00"), self.day(1, 18), "Car insurance (yearly)",
                "Transport", ["essentials"])
        # Cancelled service on a deactivated category
        self.tx(checking, EX, Decimal("49.90"), self.day(-HISTORY_MONTHS, 8), "Cable TV",
                "Cable TV", ["home"])
        # Archived account with its history and the move out of it
        self.tx(old_bank, IN, Decimal("1200.00"), date(2015, 3, 2), "Opening balance",
                notes="Very old transactions are no problem.")
        self.transfer(old_bank, checking, Decimal("1200.00"), self.day(-HISTORY_MONTHS, 3),
                      "Closing old bank account", category="Transfers")
        # Balance reconciliation: the wallet had less cash than recorded
        self.tx(cash, EX, Decimal("12.40"), self.day(-2, 28), "Balance reconciliation")

        # Generated occurrences start unpaid; everything up to today happened already
        Transaction.objects.filter(date__lte=today, is_paid=False).filter(
            Q(installment_plan__isnull=False) | Q(recurring_transaction__isnull=False)
        ).update(is_paid=True)

        # Quick transactions: one-click templates
        QuickTransaction.objects.create(
            name="Coffee", account=cash, type=EX, amount=Decimal("4.50"),
            description="Coffee", category=self.cats["Dining"],
        )
        QuickTransaction.objects.create(
            name="Bus ticket", account=cash, type=EX, amount=Decimal("2.75"),
            description="Bus ticket", category=self.cats["Transport"],
        )
        lunch = QuickTransaction.objects.create(
            name="Lunch near the office", account=card, type=EX, amount=Decimal("13.90"),
            description="Lunch", category=self.cats["Dining"],
        )
        lunch.tags.set([self.tags["work"]])

        # Rules run on transactions you create or edit
        ride = TransactionRule.objects.create(
            name="Ride-hailing is Transport",
            description="Categorize Uber and Lyft rides automatically.",
            trigger="'uber' in description.lower() or 'lyft' in description.lower()",
        )
        TransactionRuleAction.objects.create(rule=ride, field="category", value="'Transport'")
        TransactionRuleAction.objects.create(rule=ride, field="entities", value="['Uber']")
        big = TransactionRule.objects.create(
            name="Flag big expenses",
            description="Add a reminder to expenses of $500 or more.",
            trigger="is_expense and amount >= 500",
        )
        TransactionRuleAction.objects.create(
            rule=big, field="notes", value="'Big expense: keep the receipt!'"
        )

        # Saved filters for the transactions page
        FilterPreset.objects.create(owner=user, name="Unpaid", parameters={"is_paid": ["0"]})
        FilterPreset.objects.create(
            owner=user, name="Credit card", parameters={"account": [str(card.id)]}
        )
