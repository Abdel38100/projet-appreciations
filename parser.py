import re

def analyser_texte_bulletin(texte, nom_eleve_attendu, matieres_attendues):
    """
    Analyse le texte brut en se basant sur une liste de matières fournie.
    Version finale avec une gestion améliorée des cas particuliers.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None,
        "texte_brut": texte
    }

    # #############################################################
    # ÉTAPE 1 : VÉRIFICATION DU NOM (LOGIQUE ULTRA-ROBUSTE)
    # #############################################################
    mots_du_nom = nom_eleve_attendu.split()
    nom_trouve = True
    for mot in mots_du_nom:
        # On cherche chaque mot du nom, insensible à la casse
        if not re.search(re.escape(mot), texte, re.IGNORECASE):
            nom_trouve = False
            break # Si un seul mot manque, on arrête
    
    if nom_trouve:
        donnees["nom_eleve"] = nom_eleve_attendu
    else:
        # Si la vérification échoue, on arrête tout de suite.
        return donnees


    # --- ÉTAPE 2 : Extraction des autres métadonnées ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        donnees["appreciation_globale"] = " ".join(match_app_glob.group(1).replace('\n', ' ').split())

    # --- ÉTAPE 3 : Extraction des matières ---
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
                
                moyenne = "N/A"
                commentaire_final = ""

                if "N.Not" in commentaire_brut or "non évalué" in commentaire_brut:
                    moyenne = "N.Not"
                    commentaire_final = "non évalué ce trimestre"
                
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
        print(f"Erreur de parsing des matières pour l'élève attendu '{nom_eleve_attendu}': {e}")
    
    return donnees