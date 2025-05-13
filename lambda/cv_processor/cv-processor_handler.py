import json
import os
import google.generativeai as genai

# Set up Gemini API
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def lambda_handler(event, context):
    try:
        text = event.get("text", "")
        if not text:
            raise ValueError("No text provided in the event.")
        print(f"Text received (cut): {text[:300]}")

        prompt = f"Por favor, extrae la siguiente información clave del CV: \n\nNombre, Email, Teléfono, Ubicación, LinkedIn, Experiencia Laboral, Educación, Habilidades Técnicas, Certificaciones, Idiomas.\n\nAquí está el CV:\n\n{text}"
        response = model.generate_content(prompt)
        print(f"Gemini's response: {response.text}")

        return {
            "statusCode": 200,
            "body": json.dumps({
                "gemini_response": response.text
            })
        }

    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
