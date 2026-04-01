from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection

from .embeddings import embed_text, get_chroma_client


INDIAN_LAW_COLLECTION = "indian_law_knowledge"


@dataclass
class LawSection:
    """Represents a section from Indian law statutes."""
    act_name: str
    act_short: str
    section_number: str
    section_title: str
    text: str
    old_act_name: str | None = None
    old_act_short: str | None = None
    old_section_number: str | None = None
    category: str | None = None
    punishment: str | None = None
    keywords: list[str] | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def get_law_collection() -> Collection:
    """Get or create the Indian law knowledge collection."""
    return get_chroma_client().get_or_create_collection(name=INDIAN_LAW_COLLECTION)


IPC_TO_BNS_MAP: dict[str, dict[str, Any]] = {
    "302": {
        "bns_section": "103",
        "title": "Murder",
        "description": "Whoever commits murder shall be punished with death, or imprisonment for life, and shall also be liable to fine.",
        "category": "offenses_against_body",
        "punishment": "Death or imprisonment for life, and fine",
        "keywords": ["murder", "killing", "homicide", "death"],
    },
    "304": {
        "bns_section": "105",
        "title": "Culpable Homicide not amounting to Murder",
        "description": "Whoever commits culpable homicide not amounting to murder shall be punished with imprisonment for life, or imprisonment up to 10 years, and fine.",
        "category": "offenses_against_body",
        "punishment": "Imprisonment for life or up to 10 years, and fine",
        "keywords": ["culpable homicide", "death", "killing"],
    },
    "306": {
        "bns_section": "108",
        "title": "Abetment of Suicide",
        "description": "If any person commits suicide, whoever abets the commission of such suicide, shall be punished with imprisonment up to 10 years, and fine.",
        "category": "offenses_against_body",
        "punishment": "Imprisonment up to 10 years, and fine",
        "keywords": ["suicide", "abetment", "instigation"],
    },
    "307": {
        "bns_section": "109",
        "title": "Attempt to Murder",
        "description": "Whoever does any act with such intention or knowledge, and under such circumstances that, if he by that act caused death, he would be guilty of murder, shall be punished.",
        "category": "offenses_against_body",
        "punishment": "Imprisonment up to 10 years, and fine; if hurt caused, imprisonment for life",
        "keywords": ["attempt", "murder", "intent to kill"],
    },
    "354": {
        "bns_section": "74",
        "title": "Assault or Criminal Force to Woman with Intent to Outrage her Modesty",
        "description": "Whoever assaults or uses criminal force to any woman, intending to outrage or knowing it to be likely that he will thereby outrage her modesty.",
        "category": "offenses_against_women",
        "punishment": "Imprisonment from 1 to 5 years, and fine",
        "keywords": ["assault", "woman", "modesty", "outrage", "molestation"],
    },
    "376": {
        "bns_section": "63",
        "title": "Rape",
        "description": "A man is said to commit rape if he has sexual intercourse with a woman under circumstances falling under any of the descriptions specified.",
        "category": "offenses_against_women",
        "punishment": "Rigorous imprisonment not less than 10 years, may extend to life, and fine",
        "keywords": ["rape", "sexual assault", "consent", "woman"],
    },
    "379": {
        "bns_section": "303",
        "title": "Theft",
        "description": "Whoever commits theft shall be punished with imprisonment up to 3 years, or with fine, or with both.",
        "category": "offenses_against_property",
        "punishment": "Imprisonment up to 3 years, or fine, or both",
        "keywords": ["theft", "stealing", "dishonest", "movable property"],
    },
    "380": {
        "bns_section": "305",
        "title": "Theft in Dwelling House",
        "description": "Whoever commits theft in any building, tent or vessel used as a human dwelling, or for custody of property.",
        "category": "offenses_against_property",
        "punishment": "Imprisonment up to 7 years, and fine",
        "keywords": ["theft", "house", "dwelling", "burglary"],
    },
    "384": {
        "bns_section": "308",
        "title": "Extortion",
        "description": "Whoever commits extortion shall be punished with imprisonment up to 3 years, or with fine, or with both.",
        "category": "offenses_against_property",
        "punishment": "Imprisonment up to 3 years, or fine, or both",
        "keywords": ["extortion", "threat", "fear", "property"],
    },
    "392": {
        "bns_section": "309",
        "title": "Robbery",
        "description": "Whoever commits robbery shall be punished with rigorous imprisonment up to 10 years, and fine.",
        "category": "offenses_against_property",
        "punishment": "Rigorous imprisonment up to 10 years, and fine",
        "keywords": ["robbery", "theft", "force", "violence"],
    },
    "406": {
        "bns_section": "316",
        "title": "Criminal Breach of Trust",
        "description": "Whoever commits criminal breach of trust shall be punished with imprisonment up to 3 years, or with fine, or with both.",
        "category": "offenses_against_property",
        "punishment": "Imprisonment up to 3 years, or fine, or both",
        "keywords": ["breach of trust", "misappropriation", "entrustment"],
    },
    "415": {
        "bns_section": "318",
        "title": "Cheating",
        "description": "Whoever, by deceiving any person, fraudulently or dishonestly induces the person so deceived to deliver any property.",
        "category": "offenses_against_property",
        "punishment": "Defined in subsequent sections",
        "keywords": ["cheating", "deception", "fraud", "dishonest"],
    },
    "420": {
        "bns_section": "318",
        "title": "Cheating and Dishonestly Inducing Delivery of Property",
        "description": "Whoever cheats and thereby dishonestly induces the person deceived to deliver any property to any person, or to make, alter or destroy any valuable security.",
        "category": "offenses_against_property",
        "punishment": "Imprisonment up to 7 years, and fine",
        "keywords": ["cheating", "fraud", "dishonest", "property", "inducement", "420"],
    },
    "498A": {
        "bns_section": "85",
        "title": "Cruelty by Husband or Relatives of Husband",
        "description": "Whoever, being the husband or the relative of the husband of a woman, subjects such woman to cruelty shall be punished.",
        "category": "offenses_against_women",
        "punishment": "Imprisonment up to 3 years, and fine",
        "keywords": ["cruelty", "husband", "dowry", "harassment", "matrimonial", "domestic violence"],
    },
    "499": {
        "bns_section": "356",
        "title": "Defamation",
        "description": "Whoever makes or publishes any imputation concerning any person intending to harm the reputation of such person.",
        "category": "defamation",
        "punishment": "Simple imprisonment up to 2 years, or fine, or both",
        "keywords": ["defamation", "reputation", "libel", "slander"],
    },
    "500": {
        "bns_section": "356",
        "title": "Punishment for Defamation",
        "description": "Whoever defames another shall be punished with simple imprisonment up to 2 years, or with fine, or with both.",
        "category": "defamation",
        "punishment": "Simple imprisonment up to 2 years, or fine, or both",
        "keywords": ["defamation", "punishment"],
    },
    "503": {
        "bns_section": "351",
        "title": "Criminal Intimidation",
        "description": "Whoever threatens another with any injury to his person, reputation or property, with intent to cause alarm.",
        "category": "criminal_intimidation",
        "punishment": "Imprisonment up to 2 years, or fine, or both",
        "keywords": ["threat", "intimidation", "alarm", "injury"],
    },
    "506": {
        "bns_section": "351",
        "title": "Punishment for Criminal Intimidation",
        "description": "Whoever commits the offence of criminal intimidation shall be punished with imprisonment up to 2 years, or with fine, or with both.",
        "category": "criminal_intimidation",
        "punishment": "Imprisonment up to 2 years, or fine, or both; if threat of death or grievous hurt, up to 7 years",
        "keywords": ["criminal intimidation", "threat", "punishment"],
    },
    "509": {
        "bns_section": "79",
        "title": "Word, Gesture or Act Intended to Insult the Modesty of a Woman",
        "description": "Whoever intending to insult the modesty of any woman, utters any word, makes any sound or gesture, or exhibits any object.",
        "category": "offenses_against_women",
        "punishment": "Simple imprisonment up to 3 years, and fine",
        "keywords": ["insult", "modesty", "woman", "gesture", "eve teasing"],
    },
}

