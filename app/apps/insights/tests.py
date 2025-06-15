from django.test import TestCase
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from decimal import Decimal
from datetime import date, timedelta

from apps.accounts.models import Account, AccountGroup
from apps.currencies.models import Currency
from apps.transactions.models import TransactionCategory, Transaction
from apps.insights.utils.category_explorer import get_category_sums_by_account, get_category_sums_by_currency
from apps.insights.utils.sankey import generate_sankey_data_by_account

class InsightsUtilsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testinsightsuser', password='password')

        self.currency_usd = Currency.objects.create(code="USD", name="US Dollar", decimal_places=2)
        self.currency_eur = Currency.objects.create(code="EUR", name="Euro", decimal_places=2)

        # It's good practice to have an AccountGroup for accounts
        self.account_group = AccountGroup.objects.create(name="Test Group", owner=self.user)

        self.category_food = TransactionCategory.objects.create(name="Food", owner=self.user, type=TransactionCategory.TransactionType.EXPENSE)
        self.category_salary = TransactionCategory.objects.create(name="Salary", owner=self.user, type=TransactionCategory.TransactionType.INCOME)

        self.account_usd_1 = Account.objects.create(name="USD Account 1", owner=self.user, currency=self.currency_usd, group=self.account_group)
        self.account_usd_2 = Account.objects.create(name="USD Account 2", owner=self.user, currency=self.currency_usd, group=self.account_group)
        self.account_eur_1 = Account.objects.create(name="EUR Account 1", owner=self.user, currency=self.currency_eur, group=self.account_group)

        today = date.today()

        # T1: Acc USD1, Food, Expense 50 (paid)
        Transaction.objects.create(
            description="Groceries USD1 Food Paid", account=self.account_usd_1, category=self.category_food,
            type=Transaction.Type.EXPENSE, amount=Decimal('50.00'), date=today, is_paid=True, owner=self.user
        )
        # T2: Acc USD1, Food, Expense 20 (unpaid/projected)
        Transaction.objects.create(
            description="Restaurant USD1 Food Unpaid", account=self.account_usd_1, category=self.category_food,
            type=Transaction.Type.EXPENSE, amount=Decimal('20.00'), date=today, is_paid=False, owner=self.user
        )
        # T3: Acc USD2, Food, Expense 30 (paid)
        Transaction.objects.create(
            description="Snacks USD2 Food Paid", account=self.account_usd_2, category=self.category_food,
            type=Transaction.Type.EXPENSE, amount=Decimal('30.00'), date=today, is_paid=True, owner=self.user
        )
        # T4: Acc USD1, Salary, Income 1000 (paid)
        Transaction.objects.create(
            description="Salary USD1 Paid", account=self.account_usd_1, category=self.category_salary,
            type=Transaction.Type.INCOME, amount=Decimal('1000.00'), date=today, is_paid=True, owner=self.user
        )
        # T5: Acc EUR1, Food, Expense 40 (paid, different currency)
        Transaction.objects.create(
            description="Groceries EUR1 Food Paid", account=self.account_eur_1, category=self.category_food,
            type=Transaction.Type.EXPENSE, amount=Decimal('40.00'), date=today, is_paid=True, owner=self.user
        )
        # T6: Acc USD2, Salary, Income 200 (unpaid/projected)
        Transaction.objects.create(
            description="Bonus USD2 Salary Unpaid", account=self.account_usd_2, category=self.category_salary,
            type=Transaction.Type.INCOME, amount=Decimal('200.00'), date=today, is_paid=False, owner=self.user
        )

    def test_get_category_sums_by_account_for_food(self):
        qs = Transaction.objects.filter(owner=self.user) # Filter by user for safety in shared DB environments
        result = get_category_sums_by_account(qs, category=self.category_food)

        expected_labels = sorted([self.account_eur_1.name, self.account_usd_1.name, self.account_usd_2.name])
        self.assertEqual(result['labels'], expected_labels)

        # Expected data structure: {account_name: {'current_income': D('0'), ...}, ...}
        # Then the util function transforms this.
        # Let's map labels to their expected index for easier assertion
        label_to_idx = {name: i for i, name in enumerate(expected_labels)}

        # Initialize expected data arrays based on sorted labels length
        num_labels = len(expected_labels)
        expected_current_income = [Decimal('0.00')] * num_labels
        expected_current_expenses = [Decimal('0.00')] * num_labels
        expected_projected_income = [Decimal('0.00')] * num_labels
        expected_projected_expenses = [Decimal('0.00')] * num_labels

        # Populate expected data based on transactions for FOOD category
        # T1: Acc USD1, Food, Expense 50 (paid) -> account_usd_1, current_expenses = -50
        expected_current_expenses[label_to_idx[self.account_usd_1.name]] = Decimal('-50.00')
        # T2: Acc USD1, Food, Expense 20 (unpaid/projected) -> account_usd_1, projected_expenses = -20
        expected_projected_expenses[label_to_idx[self.account_usd_1.name]] = Decimal('-20.00')
        # T3: Acc USD2, Food, Expense 30 (paid) -> account_usd_2, current_expenses = -30
        expected_current_expenses[label_to_idx[self.account_usd_2.name]] = Decimal('-30.00')
        # T5: Acc EUR1, Food, Expense 40 (paid) -> account_eur_1, current_expenses = -40
        expected_current_expenses[label_to_idx[self.account_eur_1.name]] = Decimal('-40.00')

        self.assertEqual(result['datasets'][0]['data'], [float(x) for x in expected_current_income]) # Current Income
        self.assertEqual(result['datasets'][1]['data'], [float(x) for x in expected_current_expenses]) # Current Expenses
        self.assertEqual(result['datasets'][2]['data'], [float(x) for x in expected_projected_income]) # Projected Income
        self.assertEqual(result['datasets'][3]['data'], [float(x) for x in expected_projected_expenses]) # Projected Expenses

        self.assertEqual(result['datasets'][0]['label'], "Current Income")
        self.assertEqual(result['datasets'][1]['label'], "Current Expenses")
        self.assertEqual(result['datasets'][2]['label'], "Projected Income")
        self.assertEqual(result['datasets'][3]['label'], "Projected Expenses")

    def test_generate_sankey_data_by_account(self):
        qs = Transaction.objects.filter(owner=self.user)
        result = generate_sankey_data_by_account(qs)

        nodes = result['nodes']
        flows = result['flows']

        # Helper to find a node by a unique part of its ID
        def find_node_by_id_part(id_part):
            found_nodes = [n for n in nodes if id_part in n['id']]
            self.assertEqual(len(found_nodes), 1, f"Node with ID part '{id_part}' not found or not unique. Found: {found_nodes}")
            return found_nodes[0]

        # Helper to find a flow by unique parts of its source and target node IDs
        def find_flow_by_node_id_parts(from_id_part, to_id_part):
            found_flows = [
                f for f in flows
                if from_id_part in f['from_node'] and to_id_part in f['to_node']
            ]
            self.assertEqual(len(found_flows), 1, f"Flow from '{from_id_part}' to '{to_id_part}' not found or not unique. Found: {found_flows}")
            return found_flows[0]

        # Calculate total volumes by currency (sum of absolute amounts of ALL transactions)
        total_volume_usd = sum(abs(t.amount) for t in qs if t.account.currency == self.currency_usd) # 50+20+30+1000+200 = 1300
        total_volume_eur = sum(abs(t.amount) for t in qs if t.account.currency == self.currency_eur) # 40

        self.assertEqual(total_volume_usd, Decimal('1300.00'))
        self.assertEqual(total_volume_eur, Decimal('40.00'))

        # --- Assertions for Account USD 1 ---
        acc_usd_1_id_part = f"_{self.account_usd_1.id}"

        node_income_salary_usd1 = find_node_by_id_part(f"income_{self.category_salary.name.lower()}{acc_usd_1_id_part}")
        self.assertEqual(node_income_salary_usd1['name'], self.category_salary.name)

        node_account_usd1 = find_node_by_id_part(f"account_{self.account_usd_1.name.lower().replace(' ', '_')}{acc_usd_1_id_part}")
        self.assertEqual(node_account_usd1['name'], self.account_usd_1.name)

        node_expense_food_usd1 = find_node_by_id_part(f"expense_{self.category_food.name.lower()}{acc_usd_1_id_part}")
        self.assertEqual(node_expense_food_usd1['name'], self.category_food.name)

        node_saved_usd1 = find_node_by_id_part(f"savings_saved{acc_usd_1_id_part}")
        self.assertEqual(node_saved_usd1['name'], _("Saved"))

        # Flow 1: Salary (T4) to account_usd_1
        flow_salary_to_usd1 = find_flow_by_node_id_parts(node_income_salary_usd1['id'], node_account_usd1['id'])
        self.assertEqual(flow_salary_to_usd1['original_amount'], 1000.0)
        self.assertEqual(flow_salary_to_usd1['currency']['code'], self.currency_usd.code)
        self.assertAlmostEqual(flow_salary_to_usd1['percentage'], (1000.0 / float(total_volume_usd)) * 100, places=2)
        self.assertAlmostEqual(flow_salary_to_usd1['flow'], (1000.0 / float(total_volume_usd)), places=4)

        # Flow 2: account_usd_1 to Food (T1)
        flow_usd1_to_food = find_flow_by_node_id_parts(node_account_usd1['id'], node_expense_food_usd1['id'])
        self.assertEqual(flow_usd1_to_food['original_amount'], 50.0) # T1 is 50
        self.assertEqual(flow_usd1_to_food['currency']['code'], self.currency_usd.code)
        self.assertAlmostEqual(flow_usd1_to_food['percentage'], (50.0 / float(total_volume_usd)) * 100, places=2)

        # Flow 3: account_usd_1 to Saved
        # Net paid for account_usd_1: 1000 (T4 income) - 50 (T1 expense) = 950
        flow_usd1_to_saved = find_flow_by_node_id_parts(node_account_usd1['id'], node_saved_usd1['id'])
        self.assertEqual(flow_usd1_to_saved['original_amount'], 950.0)
        self.assertEqual(flow_usd1_to_saved['currency']['code'], self.currency_usd.code)
        self.assertAlmostEqual(flow_usd1_to_saved['percentage'], (950.0 / float(total_volume_usd)) * 100, places=2)

        # --- Assertions for Account USD 2 ---
        acc_usd_2_id_part = f"_{self.account_usd_2.id}"
        node_account_usd2 = find_node_by_id_part(f"account_{self.account_usd_2.name.lower().replace(' ', '_')}{acc_usd_2_id_part}")
        node_expense_food_usd2 = find_node_by_id_part(f"expense_{self.category_food.name.lower()}{acc_usd_2_id_part}")
        # T6 (Salary for USD2) is unpaid, so no income node/flow for it.
        # Net paid for account_usd_2 is -30 (T3 expense). So no "Saved" node.

        # Flow: account_usd_2 to Food (T3)
        flow_usd2_to_food = find_flow_by_node_id_parts(node_account_usd2['id'], node_expense_food_usd2['id'])
        self.assertEqual(flow_usd2_to_food['original_amount'], 30.0) # T3 is 30
        self.assertEqual(flow_usd2_to_food['currency']['code'], self.currency_usd.code)
        self.assertAlmostEqual(flow_usd2_to_food['percentage'], (30.0 / float(total_volume_usd)) * 100, places=2)

        # Check no "Saved" node for account_usd_2
        saved_nodes_usd2 = [n for n in nodes if f"savings_saved{acc_usd_2_id_part}" in n['id']]
        self.assertEqual(len(saved_nodes_usd2), 0, "Should be no 'Saved' node for account_usd_2 as net is negative.")

        # --- Assertions for Account EUR 1 ---
        acc_eur_1_id_part = f"_{self.account_eur_1.id}"
        node_account_eur1 = find_node_by_id_part(f"account_{self.account_eur_1.name.lower().replace(' ', '_')}{acc_eur_1_id_part}")
        node_expense_food_eur1 = find_node_by_id_part(f"expense_{self.category_food.name.lower()}{acc_eur_1_id_part}")
        # Net paid for account_eur_1 is -40 (T5 expense). No "Saved" node.

        # Flow: account_eur_1 to Food (T5)
        flow_eur1_to_food = find_flow_by_node_id_parts(node_account_eur1['id'], node_expense_food_eur1['id'])
        self.assertEqual(flow_eur1_to_food['original_amount'], 40.0) # T5 is 40
        self.assertEqual(flow_eur1_to_food['currency']['code'], self.currency_eur.code)
        self.assertAlmostEqual(flow_eur1_to_food['percentage'], (40.0 / float(total_volume_eur)) * 100, places=2) # (40/40)*100 = 100%

        # Check no "Saved" node for account_eur_1
        saved_nodes_eur1 = [n for n in nodes if f"savings_saved{acc_eur_1_id_part}" in n['id']]
        self.assertEqual(len(saved_nodes_eur1), 0, "Should be no 'Saved' node for account_eur_1 as net is negative.")

    def test_get_category_sums_by_currency_for_food(self):
        qs = Transaction.objects.filter(owner=self.user)
        result = get_category_sums_by_currency(qs, category=self.category_food)

        expected_labels = sorted([self.currency_eur.name, self.currency_usd.name])
        self.assertEqual(result['labels'], expected_labels)

        label_to_idx = {name: i for i, name in enumerate(expected_labels)}
        num_labels = len(expected_labels)

        expected_current_income = [Decimal('0.00')] * num_labels
        expected_current_expenses = [Decimal('0.00')] * num_labels
        expected_projected_income = [Decimal('0.00')] * num_labels
        expected_projected_expenses = [Decimal('0.00')] * num_labels

        # Food Transactions:
        # T1: USD Account 1, Food, Expense 50 (paid)
        # T2: USD Account 1, Food, Expense 20 (unpaid/projected)
        # T3: USD Account 2, Food, Expense 30 (paid)
        # T5: EUR Account 1, Food, Expense 40 (paid)

        # Current Expenses:
        expected_current_expenses[label_to_idx[self.currency_eur.name]] = Decimal('-40.00') # T5
        expected_current_expenses[label_to_idx[self.currency_usd.name]] = Decimal('-50.00') + Decimal('-30.00') # T1 + T3

        # Projected Expenses:
        expected_projected_expenses[label_to_idx[self.currency_usd.name]] = Decimal('-20.00') # T2

        self.assertEqual(result['datasets'][0]['data'], [float(x) for x in expected_current_income])
        self.assertEqual(result['datasets'][1]['data'], [float(x) for x in expected_current_expenses])
        self.assertEqual(result['datasets'][2]['data'], [float(x) for x in expected_projected_income])
        self.assertEqual(result['datasets'][3]['data'], [float(x) for x in expected_projected_expenses])

        self.assertEqual(result['datasets'][0]['label'], "Current Income")
        self.assertEqual(result['datasets'][1]['label'], "Current Expenses")
        self.assertEqual(result['datasets'][2]['label'], "Projected Income")
        self.assertEqual(result['datasets'][3]['label'], "Projected Expenses")

    def test_get_category_sums_by_currency_for_salary(self):
        qs = Transaction.objects.filter(owner=self.user)
        result = get_category_sums_by_currency(qs, category=self.category_salary)

        # Salary Transactions:
        # T4: USD Account 1, Salary, Income 1000 (paid)
        # T6: USD Account 2, Salary, Income 200 (unpaid/projected)
        # All are USD
        expected_labels = [self.currency_usd.name] # Only USD has salary transactions
        self.assertEqual(result['labels'], expected_labels)

        label_to_idx = {name: i for i, name in enumerate(expected_labels)}
        num_labels = len(expected_labels)

        expected_current_income = [Decimal('0.00')] * num_labels
        expected_current_expenses = [Decimal('0.00')] * num_labels
        expected_projected_income = [Decimal('0.00')] * num_labels
        expected_projected_expenses = [Decimal('0.00')] * num_labels

        # Current Income:
        expected_current_income[label_to_idx[self.currency_usd.name]] = Decimal('1000.00') # T4

        # Projected Income:
        expected_projected_income[label_to_idx[self.currency_usd.name]] = Decimal('200.00') # T6

        self.assertEqual(result['datasets'][0]['data'], [float(x) for x in expected_current_income])
        self.assertEqual(result['datasets'][1]['data'], [float(x) for x in expected_current_expenses])
        self.assertEqual(result['datasets'][2]['data'], [float(x) for x in expected_projected_income])
        self.assertEqual(result['datasets'][3]['data'], [float(x) for x in expected_projected_expenses])

        self.assertEqual(result['datasets'][0]['label'], "Current Income")
        self.assertEqual(result['datasets'][1]['label'], "Current Expenses")
        self.assertEqual(result['datasets'][2]['label'], "Projected Income")
        self.assertEqual(result['datasets'][3]['label'], "Projected Expenses")


    def test_get_category_sums_by_account_for_salary(self):
        qs = Transaction.objects.filter(owner=self.user)
        result = get_category_sums_by_account(qs, category=self.category_salary)

        # Only accounts with salary transactions should appear
        expected_labels = sorted([self.account_usd_1.name, self.account_usd_2.name])
        self.assertEqual(result['labels'], expected_labels)

        label_to_idx = {name: i for i, name in enumerate(expected_labels)}
        num_labels = len(expected_labels)

        expected_current_income = [Decimal('0.00')] * num_labels
        expected_current_expenses = [Decimal('0.00')] * num_labels
        expected_projected_income = [Decimal('0.00')] * num_labels
        expected_projected_expenses = [Decimal('0.00')] * num_labels

        # Populate expected data based on transactions for SALARY category
        # T4: Acc USD1, Salary, Income 1000 (paid) -> account_usd_1, current_income = 1000
        expected_current_income[label_to_idx[self.account_usd_1.name]] = Decimal('1000.00')
        # T6: Acc USD2, Salary, Income 200 (unpaid/projected) -> account_usd_2, projected_income = 200
        expected_projected_income[label_to_idx[self.account_usd_2.name]] = Decimal('200.00')

        self.assertEqual(result['datasets'][0]['data'], [float(x) for x in expected_current_income])
        self.assertEqual(result['datasets'][1]['data'], [float(x) for x in expected_current_expenses])
        self.assertEqual(result['datasets'][2]['data'], [float(x) for x in expected_projected_income])
        self.assertEqual(result['datasets'][3]['data'], [float(x) for x in expected_projected_expenses])

        self.assertEqual(result['datasets'][0]['label'], "Current Income")
        self.assertEqual(result['datasets'][1]['label'], "Current Expenses")
        self.assertEqual(result['datasets'][2]['label'], "Projected Income")
        self.assertEqual(result['datasets'][3]['label'], "Projected Expenses")
