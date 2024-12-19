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

## Why WYGIWYH?
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

## Key Features

**WYGIWYH** offers an array of features designed to simplify and streamline your personal finance tracking:

* **Unified transaction tracking**: Record all your income and expenses, organized in one place.
* **Multiple accounts support**: Keep track of where your money and assets are stored (banks, wallets, investments, etc.).
* **Out-of-the-box multi-currency support**: Dynamically manage transactions and balances in different currencies.
* **Custom currencies**: Create your own currencies for crypto, rewards points, or any other models.
* **Automated adjustments with rules**: Automatically modify transactions using customizable rules.
* **Built-in Dollar-Cost Average (DCA) tracker**: Essential for tracking recurring investments, especially for crypto and stocks.
* **API support for automation**: Seamlessly integrate with existing services to synchronize transactions.

## How To Use

To run this application, you'll need [Git](https://git-scm.com) and [Docker](https://docs.docker.com/engine/install/) with the [docker-compose](https://docs.docker.com/compose/install/).

From your command line:

> [!NOTE]
> Docker images for this project are currently under development, but manual setup is available now.

```bash
# Clone this repository
$ git clone https://github.com/eitchtee/WYGIWYH

# Go into the repository
$ cd WYGIWYH

# Fill the .env file with your configurations
$ cp .env.example .env
$ nano .env # or any other editor you want to use

# Create docker-compose file
$ cp docker-compose.prod.yml docker-compose.yml

# Run the app
$ docker compose up -d --build

# Create the first admin account
$ docker compose exec -it web python manage.py createsuperuser
```

## How it works
