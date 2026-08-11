from app.llm_clients import chat


def write_from_notes(notes, tone="professional"):
    text = chat(
        "You write clear, natural emails from user notes. Do not invent facts. Return only the email body.",
        f"Tone: {tone}\n\nNotes:\n{notes}",
        temperature=0.3,
        max_tokens=500,
    )
    return {"email": text}
