import os
import sys
import json
from datetime import datetime
from google.cloud import dialogflow_v2 as dialogflow
from pymongo import MongoClient
import requests
from flask import Flask, request
import spacy

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/etc/secrets/clave.json"
project_id = 'barrestaurante-eltri-ngul-xpxa'
session_id = 'me'

session_client = dialogflow.SessionsClient()
session_path = session_client.session_path(project_id, session_id)

# Conexión a la base de datos MongoDB
def conectar_base_datos():
    try:
        # Obtener las credenciales de las variables de entorno
        username = os.environ.get('MONGODB_USERNAME')
        password = os.environ.get('MONGODB_PASSWORD')
        database_name = os.environ.get('MONGODB_DATABASE_NAME')

        # Construir la URI de conexión
        uri = f"mongodb+srv://{username}:{password}@cluster0.xuxjccf.mongodb.net/{database_name}?retryWrites=true&w=majority"

        # Conectarse a la base de datos
        client = MongoClient(uri)
        db = client[database_name]
        collection = db.reservas

        return collection
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

# Guardar reserva en MongoDB
def guardar_reserva(collection, nombre, fecha, hora):
    reserva = {
        "nombre": nombre,
        "fecha": fecha,
        "hora": hora
    }

    try:
        result = collection.insert_one(reserva)
        print("La reserva se ha guardado exitosamente.")
        return result.inserted_id
    except Exception as e:
        print(f"Error al guardar la reserva: {e}")
        return None

# Inicializar Flask
app = Flask(__name__)

@app.route('/', methods=['GET'])
def verify():
    # when the endpoint is registered as a webhook, it must echo back
    # the 'hub.challenge' value it receives in the query arguments
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.challenge"):
        if not request.args.get("hub.verify_token") == os.environ["FB_VERIFY_TOKEN"]:
            return "Verification token mismatch", 403
        return request.args["hub.challenge"], 200

    return "Hello world", 200

@app.route('/', methods=['POST'])
def webhook():

    # endpoint for processing incoming messaging events

    data = request.get_json()
    if data["object"] == "page":

        # Conectar a la base de datos
        collection = conectar_base_datos()

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:
                sender_id = None
                if messaging_event.get("message"):  # someone sent us a message

                    sender_id = messaging_event["sender"]["id"]        # the facebook ID of the person sending you the message
                    recipient_id = messaging_event["recipient"]["id"]  # the recipient's ID, which should be your page's facebook ID
                    message_text = messaging_event["message"]["text"]  # the message's text
                    tx = message_text
                    text_input = dialogflow.TextInput(text=tx, language_code="es-ES")
                    query_input = dialogflow.QueryInput(text=text_input)

                    response = session_client.detect_intent(session=session_path, query_input=query_input)

                    fulfillment_messages = response.query_result.fulfillment_messages

                    text_response = []
                    seen_paragraphs = set()
                    for message in fulfillment_messages:
                        for paragraph in message.text.text:
                            if paragraph not in seen_paragraphs:
                                text_response.append(paragraph)
                            seen_paragraphs.add(paragraph)
                    response_text = "\n".join(text_response)

                    # Extraer información de la oración
                    nombre, fecha, hora = extraer_info_oracion(message_text)

                    # Guardar la reserva si se encontraron los valores
                    if collection is not None and nombre and fecha and hora:
                        guardar_reserva(collection, nombre, fecha, hora)
                        response_text += "\nLa reserva se ha guardado exitosamente."

                if sender_id is not None:
                    send_message(sender_id, response_text)

                if messaging_event.get("delivery"):  # delivery confirmation
                    pass

                if messaging_event.get("optin"):  # optin confirmation
                    pass

                if messaging_event.get("postback"):  # user clicked/tapped "postback" button in earlier message
                    pass

    return "ok", 200

def send_message(recipient_id, message_text):
    params = {
         "access_token": os.environ["FB_PAGE_ACCESS_TOKEN"]
    }
    headers = {
        'Content-Type': 'application/json'
    }
    data = {
        'recipient': {
            'id': recipient_id
        },
        'message': {
            'text': message_text
        }
    }
    response = requests.post('https://graph.facebook.com/v16.0/me/messages', params=params, headers=headers, data=json.dumps(data))
    if response.status_code != 200:
        print('Error al enviar el mensaje: ' + response.text)

def extraer_info_oracion(oracion):
    nlp = spacy.load("es_core_news_sm")
    matcher = Matcher(nlp.vocab)

    # Definir patrones para extraer el nombre, la fecha y la hora
    nombre_patron = [{"POS": "PROPN"}, {"POS": "PROPN"}]
    fecha_patron = [{"IS_DIGIT": True}, {"LOWER": "de"}, {"IS_DIGIT": True}, {"LOWER": "de"}, {"IS_DIGIT": True}]
    hora_patron = [{"IS_DIGIT": True}, {"LOWER": "horas"}]

    matcher.add("NOMBRE", [nombre_patron])
    matcher.add("FECHA", [fecha_patron])
    matcher.add("HORA", [hora_patron])

    doc = nlp(oracion)
    matches = matcher(doc)

    nombre = None
    fecha = None
    hora = None

    for match_id, start, end in matches:
        if nlp.vocab.strings[match_id] == "NOMBRE":
            nombre = doc[start:end].text
        elif nlp.vocab.strings[match_id] == "FECHA":
            fecha = doc[start:end].text
        elif nlp.vocab.strings[match_id] == "HORA":
            hora = doc[start:end].text

    return nombre, fecha, hora
