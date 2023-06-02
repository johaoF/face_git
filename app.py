import os
import json
import requests
from flask import Flask, request
from google.cloud import dialogflow_v2 as dialogflow
from pymongo import MongoClient

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
        collection = db.reservas  # Nombre de la colección donde se guardarán las reservas

        return collection
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
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
    data = request.get_json()
    if data["object"] == "page":
        # Conectar a la base de datos
        collection = conectar_base_datos()

        for entry in data["entry"]:
            for messaging_event in entry["messaging"]:
                sender_id = None
                if messaging_event.get("message"):
                    sender_id = messaging_event["sender"]["id"]
                    recipient_id = messaging_event["recipient"]["id"]
                    if messaging_event["message"].get("text"):
                        message_text = messaging_event["message"]["text"]
                    else:
                        # Si no se encuentra el campo de texto, pasar al siguiente mensaje
                        continue
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
                    
                    if response.query_result.intent.display_name == 'Reservaciones':
                        fecha_reservacion = response.query_result.parameters['fecha']
                        print(fecha_reservacion)
                        # Guardar la fecha de reservación en la base de datos
                       # if collection is not None:
                       #     documento = {'sender_id': sender_id, 'fecha_reservacion': fecha_reservacion}
                       #     collection.insert_one(documento)
                       #    print('Fecha de reservación guardada en la base de datos')
                       # else:
                       #    print('Error al conectar a la base de datos')

                    # Enviar la respuesta al usuario a través de Facebook Messenger
                    if sender_id is not None:
                        send_message(sender_id, response_text)

                if messaging_event.get("delivery"):
                    pass

                if messaging_event.get("optin"):
                    pass

                if messaging_event.get("postback"):
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
