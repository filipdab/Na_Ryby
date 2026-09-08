#!/usr/bin/env python3
"""
Fishing Forecast
----------------
Pobiera dane pogodowe z Open-Meteo, analizuje je pod kątem warunków
wędkarskich przy pomocy modelu Claude (Anthropic API), a następnie
wysyła cotygodniowy raport e-mail w formacie HTML.

Uruchamiane cyklicznie przez cron (domyślnie w piątki) na Raspberry Pi.
"""

import os
import smtplib
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

LATITUDE = os.getenv("LATITUDE")
LONGITUDE = os.getenv("LONGITUDE")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
RECIPIENTS = [r.strip() for r in os.getenv("RECIPIENTS", "").split(",") if r.strip()]


def fetch_weather():
    """Pobiera prognozę pogody z Open-Meteo dla skonfigurowanej lokalizacji."""
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
        "windspeed_10m_max,pressure_msl_mean"
        "&timezone=auto"
    )
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.json()


def analyze_conditions(weather_data):
    """Wysyła dane pogodowe do modelu Claude i zwraca ocenę warunków wędkarskich."""
    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""Na podstawie poniższych danych pogodowych oceń warunki
wędkarskie na najbliższy weekend. Podaj wskaźnik aktywności ryb
(niska / średnia / wysoka), kolor (czerwony/żółty/zielony) oraz
krótkie uzasadnienie (2-3 zdania).

Dane pogodowe:
{weather_data}
"""

    message = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def build_email_html(analysis_text):
    """Buduje prosty, mobilny szablon HTML raportu."""
    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; max-width: 480px; margin: auto;">
        <h2>🎣 Prognoza wędkarska na weekend</h2>
        <div style="padding: 16px; border-radius: 8px; background: #f2f2f2;">
          <p style="white-space: pre-line;">{analysis_text}</p>
        </div>
        <p style="font-size: 12px; color: #888;">Raport wygenerowany automatycznie.</p>
      </body>
    </html>
    """


def send_email(html_content):
    """Wysyła raport e-mail do skonfigurowanej listy odbiorców."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Prognoza wędkarska na weekend"
    msg["From"] = SMTP_USER
    msg["To"] = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_content, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(SMTP_USER, RECIPIENTS, msg.as_string())


def main():
    weather = fetch_weather()
    analysis = analyze_conditions(weather)
    html = build_email_html(analysis)
    send_email(html)
    print("Raport wysłany pomyślnie.")


if __name__ == "__main__":
    main()
