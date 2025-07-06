import re

def analyser_texte_bulletin(texte, matieres_attendues):
    """
    Analyse le texte brut d'un bulletin en se basant sur une liste de matières fournie.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None,
        "texte_brut": texte
    }

    # --- EXTRACTION DU NOM (LOGIQUE MULTI-STRATÉGIES) ---
    nom_trouve = None

    # Stratégie 1 : Chercher entre "Bulletin du..." et "Né le..." (la plus robuste)
    # Le regex cherche "Bulletin du" suivi de n'importe quoi, un saut de ligne, puis capture le texte
    # jusqu'à la ligne "Né le...". re.DOTALL permet à '.' de matcher les sauts de ligne.
    match1 = re.search(r'Bulletin du .*?\n(.*?)\nNé le', texte, re.DOTALL)
    if match1:
        # On nettoie le bloc capturé. Souvent, le nom est sur la dernière ligne de ce bloc.
        bloc_nom = match1.group(1).strip()
        lignes_nom = bloc_nom.split('\n')
        # On prend la dernière ligne non vide du bloc
        for ligne in reversed(lignes_nom):
            if ligne.strip():
                nom_trouve = ligne.strip()
                break

    # Stratégie 2 (Plan B) : Si la première échoue, on cherche un NOM Prénom après "Bulletin du..."
    if not nom_trouve:
        # Ce regex est plus flexible sur le numéro du trimestre
        match2 = re.search(r'Bulletin du (?:Trimestre \d+|\d+er Trimestre)\n([A-Z\s]+[A-Z][a-z]+)', texte)
        if match2:
            nom_trouve = match2.group(1).strip()
    
    donnees["nom_eleve"] = nom_trouve

    # --- Extraction des autres métadonnées (ne change pas) ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        donnees["appreciation_globale"] = " ".join(match_app_glob.group(1).replace('\n', ' ').split())

    # --- LOGIQUE D'EXTRACTION DES MATIÈRES (ne change pas) ---
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
                commentaire_brut = re.sub(r'(M\.|Mme)\s+[A-ZÀ-ÿ]+', '', contenu).strip()
                
                moyenne = "N/A"
                commentaire_final = "Données non parsées."

                if "N.Not" in commentaire_brut or "non évalué" in commentaire_brut:
                    moyenne = "N.Not"
                    commentaire_final = "non évalué ce trimestre"
                else:
                    match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', commentaire_brut)
                    if match_moyenne:
                        moyenne = match_moyenne.group(1).replace(',', '.')
                        position_fin_moyenne = match_moyenne.end()
                        reste_du_contenu = commentaire_brut[position_fin_moyenne:]
                        appreciation_nettoyee = re.sub(r'^\s*[\d\s,./]*', '', reste_du_contenu.strip())
                        commentaire_final = " ".join(re.sub(r'\s*\d*/\d+\s*[\d,\s.]*', ' ', appreciation_nettoyee).strip().split())

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": moyenne,
                    "commentaire": commentaire_final
                })

    except Exception as e:
        print(f"Erreur majeure de parsing guidé: {e}")

    return donnees