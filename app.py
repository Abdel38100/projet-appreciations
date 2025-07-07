import os
import re
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
    fichiers = request.files.getlist('bulletin_pdf')
    liste_matieres_str = request.form.get('liste_matieres', '')
    liste_eleves_str = request.form.get('liste_eleves', '')

    matieres_attendues = [m.strip() for m in liste_matieres_str.split(',') if m.strip()]
    eleves_attendus = [e.strip() for e in liste_eleves_str.split('\n') if e.strip()]

    if not fichiers or not matieres_attendues or not eleves_attendus:
        return "Erreur : Vous devez fournir des fichiers, la liste des matières et la liste des élèves."

    tous_les_resultats = []
    fichiers_traites = set()

    # On boucle sur chaque élève de la liste fournie
    for nom_eleve in eleves_attendus:
        resultat_eleve = {
            "nom_eleve_attendu": nom_eleve,
            "nom_fichier": "Non trouvé",
            "donnees": None,
            "appreciation_principale": "",
            "justifications": "",
            "erreur_validation": None
        }
        fichier_trouve = None

        # On cherche le fichier PDF correspondant au nom de l'élève
        for fichier in fichiers:
            # On normalise le nom de l'élève (ex: "DUPONT Jean-Marie" -> "dupont-jean-marie") pour la comparaison
            nom_eleve_simple = re.sub(r'\s+', '-', nom_eleve.lower())
            if nom_eleve_simple in fichier.filename.lower() and fichier.filename not in fichiers_traites:
                fichier_trouve = fichier
                break
        
        if not fichier_trouve:
            resultat_eleve["erreur_validation"] = "Aucun fichier PDF correspondant à cet élève n'a été trouvé dans les fichiers téléversés."
            tous_les_resultats.append(resultat_eleve)
            continue # On passe à l'élève suivant
        
        fichiers_traites.add(fichier_trouve.filename)
        resultat_eleve["nom_fichier"] = fichier_trouve.filename

        try:
            texte_extrait = ""
            chemin_fichier = os.path.join(app.config['UPLOAD_FOLDER'], fichier_trouve.filename)
            try:
                fichier_trouve.seek(0) # Important quand on lit plusieurs fois un même flux de fichier
                fichier_trouve.save(chemin_fichier)
                with pdfplumber.open(chemin_fichier) as pdf:
                    texte_extrait = pdf.pages[0].extract_text() or ""
            finally:
                if os.path.exists(chemin_fichier): os.remove(chemin_fichier)

            donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
            resultat_eleve["donnees"] = donnees_structurees

            # --- Validation après parsing ---
            if not donnees_structurees.get("nom_eleve"):
                resultat_eleve["erreur_validation"] = "Le nom de l'élève n'a pas été trouvé DANS le contenu de ce PDF, bien que le nom de fichier corresponde."
            elif len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues):
                 resultat_eleve["erreur_validation"] = f"Le nombre de matières trouvées ({len(donnees_structurees['appreciations_matieres'])}) ne correspond pas au nombre attendu ({len(matieres_attendues)})."
            else:
                # --- Si tout est bon, on lance l'IA ---
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

        except Exception as e:
            resultat_eleve["erreur_validation"] = f"ERREUR CRITIQUE lors du traitement du fichier: {e}"
        
        tous_les_resultats.append(resultat_eleve)
    
    return render_template('resultat.html', tous_les_resultats=tous_les_resultats)

if __name__ == '__main__':
    app.run(debug=True)