CRPC_TO_BNSS_MAP: dict[str, dict[str, Any]] = {
    "41": {
        "bnss_section": "35",
        "title": "When Police May Arrest Without Warrant",
        "description": "Any police officer may without an order from a Magistrate and without a warrant, arrest any person in specified circumstances.",
        "category": "arrest",
        "keywords": ["arrest", "warrant", "police", "cognizable"],
    },
    "154": {
        "bnss_section": "173",
        "title": "First Information Report (FIR)",
        "description": "Every information relating to the commission of a cognizable offence shall be reduced to writing by the officer in charge of a police station.",
        "category": "investigation",
        "keywords": ["fir", "first information report", "complaint", "cognizable", "police station"],
    },
    "156": {
        "bnss_section": "175",
        "title": "Police Officer's Power to Investigate Cognizable Case",
        "description": "Any officer in charge of a police station may investigate any cognizable case without the order of a Magistrate.",
        "category": "investigation",
        "keywords": ["investigation", "cognizable", "police"],
    },
    "161": {
        "bnss_section": "180",
        "title": "Examination of Witnesses by Police",
        "description": "Any police officer making an investigation may examine orally any person supposed to be acquainted with the facts and circumstances of the case.",
        "category": "investigation",
        "keywords": ["witness", "examination", "statement", "police"],
    },
    "164": {
        "bnss_section": "183",
        "title": "Recording of Confessions and Statements",
        "description": "Any Metropolitan Magistrate or Judicial Magistrate may record any confession or statement made to him in the course of an investigation.",
        "category": "investigation",
        "keywords": ["confession", "statement", "magistrate", "recording"],
    },
    "167": {
        "bnss_section": "187",
        "title": "Procedure When Investigation Cannot be Completed in 24 Hours",
        "description": "Whenever any person is arrested and detained in custody, and it appears that the investigation cannot be completed within 24 hours.",
        "category": "remand",
        "keywords": ["remand", "custody", "detention", "24 hours", "magistrate"],
    },
    "173": {
        "bnss_section": "193",
        "title": "Report of Police Officer on Completion of Investigation (Chargesheet)",
        "description": "Every investigation shall be completed without unnecessary delay and the officer shall forward a report to the Magistrate.",
        "category": "investigation",
        "keywords": ["chargesheet", "final report", "investigation", "completion"],
    },
    "190": {
        "bnss_section": "210",
        "title": "Cognizance of Offences by Magistrates",
        "description": "Any Magistrate of the first class may take cognizance of any offence upon receiving a complaint, police report, or information.",
        "category": "cognizance",
        "keywords": ["cognizance", "magistrate", "complaint", "offence"],
    },
    "200": {
        "bnss_section": "223",
        "title": "Examination of Complainant",
        "description": "A Magistrate taking cognizance of an offence on complaint shall examine upon oath the complainant and the witnesses present.",
        "category": "complaint",
        "keywords": ["complainant", "examination", "oath", "magistrate"],
    },
    "227": {
        "bnss_section": "250",
        "title": "Discharge",
        "description": "If upon consideration of the record and documents, the Judge considers that there is not sufficient ground for proceeding against the accused, he shall discharge the accused.",
        "category": "trial",
        "keywords": ["discharge", "accused", "insufficient ground"],
    },
    "228": {
        "bnss_section": "251",
        "title": "Framing of Charge",
        "description": "If the Judge is of opinion that there is ground for presuming that the accused has committed an offence, he shall frame a charge.",
        "category": "trial",
        "keywords": ["charge", "framing", "accused", "trial"],
    },
    "313": {
        "bnss_section": "351",
        "title": "Power to Examine the Accused",
        "description": "The Court may at any stage examine the accused for the purpose of enabling him to explain any circumstances appearing in the evidence against him.",
        "category": "trial",
        "keywords": ["accused", "examination", "statement", "313"],
    },
    "436": {
        "bnss_section": "480",
        "title": "Bail in Bailable Offences",
        "description": "When any person accused of a bailable offence is arrested or detained, he shall be released on bail.",
        "category": "bail",
        "keywords": ["bail", "bailable", "release", "bond"],
    },
    "437": {
        "bnss_section": "480",
        "title": "Bail in Non-Bailable Offences",
        "description": "When any person accused of a non-bailable offence is arrested or detained, he may be released on bail at the discretion of the Court.",
        "category": "bail",
        "keywords": ["bail", "non-bailable", "discretion", "court"],
    },
    "438": {
        "bnss_section": "482",
        "title": "Anticipatory Bail",
        "description": "Where any person has reason to believe that he may be arrested on accusation of having committed a non-bailable offence, he may apply for anticipatory bail.",
        "category": "bail",
        "keywords": ["anticipatory bail", "pre-arrest", "apprehension"],
    },
    "439": {
        "bnss_section": "483",
        "title": "Special Powers of High Court or Court of Session Regarding Bail",
        "description": "A High Court or Court of Session may direct that any person accused of an offence and in custody be released on bail.",
        "category": "bail",
        "keywords": ["bail", "high court", "sessions court", "special powers"],
    },
    "482": {
        "bnss_section": "528",
        "title": "Inherent Powers of High Court",
        "description": "Nothing in this Code shall be deemed to limit or affect the inherent powers of the High Court to make such orders as may be necessary.",
        "category": "high_court",
        "keywords": ["inherent powers", "high court", "quashing", "482"],
    },
}

