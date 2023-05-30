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
        collection = db.reservas

        return collection
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")
        return None

# Guardar reserva en MongoDB
def guardar_reserva(collection, nombre, cantidad_personas, fecha, hora):
    reserva = {
        "nombre": nombre,
        "cantidad_personas": cantidad_personas,
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

                    # Guardar la reserva si se encontraron los valores
                    if collection is not None:
                        if "cantidad de personas" in response_text.lower():
                            guardar_datos(sender_id, "cantidad_personas", response_text)
                        elif "nombre" in response_text.lower():
                            guardar_datos(sender_id, "nombre", response_text)
                        elif "hora" in response_text.lower():
                            guardar_datos(sender_id, "hora", response_text)
                        elif "fecha" in response_text.lower():
                            guardar_datos(sender_id, "fecha", response_text)
                        else:
                            guardar_datos(sender_id, "otros", response_text)
                        nombre = obtener_datos(sender_id, "nombre")
                        cantidad_personas = obtener_datos(sender_id, "cantidad_personas")
                        fecha = obtener_datos(sender_id, "fecha")
                        hora = obtener_datos(sender_id, "hora")
                        if nombre and cantidad_personas and fecha and hora:
                            reserva_existente = verificar_reserva_existente(collection, fecha, hora)
                            if reserva_existente:
                                response_text += "\nLa hora ya está reservada. Por favor, elige otra hora."
                            else:
                                guardar_reserva(collection, nombre, cantidad_personas, fecha, hora)
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
def guardar_datos(user_id, key, value):
    # Guardar los datos en la base de datos o en algún otro lugar
    try:
        # Conectar a la base de datos
        collection = conectar_base_datos()
        
        if collection is not None:
            # Buscar el documento del usuario en la colección
            query = {"user_id": user_id}
            user_data = collection.find_one(query)

            if user_data:
                # Actualizar el valor existente
                update_query = {"$set": {key: value}}
                collection.update_one(query, update_query)
            else:
                # Insertar un nuevo documento para el usuario
                user_data = {"user_id": user_id, key: value}
                collection.insert_one(user_data)

            print(f"Datos guardados: User ID: {user_id}, Key: {key}, Value: {value}")
        else:
            print("Error al conectar a la base de datos")
    except Exception as e:
        print(f"Error al guardar los datos: {e}")


def obtener_datos(user_id, key):
    # Obtener los datos de la base de datos o de algún otro lugar
    try:
        # Conectar a la base de datos
        collection = conectar_base_datos()

        if collection is not None:
            # Buscar el documento del usuario en la colección
            query = {"user_id": user_id}
            user_data = collection.find_one(query)

            if user_data and key in user_data:
                return user_data[key]

        return None
    except Exception as e:
        print(f"Error al obtener los datos: {e}")
        return None


def verificar_reserva_existente(collection, fecha, hora):
    # Verificar si existe una reserva para la fecha y hora especificadas
    try:
        query = {"fecha": fecha, "hora": hora}
        result = collection.find_one(query)
        return result is not None
    except Exception as e:
        print(f"Error al verificar la reserva existente: {e}")
        return False


