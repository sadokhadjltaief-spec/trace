"""Writes data/curriculum/tunisie_maths.json: an INDICATIVE maths reference programme written by the TRACE team from
general knowledge of the Tunisian curriculum (7e de base to the Bac). Not the official Ministry document: check it
against the official programmes before any real use. Usage: python scripts/make_curriculum.py
"""
import json
from pathlib import Path

A, G, S, N = "algebre", "geometrie", "statistiques", "analyse"

def ch(domain, fr, ar, en, notions):
    return {"domain": domain, "title": {"fr": fr, "ar": ar, "en": en}, "notions": notions}

LEVELS = [
 ("7e", "base", ("7e année de base", "السنة السابعة أساسي", "7th grade (basic)"), [
  ch(A, "Nombres entiers naturels", "الأعداد الصحيحة الطبيعية", "Whole numbers", ["Opérations", "Puissances d'un entier", "Priorités de calcul"]),
  ch(A, "Divisibilité", "قابلية القسمة", "Divisibility", ["Multiples et diviseurs", "Critères de divisibilité", "Nombres premiers"]),
  ch(A, "Fractions", "الكسور", "Fractions", ["Fractions égales", "Comparaison", "Addition et soustraction", "Multiplication"]),
  ch(A, "Nombres décimaux", "الأعداد العشرية", "Decimal numbers", ["Écriture décimale", "Opérations", "Arrondi et troncature"]),
  ch(A, "Proportionnalité", "التناسبية", "Proportionality", ["Tableau de proportionnalité", "Pourcentages", "Échelles"]),
  ch(G, "Droites, demi-droites et segments", "المستقيمات ونصف المستقيمات والقطع", "Lines, rays and segments", ["Droites parallèles et perpendiculaires", "Médiatrice d'un segment"]),
  ch(G, "Angles", "الزوايا", "Angles", ["Mesure d'un angle", "Bissectrice", "Angles particuliers"]),
  ch(G, "Triangles et quadrilatères", "المثلثات والرباعيات", "Triangles and quadrilaterals", ["Construction de triangles", "Triangles particuliers", "Quadrilatères usuels"]),
  ch(G, "Symétrie axiale", "التناظر المحوري", "Line symmetry", ["Symétrique d'un point, d'une figure", "Axes de symétrie"]),
  ch(G, "Périmètres, aires et volumes", "المحيطات والمساحات والأحجام", "Perimeters, areas and volumes", ["Aire du rectangle, du triangle, du disque", "Volume du pavé droit"]),
 ]),
 ("8e", "base", ("8e année de base", "السنة الثامنة أساسي", "8th grade (basic)"), [
  ch(A, "Nombres décimaux relatifs", "الأعداد العشرية النسبية", "Signed numbers", ["Opposé, valeur absolue", "Addition et soustraction", "Multiplication et division", "Règle des signes"]),
  ch(A, "Nombres rationnels", "الأعداد الكسرية النسبية", "Rational numbers", ["Opérations sur les fractions", "Comparaison", "Fraction irréductible"]),
  ch(A, "Puissances", "القوى", "Powers", ["Puissances d'exposant entier", "Puissances de 10", "Écriture scientifique"]),
  ch(A, "Calcul littéral", "الحساب الحرفي", "Algebraic expressions", ["Développement", "Factorisation", "Réduction d'une expression"]),
  ch(A, "Équations du premier degré", "معادلات من الدرجة الأولى", "Linear equations", ["Résolution", "Mise en équation d'un problème"]),
  ch(A, "Proportionnalité et pourcentages", "التناسبية والنسب المائوية", "Proportionality and percentages", ["Grandeurs proportionnelles", "Augmentation et réduction en pourcentage"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Effectifs et fréquences", "Diagrammes", "Moyenne"]),
  ch(G, "Symétrie centrale", "التناظر المركزي", "Point symmetry", ["Symétrique d'un point, d'une figure", "Centre de symétrie"]),
  ch(G, "Parallélogramme et quadrilatères particuliers", "متوازي الأضلاع والرباعيات الخاصة", "Parallelograms", ["Propriétés du parallélogramme", "Rectangle, losange, carré"]),
  ch(G, "Droites remarquables du triangle", "المستقيمات الخاصة في المثلث", "Special lines of a triangle", ["Médiatrices", "Hauteurs", "Médianes", "Bissectrices"]),
  ch(G, "Théorème de Pythagore", "مبرهنة بيتاغور", "Pythagorean theorem", ["Théorème direct", "Réciproque"]),
  ch(G, "Prisme droit et cylindre", "الموشور القائم والأسطوانة", "Prism and cylinder", ["Patron", "Aire latérale", "Volume"]),
 ]),
 ("9e", "base", ("9e année de base", "السنة التاسعة أساسي", "9th grade (basic)"), [
  ch(A, "Nombres réels et racines carrées", "الأعداد الحقيقية والجذور التربيعية", "Real numbers and square roots", ["Racine carrée", "Opérations sur les radicaux", "Ordre dans IR"]),
  ch(A, "Calcul algébrique et identités remarquables", "الحساب الجبري والمتطابقات الهامة", "Algebra and special products", ["(a+b)², (a−b)², (a+b)(a−b)", "Factorisation"]),
  ch(A, "Équations et inéquations du premier degré", "المعادلات والمتراجحات من الدرجة الأولى", "Linear equations and inequalities", ["Équation produit", "Inéquations", "Problèmes"]),
  ch(A, "Systèmes de deux équations à deux inconnues", "جمل معادلتين بمجهولين", "Systems of two equations", ["Substitution", "Combinaison", "Interprétation graphique"]),
  ch(N, "Applications linéaires et affines", "الدوال الخطية والتآلفية", "Linear and affine functions", ["Coefficient directeur", "Représentation graphique", "Lecture graphique"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Moyenne, médiane, étendue", "Effectifs cumulés"]),
  ch(G, "Théorème de Thalès", "مبرهنة طالس", "Thales' theorem", ["Théorème direct", "Réciproque", "Agrandissement et réduction"]),
  ch(G, "Relations métriques dans le triangle rectangle", "العلاقات القياسية في المثلث القائم", "Right-triangle relations", ["Hauteur relative à l'hypoténuse", "Projections"]),
  ch(G, "Trigonométrie", "حساب المثلثات", "Trigonometry", ["Cosinus, sinus, tangente d'un angle aigu", "Relations trigonométriques"]),
  ch(G, "Vecteurs et translation", "المتجهات والانسحاب", "Vectors and translation", ["Égalité de vecteurs", "Somme de vecteurs", "Translation"]),
  ch(G, "Angles inscrits", "الزوايا المحيطية", "Inscribed angles", ["Angle inscrit et angle au centre", "Polygones réguliers"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Pyramide", "Cône", "Sphère et boule"]),
 ]),
 ("1s", "secondaire", ("1ère année secondaire", "السنة الأولى ثانوي", "1st year secondary"), [
  ch(A, "Calcul dans IR", "الحساب في IR", "Computing in IR", ["Puissances et radicaux", "Ordre et encadrement", "Valeur absolue"]),
  ch(A, "Arithmétique", "الحسابيات", "Arithmetic", ["PGCD et PPCM", "Nombres premiers", "Décomposition en facteurs premiers"]),
  ch(A, "Équations et inéquations du premier degré", "المعادلات والمتراجحات من الدرجة الأولى", "Linear equations and inequalities", ["Équations à une inconnue", "Inéquations", "Systèmes"]),
  ch(N, "Fonctions linéaires et affines", "الدوال الخطية والتآلفية", "Linear and affine functions", ["Sens de variation", "Représentation graphique"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Caractères qualitatifs et quantitatifs", "Moyenne et médiane", "Histogrammes"]),
  ch(G, "Théorème de Thalès et applications", "مبرهنة طالس وتطبيقاتها", "Thales' theorem", ["Configurations de Thalès", "Constructions"]),
  ch(G, "Vecteurs et repérage", "المتجهات والمعالم", "Vectors and coordinates", ["Coordonnées d'un vecteur", "Milieu, distance", "Colinéarité"]),
  ch(G, "Trigonométrie", "حساب المثلثات", "Trigonometry", ["Rapports trigonométriques", "Angles remarquables"]),
  ch(G, "Isométries du plan", "التقايسات في المستوي", "Plane isometries", ["Symétries", "Translations", "Rotations"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Positions relatives de droites et plans", "Solides usuels"]),
 ]),
 ("2s", "secondaire", ("2e année Sciences", "السنة الثانية علوم", "2nd year Sciences"), [
  ch(A, "Polynômes et second degré", "كثيرات الحدود والدرجة الثانية", "Polynomials and quadratics", ["Discriminant", "Équations et inéquations du second degré", "Factorisation"]),
  ch(A, "Systèmes d'équations linéaires", "جمل المعادلات الخطية", "Linear systems", ["Méthode de Cramer / substitution", "Problèmes"]),
  ch(N, "Généralités sur les fonctions", "عموميات حول الدوال", "Functions", ["Ensemble de définition", "Sens de variation", "Parité"]),
  ch(N, "Fonctions de référence", "الدوال المرجعية", "Reference functions", ["x ↦ ax²", "x ↦ a/x", "x ↦ √x"]),
  ch(N, "Suites arithmétiques et géométriques", "المتتاليات الحسابية والهندسية", "Arithmetic and geometric sequences", ["Terme général", "Somme de termes consécutifs"]),
  ch(G, "Trigonométrie", "حساب المثلثات", "Trigonometry", ["Cercle trigonométrique", "Angles orientés", "Formules usuelles"]),
  ch(G, "Calcul vectoriel et barycentre", "الحساب المتجهي والمرجح", "Vectors and barycentre", ["Barycentre de points pondérés", "Colinéarité"]),
  ch(G, "Produit scalaire", "الجداء السلمي", "Dot product", ["Définitions", "Orthogonalité", "Applications"]),
  ch(G, "Transformations du plan", "التحويلات في المستوي", "Plane transformations", ["Homothétie", "Rotation", "Translation"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Variance et écart-type", "Séries regroupées en classes"]),
 ]),
 ("3m", "secondaire", ("3e année Mathématiques", "السنة الثالثة رياضيات", "3rd year Mathematics"), [
  ch(N, "Continuité et limites", "الاتصال والنهايات", "Continuity and limits", ["Limite finie et infinie", "Opérations sur les limites", "Asymptotes"]),
  ch(N, "Dérivabilité", "الاشتقاق", "Derivatives", ["Nombre dérivé", "Fonctions dérivées", "Tangente"]),
  ch(N, "Étude de fonctions", "دراسة الدوال", "Function analysis", ["Variations", "Extremums", "Représentation graphique"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Monotonie", "Raisonnement par récurrence", "Suites bornées"]),
  ch(G, "Trigonométrie", "حساب المثلثات", "Trigonometry", ["Formules d'addition", "Équations trigonométriques"]),
  ch(G, "Produit scalaire dans le plan", "الجداء السلمي في المستوي", "Dot product in the plane", ["Équation de droite et de cercle", "Lignes de niveau"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Vecteurs de l'espace", "Repérage dans l'espace"]),
  ch(G, "Isométries et déplacements", "التقايسات والإزاحات", "Isometries", ["Composition", "Déplacements et antidéplacements"]),
  ch(A, "Arithmétique", "الحسابيات", "Arithmetic", ["Division euclidienne", "PGCD", "Nombres premiers"]),
  ch(S, "Dénombrement et probabilités", "التعداد والاحتمالات", "Counting and probability", ["Arrangements, combinaisons", "Probabilité d'un événement"]),
 ]),
 ("3se", "secondaire", ("3e année Sciences expérimentales", "السنة الثالثة علوم تجريبية", "3rd year Experimental sciences"), [
  ch(N, "Généralités sur les fonctions", "عموميات حول الدوال", "Functions", ["Fonctions composées", "Parité, périodicité"]),
  ch(N, "Continuité et limites", "الاتصال والنهايات", "Continuity and limits", ["Limites usuelles", "Asymptotes"]),
  ch(N, "Dérivabilité et étude de fonctions", "الاشتقاق ودراسة الدوال", "Derivatives and function analysis", ["Dérivées usuelles", "Variations", "Tangente"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Suites arithmétiques et géométriques", "Récurrence"]),
  ch(G, "Trigonométrie", "حساب المثلثات", "Trigonometry", ["Formules de transformation", "Équations"]),
  ch(G, "Produit scalaire", "الجداء السلمي", "Dot product", ["Calcul dans un repère orthonormé", "Applications"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Droites et plans", "Repérage"]),
  ch(S, "Dénombrement", "التعداد", "Counting", ["Permutations", "Arrangements", "Combinaisons"]),
  ch(S, "Probabilités", "الاحتمالات", "Probability", ["Événements", "Équiprobabilité"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Paramètres de position et de dispersion"]),
 ]),
 ("bac-m", "secondaire", ("Bac Mathématiques (4e année)", "باكالوريا رياضيات (السنة الرابعة)", "Bac Mathematics (4th year)"), [
  ch(N, "Continuité et limites", "الاتصال والنهايات", "Continuity and limits", ["Théorème des valeurs intermédiaires", "Limites et ordre"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Suites convergentes", "Suites adjacentes"]),
  ch(N, "Dérivabilité et fonction réciproque", "الاشتقاق والدالة العكسية", "Derivatives and inverse functions", ["Théorème des accroissements finis", "Fonction réciproque", "Fonctions x ↦ x^(1/n)"]),
  ch(N, "Primitives et intégrales", "الدوال الأصلية والتكامل", "Antiderivatives and integrals", ["Primitives usuelles", "Intégration par parties", "Calcul d'aires et de volumes"]),
  ch(N, "Fonction logarithme népérien", "دالة اللوغاريتم النيبيري", "Natural logarithm", ["Propriétés algébriques", "Limites", "Étude de fonctions"]),
  ch(N, "Fonction exponentielle", "الدالة الأسية", "Exponential function", ["Propriétés", "Limites", "Croissances comparées"]),
  ch(N, "Équations différentielles", "المعادلات التفاضلية", "Differential equations", ["y' = ay + b", "y'' + ω²y = 0"]),
  ch(A, "Nombres complexes", "الأعداد العقدية", "Complex numbers", ["Forme algébrique, trigonométrique, exponentielle", "Équations du second degré", "Racines n-ièmes"]),
  ch(A, "Arithmétique", "الحسابيات", "Arithmetic", ["Congruences", "PGCD et théorème de Bézout", "Théorème de Gauss"]),
  ch(G, "Isométries et similitudes", "التقايسات والتشابهات", "Isometries and similarities", ["Déplacements", "Similitudes directes"]),
  ch(G, "Coniques", "المخروطيات", "Conics", ["Parabole", "Ellipse", "Hyperbole"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Produit scalaire et vectoriel", "Droites, plans et sphères"]),
  ch(S, "Probabilités et statistiques", "الاحتمالات والإحصاء", "Probability and statistics", ["Probabilités conditionnelles", "Loi binomiale", "Lois continues", "Séries à deux variables"]),
 ]),
 ("bac-se", "secondaire", ("Bac Sciences expérimentales (4e année)", "باكالوريا علوم تجريبية (السنة الرابعة)", "Bac Experimental sciences (4th year)"), [
  ch(N, "Continuité et limites", "الاتصال والنهايات", "Continuity and limits", ["Théorème des valeurs intermédiaires", "Asymptotes"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Convergence", "Suites récurrentes"]),
  ch(N, "Dérivabilité et étude de fonctions", "الاشتقاق ودراسة الدوال", "Derivatives and function analysis", ["Fonction réciproque", "Tableau de variation"]),
  ch(N, "Primitives et intégrales", "الدوال الأصلية والتكامل", "Antiderivatives and integrals", ["Primitives usuelles", "Calcul d'aires"]),
  ch(N, "Fonction logarithme népérien", "دالة اللوغاريتم النيبيري", "Natural logarithm", ["Propriétés", "Limites", "Dérivée"]),
  ch(N, "Fonction exponentielle", "الدالة الأسية", "Exponential function", ["Propriétés", "Limites", "Dérivée"]),
  ch(N, "Équations différentielles", "المعادلات التفاضلية", "Differential equations", ["y' = ay + b"]),
  ch(A, "Nombres complexes", "الأعداد العقدية", "Complex numbers", ["Forme algébrique et trigonométrique", "Équations du second degré"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Produit scalaire et vectoriel", "Équations de plans et de droites"]),
  ch(S, "Probabilités", "الاحتمالات", "Probability", ["Probabilités conditionnelles", "Loi binomiale", "Variable aléatoire"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Séries statistiques à deux variables", "Ajustement affine"]),
 ]),
 ("bac-t", "secondaire", ("Bac Sciences techniques (4e année)", "باكالوريا علوم تقنية (السنة الرابعة)", "Bac Technical sciences (4th year)"), [
  ch(N, "Continuité, limites et dérivabilité", "الاتصال والنهايات والاشتقاق", "Continuity, limits and derivatives", ["Étude de fonctions", "Fonction réciproque"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Convergence", "Suites récurrentes"]),
  ch(N, "Primitives et intégrales", "الدوال الأصلية والتكامل", "Antiderivatives and integrals", ["Calcul d'aires et de volumes"]),
  ch(N, "Logarithme et exponentielle", "اللوغاريتم والدالة الأسية", "Logarithm and exponential", ["Propriétés", "Limites", "Étude de fonctions"]),
  ch(N, "Équations différentielles", "المعادلات التفاضلية", "Differential equations", ["y' = ay + b", "y'' + ω²y = 0"]),
  ch(A, "Nombres complexes", "الأعداد العقدية", "Complex numbers", ["Formes algébrique et exponentielle", "Applications géométriques"]),
  ch(G, "Géométrie dans l'espace", "الهندسة الفضائية", "Solid geometry", ["Produit vectoriel", "Plans et droites"]),
  ch(S, "Probabilités et statistiques", "الاحتمالات والإحصاء", "Probability and statistics", ["Loi binomiale", "Séries à deux variables"]),
 ]),
 ("bac-eg", "secondaire", ("Bac Économie et gestion (4e année)", "باكالوريا اقتصاد وتصرف (السنة الرابعة)", "Bac Economics and management (4th year)"), [
  ch(N, "Fonctions et limites", "الدوال والنهايات", "Functions and limits", ["Étude de fonctions", "Fonctions coût, recette, bénéfice"]),
  ch(N, "Logarithme et exponentielle", "اللوغاريتم والدالة الأسية", "Logarithm and exponential", ["Propriétés", "Applications économiques"]),
  ch(N, "Suites et mathématiques financières", "المتتاليات والرياضيات المالية", "Sequences and financial maths", ["Intérêts simples et composés", "Suites arithmétiques et géométriques"]),
  ch(N, "Intégrales", "التكامل", "Integrals", ["Primitives", "Valeur moyenne"]),
  ch(A, "Matrices et systèmes linéaires", "المصفوفات والجمل الخطية", "Matrices and linear systems", ["Calcul matriciel", "Résolution de systèmes"]),
  ch(S, "Probabilités", "الاحتمالات", "Probability", ["Probabilités conditionnelles", "Loi binomiale"]),
  ch(S, "Statistiques", "الإحصاء", "Statistics", ["Séries à deux variables", "Ajustement affine"]),
 ]),
 ("bac-si", "secondaire", ("Bac Sciences de l'informatique (4e année)", "باكالوريا علوم الإعلامية (السنة الرابعة)", "Bac Computer science (4th year)"), [
  ch(N, "Continuité, limites et dérivabilité", "الاتصال والنهايات والاشتقاق", "Continuity, limits and derivatives", ["Étude de fonctions"]),
  ch(N, "Suites réelles", "المتتاليات الحقيقية", "Real sequences", ["Convergence", "Suites récurrentes"]),
  ch(N, "Logarithme, exponentielle et intégrales", "اللوغاريتم والأسية والتكامل", "Logarithm, exponential and integrals", ["Propriétés", "Primitives", "Calcul d'aires"]),
  ch(A, "Nombres complexes", "الأعداد العقدية", "Complex numbers", ["Formes algébrique et trigonométrique"]),
  ch(A, "Arithmétique", "الحسابيات", "Arithmetic", ["Divisibilité", "Congruences", "Systèmes de numération"]),
  ch(A, "Matrices et systèmes", "المصفوفات والجمل", "Matrices and systems", ["Calcul matriciel", "Systèmes linéaires"]),
  ch(S, "Probabilités et statistiques", "الاحتمالات والإحصاء", "Probability and statistics", ["Loi binomiale", "Séries à deux variables"]),
 ]),
]

out = {
    "subject": "mathematiques",
    "country": "TN",
    "status": "indicative",
    "disclaimer": {
        "fr": "Programme de référence indicatif rédigé par l'équipe TRACE. Ce n'est pas le document officiel du ministère de l'Éducation. Vérifie avec le programme officiel.",
        "ar": "برنامج مرجعي تقريبي كتبه فريق TRACE. ليس الوثيقة الرسمية لوزارة التربية. تحقّق من البرنامج الرسمي.",
        "en": "Indicative reference programme written by the TRACE team. It is not the official Ministry of Education document. Check the official programme.",
    },
    "domains": {
        "algebre": {"fr": "Nombres et algèbre", "ar": "الأعداد والجبر", "en": "Numbers and algebra"},
        "analyse": {"fr": "Fonctions et analyse", "ar": "الدوال والتحليل", "en": "Functions and analysis"},
        "geometrie": {"fr": "Géométrie", "ar": "الهندسة", "en": "Geometry"},
        "statistiques": {"fr": "Statistiques et probabilités", "ar": "الإحصاء والاحتمالات", "en": "Statistics and probability"},
    },
    "levels": [],
}
for lid, cycle, (fr, ar, en), chapters in LEVELS:
    out["levels"].append({"id": lid, "cycle": cycle, "name": {"fr": fr, "ar": ar, "en": en},
                          "chapters": [{"id": f"{lid}-{i + 1:02d}", **c} for i, c in enumerate(chapters)]})
p = Path(__file__).resolve().parents[1] / "data" / "curriculum" / "tunisie_maths.json"
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(len(out["levels"]), sum(len(l["chapters"]) for l in out["levels"]))
