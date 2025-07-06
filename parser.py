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

    # --- Extraction des métadonnées (ne change pas) ---
    match_nom = re.search(r'Bulletin du \d+er Trimestre\n(.*?)\nNé le', texte, re.DOTALL)
    if match_nom:
        nom_candidat = match_nom.group(1).strip()
        donnees["nom_eleve"] = nom_candidat.split('\n')[-1].strip() if '\n' in nom_candidat else nom_candidat

    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        donnees["appreciation_globale"] = " ".join(match_app_glob.group(1).replace('\n', ' ').split())

    # --- NOUVELLE LOGIQUE D'EXTRACTION BASÉE SUR LA LISTE FOURNIE ---
    try:
        # On isole la section du tableau
        match_tableau = re.search(r'Appréciations\n(.+?)\nMoyenne générale', texte, re.DOTALL)
        if not match_tableau:
            return donnees # On ne peut rien faire si on ne trouve pas le tableau

        tableau_texte = match_tableau.group(1)

        # On utilise la liste fournie pour créer le pattern de découpage
        # re.escape est CRUCIAL pour gérer les caractères spéciaux comme les points et les '&'
        matieres_pattern = "|".join(re.escape(m) for m in matieres_attendues)
        
        # On découpe le texte du tableau en utilisant les noms des matières comme séparateurs
        # Le premier élément est ce qui vient avant la première matière, on l'ignore.
        # Les éléments suivants sont le contenu de chaque matière.
        blocs_contenu = re.split(matieres_pattern, tableau_texte)[1:]

        for i, nom_matiere in enumerate(matieres_attendues):
            if i < len(blocs_contenu):
                contenu = blocs_contenu[i]

                # --- Post-traitement (logique qu'on a déjà perfectionnée) ---
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