"""Write our own demo course notes (French, 4 pages) as a PDF: data/courses/trace_notes/cours_fractions_relatifs.pdf
and a copy in docs/demo/ to upload in the Study Plan demo.

Original text written by the TRACE team (no third-party content). Each page covers one of the 4 bank
misconceptions; every calculation is checked with SymPy before the file is written.
Usage: .\\.venv\\Scripts\\python.exe scripts\\make_course_notes.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import ROOT, mathcheck as mc  # noqa: E402
from engine.studio.pdf import Doc  # noqa: E402

PAGES = [
    ("Chapitre 1 : Additionner des fractions", [
        "Pour additionner deux fractions, il faut d'abord qu'elles aient le même dénominateur.",
        "On ne peut jamais additionner les dénominateurs entre eux.",
        "Méthode : 1) chercher un dénominateur commun ; 2) écrire chaque fraction avec ce dénominateur, en "
        "multipliant son numérateur et son dénominateur par le même nombre ; 3) additionner les numérateurs ; "
        "4) garder le dénominateur commun ; 5) simplifier si possible.",
        "Exemple : 1/3 + 2/5. Le dénominateur commun est 15. 1/3 = 5/15 et 2/5 = 6/15. Donc 1/3 + 2/5 = 11/15.",
        "Erreur fréquente : additionner les numérateurs et les dénominateurs, ce qui donne 3/8. "
        "Ce résultat est faux : 3/8 est plus petit que 2/5, alors que la somme doit être plus grande que chaque fraction.",
        "Cas simple : si les dénominateurs sont déjà égaux, on additionne seulement les numérateurs : "
        "2/7 + 1/7 = 3/7.",
    ]),
    ("Chapitre 2 : Multiplier une fraction par un nombre entier", [
        "Pour multiplier une fraction par un nombre entier, on multiplie seulement le numérateur. "
        "Le dénominateur ne change pas.",
        "Exemple : 2/3 × 5 = 10/3. En nombre mixte : 10/3 = 3 + 1/3.",
        "Vérification : 2/3 × 5 = 2/3 + 2/3 + 2/3 + 2/3 + 2/3 = 10/3.",
        "Erreur fréquente : multiplier aussi le dénominateur, ce qui donne 10/15. "
        "Ce résultat est faux : 10/15 = 2/3, la valeur de départ n'a pas changé, alors qu'on a multiplié par 5.",
        "Autre exemple : 1/6 × 6 = 6/6 = 1.",
    ]),
    ("Chapitre 3 : Soustraire un nombre négatif", [
        "Soustraire un nombre négatif revient à ajouter son opposé.",
        "Exemple : (-8) - (-5) = -8 + 5 = -3.",
        "Sur une droite graduée : on part de -8 ; enlever -5 revient à avancer de 5 vers la droite ; on arrive à -3.",
        "Erreur fréquente : appliquer « moins par moins donne plus » à une soustraction et répondre 3 ou 13. "
        "Cette règle concerne la multiplication : (-2) × (-3) = 6.",
        "Autre exemple : (-3) - 5 = -8, car on enlève 5 à partir de -3.",
    ]),
    ("Chapitre 4 : Fractions égales (équivalentes)", [
        "Deux fractions sont égales quand on passe de l'une à l'autre en multipliant (ou en divisant) "
        "le numérateur et le dénominateur par le même nombre.",
        "Exemple : 9/15 = 3/5 (on divise par 3) et 3/5 = 6/10 (on multiplie par 2). Donc 9/15 = 6/10.",
        "Pour trouver A dans A/10 = 9/15 : on simplifie 9/15 en 3/5, puis 3/5 = 6/10. Donc A = 6.",
        "Erreur fréquente : ajouter ou enlever le même nombre en haut et en bas. "
        "Passer de 15 à 10 en enlevant 5, puis faire 9 - 5 = 4, donne 4/10. Ce résultat est faux : 4/10 = 2/5, "
        "et 2/5 n'est pas égal à 3/5.",
        "Autre exemple : 4/6 = 8/12 (on multiplie par 2).",
    ]),
]
NOTE = "Notes de cours rédigées par l'équipe TRACE pour la démonstration (contenu original)."

# every equality written as "a = b" in the notes, checked with SymPy (statements the text calls wrong are skipped)
CHECKS = [("1/3 + 2/5", "11/15"), ("5/15", "1/3"), ("6/15", "2/5"), ("2/7 + 1/7", "3/7"), ("2/3 * 5", "10/3"),
          ("10/3", "3 + 1/3"), ("10/15", "2/3"), ("1/6 * 6", "1"), ("(-8) - (-5)", "-3"), ("(-2) * (-3)", "6"),
          ("(-3) - 5", "-8"), ("9/15", "3/5"), ("3/5", "6/10"), ("4/10", "2/5"), ("4/6", "8/12")]


def main():
    for a, b in CHECKS:
        assert mc.equal(a, b), (a, b)
    assert mc.compare("3/8", "<", "2/5") and not mc.equal("2/5", "3/5")
    doc = Doc("Cours : fractions et nombres relatifs")
    for i, (title, paras) in enumerate(PAGES):
        if i:
            doc.page()
        doc.title(title)
        for p in paras:
            doc.text(p)
        doc.text(NOTE, size=8)
    out = ROOT / "data" / "courses" / "trace_notes" / "cours_fractions_relatifs.pdf"
    doc.save(out)
    (out.parent / "meta.yaml").write_text("# Our own course notes (TRACE team): derivatives allowed.\n"
                                          "allow_derivatives: true\n", encoding="utf-8")
    demo = ROOT / "docs" / "demo" / out.name
    demo.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(out, demo)
    print("wrote", out.relative_to(ROOT), "and", demo.relative_to(ROOT))


if __name__ == "__main__":
    main()
