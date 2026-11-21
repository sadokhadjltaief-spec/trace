# Najahni (najahni.tn): how TRACE may use its material

Najahni is a Tunisian education site with free lessons and exercises and paid premium PDFs. Its terms of use
forbid modifying or adapting the site's content, and the footer says all rights are reserved. Scraping is not
mentioned. TRACE therefore follows these rules (enforced in code where possible):

1. **No crawling, no bulk or scripted downloads, no login or paywall bypass.** TRACE contains no code that
   contacts najahni.tn.
2. A team member downloads a **small number of free PDFs by hand** (or obtains the owner's written permission) and
   puts them in `data/courses/najahni/`. Each file's URL is recorded in `data/courses/najahni/SOURCES.md`
   (format: `- file.pdf: https://...`). TRACE shows that link next to every citation.
3. These files are used for **retrieval with citation only**: the passage is shown as it is, with file name, page
   number and source link (`engine/rag.py`, Course Q&A, lesson references in the report).
4. **No derivatives** (summaries, flashcards, slides, videos) from these files unless `SOURCES.md` records the
   owner's permission and `data/courses/najahni/meta.yaml` is changed to `allow_derivatives: true`. The default
   is `false`; the Study Studio refuses with a clear message when it is false (`StudioOutput.refused`).
5. The PDFs are **never committed or redistributed** (`data/courses/**` is gitignored).

The partnership is part of the go-to-market story: TRACE is the diagnostic layer, Najahni (and similar sites) the
content layer. TRACE points the student to the exact lesson page that fixes the diagnosed misconception, which
sends traffic to the content owner.

## Partnership email template (French)

> **Objet : Proposition de partenariat – TRACE, diagnostic des erreurs en mathématiques**
>
> Bonjour,
>
> Nous sommes une équipe de deux étudiants et nous développons TRACE, un tuteur qui identifie l'erreur de
> raisonnement précise d'un élève en mathématiques (par exemple « additionne les numérateurs et les
> dénominateurs ») puis l'aide à la corriger.
>
> Lorsqu'une erreur est identifiée, TRACE peut orienter l'élève vers la page de cours qui traite exactement ce
> point. Nous aimerions pouvoir citer vos leçons gratuites dans ce cadre : extrait court, nom du fichier, numéro
> de page et lien vers votre site, sans modification de votre contenu et sans le redistribuer.
>
> Avec votre accord écrit, nous pourrions aussi proposer à l'élève des fiches de révision ciblées tirées de vos
> leçons, en indiquant clairement leur source.
>
> Seriez-vous disponible pour un court échange ? Nous serions heureux de vous présenter une démonstration.
>
> Cordialement,
> [Prénom Nom], équipe TRACE
> [adresse e-mail] – [téléphone]

(Fill in the bracketed fields before sending. Nothing is sent automatically.)
