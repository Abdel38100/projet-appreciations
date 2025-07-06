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


    # --- 4. Extraire les détails des matières ---
    # C'est la partie la plus complexe. On cherche des blocs qui commencent par une matière en majuscules.
    # On définit une liste de matières possibles pour les identifier.
    # Cette liste est basée sur votre exemple.
    matieres_possibles = [
        "ENS. MORAL & CIVIQUE", "HISTOIRE-GEOGRAPHIE", "PHILOSOPHIE", 
        "ITALIEN LV2", "ANGLAIS LV1", "HIST.GEO.GEOPOL.S.P.",
        "ENSEIGN.SCIENTIFIQUE", "SC. ECONO.& SOCIALES", "ED.PHYSIQUE & SPORT."
    ]
    # Création d'un grand pattern regex pour trouver n'importe laquelle de ces matières.
    matieres_pattern = "|".join(re.escape(m) for m in matieres_possibles)
    
    # On divise le texte en blocs, chaque bloc commençant par une matière.
    blocs = re.split(f'({matieres_pattern})', texte)
    
    # Le premier bloc est ce qui vient avant la première matière, on l'ignore.
    # On traite les blocs par paires : (nom_matiere, contenu_matiere)
    for i in range(1, len(blocs), 2):
        nom_matiere = blocs[i]
        contenu = blocs[i+1]
        
        # Dans le contenu, on cherche la moyenne (le premier nombre avec une virgule)
        match_moyenne = re.search(r'(\d{1,2}[,.]\d{1,2})', contenu)
        moyenne = match_moyenne.group(1).replace(',', '.') if match_moyenne else "N/A"
        
        # L'appréciation est tout ce qui vient après la moyenne.
        # On cherche après les 4 chiffres de la moyenne de la classe (ex: 5,6917,60)
        match_appreciation = re.search(r'\d{1,2}[,.]\d{2}\s*(.+)', contenu, re.DOTALL)
        if match_appreciation:
            appreciation_matiere = match_appreciation.group(1).replace('\n', ' ').strip()
            appreciation_matiere = " ".join(appreciation_matiere.split())
        else:
            # Cas spécial pour "non évalué"
            if "non évalué" in contenu:
                appreciation_matiere = "non évalué ce trimestre"
            else:
                appreciation_matiere = "Appréciation non trouvée"

        donnees["appreciations_matieres"].append({
            "matiere": nom_matiere,
            "moyenne": moyenne,
            "commentaire": appreciation_matiere
        })

    return donnees