OTHER_IMPORTANT_LAWS: list[dict[str, Any]] = [
    {
        "act_name": "Indian Contract Act, 1872",
        "act_short": "ICA",
        "sections": {
            "2": {"title": "Interpretation Clause", "description": "Definitions of proposal, promise, agreement, contract, void agreement, etc.", "keywords": ["definition", "contract", "agreement", "promise"]},
            "10": {"title": "What Agreements are Contracts", "description": "All agreements are contracts if made by free consent of parties competent to contract, for lawful consideration and lawful object.", "keywords": ["valid contract", "free consent", "competent", "lawful"]},
            "14": {"title": "Free Consent", "description": "Consent is said to be free when it is not caused by coercion, undue influence, fraud, misrepresentation, or mistake.", "keywords": ["consent", "coercion", "fraud", "misrepresentation"]},
            "23": {"title": "Unlawful Consideration and Object", "description": "The consideration or object of an agreement is unlawful if it is forbidden by law, defeats provisions of law, is fraudulent, involves injury, or is immoral.", "keywords": ["unlawful", "illegal", "void", "consideration"]},
            "73": {"title": "Compensation for Breach", "description": "When a contract has been broken, the party who suffers is entitled to receive compensation for any loss or damage caused.", "keywords": ["breach", "compensation", "damages", "loss"]},
            "74": {"title": "Liquidated Damages", "description": "When a contract has been broken, if a sum is named in the contract as the amount to be paid in case of breach, the party complaining may receive reasonable compensation not exceeding the amount so named.", "keywords": ["liquidated damages", "penalty", "breach", "compensation"]},
        },
    },
    {
        "act_name": "Consumer Protection Act, 2019",
        "act_short": "CPA",
        "sections": {
            "2(7)": {"title": "Definition of Consumer", "description": "Consumer means any person who buys goods or hires services for consideration.", "keywords": ["consumer", "buyer", "goods", "services"]},
            "2(9)": {"title": "Definition of Defect", "description": "Defect means any fault, imperfection or shortcoming in the quality, quantity, potency, purity or standard.", "keywords": ["defect", "fault", "quality", "standard"]},
            "2(11)": {"title": "Definition of Deficiency", "description": "Deficiency means any fault, imperfection, shortcoming or inadequacy in the quality, nature and manner of performance of service.", "keywords": ["deficiency", "service", "inadequacy", "performance"]},
            "34": {"title": "Jurisdiction of District Commission", "description": "District Commission shall have jurisdiction to entertain complaints where value of goods or services does not exceed one crore rupees.", "keywords": ["district commission", "jurisdiction", "complaint", "one crore"]},
            "35": {"title": "Jurisdiction of State Commission", "description": "State Commission shall have jurisdiction where value exceeds one crore but does not exceed ten crore rupees.", "keywords": ["state commission", "jurisdiction", "ten crore"]},
            "47": {"title": "Penalties", "description": "Where a trader or person fails to comply with any order, he shall be punishable with imprisonment or fine or both.", "keywords": ["penalty", "non-compliance", "punishment"]},
        },
    },
    {
        "act_name": "Negotiable Instruments Act, 1881",
        "act_short": "NI Act",
        "sections": {
            "138": {"title": "Dishonour of Cheque for Insufficiency of Funds", "description": "Where any cheque is returned unpaid due to insufficient funds, the drawer shall be deemed to have committed an offence.", "keywords": ["cheque bounce", "dishonour", "insufficient funds", "138"]},
            "139": {"title": "Presumption in Favour of Holder", "description": "It shall be presumed that the holder of a cheque received the cheque for discharge of any debt or liability.", "keywords": ["presumption", "holder", "debt", "liability"]},
            "141": {"title": "Offences by Companies", "description": "If the person committing an offence under section 138 is a company, every person who was in charge of the company shall be deemed guilty.", "keywords": ["company", "director", "liability", "138"]},
            "142": {"title": "Cognizance of Offences", "description": "No court shall take cognizance of any offence punishable under section 138 except upon a complaint in writing made by the payee.", "keywords": ["cognizance", "complaint", "payee", "138"]},
            "143": {"title": "Power of Court to Try Cases Summarily", "description": "Notwithstanding anything contained in the Code, all offences under this Chapter shall be tried by a Judicial Magistrate of the first class or by a Metropolitan Magistrate.", "keywords": ["summary trial", "magistrate", "138"],},
        },
    },
    {
        "act_name": "Information Technology Act, 2000",
        "act_short": "IT Act",
        "sections": {
            "43": {"title": "Penalty for Damage to Computer System", "description": "If any person without permission accesses or downloads data from a computer, he shall be liable to pay damages.", "keywords": ["hacking", "unauthorized access", "computer", "damage"]},
            "66": {"title": "Computer Related Offences", "description": "If any person dishonestly or fraudulently does any act referred to in section 43, he shall be punishable with imprisonment up to 3 years or fine up to 5 lakh rupees.", "keywords": ["hacking", "fraud", "computer crime", "cyber"]},
            "66A": {"title": "Sending Offensive Messages (Struck Down)", "description": "This section was struck down by the Supreme Court in Shreya Singhal case as unconstitutional.", "keywords": ["offensive message", "struck down", "unconstitutional"]},
            "66C": {"title": "Identity Theft", "description": "Whoever fraudulently or dishonestly makes use of the electronic signature, password or any other unique identification feature of any other person.", "keywords": ["identity theft", "password", "fraud", "impersonation"]},
            "66D": {"title": "Cheating by Personation using Computer Resource", "description": "Whoever by means of any communication device or computer resource cheats by personation.", "keywords": ["cheating", "personation", "online fraud", "impersonation"]},
            "67": {"title": "Publishing Obscene Material", "description": "Whoever publishes or transmits or causes to be published in electronic form any material which is obscene.", "keywords": ["obscene", "pornography", "electronic", "publish"]},
            "72": {"title": "Breach of Confidentiality and Privacy", "description": "Any person who has secured access to any electronic record, book, register, correspondence, information, document or other material, and discloses it without consent.", "keywords": ["privacy", "confidentiality", "disclosure", "breach"]},
        },
    },
    {
        "act_name": "Constitution of India",
        "act_short": "COI",
        "sections": {
            "14": {"title": "Equality Before Law", "description": "The State shall not deny to any person equality before the law or the equal protection of the laws within the territory of India.", "keywords": ["equality", "law", "discrimination", "fundamental right"]},
            "19": {"title": "Protection of Certain Rights", "description": "All citizens shall have the right to freedom of speech and expression, to assemble peaceably, to form associations, to move freely, to reside and settle, and to practice any profession.", "keywords": ["freedom", "speech", "expression", "assembly", "movement"]},
            "21": {"title": "Protection of Life and Personal Liberty", "description": "No person shall be deprived of his life or personal liberty except according to procedure established by law.", "keywords": ["life", "liberty", "due process", "fundamental right"]},
            "22": {"title": "Protection Against Arrest and Detention", "description": "No person who is arrested shall be detained in custody without being informed of the grounds for such arrest.", "keywords": ["arrest", "detention", "grounds", "legal aid"]},
            "32": {"title": "Remedies for Enforcement of Fundamental Rights", "description": "The right to move the Supreme Court for enforcement of fundamental rights is guaranteed.", "keywords": ["supreme court", "writ", "fundamental rights", "enforcement"]},
            "226": {"title": "Power of High Courts to Issue Writs", "description": "Every High Court shall have power to issue writs for enforcement of fundamental rights and for any other purpose.", "keywords": ["high court", "writ", "habeas corpus", "mandamus", "certiorari"]},
        },
    },
]


