from cs50 import SQL
from flask import Flask, jsonify, redirect, render_template, request, session, url_for, flash
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

app = Flask(__name__)

if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    rows_portfolios = db.execute("SELECT * FROM portfolios WHERE id = :id", id=session["user_id"])

    if rows_portfolios == []:
        cashier = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        cash = cashier[0]['cash']
        return render_template("index.html", current_cash=cash, total_cash=cash)
    else:
        new_rows_portfolios = []
        for row in rows_portfolios:
            new_portfolios_dict = {}
            quote = lookup(row["symbol"])
            new_portfolios_dict["symbol"] = quote["symbol"]
            new_portfolios_dict["name"] = quote["name"]
            new_portfolios_dict["shares"] = row["shares"]
            new_portfolios_dict["price"] = quote["price"]
            new_portfolios_dict["total"] = row["shares"] * quote["price"]

            new_rows_portfolios.append(new_portfolios_dict)
            print(new_portfolios_dict)

            cashier = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
            cash = cashier[0]['cash']
            total_cash = cash
            for row in new_rows_portfolios:
                total_cash += row["total"]
        return render_template("index.html", rows_portfolios=new_rows_portfolios, current_cash=cash, total_cash=total_cash)


@app.route('/selling', methods=['POST'])
def selling_shares():
    rows_portfolios = db.execute("SELECT * FROM portfolios WHERE id = :id", id=session["user_id"])
    cashier = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = cashier[0]['cash']

    if request.method == 'POST':

        data = request.get_json()
        print(data)
        shares = data['shares']
        symbol = data['symbol']
        db.execute("UPDATE portfolios SET shares = shares + :shares WHERE symbol = :symbol", shares=shares, symbol=symbol)
        new_shares = db.execute('SELECT shares FROM portfolios WHERE symbol = :symbol', symbol=symbol)
        price = float(data['price'])
        updated_cash = cash - int(shares) * price
        total = int(new_shares[0]['shares']) * price
        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :id", updated_cash=updated_cash, id=session["user_id"])
        return jsonify({'share': new_shares[0]['shares'], 'cash': updated_cash, 'price': price, 'total': total})


@app.route('/buying', methods=['POST'])
def buying_shares():
    cashier = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
    cash = cashier[0]['cash']

    if request.method == 'POST':

        data = request.get_json()
        print(data)
        shares = data['shares']
        symbol = data['symbol']
        price = float(data['price'])

        db.execute("UPDATE portfolios SET shares = shares - :shares WHERE symbol = :symbol", symbol=symbol, shares=shares)
        new_shares = db.execute('SELECT shares FROM portfolios WHERE symbol = :symbol', symbol=symbol)
        print(new_shares[0]['shares'])
        if new_shares[0]['shares'] == 0:
            db.execute("DELETE FROM portfolios WHERE id = :id AND symbol = :symbol", id=session["user_id"], symbol=symbol)
        updated_cash = cash + int(shares) * price
        total = int(new_shares[0]['shares']) * price
        print(updated_cash)
        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :id", id=session["user_id"], updated_cash=updated_cash)
        db.execute("INSERT INTO history (id, symbol, shares, price) VALUES (:id, :symbol, :shares, :price)", id=session["user_id"], symbol=symbol, shares=-(int(shares)), price=price)
        return jsonify({'share': new_shares[0]['shares'], 'cash': updated_cash, 'price': price, 'total': total})


