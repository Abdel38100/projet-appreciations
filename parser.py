import re

def analyser_texte_bulletin(texte, nom_eleve_attendu, matieres_attendues):
    """
    Analyse le texte brut en vérifiant la présence du nom attendu et en utilisant la liste de matières fournie.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None,
        "texte_brut": texte
    }

    # --- ÉTAPE 1 : VÉRIFICATION DU NOM DE L'ÉLÈVE ---
    # On cherche simplement si le nom attendu (insensible à la casse) est dans le texte.
    if re.search(re.escape(nom_eleve_attendu), texte, re.IGNORECASE):
        donnees["nom_eleve"] = nom_eleve_attendu
    else:
        # Si on ne trouve pas le nom, on arrête le parsing pour ce bulletin.
        # L'erreur sera gérée dans app.py.
        return donnees

    # --- ÉTAPE 2 : Extraction des autres métadonnées ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        donnees["appreciation_globale"] = " ".join(match_app_glob.group(1).replace('\n', ' ').split())

    # --- ÉTAPE 3 : Extraction des matières (méthode robuste basée sur la liste) ---
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
                
                moyenne, commentaire_final = "N/A", "Données non parsées."
                if "N.Not" in commentaire_brut or "non évalué" in commentaire_brut:
                    moyenne, commentaire_final = "N.Not", "non évalué ce trimestre"
                else:
                    match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', commentaire_brut)
                    if match_moyenne:
                        moyenne = match_moyenne.group(1).replace(',', '.')
                        reste = commentaire_brut[match_moyenne.end():]
                        nettoye = re.sub(r'^\s*[\d\s,./]*', '', reste.strip())
                        commentaire_final = " ".join(re.sub(r'\s*\d*/\d+\s*[\d,\s.]*', ' ', nettoye).strip().split())

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": moyenne, "commentaire": commentaire_final
                })
    except Exception as e:
        print(f"Erreur de parsing des matières pour {nom_eleve_attendu}: {e}")

    return donnees