def normalize_section_number(section: str) -> str:
    """Normalize section number for matching."""
    section = section.strip().upper()
    section = re.sub(r"^(SECTION|SEC\.?|S\.?)\s*", "", section, flags=re.IGNORECASE)
    section = re.sub(r"\s+", "", section)
    return section


def lookup_ipc_section(section: str) -> dict[str, Any] | None:
    """Look up an IPC section and return its details with BNS mapping."""
    normalized = normalize_section_number(section)
    
    if normalized in IPC_TO_BNS_MAP:
        data = IPC_TO_BNS_MAP[normalized]
        return {
            "found": True,
            "act": "Indian Penal Code, 1860",
            "act_short": "IPC",
            "section": normalized,
            "title": data["title"],
            "description": data["description"],
            "category": data["category"],
            "punishment": data.get("punishment"),
            "keywords": data.get("keywords", []),
            "new_law": {
                "act": "Bharatiya Nyaya Sanhita, 2023",
                "act_short": "BNS",
                "section": data["bns_section"],
            },
        }
    return None


def lookup_bns_section(section: str) -> dict[str, Any] | None:
    """Look up a BNS section and return its details with IPC mapping."""
    normalized = normalize_section_number(section)
    
    for ipc_section, data in IPC_TO_BNS_MAP.items():
        if data["bns_section"] == normalized:
            return {
                "found": True,
                "act": "Bharatiya Nyaya Sanhita, 2023",
                "act_short": "BNS",
                "section": normalized,
                "title": data["title"],
                "description": data["description"],
                "category": data["category"],
                "punishment": data.get("punishment"),
                "keywords": data.get("keywords", []),
                "old_law": {
                    "act": "Indian Penal Code, 1860",
                    "act_short": "IPC",
                    "section": ipc_section,
                },
            }
    return None


