import re

def analyser_texte_bulletin(texte):
    """
    Analyse le texte brut d'un bulletin pour en extraire les informations structurées.
    Cette version est plus robuste et ne dépend plus d'une liste de matières codée en dur.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None
    }

    # --- 1, 2, 3 : Extraction des métadonnées (ne change pas) ---
    match_nom = re.search(r'([A-Z\s]+[A-Z][a-z]+)\nNé le', texte)
    if match_nom:
        donnees["nom_eleve"] = match_nom.group(1).strip()
    else:
        match_nom_alt = re.search(r'Échirolles\s*(.*?)\nNé le', texte, re.DOTALL)
        if match_nom_alt: donnees["nom_eleve"] = match_nom_alt.group(1).strip()

    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        appreciation = match_app_glob.group(1).replace('\n', ' ').strip()
        donnees["appreciation_globale"] = " ".join(appreciation.split())

    # --- 4. NOUVELLE LOGIQUE D'EXTRACTION DES MATIÈRES ---
    # On isole d'abord la section du tableau des matières
    try:
        # Le tableau commence après "Appréciations" et se termine avant "Moyenne générale"
        tableau_texte = re.search(r'Appréciations\n(.+?)\nMoyenne générale', texte, re.DOTALL).group(1)
        
        # On divise le tableau en lignes de texte
        lignes = tableau_texte.strip().split('\n')
        
        matiere_actuelle = None
        for ligne in lignes:
            # On cherche une ligne qui commence par un nom de matière potentiel (au moins 3 majuscules)
            # suivi d'un format de note comme "5/5" ou "N.Not"
            match_ligne_matiere = re.match(r'([A-Z. &]{3,})\s+(?:\d+/\d+|N\.Not)', ligne)
            
            if match_ligne_matiere:
                # Si on trouve une nouvelle matière, on sauvegarde la précédente si elle existe
                if matiere_actuelle:
                    donnees["appreciations_matieres"].append(matiere_actuelle)
                
                # On initialise la nouvelle matière
                nom_matiere = match_ligne_matiere.group(1).strip()
                matiere_actuelle = {
                    "matiere": nom_matiere,
                    "moyenne": "N/A",
                    "commentaire": ""
                }
                # On ajoute le reste de la ligne au commentaire pour analyse future
                matiere_actuelle["commentaire"] += ligne[match_ligne_matiere.end():].strip() + " "
            
            elif matiere_actuelle:
                # Si ce n'est pas une nouvelle ligne de matière, on l'ajoute au commentaire de la matière actuelle
                matiere_actuelle["commentaire"] += ligne.strip() + " "

        # Ne pas oublier d'ajouter la toute dernière matière traitée
        if matiere_actuelle:
            donnees["appreciations_matieres"].append(matiere_actuelle)

        # --- 5. POST-TRAITEMENT : On nettoie les commentaires et on extrait les moyennes ---
        for matiere in donnees["appreciations_matieres"]:
            commentaire_brut = matiere["commentaire"]
            
            # Nettoyer les noms de profs
            commentaire_brut = re.sub(r'(M\.|Mme)\s+[A-Z]+', '', commentaire_brut)
            
            if "N.Not" in commentaire_brut or "non évalué" in commentaire_brut:
                matiere["moyenne"] = "N.Not"
                matiere["commentaire"] = "non évalué ce trimestre"
                continue

            # Extraire la moyenne de l'élève
            match_moyenne = re.search(r'(\d{1,2}[,.]\d{2})', commentaire_brut)
            if match_moyenne:
                matiere["moyenne"] = match_moyenne.group(1).replace(',', '.')
                # On supprime tout ce qui vient avant l'appréciation
                position_fin_moyenne = match_moyenne.end()
                reste_du_contenu = commentaire_brut[position_fin_moyenne:]
                appreciation_nettoyee = re.sub(r'^\s*[\d\s,./]*', '', reste_du_contenu.strip())
                appreciation_finale = re.sub(r'\s*\d*/\d+\s*[\d,\s.]*', ' ', appreciation_nettoyee).strip()
                matiere["commentaire"] = " ".join(appreciation_finale.split())
            else:
                matiere["moyenne"] = "Erreur"
                matiere["commentaire"] = "Données de la matière non parsées."

    except Exception as e:
        print(f"Erreur majeure lors du parsing du tableau des matières : {e}")

    return donnees