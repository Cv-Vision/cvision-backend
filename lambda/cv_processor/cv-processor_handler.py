import json
import os
import google.generativeai as genai

# Set up Gemini API
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-2.0-flash")

def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        text = body.get("text", "")

        prompt = f"Extraé los datos clave de este CV: \n{text}"
        response = model.generate_content(prompt)

        print(f"Text received (cut): {text[:300]}")
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