def lookup_crpc_section(section: str) -> dict[str, Any] | None:
    """Look up a CrPC section and return its details with BNSS mapping."""
    normalized = normalize_section_number(section)
    
    if normalized in CRPC_TO_BNSS_MAP:
        data = CRPC_TO_BNSS_MAP[normalized]
        return {
            "found": True,
            "act": "Code of Criminal Procedure, 1973",
            "act_short": "CrPC",
            "section": normalized,
            "title": data["title"],
            "description": data["description"],
            "category": data["category"],
            "keywords": data.get("keywords", []),
            "new_law": {
                "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
                "act_short": "BNSS",
                "section": data["bnss_section"],
            },
        }
    return None


def lookup_bnss_section(section: str) -> dict[str, Any] | None:
    """Look up a BNSS section and return its details with CrPC mapping."""
    normalized = normalize_section_number(section)
    
    for crpc_section, data in CRPC_TO_BNSS_MAP.items():
        if data["bnss_section"] == normalized:
            return {
                "found": True,
                "act": "Bharatiya Nagarik Suraksha Sanhita, 2023",
                "act_short": "BNSS",
                "section": normalized,
                "title": data["title"],
                "description": data["description"],
                "category": data["category"],
                "keywords": data.get("keywords", []),
                "old_law": {
                    "act": "Code of Criminal Procedure, 1973",
                    "act_short": "CrPC",
                    "section": crpc_section,
                },
            }
    return None


