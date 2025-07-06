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

    # --- 1. Extraire le nom de l'élève ---
    # On cherche une ligne qui contient "Né le" et on prend ce qui est juste avant.
    match_nom = re.search(r'(.+?)\nNé le', texte)
    if match_nom:
        # On nettoie un peu le nom pour enlever les retours à la ligne et les espaces en trop
        nom_brut = match_nom.group(1).split('\n')[-1]
        donnees["nom_eleve"] = nom_brut.strip()

    # --- 2. Extraire la moyenne générale ---
    # On cherche le nombre qui suit "Moyenne générale"
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    # --- 3. Extraire l'appréciation globale ---
    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        # On remplace les sauts de ligne par des espaces pour avoir une seule phrase.
        appreciation = match_app_glob.group(1).replace('\n', ' ').strip()
        donnees["appreciation_globale"] = " ".join(appreciation.split())


# ... (début du fichier parser.py, les extractions de nom, etc. ne changent pas)

    # --- 4. Extraire les détails des matières ---
    # C'est la partie la plus complexe. On cherche des blocs qui commencent par une matière en majuscules.
    # Cette liste est basée sur votre exemple.
    matieres_possibles = [
        "ENS. MORAL & CIVIQUE", "HISTOIRE-GEOGRAPHIE", "PHILOSOPHIE", 
        "ITALIEN LV2", "ANGLAIS LV1", "HIST.GEO.GEOPOL.S.P.",
        "ENSEIGN.SCIENTIFIQUE", "SC. ECONO.& SOCIALES", "ED.PHYSIQUE & SPORT."
    ]
    matieres_pattern = "|".join(re.escape(m) for m in matieres_possibles)
    
    blocs = re.split(f'({matieres_pattern})', texte)
    
    if len(blocs) > 1:
        # On ignore le premier bloc (ce qui est avant la première matière)
        for i in range(1, len(blocs), 2):
            nom_matiere = blocs[i]
            contenu = blocs[i+1]
            
            # Cas spécial pour les matières non notées
            if "N.Not" in contenu or "non évalué" in contenu:
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": "N.Not",
                    "commentaire": "non évalué ce trimestre"
                })
                continue # On passe à la matière suivante

            # NOUVEAU REGEX AMÉLIORÉ
            # Il cherche 3 groupes de nombres (moyennes) suivis par le texte de l'appréciation
            # \s*   -> zéro ou plusieurs espaces
            # ([\d,.]+) -> capture un groupe de chiffres, virgules ou points
            # (.+)  -> capture le reste du texte (l'appréciation)
            # re.DOTALL permet au . de capturer aussi les sauts de ligne
            pattern_detail = re.compile(r'([\d,.]+) \s* ([\d,.]+) \s* ([\d,.]+) \s* (.+)', re.DOTALL)
            match_detail = pattern_detail.search(contenu)

            if match_detail:
                moyenne_eleve = match_detail.group(1).replace(',', '.')
                # Les groupes 2 et 3 (moyennes basse/haute) sont capturés mais on ne les utilise pas pour l'instant
                # moyenne_basse = match_detail.group(2)
                # moyenne_haute = match_detail.group(3)
                
                # On nettoie l'appréciation
                appreciation_brute = match_detail.group(4)
                appreciation_propre = " ".join(appreciation_brute.replace('\n', ' ').split())

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": moyenne_eleve,
                    "commentaire": appreciation_propre
                })
            else:
                # Si le nouveau regex ne fonctionne pas, on met un message d'erreur
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": "Erreur",
                    "commentaire": "Impossible de parser cette ligne."
                })

    return donnees