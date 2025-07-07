import os
import re
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
# Nous importons le parser que nous avons perfectionné
from parser import analyser_texte_bulletin

def traiter_un_bulletin(texte_brut, nom_eleve_attendu, matieres_attendues):
    """
    C'est la fonction qui sera exécutée par un "worker" en arrière-plan.
    Elle prend le texte d'un PDF et les infos attendues, et renvoie un dictionnaire de résultat.
    Elle n'a aucune connaissance de Flask ou du web.
    """
    try:
        # 1. Parsing du texte
        donnees_structurees = analyser_texte_bulletin(texte_brut, nom_eleve_attendu, matieres_attendues)
        
        # 2. Validation des données parsées
        if not donnees_structurees.get("nom_eleve"):
            raise ValueError("Le nom de l'élève n'a pas été trouvé dans le contenu du PDF.")
        if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues):
            raise ValueError(f"Le nombre de matières trouvées ({len(donnees_structurees['appreciations_matieres'])}) ne correspond pas au nombre attendu ({len(matieres_attendues)}).")

        # 3. Appel à l'API de Mistral
        api_key = os.environ.get("MISTRAL_API_KEY")
        if not api_key:
            raise ValueError("La clé MISTRAL_API_KEY n'est pas définie dans l'environnement du worker.")
        
        client = MistralClient(api_key=api_key)
        
        liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
        prompt_systeme = "Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions."
        prompt_utilisateur = f"""
        Voici les données de l'élève {donnees_structurees['nom_eleve']}.
        Données brutes :
        {liste_appreciations}
        Ta réponse doit être en DEUX parties distinctes, séparées par la ligne "--- JUSTIFICATIONS ---".
        **Partie 1 : Appréciation Globale**
        Rédige un paragraphe de 2 à 3 phrases pour le bulletin. Ce texte doit être synthétique, fluide et ne doit PAS mentionner la moyenne générale. Il doit identifier les tendances de fond (qualités, points d'amélioration) sans citer de matières spécifiques.
        **Partie 2 : Justifications**
        Sous le séparateur, justifie chaque idée clé de ta synthèse. Pour chaque point, cite les preuves exactes des commentaires des professeurs. Utilise le format suivant :
        - **Idée synthétisée:** [Ex: L'élève fait preuve de sérieux.]
        - **Preuves:**
        - **[Nom de la matière]:** "[Citation exacte du commentaire]"
        Rédige maintenant ta réponse complète.
        """

        messages = [ChatMessage(role="system", content=prompt_systeme), ChatMessage(role="user", content=prompt_utilisateur)]
        chat_response = client.chat(model="mistral-large-latest", messages=messages, temperature=0.5)
        reponse_complete_ia = chat_response.choices[0].message.content

        separateur = "--- JUSTIFICATIONS ---"
        if separateur in reponse_complete_ia:
            parties = reponse_complete_ia.split(separateur, 1)
            appreciation_principale = parties[0].strip()
            justifications = parties[1].strip()
        else:
            appreciation_principale = reponse_complete_ia
            justifications = "L'IA n'a pas fourni de justifications séparées."
        
        # Si tout réussit, on renvoie un dictionnaire de succès
        return {
            "nom_eleve": nom_eleve_attendu,
            "donnees": donnees_structurees,
            "appreciation_principale": appreciation_principale,
            "justifications": justifications
        }

    except Exception as e:
        # En cas d'erreur, on la "capture" et on la renvoie proprement
        print(f"ERREUR DANS LA TÂCHE pour {nom_eleve_attendu}: {e}")
        # On ne propage pas l'erreur, mais on renvoie un dictionnaire d'échec
        # Cela évite que le worker entier ne plante
        raise e # On propage l'erreur pour que RQ la marque comme "failed"