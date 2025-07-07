import re
import unicodedata

def normaliser_pour_comparaison(s):
    """Normalisation agressive pour la comparaison : enlève tout sauf les lettres et chiffres."""
    if not s: return ""
    # Enlève les accents
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    # Met en minuscule et ne garde que les lettres et chiffres
    s = re.sub(r'[^a-z0-9]+', '', s.lower())
    return s

def analyser_texte_bulletin(texte, nom_eleve_attendu, matieres_attendues):
    """
    Analyse le texte brut en se basant sur une liste de matières fournie.
    Version finale avec une validation de nom ultra-robuste.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None,
        "texte_brut": texte
    }

    # --- ÉTAPE 1 : VÉRIFICATION DU NOM (LOGIQUE FINALE) ---
    nom_trouve_dans_pdf = None

    # On cherche le bloc de texte où le nom est censé se trouver.
    # C'est la méthode la plus fiable pour isoler le nom.
    match_bloc_nom = re.search(r'Bulletin du .*?\n(.*?)\nNé le', texte, re.DOTALL)
    if match_bloc_nom:
        # On nettoie ce bloc pour ne garder que le nom probable
        lignes_candidat = match_bloc_nom.group(1).strip().split('\n')
        for ligne in reversed(lignes_candidat):
            if ligne.strip():
                nom_trouve_dans_pdf = ligne.strip()
                break

    # Maintenant, on compare le nom attendu avec le nom trouvé, de manière très tolérante.
    if nom_trouve_dans_pdf:
        nom_attendu_norm = normaliser_pour_comparaison(nom_eleve_attendu)
        nom_trouve_norm = normaliser_pour_comparaison(nom_trouve_dans_pdf)
        
        # Si le nom normalisé trouvé contient le nom normalisé attendu, c'est un succès.
        if nom_attendu_norm in nom_trouve_norm:
            donnees["nom_eleve"] = nom_eleve_attendu # On garde le nom propre fourni par l'utilisateur
        else:
            # Le bloc a été trouvé mais le nom ne correspond pas, on arrête.
            return donnees
    else:
        # Le bloc n'a même pas été trouvé, on arrête.
        return donnees
    
    # --- Le reste du parsing (matières, etc.) ne change pas ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        donnees["appreciation_globale"] = " ".join(match_app_glob.group(1).replace('\n', ' ').split())

    try:
        match_tableau = re.search(r'Appréciations\n(.+?)\nMoyenne générale', texte, re.DOTALL)
        if not match_tableau:
            return donnees

        tableau_texte = match_tableau.group(1)
        matieres_pattern = "|".join(re.escape(m) for m in matieres_attendues)
        blocs_contenu = re.split(matieres_pattern, tableau_texte)[1:]

        for i, nom_matiere in enumerate(matieres_attendues):
            if i < len(blocs_contenu):
                contenu = blocs_contenu[i]
                commentaire_brut = re.sub(r'(M\.|Mme)\s+((?:[A-ZÀ-ÿ-]+\s?)+)', '', contenu).strip()
                
                moyenne, commentaire_final = "N/A", ""
                if "N.Not" in commentaire_brut or "non évalué" in commentaire_brut:
                    moyenne, commentaire_final = "N.Not", "non évalué ce trimestre"
                elif re.search(r'\d{1,2}[,.]\d{2}', commentaire_brut):
                    match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', commentaire_brut)
                    moyenne = match_moyenne.group(1).replace(',', '.')
                    reste = commentaire_brut[match_moyenne.end():]
                    nettoye = re.sub(r'^\s*[\d\s,./]*', '', reste.strip())
                    commentaire_final = " ".join(re.sub(r'\s*\d*/\d+\s*[\d,\s.]*', ' ', nettoye).strip().split())
                else:
                    moyenne = "N/A"
                    commentaire_final = " ".join(re.sub(r'^\s*\d*/\d+\s*', '', commentaire_brut).strip().split())

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": moyenne, "commentaire": commentaire_final
                })
    except Exception as e:
        print(f"Erreur de parsing des matières pour {nom_eleve_attendu}: {e}")

    return donnees