def lookup_section(query: str) -> dict[str, Any] | None:
    """
    Universal section lookup that tries to identify the act and section.
    Supports formats like:
    - "IPC 420", "Section 420 IPC", "420 IPC"
    - "BNS 318", "Section 318 BNS"
    - "CrPC 154", "Section 154 CrPC"
    - "BNSS 173"
    """
    query = query.strip().upper()
    
    ipc_match = re.search(r"(?:IPC|INDIAN\s*PENAL\s*CODE)\s*(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)", query)
    if not ipc_match:
        ipc_match = re.search(r"(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)\s*(?:OF\s*)?(?:IPC|INDIAN\s*PENAL\s*CODE)", query)
    if ipc_match:
        return lookup_ipc_section(ipc_match.group(1))
    
    bns_match = re.search(r"(?:BNS|BHARATIYA\s*NYAYA\s*SANHITA)\s*(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)", query)
    if not bns_match:
        bns_match = re.search(r"(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)\s*(?:OF\s*)?(?:BNS|BHARATIYA\s*NYAYA\s*SANHITA)", query)
    if bns_match:
        return lookup_bns_section(bns_match.group(1))
    
    crpc_match = re.search(r"(?:CRPC|CR\.?P\.?C\.?|CRIMINAL\s*PROCEDURE\s*CODE)\s*(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)", query)
    if not crpc_match:
        crpc_match = re.search(r"(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)\s*(?:OF\s*)?(?:CRPC|CR\.?P\.?C\.?)", query)
    if crpc_match:
        return lookup_crpc_section(crpc_match.group(1))
    
    bnss_match = re.search(r"(?:BNSS|BHARATIYA\s*NAGARIK\s*SURAKSHA\s*SANHITA)\s*(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)", query)
    if not bnss_match:
        bnss_match = re.search(r"(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)\s*(?:OF\s*)?(?:BNSS)", query)
    if bnss_match:
        return lookup_bnss_section(bnss_match.group(1))
    
    section_only = re.search(r"(?:SECTION|SEC\.?|S\.?)?\s*(\d+[A-Z]?)", query)
    if section_only:
        section = section_only.group(1)
        result = lookup_ipc_section(section)
        if result:
            return result
        result = lookup_crpc_section(section)
        if result:
            return result
    
    return None


