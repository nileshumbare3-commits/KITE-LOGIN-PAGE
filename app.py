from flask import Flask, request, redirect, session, render_template
from kiteconnect import KiteConnect
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Replace with your API key and secret
api_key = "jaibrxwjfdmr86ao"
api_secret = "se1mzachqkdv963oqgbu7ij0y6002di1"

kite = KiteConnect(api_key=api_key)

@app.route("/")
def index():
    if "access_token" in session:
        return redirect("/home")
    return render_template("index.html")

@app.route("/login")
def login():
    return redirect(kite.login_url())

@app.route("/callback")
def callback():
    request_token = request.args.get("request_token")
    if not request_token:
        return "Error: request_token not found."

    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        session["access_token"] = data["access_token"]
        return redirect("/home")
    except Exception as e:
        return f"Error: {e}"

@app.route("/home")
def home():
    if "access_token" not in session:
        return redirect("/")

    try:
        kite.set_access_token(session["access_token"])
        profile = kite.profile()
        return render_template("home.html", user=profile)
    except Exception as e:
        return f"Error: {e}"

@app.route("/logout")
def logout():
    session.pop("access_token", None)
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
