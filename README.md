<h1 align="center">
  <br>
  <img alt="WYGIWYH" title="WYGIWYH" src="./.github/img/logo.png" />
  <br>
  WYGIWYH
  <br>
</h1>

<h4 align="center">An optionated and powerful finance tracker.</h4>

<p align="center">
  <a href="#why-wygiwyh">Why</a> •
  <a href="#key-features">Features</a> •
  <a href="#how-to-use">Usage</a> •
  <a href="#how-it-works">How</a>
</p>

**WYGIWYH** (_What You Get Is What You Have_) is a powerful, principles-first finance tracker designed for people who prefer a no-budget, straightforward approach to managing their money. With features like multi-currency support, customizable transactions, and a built-in dollar-cost averaging tracker, WYGIWYH helps you take control of your finances with simplicity and flexibility.

# Why WYGIWYH?
Managing money can feel unnecessarily complex, but it doesn’t have to be. WYGIWYH (pronounced "wiggy-wih") is based on a simple principle:

> Use what you earn this month for this month. Any savings are tracked but treated as untouchable for future months.

By sticking to this straightforward approach, you avoid dipping into your savings while still keeping tabs on where your money goes.

While this philosophy is simple, finding tools to make it work wasn’t. I initially used a spreadsheet, which served me well for years—until it became unwieldy as I started managing multiple currencies, accounts, and investments. I tried various financial management apps, but none met my key requirements:

1. **Multi-currency support** to track income and expenses in different currencies.
2. **Not a budgeting app** — as I dislike budgeting constraints.
3. **Web app usability** (ideally with mobile support, though optional).
4. **Automation-ready API** to integrate with other tools and services.
5. **Custom transaction rules** for credit card billing cycles or similar quirks.

Frustrated by the lack of comprehensive options, I set out to build **WYGIWYH** — an opinionated yet powerful tool that I believe will resonate with like-minded users.

# Key Features

**WYGIWYH** offers an array of features designed to simplify and streamline your personal finance tracking:

* **Unified transaction tracking**: Record all your income and expenses, organized in one place.
* **Multiple accounts support**: Keep track of where your money and assets are stored (banks, wallets, investments, etc.).
* **Out-of-the-box multi-currency support**: Dynamically manage transactions and balances in different currencies.
* **Custom currencies**: Create your own currencies for crypto, rewards points, or any other models.
* **Automated adjustments with rules**: Automatically modify transactions using customizable rules.
* **Built-in Dollar-Cost Average (DCA) tracker**: Essential for tracking recurring investments, especially for crypto and stocks.
* **API support for automation**: Seamlessly integrate with existing services to synchronize transactions.

# How To Use

To run this application, you'll need [Docker](https://docs.docker.com/engine/install/) with [docker-compose](https://docs.docker.com/compose/install/).

From your command line:

```bash
# Clone this repository
$ mkdir WYGIWYH

# Go into the repository
$ cd WYGIWYH

$ touch docker-compose.yml
$ nano docker-compose.yml
# Paste the contents of https://github.com/eitchtee/WYGIWYH/blob/main/docker-compose.prod.yml and edit according to your needs

# Fill the .env file with your configurations
$ touch .env
$ nano .env # or any other editor you want to use
# Paste the contents of https://github.com/eitchtee/WYGIWYH/blob/main/.env.example and edit accordingly

# Run the app
$ docker compose up -d

# Create the first admin account
$ docker compose exec -it web python manage.py createsuperuser
```

# How it works

## Models

### Transactions

Transactions are the core feature of WYGIWYH, representing expenses or income in your accounts. Each transaction consists of the following fields:

#### Type

- **Income**: A positive amount entering your account
- **Expense**: A negative amount exiting your account

#### Paid Status

A transaction can be either:

- **Current**: When marked as paid
- **Projected**: When marked as unpaid

#### Account

The account associated with the transaction. Required, limited to one account per transaction.

#### Entity

The party involved in the transaction:

- For **Income**: The paying entity
- For **Expense**: The receiving entity

Optional field.

#### Date

The date when the transaction occurred. Required.

#### Reference Date

One of **WYGIWYH**'s key features. The reference date determines which month a transaction should count towards. For example, you can have a transaction that occurred on January 26th count towards February's finances.

Optional - defaults to the transaction date's month if not specified.

> [!CAUTION]
> While designed primarily for credit card closing dates, this feature allows for debt rolling across months. Use responsibly to maintain accurate financial tracking.

#### Type

- Income, meaning a positive amount (usually) entering your account
- Expense, meaning a negative amount exiting your account

#### Description

The name or purpose of the transaction. Required.

#### Amount

The monetary value of the transaction. Required.

#### Category

The primary classification of the transaction. Optional.

#### Tags

Additional labels for transaction categorization. Optional.

#### Notes

Additional information about the transaction. Optional.

