import os
import pdfplumber
from flask import Flask, render_template, request
from flask_misaka import Misaka
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from parser import analyser_texte_bulletin

app = Flask(__name__)
Misaka(app)
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def accueil():
    return render_template('accueil.html')

@app.route('/analyser', methods=['POST'])
def analyser_bulletin():
    # On récupère la LISTE des fichiers envoyés
    fichiers = request.files.getlist('bulletin_pdf')

    if not fichiers or all(f.filename == '' for f in fichiers):
        return "Erreur : Aucun fichier sélectionné."

    tous_les_resultats = []

    # On boucle sur chaque fichier reçu
    for fichier in fichiers:
        if not (fichier and fichier.filename.endswith('.pdf')):
            continue # On ignore les fichiers non-PDF

        # On initialise un dictionnaire de résultat pour ce fichier spécifique.
        # Cela nous permet de gérer les erreurs fichier par fichier.
        resultat_eleve = {
            "nom_fichier": fichier.filename,
            "donnees": None,
            "appreciation_principale": "",
            "justifications": ""
        }

        try:
            # --- Lecture et Parsing du PDF ---
            texte_extrait = ""
            chemin_fichier = os.path.join(app.config['UPLOAD_FOLDER'], fichier.filename)
            try:
                fichier.save(chemin_fichier)
                with pdfplumber.open(chemin_fichier) as pdf:
                    texte_extrait = pdf.pages[0].extract_text() or ""
            finally:
                if os.path.exists(chemin_fichier):
                    os.remove(chemin_fichier)

            donnees_structurees = analyser_texte_bulletin(texte_extrait)
            resultat_eleve["donnees"] = donnees_structurees

            # --- Génération par IA (uniquement si le parsing a réussi) ---
            if donnees_structurees.get("nom_eleve") and donnees_structurees.get("appreciations_matieres"):
                api_key = os.environ.get("MISTRAL_API_KEY")
                if not api_key: raise ValueError("Clé MISTRAL_API_KEY non définie.")

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
                    resultat_eleve["appreciation_principale"] = parties[0].strip()
                    resultat_eleve["justifications"] = parties[1].strip()
                else:
                    resultat_eleve["appreciation_principale"] = reponse_complete_ia
                    resultat_eleve["justifications"] = "L'IA n'a pas fourni de justifications séparées."
            else:
                # Cas où le parsing n'a pas trouvé les informations de base
                resultat_eleve["appreciation_principale"] = "Analyse impossible : les données de base (nom ou matières) n'ont pas pu être extraites du PDF."
                resultat_eleve["justifications"] = "Le parser n'a pas réussi à identifier la structure de ce bulletin."

        except Exception as e:
            # Si une erreur majeure se produit pour CE fichier, on la note et on continue
            print(f"Erreur de traitement pour le fichier {fichier.filename}: {e}")
            resultat_eleve["appreciation_principale"] = f"ERREUR CRITIQUE"
            resultat_eleve["justifications"] = f"Impossible de traiter ce bulletin. L'erreur suivante s'est produite: {e}"
        
        # On ajoute le résultat complet pour cet élève (réussi ou en erreur) à notre liste globale
        tous_les_resultats.append(resultat_eleve)

    # On envoie la liste complète des résultats au template
    return render_template('resultat.html', tous_les_resultats=tous_les_resultats)

if __name__ == '__main__':
    app.run(debug=True)