def search_law_by_topic(topic: str, limit: int = 5) -> list[dict[str, Any]]:
    """
    Search for relevant law sections by topic/keyword.
    """
    topic_lower = topic.lower()
    results = []
    
    for ipc_section, data in IPC_TO_BNS_MAP.items():
        keywords = data.get("keywords", [])
        title_lower = data["title"].lower()
        desc_lower = data["description"].lower()
        
        score = 0
        for kw in keywords:
            if kw in topic_lower:
                score += 2
        if any(word in title_lower for word in topic_lower.split()):
            score += 1
        if any(word in desc_lower for word in topic_lower.split()):
            score += 0.5
        
        if score > 0:
            results.append({
                "score": score,
                "act": "IPC",
                "section": ipc_section,
                "title": data["title"],
                "description": data["description"],
                "bns_section": data["bns_section"],
            })
    
    for crpc_section, data in CRPC_TO_BNSS_MAP.items():
        keywords = data.get("keywords", [])
        title_lower = data["title"].lower()
        desc_lower = data["description"].lower()
        
        score = 0
        for kw in keywords:
            if kw in topic_lower:
                score += 2
        if any(word in title_lower for word in topic_lower.split()):
            score += 1
        if any(word in desc_lower for word in topic_lower.split()):
            score += 0.5
        
        if score > 0:
            results.append({
                "score": score,
                "act": "CrPC",
                "section": crpc_section,
                "title": data["title"],
                "description": data["description"],
                "bnss_section": data["bnss_section"],
            })
    
    for act_info in OTHER_IMPORTANT_LAWS:
        for section, data in act_info["sections"].items():
            keywords = data.get("keywords", [])
            title_lower = data["title"].lower()
            desc_lower = data["description"].lower()
            
            score = 0
            for kw in keywords:
                if kw in topic_lower:
                    score += 2
            if any(word in title_lower for word in topic_lower.split()):
                score += 1
            if any(word in desc_lower for word in topic_lower.split()):
                score += 0.5
            
            if score > 0:
                results.append({
                    "score": score,
                    "act": act_info["act_short"],
                    "act_full": act_info["act_name"],
                    "section": section,
                    "title": data["title"],
                    "description": data["description"],
                })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def get_all_law_entries() -> list[dict[str, Any]]:
    """Get all law entries for indexing."""
    entries = []
    
    for section, data in IPC_TO_BNS_MAP.items():
        entries.append({
            "id": f"ipc-{section}",
            "act": "Indian Penal Code, 1860",
            "act_short": "IPC",
            "section": section,
            "title": data["title"],
            "text": f"Section {section} IPC - {data['title']}: {data['description']}",
            "description": data["description"],
            "category": data["category"],
            "punishment": data.get("punishment"),
            "keywords": data.get("keywords", []),
            "bns_section": data["bns_section"],
        })
    
    for section, data in CRPC_TO_BNSS_MAP.items():
        entries.append({
            "id": f"crpc-{section}",
            "act": "Code of Criminal Procedure, 1973",
            "act_short": "CrPC",
            "section": section,
            "title": data["title"],
            "text": f"Section {section} CrPC - {data['title']}: {data['description']}",
            "description": data["description"],
            "category": data["category"],
            "keywords": data.get("keywords", []),
            "bnss_section": data["bnss_section"],
        })
    
    for act_info in OTHER_IMPORTANT_LAWS:
        for section, data in act_info["sections"].items():
            entries.append({
                "id": f"{act_info['act_short'].lower().replace(' ', '-')}-{section}",
                "act": act_info["act_name"],
                "act_short": act_info["act_short"],
                "section": section,
                "title": data["title"],
                "text": f"Section {section} {act_info['act_short']} - {data['title']}: {data['description']}",
                "description": data["description"],
                "keywords": data.get("keywords", []),
            })
    
    return entries


