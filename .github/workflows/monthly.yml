name: InvestoBot Consiglio Mensile

on:
  schedule:
    - cron: '0 8 1 * *'
  workflow_dispatch:

jobs:
  analisi:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests yfinance pandas numpy
      - run: python monthly.py
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          CHAT_ID: ${{ secrets.CHAT_ID }}
          AV_KEY: ${{ secrets.AV_KEY }}