![img_4.png](.github/img/readme_transaction.png)

### Installment Plan

An Installment Plan is a helper model that generates a series of recurring transactions over a fixed period.

#### Core Fields

- **Account**: The account for all transactions in the plan. Required.
- **Entity**: The paying or receiving party for all transactions. Optional.
- **Description**: The name of the installment plan, used for all transactions. Required.
- **Notes**: Additional information applied to all transactions. Optional.

#### Installment Configuration

- **Number of Installments**: Total number of transactions to create (e.g., 1/10, 2/10)
- **Installment Start**: Initial counting point
- **Start Date**: Date of the first transaction
- **Reference Date**: Reference date for the first transaction
- **Recurrence**: Frequency of transactions (e.g., Monthly)

![img_1.png](.github/img/readme_installment_plan.png)

### Transaction Details

- **Amount**: Value for each transaction. Required.
- **Category**: Primary classification for all transactions. Optional.
- **Tags**: Labels applied to all transactions. Optional.

### Recurring Transaction
A Recurring Transaction is a helper model that generates recurring transactions indefinitely or until a certain date.

#### Core Fields

- **Account**: The account for all transactions in the plan. Required.
- **Entity**: The paying or receiving party for all transactions. Optional.
- **Description**: The name of the recurring transaction, used for all transactions. Required.
- **Notes**: Additional information applied to all transactions. Optional.

#### Recurring Transaction Configuration

- **Start Date**: Date of the first transaction. Required.
- **Reference Date**: Reference date for the first transaction. Optional.
- **Recurrence Type**: Frequency of transactions (e.g., Monthly). Required.
- **Recurrence Interval**: The interval between transactions (e.g. every 1 month, every 2 weeks, etc.). Required.
- **End date**: When new transactions should stop being created. Optional.

#### Transaction Details

- **Amount**: Value for each transaction. Required.
- **Category**: Primary classification for all transactions. Optional.
- **Tags**: Labels applied to all transactions. Optional.

#### Other information

- Recurring transactions are checked and created every midnight using Procrastinate.
- **WYGIWYH** tries to keep at most **6** future transactions created at any time.
- If you delete a recurring transaction it will not be recreated.
- You can stop or pause a recurring transaction at any time on the config page (/recurring-trasanctions/)

![img_3.png](.github/img/readme_recurring_transaction.png)

### Account

TO-DO

### Account Groups

TO-DO

### Currency

TO-DO

### Exchange Rate

TO-DO

### Category

TO-DO

### Tag

TO-DO

### Entity

TO-DO

### Rule

TO-DO

---

## Helper actions

### Transfer

A transfer happens when you move a monetary value from one account to another. This will create two transactions, one expense and one income with the values set by the user.

Contrary to other finance trackers, due to our multi-currency support, **WYGIWYH**'s transfer system allows for non-zero transfers.

![img.png](.github/img/readme_transfer.png)

### Balance (Account Reconciliation)

A balance is a easy way of updating your accounts balance. It creates a transaction with the difference between the balance currently in **WYGIWYH** and the new balance informed by you.

This can be useful for savings accounts or other interest accruing investments.![img_2.png](.github/img/readme_balance.png)

---

## Views

### Monthly

TO-DO

### Yearly by currency

TO-DO

### Yearly by account

TO-DO

### Calendar

TO-DO

### Networh

#### Current

TO-DO

#### Projected

TO-DO

### All Transactions

TO-DO

### Configuration and Management

TO-DO

---

## Tools

### Calculator

The calculator is a floating widget that can be toggled by clicking the calculator icon on the navbar.

It allows for any math expression supported by [math.js](https://mathjs.org).

![calculator](.github/img/readme_calculator.gif)

### Dollar Cost Average Tracker

The DCA Tracker can be accessed from the navbar's **Tools** menu.

It allows for tracking DCA strategies and getting helpful information and insights.

> [!IMPORTANT]
> Currently DCA exists separately from your main transactions. You will need to add your entries manually.

<img src=".github/img/readme_dca_1.png" width="45%"></img> <img src=".github/img/readme_dca_2.png" width="45%"></img>

### Unit Price Calculator

The Unit Price Calculator can be accessed from the navbar's **Tools** menu.

This is a self-contained tool for comparing and finding the most cost-efficient item quickly and easily.

Input the price and the amount of each item, the cheapeast will be highlighted in green, and the most expensive in red.

You can add additional items by clicking the _Add_ button at the end of the page.

> [!NOTE]
> This doesn't do unit convertion. The amount of all items needs to be on the same the unit for proper functioning.

![img.png](.github/img/readme_unit_price_calculator.png)

### Currency Converter

TO-DO

# Built with

WYGIWYH is possible thanks to a lot of amazing open source tools, to name a few:

- Django
- HTMX
- _hyperscript
- Procrastinate
- Bootstrap
- Tailwind
- Webpack
