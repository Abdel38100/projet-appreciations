import re

def analyser_texte_bulletin(texte):
    """
    Analyse le texte brut d'un bulletin pour en extraire les informations structurées.
    Retourne un dictionnaire avec les données.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None
    }

    # --- 1. Extraire le nom de l'élève (REGEX CORRIGÉ) ---
    # On cherche une suite de mots en majuscules (le nom) suivi d'un mot avec une majuscule (le prénom)
    # juste avant "Né le". C'est plus robuste.
    match_nom = re.search(r'([A-Z\s]+[A-Z][a-z]+)\nNé le', texte)
    if match_nom:
        donnees["nom_eleve"] = match_nom.group(1).strip()
    else:
        # Plan B si le premier regex échoue
        match_nom_alt = re.search(r'Échirolles\s*(.*?)\nNé le', texte, re.DOTALL)
        if match_nom_alt:
            donnees["nom_eleve"] = match_nom_alt.group(1).strip()


    # --- 2. Extraire la moyenne générale ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    # --- 3. Extraire l'appréciation globale ---
    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        appreciation = match_app_glob.group(1).replace('\n', ' ').strip()
        donnees["appreciation_globale"] = " ".join(appreciation.split())


    # --- 4. Extraire les détails des matières (LOGIQUE CORRIGÉE) ---
    matieres_possibles = [
        "ENS. MORAL & CIVIQUE", "HISTOIRE-GEOGRAPHIE", "PHILOSOPHIE", 
        "ITALIEN LV2", "ANGLAIS LV1", "HIST.GEO.GEOPOL.S.P.",
        "ENSEIGN.SCIENTIFIQUE", "SC. ECONO.& SOCIALES", "ED.PHYSIQUE & SPORT."
    ]
    matieres_pattern = "|".join(re.escape(m) for m in matieres_possibles)
    
    blocs = re.split(f'({matieres_pattern})', texte)
    
    if len(blocs) > 1:
        for i in range(1, len(blocs), 2):
            nom_matiere = blocs[i]
            contenu = blocs[i+1]
            
            if "N.Not" in contenu or "non évalué" in contenu:
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": "N.Not", "commentaire": "non évalué ce trimestre"
                })
                continue

            # NOUVEAU REGEX (plus simple et plus robuste)
            # On cherche juste la première moyenne (celle de l'élève)
            match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', contenu)
            
            if match_moyenne:
                moyenne_eleve = match_moyenne.group(1).replace(',', '.')
                
                # Maintenant, on trouve la position de la fin de cette moyenne
                position_fin_moyenne = match_moyenne.end()
                
                # L'appréciation commence après cette position.
                # On prend le reste de la chaine 'contenu' à partir de là.
                reste_du_contenu = contenu[position_fin_moyenne:]
                
                # On nettoie ce qui reste pour trouver l'appréciation.
                # On supprime les chiffres et points/virgules du début (les moyennes de la classe)
                appreciation_brute = re.sub(r'^[\d\s,.]*', '', reste_du_contenu)
                appreciation_propre = " ".join(appreciation_brute.replace('\n', ' ').strip().split())

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": moyenne_eleve,
                    "commentaire": appreciation_propre
                })
            else:
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": "Erreur", "commentaire": "Moyenne élève non trouvée."
                })

    return donnees