@app.route("/description", methods=['POST'])
# @login_required
def description():
    """Получение цены акции"""
    if request.method == "POST":

        # проверка на заполнение символа
        data = request.get_json()
        # перевод в верхний регистр введенного символа
        symbol = data.get("symbol").upper()

        # получение данных о акции
        quote = lookup(symbol)

        # проверка на ошибку получения данных
        if quote is None:
            return jsonify({'result': 'Such quote does not found'})

        result = 'A share of {} ({}) costs ${}'.format(quote['name'], symbol, quote['price'])
        return jsonify({'result': result})


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Покупка акций"""
    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("missing symbol", 403)

        elif not request.form.get("shares"):
            return apology("missing shares", 403)

        # если количество не integer
        elif not request.form.get("shares").isdigit():
            return apology("invalid shares", 400)

        # перевод в верхний регистр введенного символа
        symbol = request.form.get("symbol").upper()

        # получение данных о акции
        quote = lookup(symbol)

        # проверка на ошибку получения данных
        if quote is None:
            return apology("invalid symbol", 400)

        # проверка на достаточность средств
        cashier = db.execute("SELECT cash FROM users WHERE id = :id", id=session["user_id"])
        cash = cashier[0]['cash']

        shares = int(request.form.get("shares"))
        price = quote["price"]
        updated_cash = cash - shares * price

        if updated_cash < 0:
            return apology("can't afford", 400)

        # обновление кэша в таблице БД
        db.execute("UPDATE users SET cash = :updated_cash WHERE id = :id", id=session["user_id"], updated_cash=updated_cash)

        rows = db.execute("SELECT * FROM portfolios WHERE id = :id AND symbol = :symbol", id=session["user_id"], symbol=symbol)
        # если таких акций не было, то вставляем новую строку в таблицу БД
        if len(rows) == 0:
            db.execute("INSERT INTO portfolios (id, symbol, shares) VALUES (:id, :symbol, :shares)", id=session["user_id"], symbol=symbol, shares=shares)
        else:
            db.execute("UPDATE portfolios SET shares = shares + :shares WHERE id = :id AND symbol = :symbol", id=session["user_id"], shares=shares, symbol=symbol)

        # обновление таблицы с историей в БД
        db.execute("INSERT INTO history (id, symbol, shares, price) VALUES (:id, :symbol, :shares, :price)", id=session["user_id"], symbol=symbol, shares=shares, price=price)

        # возврат на главную страницу
        return redirect(url_for("index"))

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """История покупок и продаж"""
    rows = db.execute("SELECT * FROM history WHERE id = :id", id=session["user_id"])
    return render_template("history.html", history_list=rows)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Вход"""

    session.clear()

    if request.method == "POST":

        # проверка на заполнение имени
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # проверка на заполнение пароля
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # запрос к БД для имени
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # проверка на существование имени и пароля
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username andor password", 403)

        # запомнить какой пользователь вошёл в систему
        session["user_id"] = rows[0]["id"]

        # возврат на главную страницу
        return redirect(url_for("index"))

    # иначе перенаправить на страницу логина
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Выход из системы"""

    session.clear()

    # перенаправление на страницу логина
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", 'POST'])
@login_required
def quote():
    """Получение цены акции"""
    if request.method == "POST":

        # проверка на заполнение символа
        if not request.form.get("symbol"):
            return apology("missing symbol", 403)

        # перевод в верхний регистр введенного символа
        symbol = request.form.get("symbol").upper()

        # получение данных о акции
        quote = lookup(symbol)

        # проверка на ошибку получения данных
        if quote == None:
            return apology("Invalid Symbol", 400)

        return render_template("quoted.html", name=quote["name"], symbol=symbol, price=quote["price"])

    else:
        try:
            puck = showup()
            return render_template("quote.html", puck=puck)
        except:
            return apology("Data not found", 503)

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""

    session.clear()

    if request.method == "POST":
        # проверка на заполнение имени
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # проверка на заполнение пароля
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        # проверка на заполнение повторного пароля
        elif not request.form.get("password_confirmation"):
            return apology("must provide password (again)", 400)
        # проверка на совпадение паролей
        elif request.form.get("password_confirmation") != request.form.get("password"):
            return apology("Passwords don't match!", 400)


        # вносим в таблицу БД данные пользователя

        result = db.execute("INSERT INTO users (username, hash) VALUES (:username, :hash)", username=request.form.get("username"), hash=pwd_context.hash(request.form.get("password")))
        if not result:
            return apology("Username taken", 400)


        # запрос к БД для имени
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # проверка на существование имени и пароля
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password", 400)

        # запомнить какой пользователь вошёл в систему
        session["user_id"] = rows[0]["id"]

        # перенаправление на главную страницу
        return redirect(url_for("index"))

    else:
        return render_template("register.html")

    return apology("TODO")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Продажа акций"""

    if request.method == "POST":

        if not request.form.get("symbol"):
            return apology("missing symbol", 403)

        elif not request.form.get("shares"):
            return apology("missing shares", 403)

        # если количество не integer
        elif not request.form.get("shares").isdigit():
            return apology("invalid shares", 400)

        # перевод в верхний регистр введенного символа
        symbol = request.form.get("symbol").upper()

        # получение данных о акции
        quote = lookup(symbol)

        # проверка на ошибку получения данных
        if quote == None:
            return apology("invalid symbol", 400)


        # количество акций введенных пользователем
        shares = int(request.form.get("shares"))

        # проверка на то, что пользователь имеет набранное им количество акций
        shares_already_list = db.execute("SELECT shares FROM portfolios WHERE id = :id AND symbol = :symbol", id=session["user_id"], symbol=symbol)
        if len(shares_already_list) == 0:
            return apology("symbol not owned", 400)
        shares_already = shares_already_list[0]["shares"]
        updated_shares = shares_already - shares
        if (updated_shares < 0):
            return apology("too many shares", 400)

        # текущая цена
        price = quote["price"]

        # кэш после продажи акций
        cash_increase = price * shares

        # обновить кэш в таблице БД после продажи
        db.execute("UPDATE users SET cash = cash + :cash_increase WHERE id = :id", id=session["user_id"], cash_increase=cash_increase)

        # если акций не осталось, то удалить строку с символом из БД
        if updated_shares == 0:
            db.execute("DELETE FROM portfolios WHERE id = :id AND symbol = :symbol", id=session["user_id"], symbol=symbol)
        # иначе обновляем таблицу
        elif updated_shares > 0:
            db.execute("UPDATE portfolios SET shares = :updated_shares WHERE id = :id AND symbol = :symbol", id=session["user_id"], updated_shares=updated_shares, symbol=symbol)

        # добавление информации о продажи акций
        db.execute("INSERT INTO history (id, symbol, shares, price) VALUES (:id, :symbol, :shares, :price)", id=session["user_id"], symbol=symbol, shares=-(shares), price=price)

        # перенаправление на главную страницу
        return redirect(url_for("index"))

    else:
        return render_template("sell.html")
