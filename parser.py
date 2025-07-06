import re

def analyser_texte_bulletin(texte):
    """
    Analyse le texte brut d'un bulletin.
    Logique revue pour être plus simple et plus directe.
    """
    donnees = {
        "nom_eleve": None,
        "moyenne_generale": None,
        "appreciations_matieres": [],
        "appreciation_globale": None,
        "texte_brut": texte # On garde le texte brut pour le débogage
    }

    # --- NOUVELLE LOGIQUE POUR LE NOM ---
    # On cherche ce qui se trouve entre "Bulletin du 1er Trimestre" et "Né le"
    match_nom = re.search(r'Bulletin du \d+er Trimestre\n(.*?)\nNé le', texte, re.DOTALL)
    if match_nom:
        # On prend la dernière partie non vide après avoir nettoyé
        nom_candidat = match_nom.group(1).strip()
        if '\n' in nom_candidat: # S'il y a plusieurs lignes, on prend la dernière
             donnees["nom_eleve"] = nom_candidat.split('\n')[-1].strip()
        else:
             donnees["nom_eleve"] = nom_candidat
    
    # --- Extraction des autres métadonnées ---
    match_moy_gen = re.search(r'Moyenne générale\s+([\d,\.]+)', texte)
    if match_moy_gen:
        donnees["moyenne_generale"] = match_moy_gen.group(1).replace(',', '.')

    match_app_glob = re.search(r'Appréciation globale\s*:\s*(.+?)\nMentions', texte, re.DOTALL)
    if match_app_glob:
        appreciation = match_app_glob.group(1).replace('\n', ' ').strip()
        donnees["appreciation_globale"] = " ".join(appreciation.split())

    # --- LOGIQUE D'EXTRACTION DES MATIÈRES SIMPLIFIÉE ---
    try:
        tableau_texte = re.search(r'Appréciations\n(.+?)\nMoyenne générale', texte, re.DOTALL).group(1)
        
        # Un regex pour trouver une ligne de matière : MAJUSCULES (NOM) X/X (NOTES)
        pattern_matiere = re.compile(r'([A-ZÀ-ÿ. &]{3,})\s+(?:M\.|Mme)?\s*[A-ZÀ-ÿ]*\s*\n?.*?(?:\d+/\d+|N\.Not)', re.DOTALL)
        
        # On trouve TOUTES les correspondances dans le bloc du tableau
        matieres_trouvees = pattern_matiere.finditer(tableau_texte)
        
        blocs_matieres = []
        positions = []
        for match in matieres_trouvees:
            # On stocke le nom de la matière et la position de début
            blocs_matieres.append(match.group(1).strip())
            positions.append(match.start())

        for i in range(len(blocs_matieres)):
            nom_matiere = blocs_matieres[i]
            
            # Le contenu de la matière est le texte entre sa position et la position de la suivante
            start_pos = positions[i]
            end_pos = positions[i+1] if i + 1 < len(positions) else None
            contenu = tableau_texte[start_pos:end_pos]
            
            # Post-traitement sur le contenu
            commentaire_brut = re.sub(r'^[A-ZÀ-ÿ. &]+', '', contenu).strip() # Enlève le nom de la matière
            commentaire_brut = re.sub(r'(M\.|Mme)\s+[A-ZÀ-ÿ]+', '', commentaire_brut) # Enlève nom prof
            
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
        print(f"Erreur majeure de parsing: {e}")

    return donnees