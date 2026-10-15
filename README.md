# Rybackie Prognozy

Skrypt na Raspberry Pi, który co tydzień generuje i wysyła mailem prognozę warunków wędkarskich na nadchodzący weekend.

## Co dokładnie robi

1. **Pogoda** — pobiera prognozę godzinową (temperatura, wiatr, ciśnienie, zachmurzenie, opady) z Open-Meteo dla najbliższej soboty i niedzieli, osobno dla dnia (6:00–17:00) i wieczoru (18:00–22:00), wraz z trendem ciśnienia z 2 dni wcześniej.
2. **Faza Księżyca** — liczona lokalnie (bez zewnętrznego API) dla obu dni.
3. **Indeks aktywności ryb (1–10)** — lokalny, regułowy wskaźnik uwzględniający trend ciśnienia, siłę wiatru, zachmurzenie, opady i fazę Księżyca — liczony osobno dla dnia i wieczoru każdego dnia.
4. **Analiza AI** — wszystkie powyższe dane trafiają do modelu Claude Haiku 4.5 (Anthropic API), który pisze krótką ocenę warunków na sobotę i niedzielę (dzień/wieczór) plus jedną praktyczną rekomendację.
5. **Przepisy** — sekcja z okresami ochronnymi, wymiarami i limitami (zasady Okręgu Mazowieckiego PZW) oraz lokalnymi zakazami dla Zalewu Zegrzyńskiego, z zapowiedzią zmian w najbliższych 2 tygodniach. Tabela `GATUNKI` i lista `ZASADY_LOKALNE` w skrypcie wymagają aktualizacji raz w roku, gdy PZW publikuje nowy regulamin. AI dostaje te przepisy i nie poleca zabierania ryb w okresie ochronnym.
6. **E-mail** — gotowy raport wysyłany jest jako czytelny, mobilny HTML (kolorowe karty z indeksem aktywności) do listy odbiorców, z wersją plain-text jako fallback.

Skrypt ma wbudowane ponawianie zapytań (retry z backoffem) zarówno dla Open-Meteo, jak i Anthropic API, na wypadek chwilowych błędów 429/5xx.

## Harmonogram

Uruchamiany przez `cron`, domyślnie w piątek wieczorem:

```
0 18 * * 5 /usr/bin/python3 /home/pi/rybackie_prognozy.py >> /home/pi/rybackie_prognozy.log 2>&1
```

## Wymagania

- Python 3.7+ (kompatybilny ze starszymi Raspberry Pi OS)
- `pip3 install -r requirements.txt`
- Klucz API Anthropic (https://console.anthropic.com/settings/keys)
- Hasło aplikacji (App Password) do konta e-mail nadawcy, jeśli używasz Gmaila

## Konfiguracja

Dane wrażliwe (lokalizacja łowiska, adresy e-mail, klucze API) **nie są wpisane w kodzie** — wczytywane są ze zmiennych środowiskowych. Skopiuj `.env.example` do `.env` i uzupełnij:

| Zmienna | Opis |
|---|---|
| `ANTHROPIC_API_KEY` | Klucz API do modelu Claude |
| `EMAIL_FROM` | Adres e-mail nadawcy |
| `EMAIL_TO` | Adresy odbiorców, oddzielone przecinkiem |
| `EMAIL_PASSWORD` | Hasło aplikacji do konta nadawcy |
| `SMTP_SERVER` / `SMTP_PORT` | Domyślnie `smtp.gmail.com` / `465` |
| `LATITUDE` / `LONGITUDE` | Współrzędne łowiska |
| `LOCATION_NAME` | Nazwa łowiska w treści maila |

> Skrypt sam wczytuje plik `.env` leżący obok niego. Zmienne ustawione już w środowisku mają pierwszeństwo, więc jeśli wolisz, ustaw je zamiast pliku `.env` bezpośrednio w `crontab` albo `/etc/environment`.

## Struktura repo

```
Na_Ryby/
├── fishing_forecast.py    # główny skrypt (na Raspberry Pi zapisany jako rybackie_prognozy.py)
├── requirements.txt       # zależności Pythona
├── .env.example           # przykładowa konfiguracja (bez prawdziwych danych)
├── IMG_271*.png           # zrzuty ekranu przykładowego maila
└── README.md
```