def index_law_knowledge() -> int:
    """Index all law entries into ChromaDB for semantic search."""
    collection = get_law_collection()
    entries = get_all_law_entries()
    
    if not entries:
        return 0
    
    ids = [entry["id"] for entry in entries]
    documents = [entry["text"] for entry in entries]
    embeddings = [embed_text(doc) for doc in documents]
    metadatas = [
        {
            "act": entry["act"],
            "act_short": entry["act_short"],
            "section": entry["section"],
            "title": entry["title"],
            "category": entry.get("category", ""),
            "punishment": entry.get("punishment", ""),
        }
        for entry in entries
    ]
    
    collection.upsert(ids=ids, documents=documents, embeddings=embeddings, metadatas=metadatas)
    return len(entries)


def semantic_search_laws(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Perform semantic search over the law knowledge base."""
    collection = get_law_collection()
    
    try:
        count = collection.count()
        if count == 0:
            index_law_knowledge()
    except Exception:
        index_law_knowledge()
    
    results = collection.query(
        query_embeddings=[embed_text(query)],
        n_results=limit,
        include=["documents", "metadatas", "distances"],
    )
    
    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    
    output = []
    for doc, meta, dist in zip(documents, metadatas, distances):
        output.append({
            "text": doc,
            "metadata": meta,
            "distance": dist,
            "relevance_score": 1.0 / (1.0 + dist),
        })
    
    return output
