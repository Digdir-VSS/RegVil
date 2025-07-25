from typing import TypedDict, Optional, List


class Valg(TypedDict, total=False):
    Nummer: Optional[str]
    Tekst: Optional[str]


class AndreVirksomheter(TypedDict, total=False):
    Navn: Optional[str]


class Kontaktperson(TypedDict, total=False):
    FulltNavn: Optional[str]
    Telefonnummer: Optional[str]
    EPostadresse: Optional[str]


class Tiltak(TypedDict, total=False):
    Nummer: Optional[str]
    Tekst: Optional[str]
    ErDeltiltak: Optional[bool]


class AnsvarligEnhet(TypedDict, total=False):
    Navn: Optional[str]
    Organisasjonsnummer: Optional[str]


class Godkjenning(TypedDict, total=False):
    SkalGodkjennes: Optional[bool]
    Godkjenner: Optional[Kontaktperson]


class Prefill(TypedDict, total=False):
    Tiltak: Optional[Tiltak]
    Kapittel: Optional[Valg]
    Maal: Optional[Valg]
    AnsvarligDepartement: Optional[AnsvarligEnhet]
    AnsvarligVirksomhet: Optional[AnsvarligEnhet]
    Kontaktperson: Optional[Kontaktperson]
    Godkjenning: Optional[Godkjenning]


class Initiell(TypedDict, total=False):
    TiltakKortnavn: Optional[str]
    AndreMaal: Optional[List[Valg]]
    AndreVirksomheter: Optional[List[AndreVirksomheter]]
    Kontaktperson: Optional[Kontaktperson]
    AndreKontaktpersoner: Optional[List[Kontaktperson]]
    ErTiltaketPaabegynt: Optional[bool]
    DatoPaabegynt: Optional[str]
    VetOppstartsDato: Optional[bool]
    DatoForventetOppstart: Optional[str]


class Leveranse(TypedDict, total=False):
    Beskrivelse: Optional[str]
    Status: Optional[str]


class Likert(TypedDict, total=False):
    Id: Optional[str]
    Svar: Optional[str]


class Oppstart(TypedDict, total=False):
    StemmerTidligereInfo: Optional[bool]
    ForventetSluttdato: Optional[str]
    HarKostnadsestimat: Optional[str]
    Kostnadsestimat: Optional[str]
    HarFinansiering: Optional[str]
    Finansieringskilder: Optional[str]


class Status(TypedDict, total=False):
    StemmerTidligereInfo: Optional[bool]
    ErArbeidAvsluttet: Optional[bool]
    TiltakStatus: Optional[str]
    ForsinkelseTiltakBeskrivelse: Optional[str]
    Nettside: Optional[str]
    HindringerLikert: Optional[List[Likert]]
    HindringerBeskrivelse: Optional[str]
    DrivereLikert: Optional[List[Likert]]
    DrivereBeskrivelse: Optional[str]


class Slutt(TypedDict, total=False):
    TiltakArbeidBeskrivelse: Optional[str]
    DatoAvsluttet: Optional[str]
    HindringerLikert: Optional[List[Likert]]
    HindringerBeskrivelse: Optional[str]
    DrivereLikert: Optional[List[Likert]]
    DrivereBeskrivelse: Optional[str]
    LaerdommerBeskrivelse: Optional[str]


class DataModel(TypedDict, total=False):
    Prefill: Optional[Prefill]
    Initiell: Optional[Initiell]
    Oppstart: Optional[Oppstart]
    Status: Optional[Status]
    Slutt: Optional[Slutt]
    Leveranser: Optional[List[Leveranse]]
