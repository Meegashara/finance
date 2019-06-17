import csv
import urllib.request
import json
import sys

from flask import redirect, render_template, request, session, url_for
from functools import wraps

def apology(message, code=400):
    return render_template("apology.html", top=code, bottom=message), code

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def lookup(symbol):
    """Найти цену"""

    # отклонить символ, если он содержит запятую
    if "," in symbol:
        return None

    try:
        # Получить json
        url = "https://cloud.iexapis.com/stable/stock/{}/quote?token=pk_812e421a68ab4cb795fa08c8528de90e".format(symbol)
        webpage = urllib.request.urlopen(url)

        # загрузить содержимое json
        data = json.loads(webpage.read().decode("utf-8"))

        try:
            check = data["symbol"]
        except:
            return None

        #значение акции: имя, символ и цена
        qName = data["companyName"]
        qSymbol = data["symbol"]
        qPrice = data["latestPrice"]

        return {
            'name': str(qName.upper()),
            'symbol': str(qSymbol.upper()),
            'price': float(qPrice)
        }

    except urllib.error.HTTPError as e:
        # Return code error (e.g. 404, 501, ...)
        print('HTTPError: {}'.format(e.code))

    except urllib.error.URLError as e:
        # Not an HTTP-specific error (e.g. connection refused)
        print('URLError: {}'.format(e.reason))

def usd(value):
    """Форматирование значения в USD"""
    return "${:,.2f}".format(value)

def showup():
    """mostactive"""

    # Получить json
    url = "https://cloud.iexapis.com/stable/stock/market/list/mostactive?token=pk_812e421a68ab4cb795fa08c8528de90e"
    webpage = urllib.request.urlopen(url)

    # загрузить содержимое json
    data = json.loads(webpage.read().decode("utf-8"))

    list = []

    for item in data:
        store_details = {"companyName":None, "symbol":None, "latestPrice":None}
        store_details['companyName'] = item['companyName']
        store_details['symbol'] = item['symbol']
        store_details['latestPrice'] = item['latestPrice']
        list.append(store_details)

    return list