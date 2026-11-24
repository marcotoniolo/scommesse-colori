from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
COLORI = ["Nero", "Blu", "Rosso", "Bianco", "Verde", "Panna", "Arancione", "Giallo", "Altro"]


@st.cache_resource
def get_engine():
    url = st.secrets["database"]["url"].replace(
        "postgresql://", "postgresql+psycopg://", 1
    )
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS utenti (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL UNIQUE
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lezioni (
                id SERIAL PRIMARY KEY,
                data DATE NOT NULL UNIQUE,
                colore_reale TEXT
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS scommesse (
                id SERIAL PRIMARY KEY,
                utente_id INTEGER NOT NULL REFERENCES utenti(id),
                lezione_id INTEGER NOT NULL REFERENCES lezioni(id),
                colore_previsto TEXT NOT NULL,
                UNIQUE (utente_id, lezione_id)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS storico (
                nome TEXT PRIMARY KEY,
                giocate INTEGER NOT NULL,
                vittorie INTEGER NOT NULL
            )
        """))
    return engine


engine = get_engine()
oggi = datetime.now(ZoneInfo("Europe/Rome")).date()

with engine.begin() as conn:
    conn.execute(
        text("INSERT INTO lezioni (data) VALUES (:oggi) ON CONFLICT (data) DO NOTHING"),
        {"oggi": oggi},
    )

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
        esito = None
        with engine.begin() as conn:
            lezione_id, colore_reale = conn.execute(
                text("SELECT id, colore_reale FROM lezioni WHERE data = :oggi"),
                {"oggi": oggi},
            ).one()

            if colore_reale is not None:
                esito = "chiusa"
            else:
                conn.execute(
                    text("INSERT INTO utenti (nome) VALUES (:nome) ON CONFLICT (nome) DO NOTHING"),
                    {"nome": nome},
                )
                utente_id = conn.execute(
                    text("SELECT id FROM utenti WHERE nome = :nome"), {"nome": nome}
                ).scalar_one()
                inserite = conn.execute(
                    text(
                        "INSERT INTO scommesse (utente_id, lezione_id, colore_previsto) "
                        "VALUES (:u, :l, :c) "
                        "ON CONFLICT (utente_id, lezione_id) DO NOTHING"
                    ),
                    {"u": utente_id, "l": lezione_id, "c": colore},
                ).rowcount
                esito = "ok" if inserite == 1 else "duplicata"

        if esito == "chiusa":
            st.error("Le scommesse per questa lezione sono chiuse.")
        elif esito == "duplicata":
            st.warning("Hai già scommesso per la lezione di oggi.")
        else:
            st.success(f"Hai scommesso su: {colore}")


st.subheader("Scommesse di oggi")
with engine.connect() as conn:
    righe = conn.execute(
        text("""
            SELECT u.nome, s.colore_previsto
            FROM scommesse s
            JOIN utenti u ON u.id = s.utente_id
            JOIN lezioni l ON l.id = s.lezione_id
            WHERE l.data = :oggi
        """),
        {"oggi": oggi},
    ).all()

df_oggi = pd.DataFrame([tuple(r) for r in righe], columns=["Nome", "Colore"])
df_oggi["Nome"] = df_oggi["Nome"].str.title()
st.table(df_oggi)


if st.session_state["admin"]:
    st.subheader("Inserisci il colore reale")
    with engine.connect() as conn:
        lezioni_aperte = [
            tuple(r)
            for r in conn.execute(
                text("SELECT id, data FROM lezioni WHERE colore_reale IS NULL ORDER BY data DESC")
            ).all()
        ]

    if lezioni_aperte:
        lezione_scelta = st.selectbox(
            "Lezione", lezioni_aperte, format_func=lambda r: str(r[1])
        )
        colore_reale = st.selectbox("Colore reale", COLORI, key="colore_reale")
        if st.button("Salva risultato"):
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE lezioni SET colore_reale = :c WHERE id = :id"),
                    {"c": colore_reale, "id": lezione_scelta[0]},
                )
            st.success("Risultato salvato.")
    else:
        st.info("Nessuna lezione in attesa di risultato.")

st.subheader("Classifica")
with engine.connect() as conn:
    classifica = conn.execute(
        text("""
            WITH live AS (
                SELECT u.nome,
                       SUM(CASE WHEN s.colore_previsto = l.colore_reale THEN 1 ELSE 0 END) AS indovinate,
                       COUNT(*) AS giocate
                FROM scommesse s
                JOIN utenti u ON u.id = s.utente_id
                JOIN lezioni l ON l.id = s.lezione_id
                WHERE l.colore_reale IS NOT NULL
                GROUP BY u.nome
            )
            SELECT COALESCE(live.nome, h.nome) AS nome,
                   COALESCE(live.indovinate, 0) + COALESCE(h.vittorie, 0) AS indovinate,
                   COALESCE(live.giocate, 0) + COALESCE(h.giocate, 0) AS giocate
            FROM live
            FULL OUTER JOIN storico h ON live.nome = h.nome
            ORDER BY indovinate DESC, giocate ASC, nome ASC
        """)
    ).all()
df_class = pd.DataFrame([tuple(r) for r in classifica], columns=["Nome", "Indovinate", "Giocate"])
df_class["Nome"] = df_class["Nome"].str.title()
st.table(df_class)