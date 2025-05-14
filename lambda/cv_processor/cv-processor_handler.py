import json
import os
import google.generativeai as genai

# Set up Gemini API
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def lambda_handler(event, context):
    try:
        text = event.get("text", "")
        job_description = event.get("job_description", "")

        if not text:
            raise ValueError("No text (CV) provided in the event.")
        if not job_description:
            raise ValueError("No job_description provided in the event.")

        print(f"CV text received (cut): {text[:300]}")
        print(f"Job description received (cut): {job_description[:300]}")

        prompt = f"""
Actuá como un asistente de RRHH experto en análisis de CVs.

1. Extraé la siguiente información del CV:
- Nombre
- Email
- Teléfono
- Ubicación
- LinkedIn
- Experiencia Laboral
- Educación
- Habilidades Técnicas
- Certificaciones
- Idiomas

2. Evaluá la compatibilidad del candidato con la siguiente oferta laboral:
{job_description}

3. Asignale un puntaje de *match* de 0 a 100 al candidato, explicando por qué.

4. Resaltá las habilidades técnicas y blandas más relevantes que coinciden con la descripción del puesto.

5. Indicá áreas de mejora o posibles debilidades para el rol.

Este es el CV:
{text}
"""

        response = model.generate_content(prompt)
        print("Gemini's response:")
        print(response.text)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "gemini_response": response.text
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
