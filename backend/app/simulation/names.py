"""Fictional name generation and the perturbations that make screening hard.

All names are random combinations of common given names and surnames. They are not drawn from
any real sanctions, PEP or watch list.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np

REGIONS = ["North America", "Europe", "Latin America", "Middle East", "Asia Pacific", "Africa"]

GIVEN: Dict[str, List[str]] = {
    "North America": ["James", "Emily", "Michael", "Sarah", "Daniel", "Megan", "Robert", "Ashley", "Kevin", "Rachel",
                      "Brian", "Lauren", "Gregory", "Natalie", "Steven", "Hannah"],
    "Europe": ["Thomas", "Laura", "Lukas", "Claire", "Pierre", "Sophie", "Henrik", "Ingrid", "Matteo", "Elena",
               "Johannes", "Marta", "Stefan", "Camille", "Pieter", "Agnieszka"],
    "Latin America": ["Mateo", "Valentina", "Santiago", "Camila", "Diego", "Lucia", "Andres", "Gabriela", "Joaquin",
                      "Daniela", "Rodrigo", "Paula", "Esteban", "Mariana", "Felipe", "Ximena"],
    "Middle East": ["Omar", "Layla", "Karim", "Yasmin", "Tariq", "Nadia", "Hassan", "Rania", "Youssef", "Samira",
                    "Khalid", "Dalia", "Faisal", "Huda", "Ziad", "Mona"],
    "Asia Pacific": ["Wei", "Mei", "Jun", "Hiroshi", "Aiko", "Minh", "Linh", "Arjun", "Priya", "Rohan", "Siew",
                     "Kenji", "Anh", "Ravi", "Xiu", "Tomoko"],
    "Africa": ["Kwame", "Amara", "Chidi", "Zainab", "Tendai", "Nia", "Kofi", "Ayodele", "Thabo", "Fatou", "Jabari",
               "Imani", "Sekou", "Adaeze", "Tunde", "Wanjiru"],
}

SURNAME: Dict[str, List[str]] = {
    "North America": ["Whitfield", "Hartley", "Brennan", "Fairbanks", "Holloway", "Vance", "Prescott", "Calloway",
                      "Thornton", "Merriweather", "Ashford", "Kingsley", "Dalton", "Mercer", "Langford", "Sutton"],
    "Europe": ["Kowalczyk", "Lindqvist", "Moreau", "Becker", "Rossetti", "Vasquez", "Jansen", "Novak", "Hoffmann",
               "Dubois", "Andersen", "Ferreira", "Kaminski", "Lambert", "Weiss", "Bergstrom"],
    "Latin America": ["Restrepo", "Quintero", "Valderrama", "Cardenas", "Arriaga", "Benavides", "Montoya", "Salcedo",
                      "Figueroa", "Echeverria", "Villalobos", "Saavedra", "Orozco", "Bustamante", "Cifuentes", "Paredes"],
    "Middle East": ["Haddad", "Mansour", "Khoury", "Nasser", "Saleh", "Farouk", "Rahimi", "Darwish", "Aziz",
                    "Sabbagh", "Hamdan", "Qasim", "Tahan", "Bishara", "Jaber", "Najjar"],
    "Asia Pacific": ["Tan", "Lim", "Wong", "Nakamura", "Takeda", "Nguyen", "Iyer", "Raman", "Chua", "Ong",
                     "Matsuda", "Pham", "Krishnan", "Goh", "Yamada", "Desai"],
    "Africa": ["Okafor", "Mensah", "Adeyemi", "Banda", "Diallo", "Kamau", "Owusu", "Nkosi", "Abiodun", "Mwangi",
               "Traore", "Achebe", "Moyo", "Boateng", "Odhiambo", "Keita"],
}

# Fictional surnames built from syllables, so list names rarely collide by accident with
# customer names (and never with a real listed person by design).
SURNAME_PRE: Dict[str, List[str]] = {
    "North America": ["Whit", "Hart", "Bren", "Fair", "Hollo", "Pres", "Callo", "Thorn", "Merri", "Ash", "Kings",
                      "Dal", "Lang", "Sut", "Bram", "Wex"],
    "Europe": ["Kowal", "Lind", "Mor", "Beck", "Ross", "Jans", "Nov", "Hoff", "Dub", "Ander", "Ferr", "Kamin",
               "Lamb", "Weis", "Berg", "Schm"],
    "Latin America": ["Restr", "Quint", "Valder", "Carden", "Arri", "Benav", "Mont", "Salc", "Figu", "Echev",
                      "Villa", "Saav", "Oroz", "Bust", "Cifu", "Pare"],
    "Middle East": ["Hadd", "Mans", "Khour", "Nass", "Sal", "Far", "Rah", "Darw", "Az", "Sabb", "Hamd", "Qas",
                    "Tah", "Bish", "Jab", "Najj"],
    "Asia Pacific": ["Naka", "Take", "Yama", "Matsu", "Kri", "Desa", "Wata", "Hira", "Sato", "Ko", "Mura", "Tana",
                     "Kawa", "Fuji", "Ishi", "Mori"],
    "Africa": ["Oka", "Men", "Adey", "Ban", "Dia", "Kam", "Ow", "Nko", "Abi", "Mwa", "Tra", "Ache", "Mo", "Boa",
               "Odhi", "Kei"],
}
SURNAME_SUF: Dict[str, List[str]] = {
    "North America": ["field", "ley", "nan", "banks", "way", "cott", "ton", "weather", "ford", "worth", "more", "by",
                      "well", "ridge", "man", "er"],
    "Europe": ["czyk", "qvist", "eau", "er", "etti", "sen", "ak", "mann", "ois", "sson", "eira", "ski", "ert",
               "stein", "strom", "idt"],
    "Latin America": ["epo", "ero", "rama", "as", "aga", "ides", "oya", "edo", "eroa", "erria", "lobos", "edra",
                      "co", "amante", "entes", "des"],
    "Middle East": ["ad", "our", "y", "er", "eh", "ouk", "imi", "ish", "iz", "agh", "an", "im", "ani", "ara", "eri",
                    "ar"],
    "Asia Pacific": ["mura", "da", "moto", "shita", "naka", "ta", "zawa", "nabe", "hara", "gawa", "yama", "kami",
                     "saki", "no", "bayashi", "uchi"],
    "Africa": ["for", "sah", "emi", "da", "llo", "au", "usu", "si", "odun", "ngi", "ore", "be", "yo", "teng",
               "ambo", "ta"],
}


def surname(rng: np.random.Generator, region: str) -> str:
    if rng.random() < 0.25:
        return str(rng.choice(SURNAME[region]))
    return str(rng.choice(SURNAME_PRE[region])) + str(rng.choice(SURNAME_SUF[region]))


COMPANY_WORDS = ["Northgate", "Silverline", "Harbor", "Crescent", "Summit", "Bluewater", "Ironbridge", "Meridian",
                 "Oakridge", "Pinnacle", "Redstone", "Westbrook", "Lakeshore", "Granite", "Evergreen", "Falcon",
                 "Cobalt", "Juniper", "Sterling", "Atlas", "Beacon", "Cedar", "Horizon", "Keystone"]
COMPANY_TRADES = ["Trading", "Logistics", "Holdings", "Imports", "Capital", "Ventures", "Shipping", "Metals",
                  "Textiles", "Commodities", "Consulting", "Exports", "Industries", "Partners"]
COMPANY_SUFFIX = ["LLC", "Ltd", "GmbH", "SA", "Pte Ltd", "FZE", "Inc", "BV"]

# Transliteration pairs used for name variants (both directions)
TRANSLIT = {
    "Omar": "Umar", "Hassan": "Hasan", "Youssef": "Yusuf", "Khalid": "Khaled", "Faisal": "Faysal",
    "Tariq": "Tareq", "Huda": "Hoda", "Ziad": "Ziyad", "Mansour": "Mansur", "Haddad": "Hadad",
    "Nasser": "Nasir", "Saleh": "Salih", "Farouk": "Faruq", "Qasim": "Kassem", "Jaber": "Jabir",
    "Wei": "Way", "Xiu": "Hsiu", "Nguyen": "Nguen", "Kenji": "Kenzi", "Iyer": "Ayyar",
    "Tunde": "Tundey", "Kwame": "Kwami", "Diallo": "Dialo", "Traore": "Traoret",
    "Joaquin": "Joakin", "Echeverria": "Etcheverria", "Villalobos": "Vilalobos",
    "Kowalczyk": "Kovalchik", "Novak": "Nowak", "Hoffmann": "Hofman",
}


def person_name(rng: np.random.Generator, region: str, middle_initial_p: float = 0.15) -> str:
    g = rng.choice(GIVEN[region])
    s = surname(rng, region)
    if rng.random() < middle_initial_p:
        return f"{g} {chr(65 + int(rng.integers(0, 26)))}. {s}"
    return f"{g} {s}"


def company_name(rng: np.random.Generator) -> str:
    return f"{rng.choice(COMPANY_WORDS)} {rng.choice(COMPANY_TRADES)} {rng.choice(COMPANY_SUFFIX)}"


def _typo(rng: np.random.Generator, token: str) -> str:
    if len(token) < 4:
        return token
    i = int(rng.integers(1, len(token) - 1))
    op = rng.integers(0, 3)
    if op == 0:  # swap adjacent
        return token[:i] + token[i + 1] + token[i] + token[i + 2:]
    if op == 1:  # drop a letter
        return token[:i] + token[i + 1:]
    return token[:i] + token[i] + token[i:]  # double a letter


def variant(rng: np.random.Generator, name: str, aggressiveness: float = 0.0) -> str:
    """Return a spelling variant of a listed name, as it might appear in a payment message.

    aggressiveness 0 gives one light edit; 1 stacks transliteration, typos and token changes,
    which is what pushes true matches below the screening threshold.
    """
    tokens = [t for t in name.replace(".", "").split() if len(t) > 1]
    n_edits = 1 + int(rng.binomial(2, min(1.0, 0.15 + 0.6 * aggressiveness)))
    for _ in range(n_edits):
        op = rng.integers(0, 4)
        if op == 0:
            tokens = [TRANSLIT.get(t, {v: k for k, v in TRANSLIT.items()}.get(t, t)) for t in tokens]
        elif op == 1:
            j = int(rng.integers(0, len(tokens)))
            tokens[j] = _typo(rng, tokens[j])
        elif op == 2 and len(tokens) > 1:
            tokens = tokens[::-1]
        else:
            if rng.random() < 0.5 and len(tokens) > 2:
                tokens = [tokens[0], tokens[-1]]
            else:
                tokens.insert(1, chr(65 + int(rng.integers(0, 26))))
    if aggressiveness > 0 and rng.random() < 0.6 * aggressiveness:
        # payment-system truncation and concatenation, common after a messaging-format migration
        tokens = ["".join(tokens[:2])] + tokens[2:]
    return " ".join(tokens)


def near_miss(rng: np.random.Generator, name: str, region: str) -> str:
    """A different person who shares the listed surname: a classic false-positive source."""
    tokens = name.replace(".", "").split()
    others = [g for g in GIVEN[region] if g != tokens[0]]
    return f"{rng.choice(others)} {tokens[-1]}"
