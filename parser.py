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
    match_nom = re.search(r'([A-Z\s]+[A-Z][a-z]+)\nNé le', texte)
    if match_nom:
        donnees["nom_eleve"] = match_nom.group(1).strip()
    else:
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

    # --- 4. Extraire les détails des matières ---
    matieres_possibles = [
        "ENS. MORAL & CIVIQUE", "HISTOIRE-GEOGRAPHIE", "PHILOSOPHIE", 
        "ITALIEN LV2", "ANGLAIS LV1", "HIST.GEO.GEOPOL.S.P.",
        "ENSEIGN.SCIENTIFIQUE", "SC. ECONO.& SOCIALES", "ED.PHYSIQUE & SPORT."
    ]
    matieres_pattern = "|".join(re.escape(m) for m in matieres_possibles)
    
    # NOUVELLE LOGIQUE : On ajoute "Moyenne générale" comme un délimiteur de fin
    terminator = "Moyenne générale"
    # On crée un pattern qui cherche soit une matière, soit le terminateur
    split_pattern = f'({matieres_pattern}|{terminator})'
    
    blocs = re.split(split_pattern, texte)
    
    if len(blocs) > 1:
        for i in range(1, len(blocs), 2):
            nom_bloc = blocs[i]
            if nom_bloc == "Moyenne générale":
                break
            
            nom_matiere = nom_bloc
            contenu = blocs[i+1]
            contenu = re.sub(r'(M\.|Mme)\s+[A-Z]+', '', contenu)
            
            if "N.Not" in contenu or "non évalué" in contenu:
                # ... (partie N.Not identique)
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": "N.Not", "commentaire": "non évalué ce trimestre"
                })
                continue

            match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', contenu)
            
            if match_moyenne:
                moyenne_eleve = match_moyenne.group(1).replace(',', '.')
                position_fin_moyenne = match_moyenne.end()
                reste_du_contenu = contenu[position_fin_moyenne:]
                
                appreciation_brute = re.sub(r'^\s*(\d+/\d+\s+)?[\d\s,./]*', '', reste_du_contenu.strip())
                appreciation_propre = " ".join(appreciation_brute.replace('\n', ' ').strip().split())

                # #############################################################
                # ULTIME NETTOYAGE CORRIGÉ : On utilise d* au lieu de d+
                # #############################################################
                # Ce regex supprime les motifs comme "4/4 ..." ou "/7 ..."
                appreciation_finale = re.sub(r'\s*\d*/\d+\s*[\d,\s.]*', ' ', appreciation_propre).strip()

                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere,
                    "moyenne": moyenne_eleve,
                    "commentaire": appreciation_finale
                })
            else:
                donnees["appreciations_matieres"].append({
                    "matiere": nom_matiere, "moyenne": "Erreur", "commentaire": "Moyenne élève non trouvée."
                })

    return donnees