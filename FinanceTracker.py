2# StudentSpend
# College Student Financial Tracker

print("=====================================")
print("          STUDENTSPEND")
print("     College Financial Tracker")
print("=====================================")

print("\nWelcome to StudentSpend!")

# Stores all financial transactions
transactions = []

# Main Menu
while True:

    print("\n=====================================")
    print("             MAIN MENU")
    print("=====================================")

    print("\n1. Add Income")
    print("2. Add Expense")
    print("3. View Current Balance")
    print("4. View Transaction History")
    print("5. Set Monthly Budget")
    print("6. View Spending Summary")
    print("7. Exit")

    choice = input("\nPlease select an option: ")

    # Option 1: Add Income
    if choice == "1":
        print("\n========== ADD INCOME ==========")

        source = input("Enter income source: ")
        amount = float(input("Enter income amount: $"))

        transaction = {
            "type": "income",
            "source": source,
            "amount": amount
        }

        transactions.append(transaction)

        print("\nIncome successfully recorded!")

    # Option 2: Add Expense
    elif choice == "2":
        print("\n========== ADD EXPENSE ==========")

        source = input("What did you purchase? ")
        category = input("Enter expense category: ")
        amount = float(input("Enter expense amount: $"))

        transaction = {
            "type": "expense",
            "source": source,
            "category": category,
            "amount": amount
        }

        transactions.append(transaction)

        print("\nExpense successfully recorded!")

    # Option 3: View Current Balance
    elif choice == "3":
        print("\nYou selected View Current Balance!")

    # Option 4: View Transaction History
    elif choice == "4":
        print("\nYou selected Transaction History!")

    # Option 5: Set Monthly Budget
    elif choice == "5":
        print("\nYou selected Set Monthly Budget!")

    # Option 6: View Spending Summary
    elif choice == "6":
        print("\nYou selected Spending Summary!")

    # Option 7: Exit
    elif choice == "7":
        print("\nThank you for using FinanceTracker!")
        break

    # Invalid menu selection
    else:
        print("\nInvalid selection. Please try again.")
