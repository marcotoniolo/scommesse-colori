import sqlite3
from datetime import date

import pandas as pd
import streamlit as st

DB_FILE = "scommesse.db"
COLORI = ["Nero", "Blu", "Rosso", "Bianco", "Verde", "Panna", "Arancione", "Giallo", "Altro"]


def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def crea_tabelle(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS utenti (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS lezioni (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL UNIQUE,
        colore_reale TEXT
    );
    CREATE TABLE IF NOT EXISTS scommesse (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        utente_id INTEGER NOT NULL REFERENCES utenti(id),
        lezione_id INTEGER NOT NULL REFERENCES lezioni(id),
        colore_previsto TEXT NOT NULL,
        UNIQUE (utente_id, lezione_id)
    );
    """)


conn = get_conn()
crea_tabelle(conn)

oggi = date.today().isoformat()
conn.execute("INSERT OR IGNORE INTO lezioni (data) VALUES (?)", (oggi,))
conn.commit()

st.title("Che colore indosserà la prof?")
if "admin" not in st.session_state:
    st.session_state["admin"] = False

with st.sidebar:
    st.header("Area admin")
    if st.session_state["admin"]:
        st.success("Accesso effettuato")
        if st.button("Esci"):
            st.session_state["admin"] = False
            st.rerun()
    else:
        pwd = st.text_input("Password", type="password", key="pwd_admin")
        if st.button("Accedi"):
            if pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state["admin"] = True
                st.rerun()
            else:
                st.error("Password errata.")

nome = " ".join(st.text_input("Il tuo nome").split()).lower()
colore = st.selectbox("La tua scommessa", COLORI)

if st.button("Conferma scommessa"):
    if not nome:
        st.error("Scrivi il tuo nome.")
    else:
        conn.execute("INSERT OR IGNORE INTO utenti (nome) VALUES (?)", (nome,))
        utente_id = conn.execute(
            "SELECT id FROM utenti WHERE nome = ?", (nome,)
        ).fetchone()[0]
        lezione_id = conn.execute(
            "SELECT id FROM lezioni WHERE data = ?", (oggi,)
        ).fetchone()[0]

        gia_chiusa = conn.execute(
            "SELECT colore_reale FROM lezioni WHERE id = ?", (lezione_id,)
        ).fetchone()[0]
        if gia_chiusa is not None:
            st.error("Le scommesse per questa lezione sono chiuse.")
            st.stop()

        try:
            conn.execute(
                "INSERT INTO scommesse (utente_id, lezione_id, colore_previsto) "
                "VALUES (?, ?, ?)",
                (utente_id, lezione_id, colore),
            )
            conn.commit()
            st.success(f"Hai scommesso su: {colore}")
        except sqlite3.IntegrityError:
            st.warning("Hai già scommesso per la lezione di oggi.")


st.subheader("Scommesse di oggi")
righe = conn.execute(
    """
    SELECT u.nome, s.colore_previsto
    FROM scommesse s
    JOIN utenti u ON u.id = s.utente_id
    JOIN lezioni l ON l.id = s.lezione_id
    WHERE l.data = ?
    """,
    (oggi,),
).fetchall()

df_oggi = pd.DataFrame(righe, columns=["Nome", "Colore"])
df_oggi["Nome"] = df_oggi["Nome"].str.title()
st.table(df_oggi)


if st.session_state["admin"]:
    st.subheader("Inserisci il colore reale")
    lezioni_aperte = conn.execute(
        "SELECT id, data FROM lezioni WHERE colore_reale IS NULL ORDER BY data DESC"
    ).fetchall()

    if lezioni_aperte:
        lezione_scelta = st.selectbox(
            "Lezione", lezioni_aperte, format_func=lambda r: r[1]
        )
        colore_reale = st.selectbox("Colore reale", COLORI, key="colore_reale")
        if st.button("Salva risultato"):
            conn.execute(
                "UPDATE lezioni SET colore_reale = ? WHERE id = ?",
                (colore_reale, lezione_scelta[0]),
            )
            conn.commit()
            st.success("Risultato salvato.")
    else:
        st.info("Nessuna lezione in attesa di risultato.")
st.subheader("Classifica")
classifica = conn.execute(
    """
    SELECT u.nome,
           SUM(s.colore_previsto = l.colore_reale) AS indovinate,
           COUNT(*) AS giocate
    FROM scommesse s
    JOIN utenti u ON u.id = s.utente_id
    JOIN lezioni l ON l.id = s.lezione_id
    WHERE l.colore_reale IS NOT NULL
    GROUP BY u.nome
    ORDER BY indovinate DESC
    """
).fetchall()
df_class = pd.DataFrame(classifica, columns=["Nome", "Indovinate", "Giocate"])
df_class["Nome"] = df_class["Nome"].str.title()
st.table(df_class)

conn.close()