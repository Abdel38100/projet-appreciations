import os
import re
import pdfplumber
import io
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from parser import analyser_texte_bulletin
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from rq import get_current_job
from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, String, Text, DateTime, func

Base = declarative_base()

class Analyse(Base):
    __tablename__ = 'analyse'
    id = Column(String(36), primary_key=True)
    nom_eleve = Column(String(200), nullable=False)
    moyenne_generale = Column(String(10))
    appreciation_principale = Column(Text, nullable=False)
    justifications = Column(Text)
    cree_le = Column(DateTime, server_default=func.now())

def traiter_un_bulletin(pdf_bytes, nom_eleve_attendu, matieres_attendues):
    job = get_current_job()
    try:
        texte_extrait = ""
        pdf_file_in_memory = io.BytesIO(pdf_bytes)
        with pdfplumber.open(pdf_file_in_memory) as pdf:
            texte_extrait = pdf.pages[0].extract_text(x_tolerance=1, y_tolerance=1) or ""
        
        if not texte_extrait:
            raise ValueError("Le contenu du PDF est vide ou n'a pas pu être lu.")
        
        donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve_attendu, matieres_attendues)
        
        # --- ON SUPPRIME LA VÉRIFICATION QUI POSAIT PROBLÈME ---
        # if not donnees_structurees.get("nom_eleve"):
        #    raise ValueError("Le nom de l'élève n'a pas été trouvé dans le contenu du PDF.")
        
        if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues):
            raise ValueError(f"Le nombre de matières trouvées ({len(donnees_structurees['appreciations_matieres'])}) ne correspond pas au nombre attendu ({len(matieres_attendues)}).")

        # --- Le reste de la logique (IA, sauvegarde BDD) est identique ---
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
            appreciation_principale = parties[0].strip()
            justifications = parties[1].strip()
        else:
            appreciation_principale = reponse_complete_ia
            justifications = "L'IA n'a pas fourni de justifications séparées."
        
        db_url = os.getenv('DATABASE_URL')
        if db_url and db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        nouvelle_analyse = Analyse(
            id=job.get_id(),
            nom_eleve=nom_eleve_attendu,
            moyenne_generale=donnees_structurees.get("moyenne_generale"),
            appreciation_principale=appreciation_principale,
            justifications=justifications
        )
        session.add(nouvelle_analyse)
        session.commit()
        session.close()

    except Exception as e:
        print(f"ERREUR DANS LA TÂCHE pour {nom_eleve_attendu}: {e}")
        raise e