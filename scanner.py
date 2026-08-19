import os
import re
import io
import logging
import requests
from flask import Flask, request, send_file, jsonify
from fpdf import FPDF, XPos, YPos
import pandas as pd
from github import Github
from github.GithubException import UnknownObjectException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DEFAULT_DEV_ORIGINS = [
    "null", "http://127.0.0.1:5500", "http://localhost:5500",
    "http://127.0.0.1:5000", "http://localhost:5000"
]

@app.after_request
def add_security_headers(response):
    origin = request.headers.get("Origin")
    allowed_env = os.environ.get("ALLOWED_ORIGINS", "")
    allowed_list = [o.strip() for o in allowed_env.split(",") if o.strip()] + DEFAULT_DEV_ORIGINS
    
    if origin and origin in allowed_list:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Vary"] = "Origin"
    
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = "frame-ancestors 'self' file:// http://127.0.0.1:* http://localhost:*;"
    return response

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_NAME = os.environ.get("REPO_NAME", "tonecraft17/dati-privati-pdf")

g = Github(GITHUB_TOKEN) if GITHUB_TOKEN else None
if not g:
    logger.error("ATTENZIONE: GITHUB_TOKEN non trovato nelle variabili d'ambiente!")

MAX_CLASSI = 20
MAX_ROWS_PDF = 500

PROVINCE_DATA = {
    "AG": ("Sicilia", "Agrigento"), "AL": ("Piemonte", "Alessandria"), "AN": ("Marche", "Ancona"),
    "AO": ("Valle d'Aosta", "Aosta"), "AP": ("Marche", "Ascoli Piceno"), "AT": ("Piemonte", "Asti"),
    "AV": ("Campania", "Avellino"), "BA": ("Puglia", "Bari"), "BT": ("Puglia", "Barletta-Andria-Trani"),
    "BL": ("Veneto", "Belluno"), "BN": ("Campania", "Benevento"), "BG": ("Lombardia", "Bergamo"),
    "BI": ("Piemonte", "Biella"), "BO": ("Emilia-Romagna", "Bologna"), "BZ": ("Trentino-Alto Adige", "Bolzano"),
    "BS": ("Lombardia", "Brescia"), "BR": ("Puglia", "Brindisi"), "CA": ("Sardegna", "Cagliari"),
    "CL": ("Sicilia", "Caltanissetta"), "CB": ("Molise", "Campobasso"), "CE": ("Campania", "Caserta"),
    "CT": ("Sicilia", "Catania"), "CZ": ("Calabria", "Catanzaro"), "CH": ("Abruzzo", "Chieti"),
    "CO": ("Lombardia", "Como"), "CS": ("Calabria", "Cosenza"), "CR": ("Lombardia", "Cremona"),
    "KR": ("Calabria", "Crotone"), "CN": ("Piemonte", "Cuneo"), "EN": ("Sicilia", "Enna"),
    "FM": ("Marche", "Fermo"), "FE": ("Emilia-Romagna", "Ferrara"), "FI": ("Toscana", "Firenze"),
    "FG": ("Puglia", "Foggia"), "FC": ("Emilia-Romagna", "Forlì-Cesena"), "FR": ("Lazio", "Frosinone"),
    "GE": ("Liguria", "Genova"), "GO": ("Friuli-Venezia Giulia", "Gorizia"), "GR": ("Toscana", "Grosseto"),
    "IM": ("Liguria", "Imperia"), "IS": ("Molise", "Isernia"), "AQ": ("Abruzzo", "L'Aquila"),
    "SP": ("Liguria", "La Spezia"), "LT": ("Lazio", "Latina"), "LE": ("Puglia", "Lecce"),
    "LC": ("Lombardia", "Lecco"), "LI": ("Toscana", "Livorno"), "LO": ("Lombardia", "Lodi"),
    "LU": ("Toscana", "Lucca"), "MC": ("Marche", "Macerata"), "MN": ("Lombardia", "Mantova"),
    "MS": ("Toscana", "Massa-Carrara"), "MT": ("Basilicata", "Matera"), "ME": ("Sicilia", "Messina"),
    "MI": ("Lombardia", "Milano"), "MO": ("Emilia-Romagna", "Modena"), "MB": ("Lombardia", "Monza e della Brianza"),
    "NA": ("Campania", "Napoli"), "NO": ("Piemonte", "Novara"), "NU": ("Sardegna", "Nuoro"),
    "OR": ("Sardegna", "Oristano"), "PD": ("Veneto", "Padova"), "PA": ("Sicilia", "Palermo"),
    "PR": ("Emilia-Romagna", "Parma"), "PV": ("Lombardia", "Pavia"), "PG": ("Umbria", "Perugia"),
    "PU": ("Marche", "Pesaro e Urbino"), "PE": ("Abruzzo", "Pescara"), "PC": ("Emilia-Romagna", "Piacenza"),
    "PI": ("Toscana", "Pisa"), "PT": ("Toscana", "Pistoia"), "PN": ("Friuli-Venezia Giulia", "Pordenone"),
    "PZ": ("Basilicata", "Potenza"), "PO": ("Toscana", "Prato"), "RG": ("Sicilia", "Ragusa"),
    "RA": ("Emilia-Romagna", "Ravenna"), "RC": ("Calabria", "Reggio Calabria"), "RE": ("Emilia-Romagna", "Reggio Emilia"),
    "RI": ("Lazio", "Rieti"), "RN": ("Emilia-Romagna", "Rimini"), "RM": ("Lazio", "Roma"),
    "RO": ("Veneto", "Rovigo"), "SA": ("Campania", "Salerno"), "SS": ("Sardegna", "Sassari"),
    "SV": ("Liguria", "Savona"), "SI": ("Toscana", "Siena"), "SR": ("Sicilia", "Siracusa"),
    "SO": ("Lombardia", "Sondrio"), "SU": ("Sardegna", "Sud Sardegna"), "TA": ("Puglia", "Taranto"),
    "TE": ("Abruzzo", "Teramo"), "TR": ("Umbria", "Terni"), "TO": ("Piemonte", "Torino"),
    "TP": ("Sicilia", "Trapani"), "TN": ("Trentino-Alto Adige", "Trento"), "TV": ("Veneto", "Treviso"),
    "TS": ("Friuli-Venezia Giulia", "Trieste"), "UD": ("Friuli-Venezia Giulia", "Udine"), "VA": ("Lombardia", "Varese"),
    "VE": ("Veneto", "Venezia"), "VB": ("Piemonte", "Verbano-Cusio-Ossola"), "VC": ("Piemonte", "Vercelli"),
    "VR": ("Veneto", "Verona"), "VV": ("Calabria", "Vibo Valentia"), "VI": ("Veneto", "Vicenza"),
    "VT": ("Lazio", "Viterbo")
}
PROVINCE_SIGLE = { name: sigla for sigla, (region, name) in PROVINCE_DATA.items() }

SCUOLE_FALLBACK = {name: 0 for sigla, (region, name) in PROVINCE_DATA.items()}

SEC_I_CLASSI = {
    "AB24", "A011", "A012", "A013", "A014", "A015", "A016", "A017", "A018", "A019", "A020", "A021", "A022", "A0
